import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agent.registry import ToolContext, ToolResult, register
from app.core.errors import AppError
from app.services.media import store_agent_upload
from app.services.notes import (
    create_block,
    create_note,
    get_note,
    list_blocks,
    list_tags,
    note_access_clause,
)
from app.services.search import search_notes


class SearchNotesParams(BaseModel):
    query: str = Field(default="", max_length=500)
    types: list[str] | None = None
    tags: list[str] | None = None
    statuses: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=50)


class NoteIdParams(BaseModel):
    note_id: uuid.UUID


class GetNoteParams(NoteIdParams):
    include_blocks: bool = True


class GetBlocksParams(NoteIdParams):
    types: list[str] | None = None


class NoParams(BaseModel):
    pass


class ExpiringItemsParams(BaseModel):
    days: int = Field(default=30, ge=1, le=365)
    types: list[str] | None = None


@register(
    name="search_notes",
    description="Search visible household notes by text, type, tag, and status.",
    category="notes",
    params=SearchNotesParams,
    permissions=("notes.read",),
)
async def search_notes_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = SearchNotesParams.model_validate(params)
    result = await search_notes(
        session=context.session,
        actor=context.actor,
        query=values.query,
        types=values.types,
        tags=values.tags,
        statuses=values.statuses,
        limit=values.limit,
        offset=0,
    )
    return ToolResult(ok=True, data=result["items"], meta={"count": len(result["items"])})


@register(
    name="get_note",
    description="Read one visible note, optionally including its blocks.",
    category="notes",
    params=GetNoteParams,
    permissions=("notes.read",),
)
async def get_note_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = GetNoteParams.model_validate(params)
    note = await get_note(session=context.session, actor=context.actor, note_id=values.note_id)
    if not values.include_blocks:
        note = note.model_copy(update={"blocks": []})
    return ToolResult(ok=True, data=note)


@register(
    name="get_blocks",
    description="Read blocks belonging to a visible note.",
    category="notes",
    params=GetBlocksParams,
    permissions=("notes.read",),
)
async def get_blocks_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = GetBlocksParams.model_validate(params)
    blocks = await list_blocks(session=context.session, actor=context.actor, note_id=values.note_id)
    if values.types:
        blocks = [block for block in blocks if block.type in values.types]
    return ToolResult(ok=True, data=blocks, meta={"count": len(blocks)})


@register(
    name="list_tags",
    description="List household tags visible to the requesting member.",
    category="notes",
    params=NoParams,
    permissions=("notes.read",),
)
async def list_tags_tool(_: BaseModel, context: ToolContext) -> ToolResult:
    tags = await list_tags(session=context.session, actor=context.actor)
    return ToolResult(ok=True, data=tags, meta={"count": len(tags)})


@register(
    name="get_expiring_items",
    description="List visible notes that expire within the next number of days.",
    category="expiry",
    params=ExpiringItemsParams,
    permissions=("notes.read",),
)
async def get_expiring_items_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.models import Note

    values = ExpiringItemsParams.model_validate(params)
    statement = (
        select(Note)
        .where(
            Note.household_id == context.actor.household_id,
            Note.deleted_at.is_(None),
            note_access_clause(context.actor),
            Note.expires_at.between(datetime.now(UTC), datetime.now(UTC) + timedelta(days=values.days)),
        )
    )
    if values.types:
        statement = statement.where(Note.type.in_(values.types))
    result = await context.session.execute(statement)
    notes = result.scalars().all()
    return ToolResult(ok=True, data=notes, meta={"count": len(notes)})


# ── Write tools ──────────────────────────────────────────────────────────────
#
# These require an explicit ``notes.write`` scope on the calling token. Minting
# a token with that scope is the operator's consent; there is no per-call
# confirmation prompt. Every call lands in ``agent_tool_calls`` for audit.


