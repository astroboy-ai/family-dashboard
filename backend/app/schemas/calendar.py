"""Pydantic schemas for calendar API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CalendarAccountResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime


class CalendarResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    google_calendar_id: str
    name: str
    description: str | None = None
    color: str | None = None
    theme: str | None = None
    is_primary: bool
    is_visible: bool
    is_customized: bool = False
    last_synced_at: datetime | None = None


class CalendarUpdateRequest(BaseModel):
    """Local-only calendar display settings.

    ``name`` and ``color`` are also written by the sync from Google, so setting
    either one flips ``is_customized`` and the sync stops overwriting them.
    ``is_visible`` and ``theme`` are purely local and never come from Google.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    color: str | None = Field(default=None, max_length=32)
    theme: str | None = Field(default=None, max_length=32)
    is_visible: bool | None = None


class CalendarEventResponse(BaseModel):
    id: uuid.UUID
    calendar_id: uuid.UUID
    google_event_id: str
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime
    all_day: bool
    location: str | None = None
    # RRULE strings (RFC 5545), e.g. ["FREQ=WEEKLY;INTERVAL=1"]. Exposed so the
    # UI can prefill the repeat dropdown when editing a recurring event.
    recurrence: list[str] | None = None
    status: str
    html_link: str | None = None


class CalendarEventCreateRequest(BaseModel):
    calendar_id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    start_time: datetime
    end_time: datetime
    all_day: bool = False
    location: str | None = None
    recurrence: list[str] | None = Field(
        default=None,
        description='RRULE strings, e.g. ["FREQ=WEEKLY;INTERVAL=1"]',
    )


class CalendarEventUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    all_day: bool | None = None
    location: str | None = None
    recurrence: list[str] | None = Field(
        default=None,
        description='RRULE strings. Empty list clears the recurrence.',
    )


class SyncResponse(BaseModel):
    calendars: int
    events: int


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class OAuthUrlResponse(BaseModel):
    authorize_url: str


class CalendarPermissionResponse(BaseModel):
    id: uuid.UUID
    calendar_id: uuid.UUID
    member_id: uuid.UUID
    level: str
    # Denormalised for display. The settings UI needs a name, not a UUID, and
    # resolving it client-side would need a second lookup per row.
    member_name: str | None = None
    calendar_name: str | None = None


class CalendarPermissionBulkRequest(BaseModel):
    """Grant one level to many members across many calendars in one call.

    The UI selects members and calendars with multi-select controls; posting
    each pair individually would be N×M round-trips for one screen action.
    """

    member_ids: list[uuid.UUID] = Field(min_length=1)
    calendar_ids: list[uuid.UUID] = Field(min_length=1)
    level: str = Field(pattern="^(view|edit|manage|admin)$")


class CalendarPermissionRequest(BaseModel):
    member_id: uuid.UUID
    level: str = Field(pattern="^(view|edit|manage|admin)$")


class CalendarViewResponse(BaseModel):
    id: uuid.UUID
    name: str
    calendar_ids: list[uuid.UUID]
    layout: str
    is_default: bool


class CalendarViewCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    calendar_ids: list[uuid.UUID]
    layout: str = Field(pattern="^(month|week|day|agenda)$")
    is_default: bool = False


class CalendarViewUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    calendar_ids: list[uuid.UUID] | None = None
    layout: str | None = Field(default=None, pattern="^(month|week|day|agenda)$")
    is_default: bool | None = None
