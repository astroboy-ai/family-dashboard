import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.schemas.notes import NoteListResponse
from app.services.search import DateField, search_notes


router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=NoteListResponse)
async def get_search(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    q: str = Query(default="", max_length=500),
    types: Annotated[list[str] | None, Query()] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    tag_mode: Literal["any", "all"] = "any",
    member_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    date_field: DateField = "updated_at",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    visibility: Annotated[list[str] | None, Query()] = None,
    media_types: Annotated[list[str] | None, Query()] = None,
    expiry: str | None = Query(default=None, pattern=r"^(none|expired|within_7d|within_30d|within_90d)$"),
    pinned: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> NoteListResponse:
    return await search_notes(
        session=session,
        actor=actor,
        query=q,
        types=types,
        tags=tags,
        tag_mode=tag_mode,
        member_ids=member_ids,
        date_field=date_field,
        date_from=date_from,
        date_to=date_to,
        statuses=statuses,
        visibility=visibility,
        media_types=media_types,
        expiry=expiry,
        pinned=pinned,
        limit=limit,
        offset=offset,
    )