class UploadMediaParams(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime: str = Field(min_length=3, max_length=160)
    content_base64: str = Field(min_length=1)
    # Optional: an agent that already analysed the file (its own vision model)
    # passes the description here and no local vision call is queued.
    description: str | None = Field(default=None, max_length=8000)


class CreateNoteParams(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    type: str = Field(default="freeform", min_length=1, max_length=40)
    summary: str | None = None
    # The member this note is for. Omit for the household in general.
    owner_member_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    occurred_at: datetime | None = None
    blocks: list[dict] = Field(default_factory=list, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=30)


class AppendBlockParams(BaseModel):
    note_id: uuid.UUID
    type: str = Field(min_length=1, max_length=32)
    text_content: str | None = None
    media_asset_id: uuid.UUID | None = None
    data: dict = Field(default_factory=dict)
    caption: str | None = None
    expires_at: datetime | None = None
    importance: int = Field(default=0, ge=0, le=5)


@register(
    name="upload_media",
    description=(
        "Upload a file (image, PDF, any document) to the household store and get "
        "an asset_id to attach to a note block. Pass the file base64-encoded. If "
        "you have already analysed the file with your own vision model, put that "
        "text in `description` and the system will not analyse it again."
    ),
    category="media",
    params=UploadMediaParams,
    permissions=("notes.write",),
    mutates=True,
)
async def upload_media_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    import base64
    import binascii

    from app.core.config import get_settings
    from app.core.storage import S3CompatibleStorage

    values = UploadMediaParams.model_validate(params)
    try:
        data = base64.b64decode(values.content_base64, validate=True)
    except (binascii.Error, ValueError):
        return ToolResult(ok=False, error="content_base64 is not valid base64", error_code="invalid_params")

    if not data:
        return ToolResult(ok=False, error="Uploaded file is empty", error_code="invalid_params")

    # Build the storage backend directly: `get_storage` is a FastAPI dependency
    # and this path has no request to resolve it from.
    settings = get_settings()
    storage = S3CompatibleStorage(
        internal_endpoint=settings.s3_endpoint,
        public_endpoint=settings.s3_public_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
    )
    try:
        asset = await store_agent_upload(
            session=context.session,
            storage=storage,
            actor=context.actor,
            filename=values.filename,
            mime=values.mime,
            data=data,
            description=values.description,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(
        ok=True,
        data={"asset_id": str(asset.id), "mime": asset.mime, "size_bytes": asset.size_bytes},
    )


@register(
    name="create_note",
    description=(
        "Create a note for the household, optionally on behalf of a member. Blocks "
        "and tags can be set in the same call. Use this to record something you "
        "found or were told to remember."
    ),
    category="notes",
    params=CreateNoteParams,
    permissions=("notes.write",),
    mutates=True,
)
async def create_note_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.schemas.notes import NoteBlockInput, NoteCreateRequest

    values = CreateNoteParams.model_validate(params)
    payload = NoteCreateRequest(
        title=values.title,
        type=values.type,
        summary=values.summary,
        owner_member_id=values.owner_member_id,
        visibility="family",  # agents may only write family-visible notes
        expires_at=values.expires_at,
        occurred_at=values.occurred_at,
        blocks=[NoteBlockInput.model_validate(block) for block in values.blocks],
        tags=values.tags,
    )
    try:
        note = await create_note(session=context.session, actor=context.actor, payload=payload)
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(ok=True, data=note, meta={"note_id": str(note.id)})


@register(
    name="append_block",
    description=(
        "Append one block to an existing note. Use this to attach a photo, a file, "
        "a text note, or a reminder to a note you or the family already have."
    ),
    category="notes",
    params=AppendBlockParams,
    permissions=("notes.write",),
    mutates=True,
)
async def append_block_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.schemas.notes import NoteBlockInput

    values = AppendBlockParams.model_validate(params)
    payload = NoteBlockInput(
        type=values.type,
        text_content=values.text_content,
        media_asset_id=values.media_asset_id,
        data=values.data,
        caption=values.caption,
        expires_at=values.expires_at,
        importance=values.importance,
    )
    try:
        block = await create_block(
            session=context.session,
            actor=context.actor,
            note_id=values.note_id,
            payload=payload,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(ok=True, data=block, meta={"block_id": str(block.id)})