"""Calendar API router.

Endpoints for Google Calendar OAuth, calendar/event listing, and sync.
All endpoints require authentication and appropriate scopes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, UTC
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.api.deps import Actor, get_current_actor, require_scope
from app.core.config import get_settings
from app.core.db import get_session
from app.models.calendar import Calendar, CalendarAccount, CalendarEvent, CalendarPermission, CalendarView
from app.schemas.calendar import (
    CalendarAccountResponse,
    CalendarEventCreateRequest,
    CalendarEventResponse,
    CalendarEventUpdateRequest,
    CalendarPermissionRequest,
    CalendarPermissionResponse,
    CalendarResponse,
    CalendarViewCreateRequest,
    CalendarViewResponse,
    CalendarViewUpdateRequest,
    OAuthCallbackRequest,
    OAuthUrlResponse,
    SyncResponse,
)
from app.services.calendar_sync import sync_account
from app.services.google_calendar import (
    create_event as google_create_event,
    delete_event as google_delete_event,
    exchange_code,
    get_authorize_url,
    GoogleEvent,
    list_calendars as google_list_calendars,
    list_events as google_list_events,
    update_event as google_update_event,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])
logger = structlog.get_logger(__name__)


@router.get("/oauth/url", response_model=OAuthUrlResponse)
async def get_oauth_url(
    actor: Annotated[Actor, Depends(require_scope("calendar.read"))],
) -> OAuthUrlResponse:
    """Get Google OAuth authorize URL."""
    settings = get_settings()
    if not settings.google_calendar_enabled:
        raise HTTPException(status_code=400, detail="Google Calendar is not enabled")

    # Use a signed JWT as state for CSRF protection (stateless)
    import jwt
    state = jwt.encode(
        {
            "household_id": str(actor.household_id),
            "member_id": str(actor.member_id) if actor.member_id else None,
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return OAuthUrlResponse(authorize_url=get_authorize_url(state, settings.google_redirect_uri))


@router.get("/oauth/callback")
async def oauth_callback(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    code: str = Query(...),
    state: str = Query(...),
) -> RedirectResponse:
    """Exchange OAuth code for tokens and create calendar account."""
    settings = get_settings()
    if not settings.google_calendar_enabled:
        raise HTTPException(status_code=400, detail="Google Calendar is not enabled")

    # Decode and verify the signed JWT state
    import jwt
    try:
        state_claims = jwt.decode(
            state,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=400, detail="Invalid or expired state") from e

    if state_claims.get("household_id") != str(actor.household_id):
        raise HTTPException(status_code=403, detail="State mismatch")

    token_data = await exchange_code(code, settings.google_redirect_uri)

    # Fetch user info to get email
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data.access_token}"},
        )
        resp.raise_for_status()
        user_info = resp.json()
        email = user_info.get("email", "unknown@gmail.com")

    # Check if account already exists for this email in this household
    existing = (
        await session.execute(
            select(CalendarAccount).where(
                CalendarAccount.household_id == actor.household_id,
                CalendarAccount.email == email,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.access_token = token_data.access_token
        existing.refresh_token = token_data.refresh_token
        existing.token_expiry = datetime.now(UTC) + timedelta(seconds=token_data.expires_in)
        existing.is_active = True
        await session.commit()
        return RedirectResponse(url="/calendar/settings?oauth=success", status_code=303)

    account = CalendarAccount(
        household_id=actor.household_id,
        member_id=actor.member_id,
        email=email,
        access_token=token_data.access_token,
        refresh_token=token_data.refresh_token,
        token_expiry=datetime.now(UTC) + timedelta(seconds=token_data.expires_in),
        scopes=token_data.scope.split() if token_data.scope else [],
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    # Auto-sync right away so the user sees calendars without pressing Sync.
    # A failure here must not break the OAuth redirect.
    try:
        await sync_account(session, account.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("calendar.oauth.auto_sync_failed", error=str(exc))

    return RedirectResponse(url="/calendar/settings?oauth=success", status_code=303)


@router.get("/accounts", response_model=list[CalendarAccountResponse])
async def list_accounts(
    actor: Annotated[Actor, Depends(require_scope("calendar.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CalendarAccountResponse]:
    """List calendar accounts for the household."""
    rows = (
        await session.execute(
            select(CalendarAccount).where(
                CalendarAccount.household_id == actor.household_id,
                CalendarAccount.is_active.is_(True),
            )
        )
    ).scalars().all()
    return [
        CalendarAccountResponse(
            id=r.id,
            email=r.email,
            is_active=r.is_active,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/calendars", response_model=list[CalendarResponse])
async def list_calendars(
    actor: Annotated[Actor, Depends(require_scope("calendar.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CalendarResponse]:
    """List calendars for the household."""
    rows = (
        await session.execute(
            select(Calendar)
            .join(CalendarAccount, Calendar.account_id == CalendarAccount.id)
            .where(
                CalendarAccount.household_id == actor.household_id,
                Calendar.is_visible.is_(True),
            )
        )
    ).scalars().all()
    return [
        CalendarResponse(
            id=r.id,
            account_id=r.account_id,
            google_calendar_id=r.google_calendar_id,
            name=r.name,
            description=r.description,
            color=r.color,
            is_primary=r.is_primary,
            is_visible=r.is_visible,
            last_synced_at=r.last_synced_at,
        )
        for r in rows
    ]


def _google_time_range(
    start: datetime,
    end: datetime,
    all_day: bool,
) -> tuple[dict[str, str], dict[str, str]]:
    """Build Google's start/end objects for an event.

    Google distinguishes timed events (``dateTime``) from all-day events
    (``date``). Sending ``dateTime`` for an all-day event silently turns it into
    a timed one, so the choice has to follow the ``all_day`` flag on both the
    create and the update path.
    """

    if all_day:
        # Google treats an all-day event's end date as exclusive, so a
        # single-day event must end on the following day. Passing the same date
        # for both is rejected outright.
        last_day = end.date() if end.date() > start.date() else start.date() + timedelta(days=1)
        return {"date": start.date().isoformat()}, {"date": last_day.isoformat()}
    return {"dateTime": start.isoformat()}, {"dateTime": end.isoformat()}


def _event_response(event: CalendarEvent) -> CalendarEventResponse:
    """Serialise an event row. One place, so no field is dropped on one path."""

    return CalendarEventResponse(
        id=event.id,
        calendar_id=event.calendar_id,
        google_event_id=event.google_event_id,
        title=event.title,
        description=event.description,
        start_time=event.start_time,
        end_time=event.end_time,
        all_day=event.all_day,
        location=event.location,
        recurrence=event.recurrence,
        status=event.status,
        html_link=event.html_link,
    )


@router.get("/events", response_model=list[CalendarEventResponse])
async def list_events(
    actor: Annotated[Actor, Depends(require_scope("calendar.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    calendar_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CalendarEventResponse]:
    """List events, optionally filtered by calendar and time range."""
    stmt = (
        select(CalendarEvent)
        .join(Calendar, CalendarEvent.calendar_id == Calendar.id)
        .join(CalendarAccount, Calendar.account_id == CalendarAccount.id)
        .where(
            CalendarAccount.household_id == actor.household_id,
            Calendar.is_visible.is_(True),
        )
    )
    if calendar_id:
        stmt = stmt.where(CalendarEvent.calendar_id == calendar_id)
    if start:
        stmt = stmt.where(CalendarEvent.end_time >= start)
    if end:
        stmt = stmt.where(CalendarEvent.start_time <= end)
    stmt = stmt.order_by(CalendarEvent.start_time).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return [_event_response(r) for r in rows]


@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: CalendarEventCreateRequest,
    actor: Annotated[Actor, Depends(require_scope("calendar.write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CalendarEventResponse:
    """Create a new event in Google Calendar and cache it locally."""
    calendar = await session.get(Calendar, payload.calendar_id)
    if not calendar:
        raise HTTPException(status_code=404, detail="Calendar not found")

    account = await session.get(CalendarAccount, calendar.account_id)
    if not account or account.household_id != actor.household_id:
        raise HTTPException(status_code=403, detail="Access denied")

    google_evt = GoogleEvent(
        id="",
        summary=payload.title,
        description=payload.description,
        start=_google_time_range(payload.start_time, payload.end_time, payload.all_day)[0],
        end=_google_time_range(payload.start_time, payload.end_time, payload.all_day)[1],
        location=payload.location,
        recurrence=payload.recurrence,
    )
    created = await google_create_event(session, account.id, calendar.google_calendar_id, google_evt)

    event = CalendarEvent(
        calendar_id=calendar.id,
        google_event_id=created.id,
        title=created.summary,
        description=created.description,
        start_time=payload.start_time,
        end_time=payload.end_time,
        all_day=payload.all_day,
        location=created.location,
        recurrence=created.recurrence,
        status=created.status,
        html_link=created.htmlLink,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    return _event_response(event)


@router.patch("/events/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: uuid.UUID,
    payload: CalendarEventUpdateRequest,
    actor: Annotated[Actor, Depends(require_scope("calendar.write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CalendarEventResponse:
    """Update an existing event."""
    event = await session.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    calendar = await session.get(Calendar, event.calendar_id)
    account = await session.get(CalendarAccount, calendar.account_id)
    if not account or account.household_id != actor.household_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Resolve the effective values once: a PATCH may omit any field, and the
    # time-range shape depends on the resulting all_day, not on what was sent.
    effective_all_day = event.all_day if payload.all_day is None else payload.all_day
    effective_start = payload.start_time or event.start_time
    effective_end = payload.end_time or event.end_time
    start_obj, end_obj = _google_time_range(effective_start, effective_end, effective_all_day)

    # recurrence is tri-state: omitted keeps the current rule; an empty list
    # clears it. Google only clears when the key is present and empty, and
    # ``model_dump(exclude_none=True)`` keeps ``[]`` while dropping ``None``,
    # so the empty list must be passed through rather than collapsed to None.
    if payload.recurrence is None:
        effective_recurrence = event.recurrence
    else:
        effective_recurrence = payload.recurrence

    google_evt = GoogleEvent(
        id=event.google_event_id,
        summary=payload.title or event.title,
        description=payload.description if payload.description is not None else event.description,
        start=start_obj,
        end=end_obj,
        location=payload.location if payload.location is not None else event.location,
        recurrence=effective_recurrence,
    )
    updated = await google_update_event(session, account.id, calendar.google_calendar_id, google_evt)

    event.title = updated.summary
    event.description = updated.description
    event.start_time = effective_start
    event.end_time = effective_end
    event.all_day = effective_all_day
    event.location = updated.location
    event.recurrence = updated.recurrence
    event.html_link = updated.htmlLink
    await session.commit()
    await session.refresh(event)

    return _event_response(event)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID,
    actor: Annotated[Actor, Depends(require_scope("calendar.write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Delete an event from Google Calendar and local cache."""
    event = await session.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    calendar = await session.get(Calendar, event.calendar_id)
    account = await session.get(CalendarAccount, calendar.account_id)
    if not account or account.household_id != actor.household_id:
        raise HTTPException(status_code=403, detail="Access denied")

    await google_delete_event(session, account.id, calendar.google_calendar_id, event.google_event_id)
    await session.delete(event)
    await session.commit()


