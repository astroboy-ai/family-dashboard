import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.schemas.graph_view import (
    GraphViewCreateRequest,
    GraphViewListResponse,
    GraphViewPatchRequest,
    GraphViewResponse,
)
from app.services.graph_views import (
    create_graph_view,
    delete_graph_view,
    get_graph_view,
    list_graph_views,
    update_graph_view,
)


router = APIRouter(prefix="/graph/views", tags=["graph-views"])


@router.get("", response_model=GraphViewListResponse)
async def get_graph_views(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GraphViewListResponse:
    items, total = await list_graph_views(session=session, actor=actor)
    return GraphViewListResponse(items=[GraphViewResponse.model_validate(item) for item in items], total=total)


@router.post("", response_model=GraphViewResponse, status_code=status.HTTP_201_CREATED)
async def post_graph_view(
    payload: GraphViewCreateRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GraphViewResponse:
    view = await create_graph_view(session=session, actor=actor, payload=payload)
    return GraphViewResponse.model_validate(view)


@router.get("/{view_id}", response_model=GraphViewResponse)
async def read_graph_view(
    view_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GraphViewResponse:
    view = await get_graph_view(session=session, actor=actor, view_id=view_id)
    return GraphViewResponse.model_validate(view)


@router.patch("/{view_id}", response_model=GraphViewResponse)
async def patch_graph_view(
    view_id: uuid.UUID,
    payload: GraphViewPatchRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GraphViewResponse:
    view = await update_graph_view(session=session, actor=actor, view_id=view_id, payload=payload)
    return GraphViewResponse.model_validate(view)


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_graph_view(
    view_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await delete_graph_view(session=session, actor=actor, view_id=view_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
