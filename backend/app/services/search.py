import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Select, func, or_, select

from app.api.deps import Actor
from app.core.text import build_query_text
from app.models import MediaAsset, Note, NoteBlock, Tag, note_tags
from app.services.notes import _load_blocks, _load_tags, _note_response, note_access_clause


DateField = Literal["created_at", "updated_at", "occurred_at", "expires_at"]


def build_search_statement(
    *,
    actor: Actor,
    query: str = "",
    types: list[str] | None = None,
    tags: list[str] | None = None,
    tag_mode: Literal["any", "all"] = "any",
    member_ids: list[uuid.UUID] | None = None,
    date_field: DateField = "updated_at",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    statuses: list[str] | None = None,
    visibility: list[str] | None = None,
    media_types: list[str] | None = None,
    expiry: str | None = None,
    pinned: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Select[tuple[Note]]:
    statement = select(Note).where(
        Note.household_id == actor.household_id,
        Note.deleted_at.is_(None),
        note_access_clause(actor),
    )

    normalized_query = query.strip()
    if normalized_query:
        # Segment the query with the same tokenizer used on the write path —
        # otherwise a Chinese query never matches the indexed tokens
        # (see app/core/text.py).
        tokenized = build_query_text(normalized_query)
        tsquery = func.websearch_to_tsquery("simple", tokenized)
        note_match = Note.search_tsv.op("@@")(tsquery)
        block_match = (
            select(NoteBlock.id)
            .where(
                NoteBlock.note_id == Note.id,
                NoteBlock.search_tsv.op("@@")(tsquery),
            )
            .exists()
        )
        statement = statement.where(or_(note_match, block_match))
        statement = statement.order_by(
            func.ts_rank_cd(Note.search_tsv, tsquery).desc(),
            Note.updated_at.desc(),
        )

    if types:
        statement = statement.where(Note.type.in_(types))
    if statuses:
        statement = statement.where(Note.status.in_(statuses))
    if visibility:
        statement = statement.where(Note.visibility.in_(visibility))
    if member_ids:
        statement = statement.where(
            or_(Note.created_by.in_(member_ids), Note.owner_member_id.in_(member_ids))
        )
    if pinned is not None:
        statement = statement.where(Note.pinned.is_(pinned))
    if date_from is not None or date_to is not None:
        date_column = getattr(Note, date_field)
        if date_from is not None:
            statement = statement.where(date_column >= date_from)
        if date_to is not None:
            statement = statement.where(date_column <= date_to)
    if tags:
        matching_notes = (
            select(note_tags.c.note_id)
            .join(Tag, Tag.id == note_tags.c.tag_id)
            .where(Tag.household_id == actor.household_id, Tag.slug.in_(tags))
            .group_by(note_tags.c.note_id)
        )
        if tag_mode == "all":
            matching_notes = matching_notes.having(func.count(func.distinct(Tag.slug)) == len(set(tags)))
        statement = statement.where(Note.id.in_(matching_notes))
    if media_types:
        statement = statement.where(
            select(NoteBlock.id)
            .join(MediaAsset, MediaAsset.id == NoteBlock.media_asset_id)
            .where(
                NoteBlock.note_id == Note.id,
                MediaAsset.kind.in_(media_types),
                MediaAsset.deleted_at.is_(None),
            )
            .exists()
        )
    if expiry == "none":
        statement = statement.where(Note.expires_at.is_(None))
    elif expiry == "expired":
        statement = statement.where(Note.expires_at < datetime.now(UTC))
    elif expiry in {"within_7d", "within_30d", "within_90d"}:
        days = int(expiry.split("_")[1][:-1])
        now = datetime.now(UTC)
        statement = statement.where(Note.expires_at.between(now, now + timedelta(days=days)))

    if not normalized_query:
        statement = statement.order_by(Note.updated_at.desc())
    return statement.limit(limit).offset(offset)


async def search_notes(
    *,
    session,
    actor: Actor,
    **filters: object,
):
    statement = build_search_statement(actor=actor, **filters)
    result = await session.execute(statement)
    notes = list(result.scalars().all())
    items = [
        _note_response(note, await _load_blocks(session, note.id), await _load_tags(session, note.id))
        for note in notes
    ]
    return {"items": items, "limit": filters.get("limit", 50), "offset": filters.get("offset", 0)}