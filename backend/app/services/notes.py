import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, delete, false, func, or_, select, true
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.core.errors import AppError
from app.models import AuditLog, FamilyMember, JobOutbox, MediaAsset, Note, NoteBlock, Tag, note_tags
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
    session.add(
        JobOutbox(
            id=uuid.uuid4(),
            topic="note.enrich",
            payload={"note_id": str(note_id)},
        )
    )


def note_access_clause(actor: Actor, *, write: bool = False) -> Any:
    owned = or_(Note.created_by == actor.member_id, Note.owner_member_id == actor.member_id)
    if actor.role == "parent":
        required_scope = "notes.write" if write else "notes.read"
        return true() if required_scope in actor.scopes else false()
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
        kind="general",
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
            .values(note_id=note.id, tag_id=tag.id)
            .on_conflict_do_nothing()
        )
        tags.append(tag)

    _queue_note_enrichment(session, note.id)
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
    block = NoteBlock(
        id=uuid.uuid4(),
        note_id=note.id,
        order_index=max_order + 1000,
        **payload.model_dump(),
        created_at=now,
        updated_at=now,
    )
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
    return NoteBlockResponse.model_validate(block)


async def list_blocks(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID
) -> list[NoteBlockResponse]:
    note = await _get_note(session=session, actor=actor, note_id=note_id)
    return [
        NoteBlockResponse.model_validate(block)
        for block in await _load_blocks(session, note.id)
    ]


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
    if changes:
        _queue_note_enrichment(session, note.id)
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
    return NoteBlockResponse.model_validate(block)


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
    _record_audit(
        session,
        actor,
        action="block.reorder",
        entity_type="note",
        entity_id=note.id,
        after={"block_ids": [str(block.id) for block in ordered]},
    )
    await session.commit()
    return [NoteBlockResponse.model_validate(block) for block in ordered]


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
        .values(note_id=note.id, tag_id=tag.id)
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
        select(Tag).where(Tag.household_id == actor.household_id, Tag.slug == tag_slug)
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        raise AppError("Tag not found", status_code=404, error_code="not_found")
    await session.execute(
        delete(note_tags).where(note_tags.c.note_id == note.id, note_tags.c.tag_id == tag.id)
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
    can_read_tags = (
        (actor.role == "parent" and "notes.read" in actor.scopes)
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
