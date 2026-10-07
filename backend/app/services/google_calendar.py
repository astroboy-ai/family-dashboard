"""Google Calendar OAuth and API service.

Handles the OAuth flow (authorize URL, callback, token refresh) and provides
methods to list calendars and events from Google Calendar API.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, UTC
from typing import Any
from urllib.parse import quote

import httpx
import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.calendar import Calendar, CalendarAccount, CalendarEvent

logger = structlog.get_logger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GoogleTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int
    token_type: str = "Bearer"
    scope: str | None = None


class GoogleCalendarInfo(BaseModel):
    id: str
    summary: str
    description: str | None = None
    primary: bool = False
    backgroundColor: str | None = None


class GoogleEvent(BaseModel):
    id: str
    summary: str | None = None
    description: str | None = None
    start: dict[str, Any]
    end: dict[str, Any]
    location: str | None = None
    status: str = "confirmed"
    htmlLink: str | None = None
    recurrence: list[str] | None = None
    attendees: list[dict[str, Any]] | None = None
    transparency: str | None = None
    visibility: str | None = None
    iCalUID: str | None = None
    updated: str | None = None


def get_authorize_url(state: str, redirect_uri: str) -> str:
    """Build the Google OAuth authorize URL."""
    params = {
        "client_id": get_settings().google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    from urllib.parse import urlencode
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> GoogleTokenResponse:
    """Exchange an authorization code for tokens."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": get_settings().google_client_id,
                "client_secret": get_settings().google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return GoogleTokenResponse(**response.json())


async def refresh_access_token(refresh_token: str) -> GoogleTokenResponse:
    """Refresh an expired access token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": get_settings().google_client_id,
                "client_secret": get_settings().google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        return GoogleTokenResponse(**response.json())


async def _get_valid_token(session: AsyncSession, account_id: uuid.UUID) -> str:
    """Get a valid access token, refreshing if necessary."""
    account = await session.get(CalendarAccount, account_id)
    if not account:
        raise ValueError("Calendar account not found")

    if account.token_expiry and account.token_expiry < datetime.now(UTC) + timedelta(minutes=5):
        if not account.refresh_token:
            raise ValueError("Token expired and no refresh token available")
        token_data = await refresh_access_token(account.refresh_token)
        account.access_token = token_data.access_token
        account.token_expiry = datetime.now(UTC) + timedelta(seconds=token_data.expires_in)
        if token_data.refresh_token:
            account.refresh_token = token_data.refresh_token
        await session.commit()

    return account.access_token


async def list_calendars(session: AsyncSession, account_id: uuid.UUID) -> list[GoogleCalendarInfo]:
    """List all calendars for an account."""
    token = await _get_valid_token(session, account_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GOOGLE_CALENDAR_API}/users/me/calendarList",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        data = response.json()
        return [GoogleCalendarInfo(**item) for item in data.get("items", [])]


async def list_events(
    session: AsyncSession,
    account_id: uuid.UUID,
    calendar_id: str,
    time_min: datetime | None = None,
    time_max: datetime | None = None,
    sync_token: str | None = None,
) -> tuple[list[GoogleEvent], str | None]:
    """List events from a Google Calendar.

    Returns (events, next_sync_token). If sync_token is provided, only
    changes since the last sync are returned.
    """
    token = await _get_valid_token(session, account_id)
    params: dict[str, Any] = {
        "maxResults": 250,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if sync_token:
        # Google rejects syncToken combined with orderBy/timeMin/timeMax.
        params["syncToken"] = sync_token
    else:
        if time_min:
            params["timeMin"] = time_min.isoformat()
        if time_max:
            params["timeMax"] = time_max.isoformat()

    all_events: list[GoogleEvent] = []
    next_sync_token: str | None = None
    page_token: str | None = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            if page_token:
                params["pageToken"] = page_token
            response = await client.get(
                f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            all_events.extend(GoogleEvent(**item) for item in data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                next_sync_token = data.get("nextSyncToken")
                break

    return all_events, next_sync_token


async def get_event(
    session: AsyncSession,
    account_id: uuid.UUID,
    calendar_id: str,
    event_id: str,
) -> GoogleEvent:
    """Get a single event by ID."""
    token = await _get_valid_token(session, account_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return GoogleEvent(**response.json())


async def create_event(
    session: AsyncSession,
    account_id: uuid.UUID,
    calendar_id: str,
    event: GoogleEvent,
) -> GoogleEvent:
    """Create a new event in Google Calendar."""
    token = await _get_valid_token(session, account_id)
    body = event.model_dump(exclude={"id", "htmlLink", "updated"}, exclude_none=True)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        return GoogleEvent(**response.json())


async def update_event(
    session: AsyncSession,
    account_id: uuid.UUID,
    calendar_id: str,
    event: GoogleEvent,
) -> GoogleEvent:
    """Update an existing event."""
    token = await _get_valid_token(session, account_id)
    body = event.model_dump(exclude={"id", "htmlLink", "updated"}, exclude_none=True)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events/{quote(event.id, safe='')}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        return GoogleEvent(**response.json())


async def delete_event(
    session: AsyncSession,
    account_id: uuid.UUID,
    calendar_id: str,
    event_id: str,
) -> None:
    """Delete an event."""
    token = await _get_valid_token(session, account_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(
            f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
