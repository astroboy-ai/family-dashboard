"""MCP tools for Archify diagrams.

Agents store standalone Archify HTML diagrams here. The HTML is stored
verbatim and rendered in a sandboxed iframe by the frontend viewer — never
served as a route.

``created_by`` is taken from the authenticated actor, never from the tool
params, so an agent cannot file a diagram as someone else.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.agent.registry import ToolContext, ToolResult, register
from app.models import ArchifyDiagram


class ListArchifyParams(BaseModel):
    model_config = {"extra": "forbid"}

    search: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)


class ArchifyDiagramIdParams(BaseModel):
    diagram_id: uuid.UUID


class CreateArchifyParams(BaseModel):
    model_config = {"extra": "forbid"}

    title: str | None = Field(default=None, max_length=300)
    type: str | None = Field(default=None, max_length=40)
    html: str = Field(..., min_length=1)


class UpdateArchifyParams(BaseModel):
    model_config = {"extra": "forbid"}

    diagram_id: uuid.UUID
    title: str | None = Field(default=None, max_length=300)
    type: str | None = Field(default=None, max_length=40)
    html: str | None = None


def _extract_text(html: str) -> str:
    """Pull plain text out of a standalone HTML document for indexing."""
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _to_dict(diagram: ArchifyDiagram) -> dict:
    return {
        "id": str(diagram.id),
        "title": diagram.title,
        "type": diagram.type,
        "created_by": str(diagram.created_by) if diagram.created_by else None,
        "created_at": diagram.created_at.isoformat() if diagram.created_at else None,
        "updated_at": diagram.updated_at.isoformat() if diagram.updated_at else None,
    }


@register(
    name="list_archify_diagrams",
    description=(
        "List the household's Archify interactive HTML diagrams. Returns id, title, "
        "type, and timestamps. Use get_archify_diagram to fetch the full HTML."
    ),
    category="archify",
    params=ListArchifyParams,
    permissions=("notes.read",),
)
async def list_archify_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = ListArchifyParams.model_validate(params)
    stmt = select(ArchifyDiagram).where(
        ArchifyDiagram.household_id == context.actor.household_id
    )
    if values.search:
        stmt = stmt.where(
            ArchifyDiagram.search_tsv.op("@@")(func.plainto_tsquery("simple", values.search))
        )
    stmt = stmt.order_by(ArchifyDiagram.updated_at.desc()).limit(values.limit)
    rows = (await context.session.execute(stmt)).scalars().all()
    return ToolResult(ok=True, data=[_to_dict(d) for d in rows], meta={"count": len(rows)})


@register(
    name="get_archify_diagram",
    description=(
        "Get one Archify diagram including its full standalone HTML. The HTML is "
        "a self-contained interactive document with inline SVG; store it as-is."
    ),
    category="archify",
    params=ArchifyDiagramIdParams,
    permissions=("notes.read",),
)
async def get_archify_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = ArchifyDiagramIdParams.model_validate(params)
    stmt = select(ArchifyDiagram).where(
        ArchifyDiagram.id == values.diagram_id,
        ArchifyDiagram.household_id == context.actor.household_id,
    )
    diagram = (await context.session.execute(stmt)).scalars().first()
    if diagram is None:
        return ToolResult(ok=False, error="Diagram not found", error_code="not_found")
    data = _to_dict(diagram)
    data["html"] = diagram.html
    return ToolResult(ok=True, data=data)


@register(
    name="create_archify_diagram",
    description=(
        "Store an Archify interactive HTML diagram. The HTML must be a standalone "
        "document (the output of Archify's finalize step). Returns the new diagram id."
    ),
    category="archify",
    params=CreateArchifyParams,
    permissions=("notes.write",),
    mutates=True,
)
async def create_archify_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = CreateArchifyParams.model_validate(params)
    diagram = ArchifyDiagram(
        household_id=context.actor.household_id,
        title=values.title,
        type=values.type,
        html=values.html,
        search_tokens_text=_extract_text(values.html),
        created_by=context.actor.member_id,
    )
    context.session.add(diagram)
    await context.session.commit()
    await context.session.refresh(diagram)
    return ToolResult(ok=True, data=_to_dict(diagram), meta={"diagram_id": str(diagram.id)})


@register(
    name="update_archify_diagram",
    description=(
        "Update an Archify diagram's title, type, or HTML. Pass only the fields "
        "you want to change; html is re-indexed when it changes."
    ),
    category="archify",
    params=UpdateArchifyParams,
    permissions=("notes.write",),
    mutates=True,
)
async def update_archify_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = UpdateArchifyParams.model_validate(params)
    stmt = select(ArchifyDiagram).where(
        ArchifyDiagram.id == values.diagram_id,
        ArchifyDiagram.household_id == context.actor.household_id,
    )
    diagram = (await context.session.execute(stmt)).scalars().first()
    if diagram is None:
        return ToolResult(ok=False, error="Diagram not found", error_code="not_found")
    if values.title is not None:
        diagram.title = values.title
    if values.type is not None:
        diagram.type = values.type
    if values.html is not None:
        diagram.html = values.html
        diagram.search_tokens_text = _extract_text(values.html)
    await context.session.commit()
    await context.session.refresh(diagram)
    return ToolResult(ok=True, data=_to_dict(diagram))


@register(
    name="delete_archify_diagram",
    description="Delete an Archify diagram. This cannot be undone.",
    category="archify",
    params=ArchifyDiagramIdParams,
    permissions=("notes.write",),
    mutates=True,
)
async def delete_archify_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = ArchifyDiagramIdParams.model_validate(params)
    stmt = select(ArchifyDiagram).where(
        ArchifyDiagram.id == values.diagram_id,
        ArchifyDiagram.household_id == context.actor.household_id,
    )
    diagram = (await context.session.execute(stmt)).scalars().first()
    if diagram is None:
        return ToolResult(ok=False, error="Diagram not found", error_code="not_found")
    await context.session.delete(diagram)
    await context.session.commit()
    return ToolResult(ok=True, meta={"diagram_id": str(values.diagram_id)})
