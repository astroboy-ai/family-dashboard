import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import and_, delete, false, func, or_, select, true
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

from app.api.deps import Actor
from app.core import secrets
from app.core.errors import AppError
from app.core.text import build_search_text
from app.models import AuditLog, FamilyMember, JobOutbox, MediaAsset, Note, NoteBlock, Tag, TagAuditLog, TagExclusion, note_tags
from app.schemas.notes import (
    NoteBlockInput,
    NoteBlockPatchRequest,
    NoteBlockResponse,
    NoteCreateRequest,
    NoteListResponse,
    NotePatchRequest,
    NoteResponse,
    NoteTagRequest,
    TagResponse,
)


def _record_audit(
    session: AsyncSession,
    actor: Actor,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            household_id=actor.household_id,
            actor_type="member",
            actor_id=actor.member_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
        )
    )


def _queue_note_enrichment(session: AsyncSession, note_id: uuid.UUID) -> None:
    """Queue a re-embed for *note*.

    The topic is ``embed.note``, consumed by ``app/workers/outbox.py``. The row
    is written in the caller's transaction, so a rolled-back note never leaves a
    job behind (outbox pattern).
    """

    session.add(
        JobOutbox(
            id=uuid.uuid4(),
            topic="embed.note",
            payload={"note_id": str(note_id)},
        )
    )


def _queue_tag_propose(session: AsyncSession, note_id: uuid.UUID) -> None:
    """Queue an AI classification job for *note*.

    The topic is ``tag.propose``, consumed by ``app/workers/outbox.py``. The row
    is written in the caller's transaction, so a rolled-back note never leaves a
    job behind (outbox pattern).
    """

    session.add(
        JobOutbox(
            id=uuid.uuid4(),
            topic="tag.propose",
            payload={"note_id": str(note_id)},
        )
    )


def apply_note_search_tokens(note: Note) -> None:
    """Refresh the tokenized mirror of a note's searchable text.

    Must be called whenever ``title``/``summary``/``ai_summary`` change: the
    ``search_tsv`` column is generated from these token columns, and PostgreSQL
    cannot segment CJK text on its own (see :mod:`app.core.text`).
    """

    note.search_tokens_title = build_search_text(note.title)
    note.search_tokens_summary = build_search_text(note.summary)
    note.search_tokens_ai_summary = build_search_text(note.ai_summary)


def apply_block_search_tokens(block: NoteBlock) -> None:
    """Refresh the tokenized mirror of every searchable block field.

    Covers OCR text and transcripts as well as plain text, so a photographed
    notice becomes searchable once enrichment fills those columns.
    """

    block.search_tokens_text = build_search_text(
        block.text_content,
        block.caption,
        block.ai_description,
        block.ocr_text,
        block.transcript,
        _flatten_block_data(block.data),
    )


def _flatten_block_data(data: Any) -> str:
    """Flatten a block's structured payload into ``key: value`` lines."""

    if not isinstance(data, dict):
        return ""
    lines = []
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        lines.append(f"{key}: {value if not isinstance(value, (dict, list)) else str(value)}")
    return "\n".join(lines)


def note_access_clause(actor: Actor, *, write: bool = False) -> Any:
    owned = or_(Note.created_by == actor.member_id, Note.owner_member_id == actor.member_id)
    if actor.role == "parent":
        required_scope = "notes.write" if write else "notes.read"
        return true() if required_scope in actor.scopes else false()
    if actor.role == "agent":
        # Agents act for the household, not as a person. Read access follows the
        # same rule as a guest (shared notes only) so an agent token can never
        # reach another member's private notes.
        #
        # Write access is granted by an explicit ``notes.write`` scope on the
        # token, and is still limited to family-visible notes: an agent may add
        # to the shared record but cannot create or edit a note the family
        # cannot see. Minting a token with that scope is the operator's consent
        # — there is no per-call confirmation prompt.
        if write:
            if "notes.write" not in actor.scopes:
                return false()
            return Note.visibility == "family"
        if "notes.read" not in actor.scopes:
            return false()
        return Note.visibility == "family"
    if actor.role == "child":
        required_scope = "notes.write.own" if write else "notes.read.own"
        if required_scope not in actor.scopes:
            return false()
        if write:
            return and_(owned, Note.visibility.in_(("family", "private")))
        return or_(
            Note.visibility == "family",
            and_(Note.visibility == "private", owned),
        )
    if actor.role == "guest" and not write and "notes.read.shared" in actor.scopes:
        return Note.visibility == "family"
    return false()


