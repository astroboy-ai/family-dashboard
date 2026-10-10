from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.schemas.graph import GraphResponse
from app.services.graph import get_graph


router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", response_model=GraphResponse)
async def read_graph(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    scope: str = Query(default="all", max_length=300),
    limit: int = Query(default=2000, ge=1, le=5000),
) -> GraphResponse:
    return await get_graph(session=session, actor=actor, scope=scope, limit=limit)