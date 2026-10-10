"""Notification service — create, query, and mark notifications as read.

Notifications are produced by the reminder worker (which scans notes with
``expires_at``) and by other parts of the system. They are delivered in-app
via the notification API, and can also be pushed to external channels
(Discord, email) in future.

The ``dedupe_key`` prevents the same reminder from firing twice for the same
note — the worker checks for an existing notification with the same key before
creating a new one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification


async def create_notification(
    *,
    session: AsyncSession,
    household_id: uuid.UUID,
    kind: str,
    title: str,
    body: str | None = None,
    member_id: uuid.UUID | None = None,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    priority: int = 2,
    scheduled_for: datetime | None = None,
    channel: str = "inapp",
    dedupe_key: str | None = None,
) -> Notification:
    """Create a notification.

    If ``dedupe_key`` is provided and a notification with the same key already
    exists for the household, the existing one is returned instead of creating
    a duplicate.
    """

    if dedupe_key:
        existing = await get_by_dedupe_key(
            session=session,
            household_id=household_id,
            dedupe_key=dedupe_key,
        )
        if existing:
            return existing

    notification = Notification(
        household_id=household_id,
        member_id=member_id,
        kind=kind,
        title=title,
        body=body,
        ref_type=ref_type,
        ref_id=ref_id,
        priority=priority,
        scheduled_for=scheduled_for,
        channel=channel,
        dedupe_key=dedupe_key,
    )
    session.add(notification)
    await session.commit()
    return notification


async def get_by_dedupe_key(
    *, session: AsyncSession, household_id: uuid.UUID, dedupe_key: str
) -> Notification | None:
    result = await session.execute(
        select(Notification).where(
            Notification.household_id == household_id,
            Notification.dedupe_key == dedupe_key,
        )
    )
    return result.scalars().first()


async def list_notifications(
    *,
    session: AsyncSession,
    household_id: uuid.UUID,
    member_id: uuid.UUID | None = None,
    unread_only: bool = False,
    limit: int = 50,
) -> list[Notification]:
    """List notifications for a household, optionally filtered by member."""

    stmt = select(Notification).where(
        Notification.household_id == household_id,
    )
    if member_id:
        stmt = stmt.where(
            (Notification.member_id == member_id) | (Notification.member_id.is_(None))
        )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_as_read(
    *, session: AsyncSession, notification_id: uuid.UUID, member_id: uuid.UUID
) -> Notification | None:
    """Mark a notification as read. Returns None if not found."""

    notification = await session.get(Notification, notification_id)
    if notification is None:
        return None
    notification.read_at = datetime.now(UTC)
    await session.commit()
    return notification


async def mark_all_as_read(
    *, session: AsyncSession, household_id: uuid.UUID, member_id: uuid.UUID
) -> int:
    """Mark all unread notifications for a member as read. Returns count."""

    from sqlalchemy import update

    result = await session.execute(
        update(Notification)
        .where(
            Notification.household_id == household_id,
            Notification.member_id == member_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()
    return result.rowcount or 0


async def get_unread_count(
    *, session: AsyncSession, household_id: uuid.UUID, member_id: uuid.UUID
) -> int:
    """Count unread notifications for a member."""

    from sqlalchemy import func

    result = await session.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.household_id == household_id,
            Notification.member_id == member_id,
            Notification.read_at.is_(None),
        )
    )
    return result.scalar_one()
