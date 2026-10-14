"""CRUD routes for Archify diagrams.

Agents store standalone Archify HTML diagrams here. The HTML is stored
verbatim and rendered in a sandboxed iframe by the frontend viewer — never
served as a route.

``created_by`` is taken from the authenticated actor, never from the request
body, so a caller cannot file a diagram as someone else.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.models import ArchifyDiagram, Tag, archify_diagram_tags
from app.schemas.archify import (
    ArchifyDiagramCreateRequest,
    ArchifyDiagramDetailResponse,
    ArchifyDiagramResponse,
    ArchifyDiagramUpdateRequest,
    ArchifyListResponse,
    ArchifyTagAttachRequest,
)

router = APIRouter(prefix="/archify", tags=["archify"])


def _extract_text(html: str) -> str:
    """Pull plain text out of a standalone HTML document for indexing."""
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def _tags_for(session: AsyncSession, diagram_id: uuid.UUID) -> list[dict[str, str]]:
    stmt = (
        select(Tag.slug, Tag.name)
        .join(archify_diagram_tags, archify_diagram_tags.c.tag_id == Tag.id)
        .where(archify_diagram_tags.c.diagram_id == diagram_id)
        .order_by(Tag.slug)
    )
    rows = (await session.execute(stmt)).all()
    return [{"slug": slug, "name": name} for slug, name in rows]


def _to_response(
    diagram: ArchifyDiagram, tags: list[dict[str, str]], *, with_html: bool = False
) -> ArchifyDiagramResponse | ArchifyDiagramDetailResponse:
    base: dict[str, Any] = {
        "id": diagram.id,
        "title": diagram.title,
        "type": diagram.type,
        "created_by": diagram.created_by,
        "created_at": diagram.created_at,
        "updated_at": diagram.updated_at,
        "tags": tags,
    }
    if with_html:
        base["html"] = diagram.html
        return ArchifyDiagramDetailResponse(**base)
    return ArchifyDiagramResponse(**base)


async def _get_owned(
    session: AsyncSession, diagram_id: uuid.UUID, household_id: uuid.UUID
) -> ArchifyDiagram:
    stmt = select(ArchifyDiagram).where(
        ArchifyDiagram.id == diagram_id,
        ArchifyDiagram.household_id == household_id,
    )
    diagram = (await session.execute(stmt)).scalars().first()
    if diagram is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagram not found")
    return diagram


@router.get("", response_model=ArchifyListResponse)
async def list_diagrams(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: str | None = None,
) -> ArchifyListResponse:
    stmt = select(ArchifyDiagram).where(ArchifyDiagram.household_id == actor.household_id)
    if search:
        stmt = stmt.where(
            ArchifyDiagram.search_tsv.op("@@")(func.plainto_tsquery("simple", search))
        )
    stmt = stmt.order_by(ArchifyDiagram.updated_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    tags = [await _tags_for(session, d.id) for d in rows]
    return ArchifyListResponse(
        diagrams=[_to_response(d, t) for d, t in zip(rows, tags, strict=True)]
    )


@router.post("", response_model=ArchifyDiagramResponse, status_code=status.HTTP_201_CREATED)
async def create_diagram(
    body: ArchifyDiagramCreateRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArchifyDiagramResponse:
    diagram = ArchifyDiagram(
        household_id=actor.household_id,
        title=body.title,
        type=body.type,
        html=body.html,
        search_tokens_text=_extract_text(body.html),
        created_by=actor.member_id,
    )
    session.add(diagram)
    await session.commit()
    await session.refresh(diagram)
    return _to_response(diagram, [])


@router.get("/{diagram_id}", response_model=ArchifyDiagramDetailResponse)
async def get_diagram(
    diagram_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArchifyDiagramDetailResponse:
    diagram = await _get_owned(session, diagram_id, actor.household_id)
    tags = await _tags_for(session, diagram_id)
    return _to_response(diagram, tags, with_html=True)  # type: ignore[return-value]


@router.put("/{diagram_id}", response_model=ArchifyDiagramResponse)
async def update_diagram(
    diagram_id: uuid.UUID,
    body: ArchifyDiagramUpdateRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArchifyDiagramResponse:
    diagram = await _get_owned(session, diagram_id, actor.household_id)
    if body.title is not None:
        diagram.title = body.title
    if body.type is not None:
        diagram.type = body.type
    if body.html is not None:
        diagram.html = body.html
        diagram.search_tokens_text = _extract_text(body.html)
    await session.commit()
    await session.refresh(diagram)
    tags = await _tags_for(session, diagram_id)
    return _to_response(diagram, tags)


@router.delete("/{diagram_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_diagram(
    diagram_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    diagram = await _get_owned(session, diagram_id, actor.household_id)
    await session.delete(diagram)
    await session.commit()


@router.post("/{diagram_id}/tags", response_model=ArchifyDiagramResponse)
async def attach_tags(
    diagram_id: uuid.UUID,
    body: ArchifyTagAttachRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArchifyDiagramResponse:
    diagram = await _get_owned(session, diagram_id, actor.household_id)
    for slug in body.slugs:
        tag = (
            await session.execute(
                select(Tag).where(Tag.slug == slug, Tag.household_id == actor.household_id)
            )
        ).scalars().first()
        if tag is None:
            tag = Tag(slug=slug, name=slug, household_id=actor.household_id)
            session.add(tag)
            await session.flush()
        exists = (
            await session.execute(
                select(archify_diagram_tags).where(
                    archify_diagram_tags.c.diagram_id == diagram_id,
                    archify_diagram_tags.c.tag_id == tag.id,
                )
            )
        ).first()
        if exists is None:
            session.add(
                archify_diagram_tags.insert().values(
                    diagram_id=diagram_id,
                    tag_id=tag.id,
                    applied_by=actor.member_id,
                )
            )
    await session.commit()
    tags = await _tags_for(session, diagram_id)
    return _to_response(diagram, tags)


@router.delete("/{diagram_id}/tags/{slug}", response_model=ArchifyDiagramResponse)
async def detach_tag(
    diagram_id: uuid.UUID,
    slug: str,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArchifyDiagramResponse:
    diagram = await _get_owned(session, diagram_id, actor.household_id)
    tag = (
        await session.execute(
            select(Tag).where(Tag.slug == slug, Tag.household_id == actor.household_id)
        )
    ).scalars().first()
    if tag is not None:
        await session.execute(
            archify_diagram_tags.delete().where(
                archify_diagram_tags.c.diagram_id == diagram_id,
                archify_diagram_tags.c.tag_id == tag.id,
            )
        )
        await session.commit()
    tags = await _tags_for(session, diagram_id)
    return _to_response(diagram, tags)
