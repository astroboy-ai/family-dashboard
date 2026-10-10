"""Notification API — list, mark read, mark all read, unread count."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.services.notifications import (
    get_unread_count,
    list_notifications,
    mark_all_as_read,
    mark_as_read,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    ref_type: str | None
    ref_id: uuid.UUID | None
    priority: int
    scheduled_for: str | None
    sent_at: str | None
    read_at: str | None
    channel: str
    created_at: str


class UnreadCountResponse(BaseModel):
    count: int


class MarkAllReadResponse(BaseModel):
    marked: int


def _to_response(notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        kind=notification.kind,
        title=notification.title,
        body=notification.body,
        ref_type=notification.ref_type,
        ref_id=notification.ref_id,
        priority=notification.priority,
        scheduled_for=notification.scheduled_for.isoformat() if notification.scheduled_for else None,
        sent_at=notification.sent_at.isoformat() if notification.sent_at else None,
        read_at=notification.read_at.isoformat() if notification.read_at else None,
        channel=notification.channel,
        created_at=notification.created_at.isoformat(),
    )


@router.get("", response_model=list[NotificationResponse])
async def list_notifications_endpoint(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    actor: Annotated[Actor, Depends(get_current_actor)] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
):
    notifications = await list_notifications(
        session=session,
        household_id=actor.household_id,
        member_id=actor.member_id or None,
        unread_only=unread_only,
        limit=limit,
    )
    return [_to_response(n) for n in notifications]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count_endpoint(
    actor: Annotated[Actor, Depends(get_current_actor)] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
):
    count = await get_unread_count(
        session=session,
        household_id=actor.household_id,
        member_id=actor.member_id or None,
    )
    return UnreadCountResponse(count=count)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read_endpoint(
    notification_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
):
    notification = await mark_as_read(
        session=session,
        notification_id=notification_id,
        member_id=actor.member_id or None,
    )
    if notification is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Notification not found")
    return _to_response(notification)


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
async def mark_all_as_read_endpoint(
    actor: Annotated[Actor, Depends(get_current_actor)] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
):
    count = await mark_all_as_read(
        session=session,
        household_id=actor.household_id,
        member_id=actor.member_id or None,
    )
    return MarkAllReadResponse(marked=count)