def _normalize_tag_name(value: str) -> tuple[str, str]:
    name = " ".join(value.split())
    normalized = unicodedata.normalize("NFKD", name).casefold()
    slug = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not name or not slug:
        raise AppError("Tag name must contain letters or numbers", error_code="invalid_tag")
    return name, slug


def suggest_ai_tags(
    title: str | None,
    text: str | None,
    *,
    existing: list[str] | None = None,
) -> list[str]:
    existing_slug_map = {
        _normalize_tag_name(tag)[1]
        for tag in (existing or [])
        if tag and tag.strip()
    }
    haystack = " ".join(part for part in (title, text) if part and part.strip()).lower()
    rules: list[tuple[str, list[str]]] = [
        ("travel", ["travel", "trip", "flight", "airport", "train", "bus", "mtr", "holiday", "vacation", "japan", "kyoto", "tokyo", "beach", "camping"]),
        ("school", ["school", "class", "lesson", "assignment", "homework", "teacher", "camp", "study", "exam", "project"]),
        ("family", ["family", "dad", "mum", "mom", "parent", "parents", "grandma", "grandpa", "emma", "household"]),
        ("garden", ["garden", "plant", "plants", "seed", "soil", "greenhouse", "flower", "vegetable", "raised bed"]),
        ("meals", ["meal", "breakfast", "lunch", "dinner", "recipe", "cook", "shopping", "grocery", "snack"]),
        ("shopping", ["shopping", "market", "grocery", "receipt", "budget", "cost", "store"]),
    ]

    suggestions: list[str] = []
    for tag, keywords in rules:
        slug = _normalize_tag_name(tag)[1]
        if slug in existing_slug_map:
            continue
        if any(keyword in haystack for keyword in keywords):
            suggestions.append(tag)
    return suggestions


def build_tag_exclusion_statement(*, actor: Actor, note: Note):
    member_ids = {member_id for member_id in (note.owner_member_id, note.created_by, actor.member_id) if member_id}
    now = datetime.now(UTC)
    return select(TagExclusion.tag_slug).where(
        TagExclusion.household_id == actor.household_id,
        TagExclusion.tag_slug.is_not(None),
        or_(TagExclusion.expires_at.is_(None), TagExclusion.expires_at > now),
        or_(
            and_(TagExclusion.scope == "note", TagExclusion.scope_ref == note.id),
            and_(TagExclusion.scope == "note_type", TagExclusion.scope_note_type == note.type),
            and_(TagExclusion.scope == "member", TagExclusion.scope_ref.in_(member_ids)) if member_ids else false(),
            TagExclusion.scope == "household",
        ),
    )


async def get_excluded_tag_slugs(*, session: AsyncSession, actor: Actor, note: Note) -> set[str]:
    result = await session.execute(build_tag_exclusion_statement(actor=actor, note=note))
    return {slug for slug in result.scalars().all() if isinstance(slug, str)}


