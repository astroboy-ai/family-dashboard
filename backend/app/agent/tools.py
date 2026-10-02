import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agent.registry import ToolContext, ToolResult, register
from app.services.notes import get_note, list_blocks, list_tags, note_access_clause
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