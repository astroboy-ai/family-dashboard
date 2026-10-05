"""Sync Google Calendar data to local DB.

Syncs calendars and events from Google Calendar API into the local database
so the UI can render without hitting Google on every page load.
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobOutbox
from app.models.calendar import Calendar, CalendarAccount, CalendarEvent
from app.services.google_calendar import (
    GoogleEvent,
    list_calendars,
    list_events,
)

logger = structlog.get_logger(__name__)


def enqueue_sync(session: AsyncSession, account_id: uuid.UUID) -> None:
    """Queue a calendar.sync job for one account (outbox pattern)."""
    session.add(
        JobOutbox(
            id=uuid.uuid4(),
            topic="calendar.sync",
            payload={"account_id": str(account_id)},
        )
    )


async def sync_account(session: AsyncSession, account_id: uuid.UUID) -> dict[str, int]:
    """Sync all calendars and events for an account.

    Returns counts of synced calendars and events.
    """
    account = await session.get(CalendarAccount, account_id)
    if not account:
        raise ValueError("Calendar account not found")

    calendars = await list_calendars(session, account_id)
    calendar_count = 0
    event_count = 0

    for cal in calendars:
        # Upsert calendar
        existing = (
            await session.execute(
                select(Calendar).where(
                    Calendar.account_id == account_id,
                    Calendar.google_calendar_id == cal.id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.name = cal.summary
            existing.description = cal.description
            existing.color = cal.backgroundColor
            existing.is_primary = cal.primary
            calendar = existing
        else:
            calendar = Calendar(
                account_id=account_id,
                google_calendar_id=cal.id,
                name=cal.summary,
                description=cal.description,
                color=cal.backgroundColor,
                is_primary=cal.primary,
            )
            session.add(calendar)
            calendar_count += 1

        await session.flush()

        # Sync events
        events, next_sync_token = await list_events(
            session,
            account_id,
            cal.id,
            sync_token=calendar.sync_token,
        )

        for evt in events:
            if evt.status == "cancelled":
                # Delete cancelled events
                await session.execute(
                    CalendarEvent.__table__.delete().where(
                        CalendarEvent.calendar_id == calendar.id,
                        CalendarEvent.google_event_id == evt.id,
                    )
                )
                continue

            existing_evt = (
                await session.execute(
                    select(CalendarEvent).where(
                        CalendarEvent.calendar_id == calendar.id,
                        CalendarEvent.google_event_id == evt.id,
                    )
                )
            ).scalar_one_or_none()

            start_time = _parse_datetime(evt.start)
            end_time = _parse_datetime(evt.end)
            all_day = "date" in evt.start

            if existing_evt:
                existing_evt.title = evt.summary
                existing_evt.description = evt.description
                existing_evt.start_time = start_time
                existing_evt.end_time = end_time
                existing_evt.all_day = all_day
                existing_evt.location = evt.location
                existing_evt.recurrence = evt.recurrence
                existing_evt.attendees = evt.attendees
                existing_evt.status = evt.status
                existing_evt.visibility = evt.visibility
                existing_evt.transparency = evt.transparency
                existing_evt.ical_uid = evt.iCalUID
                existing_evt.html_link = evt.htmlLink
                existing_evt.last_modified_at = _parse_iso(evt.updated) if evt.updated else None
            else:
                session.add(
                    CalendarEvent(
                        calendar_id=calendar.id,
                        google_event_id=evt.id,
                        title=evt.summary,
                        description=evt.description,
                        start_time=start_time,
                        end_time=end_time,
                        all_day=all_day,
                        location=evt.location,
                        recurrence=evt.recurrence,
                        attendees=evt.attendees,
                        status=evt.status,
                        visibility=evt.visibility,
                        transparency=evt.transparency,
                        ical_uid=evt.iCalUID,
                        html_link=evt.htmlLink,
                        last_modified_at=_parse_iso(evt.updated) if evt.updated else None,
                    )
                )
                event_count += 1

        calendar.sync_token = next_sync_token
        calendar.last_synced_at = datetime.now(UTC)

    await session.commit()
    logger.info("calendar_sync_complete", account_id=str(account_id), calendars=calendar_count, events=event_count)
    return {"calendars": calendar_count, "events": event_count}


def _parse_datetime(time_data: dict) -> datetime:
    """Parse Google Calendar datetime or date."""
    if "dateTime" in time_data:
        return _parse_iso(time_data["dateTime"])
    # All-day event: date only
    date_str = time_data.get("date", "")
    return datetime.fromisoformat(date_str).replace(tzinfo=UTC)


def _parse_iso(iso_str: str) -> datetime:
    """Parse ISO 8601 datetime string."""
    # Handle Z suffix
    if iso_str.endswith("Z"):
        iso_str = iso_str[:-1] + "+00:00"
    return datetime.fromisoformat(iso_str)
