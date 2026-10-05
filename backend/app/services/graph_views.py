import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.core.errors import AppError
from app.models import GraphView
from app.schemas.graph_view import GraphViewCreateRequest, GraphViewPatchRequest

DEFAULT_VIEW_NAME = "System overview"
DEFAULT_VIEW_CONFIG: dict[str, Any] = {
    "scope": "all",
    "node_types": ["note", "tag"],
    "edge_types": ["tag", "relation", "hierarchy"],
    "filters": {},
    "layout": "force",
    "colors": {},
    "cluster_by": None,
}


async def list_graph_views(*, session: AsyncSession, actor: Actor) -> tuple[list[GraphView], int]:
    statement = (
        select(GraphView)
        .where(GraphView.household_id == actor.household_id)
        .order_by(GraphView.order_index, GraphView.created_at)
    )
    rows = list((await session.execute(statement)).scalars().all())
    if not rows:
        # A household with no saved views still needs something to open, so the
        # gallery is never empty on first visit.
        rows = [await create_graph_view(
            session=session,
            actor=actor,
            payload=GraphViewCreateRequest(name=DEFAULT_VIEW_NAME, kind="default", config=DEFAULT_VIEW_CONFIG),
        )]
    return rows, len(rows)


async def get_graph_view(*, session: AsyncSession, actor: Actor, view_id: uuid.UUID) -> GraphView:
    view = (
        await session.execute(
            select(GraphView).where(GraphView.id == view_id, GraphView.household_id == actor.household_id)
        )
    ).scalar_one_or_none()
    if view is None:
        raise AppError("Graph view not found", status_code=404, error_code="graph_view_not_found")
    return view


async def create_graph_view(
    *, session: AsyncSession, actor: Actor, payload: GraphViewCreateRequest
) -> GraphView:
    next_order = (
        await session.execute(
            select(func.coalesce(func.max(GraphView.order_index), -1) + 1).where(
                GraphView.household_id == actor.household_id
            )
        )
    ).scalar_one()
    view = GraphView(
        household_id=actor.household_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        kind=payload.kind.strip() or "custom",
        config=payload.config,
        is_shared=payload.is_shared,
        created_by=actor.member_id,
        order_index=int(next_order),
    )
    session.add(view)
    await session.commit()
    # Re-query: `updated_at` has onupdate=func.now(), so the committed instance is
    # expired and touching it again would lazy-load outside the greenlet context.
    return await get_graph_view(session=session, actor=actor, view_id=view.id)


async def update_graph_view(
    *, session: AsyncSession, actor: Actor, view_id: uuid.UUID, payload: GraphViewPatchRequest
) -> GraphView:
    view = await get_graph_view(session=session, actor=actor, view_id=view_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field in {"name", "description", "kind"} and isinstance(value, str):
            value = value.strip()
        setattr(view, field, value)
    await session.commit()
    return await get_graph_view(session=session, actor=actor, view_id=view_id)


async def delete_graph_view(*, session: AsyncSession, actor: Actor, view_id: uuid.UUID) -> None:
    view = await get_graph_view(session=session, actor=actor, view_id=view_id)
    await session.delete(view)
    await session.commit()