async def _get_note(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID, write: bool = False
) -> Note:
    result = await session.execute(
        select(Note).where(
            Note.id == note_id,
            Note.household_id == actor.household_id,
            Note.deleted_at.is_(None),
            note_access_clause(actor, write=write),
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise AppError("Note not found", status_code=404, error_code="not_found")
    return note


async def _validate_member(
    *, session: AsyncSession, household_id: uuid.UUID, member_id: uuid.UUID
) -> None:
    result = await session.execute(
        select(FamilyMember.id).where(
            FamilyMember.id == member_id,
            FamilyMember.household_id == household_id,
            FamilyMember.is_active.is_(True),
        )
    )
    if result.scalar_one_or_none() is None:
        raise AppError("Family member not found", status_code=404, error_code="not_found")


async def _validate_media(
    *, session: AsyncSession, household_id: uuid.UUID, media_asset_id: uuid.UUID | None
) -> None:
    if media_asset_id is None:
        return
    result = await session.execute(
        select(MediaAsset.id).where(
            MediaAsset.id == media_asset_id,
            MediaAsset.household_id == household_id,
            MediaAsset.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise AppError("Media asset not found", status_code=404, error_code="not_found")


async def _validate_parent_note(
    *,
    session: AsyncSession,
    actor: Actor,
    parent_note_id: uuid.UUID | None,
    child_note_id: uuid.UUID | None = None,
) -> None:
    if parent_note_id is None:
        return
    if parent_note_id == child_note_id:
        raise AppError("A note cannot be its own parent", error_code="invalid_parent_note")
    await _get_note(session=session, actor=actor, note_id=parent_note_id)


async def _get_or_create_tag(
    *, session: AsyncSession, household_id: uuid.UUID, raw_name: str
) -> Tag:
    name, slug = _normalize_tag_name(raw_name)
    result = await session.execute(
        select(Tag).where(Tag.household_id == household_id, Tag.slug == slug)
    )
    tag = result.scalar_one_or_none()
    if tag is not None:
        return tag
    tag = Tag(
        id=uuid.uuid4(),
        household_id=household_id,
        name=name,
        slug=slug,
        kind="topic",
    )
    session.add(tag)
    await session.flush()
    return tag


async def _load_blocks(session: AsyncSession, note_id: uuid.UUID) -> list[NoteBlock]:
    result = await session.execute(
        select(NoteBlock).where(NoteBlock.note_id == note_id).order_by(NoteBlock.order_index)
    )
    return list(result.scalars().all())


async def _load_tags(session: AsyncSession, note_id: uuid.UUID) -> list[Tag]:
    result = await session.execute(
        select(Tag)
        .join(note_tags, note_tags.c.tag_id == Tag.id)
        .where(note_tags.c.note_id == note_id)
        .order_by(Tag.name)
    )
    return list(result.scalars().all())


def _note_response(note: Note, blocks: list[NoteBlock], tags: list[Tag]) -> NoteResponse:
    return NoteResponse.model_validate(note).model_copy(
        update={
            "blocks": [NoteBlockResponse.model_validate(block) for block in blocks],
            "tags": [TagResponse.model_validate(tag) for tag in tags],
        }
    )


async def _get_block_for_write(
    *, session: AsyncSession, actor: Actor, block_id: uuid.UUID
) -> tuple[NoteBlock, Note]:
    result = await session.execute(
        select(NoteBlock, Note)
        .join(Note, Note.id == NoteBlock.note_id)
        .where(
            NoteBlock.id == block_id,
            Note.household_id == actor.household_id,
            Note.deleted_at.is_(None),
            note_access_clause(actor, write=True),
        )
    )
    row = result.first()
    if row is None:
        raise AppError("Note block not found", status_code=404, error_code="not_found")
    return row


async def list_notes(
    *,
    session: AsyncSession,
    actor: Actor,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    note_type: str | None = None,
    tag: str | None = None,
) -> NoteListResponse:
    statement = select(Note).where(
        Note.household_id == actor.household_id,
        Note.deleted_at.is_(None),
        note_access_clause(actor),
    )
    if status is not None:
        statement = statement.where(Note.status == status)
    if note_type is not None:
        statement = statement.where(Note.type == note_type)
    if tag is not None:
        statement = statement.where(
            Note.id.in_(
                select(note_tags.c.note_id)
                .join(Tag, Tag.id == note_tags.c.tag_id)
                .where(Tag.household_id == actor.household_id, Tag.slug == tag)
            )
        )
    statement = statement.order_by(Note.updated_at.desc()).limit(limit).offset(offset)
    result = await session.execute(statement)
    notes = list(result.scalars().all())
    items = [
        _note_response(note, await _load_blocks(session, note.id), await _load_tags(session, note.id))
        for note in notes
    ]
    return NoteListResponse(items=items, limit=limit, offset=offset)


async def get_note(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID
) -> NoteResponse:
    note = await _get_note(session=session, actor=actor, note_id=note_id)
    return _note_response(
        note,
        await _load_blocks(session, note.id),
        await _load_tags(session, note.id),
    )


async def create_note(
    *, session: AsyncSession, actor: Actor, payload: NoteCreateRequest
) -> NoteResponse:
    if actor.role == "parent" and "notes.write" in actor.scopes:
        owner_member_id = payload.owner_member_id
    elif actor.role == "child" and "notes.write.own" in actor.scopes:
        if payload.visibility == "parents":
            raise AppError("Children cannot create parent-only notes", status_code=403, error_code="permission_denied")
        if payload.owner_member_id not in (None, actor.member_id):
            raise AppError("Children can only own their own notes", status_code=403, error_code="permission_denied")
        owner_member_id = actor.member_id
    elif actor.role == "agent" and "notes.write" in actor.scopes:
        # An agent writes on behalf of a member when the caller names one (e.g.
        # "Lok's voucher"), otherwise it writes for the household. Family
        # visibility is enforced by note_access_clause and re-checked here so a
        # private note is refused with a clear message rather than a 404.
        if payload.visibility != "family":
            raise AppError(
                "Agents can only create family-visible notes",
                status_code=403,
                error_code="permission_denied",
            )
        owner_member_id = payload.owner_member_id
    else:
        raise AppError("Permission denied", status_code=403, error_code="permission_denied")

    if owner_member_id is not None and owner_member_id != actor.member_id:
        await _validate_member(
            session=session,
            household_id=actor.household_id,
            member_id=owner_member_id,
        )
    if payload.visibility == "parents" and actor.role != "parent":
        raise AppError("Permission denied", status_code=403, error_code="permission_denied")
    await _validate_parent_note(
        session=session,
        actor=actor,
        parent_note_id=payload.parent_note_id,
    )

    now = datetime.now(UTC)
    note = Note(
        id=uuid.uuid4(),
        household_id=actor.household_id,
        title=payload.title,
        type=payload.type,
        status=payload.status,
        summary=payload.summary,
        created_by=actor.member_id,
        owner_member_id=owner_member_id,
        visibility=payload.visibility,
        pinned=payload.pinned,
        occurred_at=payload.occurred_at,
        expires_at=payload.expires_at,
        location=payload.location,
        parent_note_id=payload.parent_note_id,
        extra=payload.extra,
        embedding_status="pending",
        created_at=now,
        updated_at=now,
    )
    apply_note_search_tokens(note)
    session.add(note)
    await session.flush()

    blocks: list[NoteBlock] = []
    for index, block_payload in enumerate(payload.blocks, start=1):
        await _validate_media(
            session=session,
            household_id=actor.household_id,
            media_asset_id=block_payload.media_asset_id,
        )
        block = NoteBlock(
            id=uuid.uuid4(),
            note_id=note.id,
            order_index=index * 1000,
            **block_payload.model_dump(),
            created_at=now,
            updated_at=now,
        )
        apply_block_search_tokens(block)
        blocks.append(block)
        session.add(block)

    tags: list[Tag] = []
    seen_tag_slugs: set[str] = set()
    for raw_name in dict.fromkeys(payload.tags):
        tag = await _get_or_create_tag(
            session=session,
            household_id=actor.household_id,
            raw_name=raw_name,
        )
        if tag.slug in seen_tag_slugs:
            continue
        seen_tag_slugs.add(tag.slug)
        await session.execute(
            pg_insert(note_tags)
            .values(
                note_id=note.id,
                tag_id=tag.id,
                source="human",
                applied_by=actor.member_id,
                approved_by_human=True,
            )
            .on_conflict_do_nothing()
        )
        tags.append(tag)

    _queue_note_enrichment(session, note.id)
    _queue_tag_propose(session, note.id)
    _record_audit(
        session,
        actor,
        action="note.create",
        entity_type="note",
        entity_id=note.id,
        after={"type": note.type, "visibility": note.visibility},
    )
    await session.commit()
    return _note_response(note, blocks, tags)


async def update_note(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID, payload: NotePatchRequest
) -> NoteResponse:
    note = await _get_note(session=session, actor=actor, note_id=note_id, write=True)
    changes = payload.model_dump(exclude_unset=True)
    before = {"status": note.status, "visibility": note.visibility}
    if "visibility" in changes and changes["visibility"] is not None:
        if changes["visibility"] == "parents" and actor.role != "parent":
            raise AppError("Permission denied", status_code=403, error_code="permission_denied")
    if "owner_member_id" in changes and changes["owner_member_id"] not in (None, actor.member_id):
        if actor.role != "parent":
            raise AppError("Permission denied", status_code=403, error_code="permission_denied")
        await _validate_member(
            session=session,
            household_id=actor.household_id,
            member_id=changes["owner_member_id"],
        )
    if "parent_note_id" in changes:
        await _validate_parent_note(
            session=session,
            actor=actor,
            parent_note_id=changes["parent_note_id"],
            child_note_id=note.id,
        )
    for field, value in changes.items():
        if value is not None or field in {"title", "summary", "owner_member_id", "occurred_at", "expires_at"}:
            setattr(note, field, value)
    note.updated_at = datetime.now(UTC)
    # Retokenize before the enrichment check: search_tsv is generated from the
    # token columns, so stale tokens mean the note becomes unsearchable by its
    # new text.
    apply_note_search_tokens(note)
    enrichment_fields = {
        "title",
        "type",
        "summary",
        "owner_member_id",
        "visibility",
        "occurred_at",
        "expires_at",
        "location",
        "parent_note_id",
        "extra",
    }
    if changes.keys() & enrichment_fields:
        _queue_note_enrichment(session, note.id)
    _queue_tag_propose(session, note.id)
    _record_audit(
        session,
        actor,
        action="note.update",
        entity_type="note",
        entity_id=note.id,
        before=before,
        after={"updated_fields": sorted(changes)},
    )
    await session.commit()
    return _note_response(
        note,
        await _load_blocks(session, note.id),
        await _load_tags(session, note.id),
    )


async def delete_note(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID
) -> None:
    note = await _get_note(session=session, actor=actor, note_id=note_id, write=True)
    before = {"status": note.status, "visibility": note.visibility}
    note.deleted_at = datetime.now(UTC)
    note.updated_at = note.deleted_at
    _record_audit(
        session,
        actor,
        action="note.soft_delete",
        entity_type="note",
        entity_id=note.id,
        before=before,
    )
    await session.commit()


def _encrypt_password_data(data: dict[str, Any]) -> dict[str, Any]:
    """Encrypt ``data.value`` in place if it is plaintext.

    Idempotent: an already-encrypted value is left alone, so re-saving a block
    does not double-encrypt. Other keys (``label``, ``masked``) are preserved.
    """

    value = data.get("value")
    if value and not secrets.is_encrypted(value):
        data = {**data, "value": secrets.encrypt(value), "encrypted": True}
    return data


async def create_block(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID, payload: NoteBlockInput
) -> NoteBlockResponse:
    note = await _get_note(session=session, actor=actor, note_id=note_id, write=True)
    await _validate_media(
        session=session,
        household_id=actor.household_id,
        media_asset_id=payload.media_asset_id,
    )
    result = await session.execute(
        select(func.max(NoteBlock.order_index)).where(NoteBlock.note_id == note.id)
    )
    max_order = result.scalar_one_or_none() or 0
    now = datetime.now(UTC)
    fields = payload.model_dump()
    if fields.get("type") == "password":
        fields["data"] = _encrypt_password_data(fields.get("data") or {})
    block = NoteBlock(
        id=uuid.uuid4(),
        note_id=note.id,
        order_index=max_order + 1000,
        **fields,
        created_at=now,
        updated_at=now,
    )
    apply_block_search_tokens(block)
    session.add(block)
    note.updated_at = now
    _record_audit(
        session,
        actor,
        action="block.create",
        entity_type="note_block",
        entity_id=block.id,
        after={"type": block.type, "order_index": block.order_index},
    )
    await session.commit()
    return _serialize_block(block, can_read_secrets="notes.read.secrets" in actor.scopes)


async def list_blocks(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID
) -> list[NoteBlockResponse]:
    note = await _get_note(session=session, actor=actor, note_id=note_id)
    blocks = await _load_blocks(session, note.id)
    can_read_secrets = "notes.read.secrets" in actor.scopes
    return [
        _serialize_block(block, can_read_secrets=can_read_secrets) for block in blocks
    ]


def _serialize_block(block: NoteBlock, *, can_read_secrets: bool) -> NoteBlockResponse:
    """Build the response, masking password values the caller may not see.

    A password block stores ``data.value`` as AES-GCM ciphertext. Without the
    ``notes.read.secrets`` scope the caller gets a masked placeholder and a flag
    saying a secret is present — enough to render the block, not enough to read
    it. With the scope, the plaintext is decrypted into ``data.value``.

    A legacy plaintext value (written before encryption existed) is treated as
    readable only with the scope, and is reported via ``data.encrypted=False``
    so the UI can offer to re-save it encrypted.
    """

    data = dict(block.data or {})
    if block.type == "password" and "value" in data:
        stored = data["value"]
        if secrets.is_encrypted(stored):
            if can_read_secrets:
                try:
                    data["value"] = secrets.decrypt(stored)
                except ValueError as error:
                    # Wrong key or tampered ciphertext. Show a distinct marker
                    # rather than a wrong password — the user must be able to tell
                    # "this is broken" from "this is not the password".
                    logger.warning("secret_decrypt_failed", block_id=str(block.id), error=str(error))
                    data["value"] = None
                    data["decrypt_error"] = True
            else:
                data["value"] = "••••••••"
                data["masked"] = True
            data["encrypted"] = True
        else:
            # Legacy plaintext row. Never hand it out without the scope.
            data["encrypted"] = False
            if not can_read_secrets:
                data["value"] = "••••••••"
                data["masked"] = True
    return NoteBlockResponse.model_validate({**block.__dict__, "data": data})


async def update_block(
    *, session: AsyncSession, actor: Actor, block_id: uuid.UUID, payload: NoteBlockPatchRequest
) -> NoteBlockResponse:
    block, note = await _get_block_for_write(
        session=session,
        actor=actor,
        block_id=block_id,
    )
    changes = payload.model_dump(exclude_unset=True)
    before = {"type": block.type, "order_index": block.order_index}
    if changes.get("type") == "password" or block.type == "password":
        new_data = changes.get("data")
        if new_data is not None:
            changes["data"] = _encrypt_password_data(new_data)
    if "media_asset_id" in changes:
        await _validate_media(
            session=session,
            household_id=actor.household_id,
            media_asset_id=changes["media_asset_id"],
        )
    for field, value in changes.items():
        if value is not None or field in {"text_content", "media_asset_id", "caption", "expires_at"}:
            setattr(block, field, value)
    now = datetime.now(UTC)
    block.updated_at = now
    note.updated_at = now
    apply_block_search_tokens(block)
    if changes:
        _queue_note_enrichment(session, note.id)
    _queue_tag_propose(session, note.id)
    _record_audit(
        session,
        actor,
        action="block.update",
        entity_type="note_block",
        entity_id=block.id,
        before=before,
        after={"updated_fields": sorted(changes)},
    )
    await session.commit()
    return _serialize_block(block, can_read_secrets="notes.read.secrets" in actor.scopes)


async def delete_block(
    *, session: AsyncSession, actor: Actor, block_id: uuid.UUID
) -> None:
    block, note = await _get_block_for_write(
        session=session,
        actor=actor,
        block_id=block_id,
    )
    await session.delete(block)
    note.updated_at = datetime.now(UTC)
    _queue_note_enrichment(session, note.id)
    _queue_tag_propose(session, note.id)
    _record_audit(
        session,
        actor,
        action="block.delete",
        entity_type="note_block",
        entity_id=block.id,
        before={"type": block.type, "order_index": block.order_index},
    )
    await session.commit()


async def reorder_blocks(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID, block_ids: list[uuid.UUID]
) -> list[NoteBlockResponse]:
    note = await _get_note(session=session, actor=actor, note_id=note_id, write=True)
    blocks = await _load_blocks(session, note.id)
    current_ids = {block.id for block in blocks}
    if len(block_ids) != len(current_ids) or set(block_ids) != current_ids:
        raise AppError(
            "block_ids must contain every block on the note exactly once",
            error_code="invalid_block_order",
        )
    by_id = {block.id: block for block in blocks}
    ordered = [by_id[block_id] for block_id in block_ids]
    for index, block in enumerate(ordered, start=1):
        block.order_index = -index * 1000
    await session.flush()
    for index, block in enumerate(ordered, start=1):
        block.order_index = index * 1000
    note.updated_at = datetime.now(UTC)
    _queue_note_enrichment(session, note.id)
    _queue_tag_propose(session, note.id)
    _record_audit(
        session,
        actor,
        action="block.reorder",
        entity_type="note",
        entity_id=note.id,
        after={"block_ids": [str(block.id) for block in ordered]},
    )
    await session.commit()
    # Re-read after commit. ``updated_at`` carries onupdate=func.now(), so the
    # flush expires it and pydantic reading it would attempt a lazy refresh —
    # impossible under async SQLAlchemy (MissingGreenlet). Re-querying gets the
    # DB-generated values; same approach as add_tag/remove_tag below.
    refreshed = await _load_blocks(session, note.id)
    by_id_after = {block.id: block for block in refreshed}
    return [
        NoteBlockResponse.model_validate(by_id_after[block.id])
        for block in ordered
        if block.id in by_id_after
    ]


async def add_tag(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID, payload: NoteTagRequest
) -> list[TagResponse]:
    note = await _get_note(session=session, actor=actor, note_id=note_id, write=True)
    tag = await _get_or_create_tag(
        session=session,
        household_id=actor.household_id,
        raw_name=payload.name,
    )
    await session.execute(
        pg_insert(note_tags)
        .values(
            note_id=note.id,
            tag_id=tag.id,
            source="human",
            applied_by=actor.member_id,
            approved_by_human=True,
        )
        .on_conflict_do_nothing()
    )
    note.updated_at = datetime.now(UTC)
    _record_audit(
        session,
        actor,
        action="note.tag_add",
        entity_type="note",
        entity_id=note.id,
        after={"tag_slug": tag.slug},
    )
    await session.commit()
    return [
        TagResponse.model_validate(item)
        for item in await _load_tags(session, note.id)
    ]


async def remove_tag(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID, tag_slug: str
) -> list[TagResponse]:
    note = await _get_note(session=session, actor=actor, note_id=note_id, write=True)
    result = await session.execute(
        select(Tag, note_tags.c.source)
        .join(note_tags, note_tags.c.tag_id == Tag.id)
        .where(
            Tag.household_id == actor.household_id,
            Tag.slug == tag_slug,
            note_tags.c.note_id == note.id,
        )
    )
    row = result.first()
    if row is None:
        raise AppError("Tag not found", status_code=404, error_code="not_found")
    tag, source = row
    await session.execute(
        delete(note_tags).where(note_tags.c.note_id == note.id, note_tags.c.tag_id == tag.id)
    )
    session.add(
        TagExclusion(
            id=uuid.uuid4(),
            household_id=actor.household_id,
            tag_id=tag.id,
            tag_slug=tag.slug,
            scope="note",
            scope_ref=note.id,
            reason="user_removed",
            created_by=actor.member_id,
        )
    )
    session.add(
        TagAuditLog(
            id=uuid.uuid4(),
            household_id=actor.household_id,
            actor_type="human",
            actor_id=actor.member_id,
            action="tag_removed",
            note_id=note.id,
            tag_slug=tag.slug,
            reason="user_removed",
            before={"source": source},
        )
    )
    note.updated_at = datetime.now(UTC)
    _record_audit(
        session,
        actor,
        action="note.tag_remove",
        entity_type="note",
        entity_id=note.id,
        before={"tag_slug": tag.slug},
    )
    await session.commit()
    return [
        TagResponse.model_validate(item)
        for item in await _load_tags(session, note.id)
    ]


async def list_tags(*, session: AsyncSession, actor: Actor) -> list[TagResponse]:
    # Mirrors `note_access_clause`: an agent reads at household level with
    # `notes.read`, the same as a parent, but sees no private notes because the
    # tag list is household-scoped metadata rather than per-member content.
    can_read_tags = (
        (actor.role == "parent" and "notes.read" in actor.scopes)
        or (actor.role == "agent" and "notes.read" in actor.scopes)
        or (actor.role == "child" and "notes.read.own" in actor.scopes)
        or (actor.role == "guest" and "notes.read.shared" in actor.scopes)
    )
    if not can_read_tags:
        raise AppError("Permission denied", status_code=403, error_code="permission_denied")
    result = await session.execute(
        select(Tag)
        .where(Tag.household_id == actor.household_id)
        .order_by(Tag.name)
        .limit(500)
    )
    return [TagResponse.model_validate(tag) for tag in result.scalars().all()]
