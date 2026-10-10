"""Dashboard API — CRUD for user-configurable dashboards."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor, get_session
from app.models.dashboard import Dashboard

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


class DashboardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    layout: str = "grid"
    is_default: bool = False
    widgets: list[dict[str, Any]] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    layout: str | None = None
    is_default: bool | None = None
    widgets: list[dict[str, Any]] | None = None


class DashboardResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    layout: str
    is_default: bool
    widgets: list[dict[str, Any]]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


def _to_response(d: Dashboard) -> DashboardResponse:
    return DashboardResponse(
        id=d.id,
        name=d.name,
        description=d.description,
        layout=d.layout,
        is_default=d.is_default,
        widgets=d.widgets,
        created_at=d.created_at.isoformat() if d.created_at else "",
        updated_at=d.updated_at.isoformat() if d.updated_at else "",
    )


@router.get("")
async def list_dashboards(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DashboardResponse]:
    result = await session.execute(
        select(Dashboard).where(Dashboard.household_id == actor.household_id).order_by(Dashboard.is_default.desc(), Dashboard.name)
    )
    return [_to_response(d) for d in result.scalars()]


@router.post("", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    payload: DashboardCreate,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DashboardResponse:
    d = Dashboard(
        household_id=actor.household_id,
        name=payload.name,
        description=payload.description,
        layout=payload.layout,
        is_default=payload.is_default,
        widgets=payload.widgets,
    )
    session.add(d)
    await session.commit()
    await session.refresh(d)
    return _to_response(d)


@router.get("/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DashboardResponse:
    d = await session.get(Dashboard, dashboard_id)
    if not d or d.household_id != actor.household_id:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return _to_response(d)


@router.patch("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: uuid.UUID,
    payload: DashboardUpdate,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DashboardResponse:
    d = await session.get(Dashboard, dashboard_id)
    if not d or d.household_id != actor.household_id:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(d, key, value)
    await session.commit()
    await session.refresh(d)
    return _to_response(d)


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    d = await session.get(Dashboard, dashboard_id)
    if not d or d.household_id != actor.household_id:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    await session.delete(d)
    await session.commit()