@router.post("/sync", response_model=SyncResponse)
async def sync_calendars(
    actor: Annotated[Actor, Depends(require_scope("calendar.write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    account_id: uuid.UUID | None = None,
) -> SyncResponse:
    """Sync calendars and events from Google Calendar API."""
    if account_id:
        account = await session.get(CalendarAccount, account_id)
        if not account or account.household_id != actor.household_id:
            raise HTTPException(status_code=403, detail="Access denied")
        result = await sync_account(session, account_id)
        return SyncResponse(**result)

    # Sync all accounts
    accounts = (
        await session.execute(
            select(CalendarAccount.id).where(
                CalendarAccount.household_id == actor.household_id,
                CalendarAccount.is_active.is_(True),
            )
        )
    ).scalars().all()

    total_calendars = 0
    total_events = 0
    for acc_id in accounts:
        result = await sync_account(session, acc_id)
        total_calendars += result["calendars"]
        total_events += result["events"]

    return SyncResponse(calendars=total_calendars, events=total_events)


# ── Calendar Permissions ──────────────────────────────────────────────────────

@router.get("/permissions", response_model=list[CalendarPermissionResponse])
async def list_permissions(
    actor: Annotated[Actor, Depends(require_scope("calendar.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    calendar_id: uuid.UUID | None = None,
) -> list[CalendarPermissionResponse]:
    """List calendar permissions for the household."""
    stmt = (
        select(CalendarPermission)
        .join(Calendar, CalendarPermission.calendar_id == Calendar.id)
        .join(CalendarAccount, Calendar.account_id == CalendarAccount.id)
        .where(CalendarAccount.household_id == actor.household_id)
    )
    if calendar_id:
        stmt = stmt.where(CalendarPermission.calendar_id == calendar_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        CalendarPermissionResponse(
            id=r.id,
            calendar_id=r.calendar_id,
            member_id=r.member_id,
            level=r.level,
        )
        for r in rows
    ]


@router.post("/permissions", response_model=CalendarPermissionResponse, status_code=status.HTTP_201_CREATED)
async def create_permission(
    payload: CalendarPermissionRequest,
    actor: Annotated[Actor, Depends(require_scope("calendar.admin"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    calendar_id: uuid.UUID = Query(...),
) -> CalendarPermissionResponse:
    """Grant a permission on a calendar. Requires admin level."""
    # Verify the calendar belongs to this household
    calendar = await session.get(Calendar, calendar_id)
    if not calendar:
        raise HTTPException(status_code=404, detail="Calendar not found")
    account = await session.get(CalendarAccount, calendar.account_id)
    if not account or account.household_id != actor.household_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check for existing permission
    existing = (
        await session.execute(
            select(CalendarPermission).where(
                CalendarPermission.calendar_id == calendar_id,
                CalendarPermission.member_id == payload.member_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.level = payload.level
        await session.commit()
        return CalendarPermissionResponse(
            id=existing.id,
            calendar_id=existing.calendar_id,
            member_id=existing.member_id,
            level=existing.level,
        )

    perm = CalendarPermission(
        calendar_id=calendar_id,
        member_id=payload.member_id,
        level=payload.level,
    )
    session.add(perm)
    await session.commit()
    await session.refresh(perm)
    return CalendarPermissionResponse(
        id=perm.id,
        calendar_id=perm.calendar_id,
        member_id=perm.member_id,
        level=perm.level,
    )


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    permission_id: uuid.UUID,
    actor: Annotated[Actor, Depends(require_scope("calendar.admin"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Revoke a permission. Requires admin level."""
    perm = await session.get(CalendarPermission, permission_id)
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    calendar = await session.get(Calendar, perm.calendar_id)
    account = await session.get(CalendarAccount, calendar.account_id)
    if not account or account.household_id != actor.household_id:
        raise HTTPException(status_code=403, detail="Access denied")

    await session.delete(perm)
    await session.commit()


# ── Calendar Views (device config) ────────────────────────────────────────────

@router.get("/views", response_model=list[CalendarViewResponse])
async def list_views(
    actor: Annotated[Actor, Depends(require_scope("calendar.read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CalendarViewResponse]:
    """List calendar views for the household."""
    rows = (
        await session.execute(
            select(CalendarView).where(CalendarView.household_id == actor.household_id)
        )
    ).scalars().all()
    return [
        CalendarViewResponse(
            id=r.id,
            name=r.name,
            calendar_ids=r.calendar_ids,
            layout=r.layout,
            is_default=r.is_default,
        )
        for r in rows
    ]


@router.post("/views", response_model=CalendarViewResponse, status_code=status.HTTP_201_CREATED)
async def create_view(
    payload: CalendarViewCreateRequest,
    actor: Annotated[Actor, Depends(require_scope("calendar.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CalendarViewResponse:
    """Create a calendar view (device config)."""
    if payload.is_default:
        # Unset any existing default
        await session.execute(
            CalendarView.__table__.update()
            .where(CalendarView.household_id == actor.household_id)
            .values(is_default=False)
        )

    view = CalendarView(
        household_id=actor.household_id,
        name=payload.name,
        calendar_ids=payload.calendar_ids,
        layout=payload.layout,
        is_default=payload.is_default,
    )
    session.add(view)
    await session.commit()
    await session.refresh(view)
    return CalendarViewResponse(
        id=view.id,
        name=view.name,
        calendar_ids=view.calendar_ids,
        layout=view.layout,
        is_default=view.is_default,
    )


@router.patch("/views/{view_id}", response_model=CalendarViewResponse)
async def update_view(
    view_id: uuid.UUID,
    payload: CalendarViewUpdateRequest,
    actor: Annotated[Actor, Depends(require_scope("calendar.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CalendarViewResponse:
    """Update a calendar view."""
    view = await session.get(CalendarView, view_id)
    if not view or view.household_id != actor.household_id:
        raise HTTPException(status_code=404, detail="View not found")

    if payload.is_default:
        await session.execute(
            CalendarView.__table__.update()
            .where(CalendarView.household_id == actor.household_id)
            .values(is_default=False)
        )

    if payload.name is not None:
        view.name = payload.name
    if payload.calendar_ids is not None:
        view.calendar_ids = payload.calendar_ids
    if payload.layout is not None:
        view.layout = payload.layout
    if payload.is_default is not None:
        view.is_default = payload.is_default

    await session.commit()
    await session.refresh(view)
    return CalendarViewResponse(
        id=view.id,
        name=view.name,
        calendar_ids=view.calendar_ids,
        layout=view.layout,
        is_default=view.is_default,
    )


@router.delete("/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    view_id: uuid.UUID,
    actor: Annotated[Actor, Depends(require_scope("calendar.manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Delete a calendar view."""
    view = await session.get(CalendarView, view_id)
    if not view or view.household_id != actor.household_id:
        raise HTTPException(status_code=404, detail="View not found")

    await session.delete(view)
    await session.commit()
