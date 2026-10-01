import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class NoteBlockInput(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    text_content: str | None = None
    media_asset_id: uuid.UUID | None = None
    thumb_media_id: uuid.UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    caption: str | None = None
    expires_at: datetime | None = None
    importance: int = Field(default=0, ge=0, le=5)


class NoteCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    type: str = Field(default="freeform", min_length=1, max_length=40)
    status: Literal["inbox", "active", "done", "archived", "expired"] = "inbox"
    summary: str | None = None
    owner_member_id: uuid.UUID | None = None
    visibility: Literal["family", "parents", "private"] = "family"
    pinned: bool = False
    occurred_at: datetime | None = None
    expires_at: datetime | None = None
    location: dict[str, Any] | None = None
    parent_note_id: uuid.UUID | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    blocks: list[NoteBlockInput] = Field(default_factory=list, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=30)


class NotePatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    type: str | None = Field(default=None, min_length=1, max_length=40)
    status: Literal["inbox", "active", "done", "archived", "expired"] | None = None
    summary: str | None = None
    owner_member_id: uuid.UUID | None = None
    visibility: Literal["family", "parents", "private"] | None = None
    pinned: bool | None = None
    occurred_at: datetime | None = None
    expires_at: datetime | None = None
    location: dict[str, Any] | None = None
    parent_note_id: uuid.UUID | None = None
    extra: dict[str, Any] | None = None


class NoteBlockPatchRequest(BaseModel):
    type: str | None = Field(default=None, min_length=1, max_length=32)
    text_content: str | None = None
    media_asset_id: uuid.UUID | None = None
    thumb_media_id: uuid.UUID | None = None
    data: dict[str, Any] | None = None
    caption: str | None = None
    expires_at: datetime | None = None
    importance: int | None = Field(default=None, ge=0, le=5)


class NoteReorderRequest(BaseModel):
    block_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class NoteTagRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class NoteBlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    note_id: uuid.UUID
    order_index: int
    type: str
    text_content: str | None
    media_asset_id: uuid.UUID | None
    thumb_media_id: uuid.UUID | None = None
    data: dict[str, Any]
    caption: str | None
    ai_description: str | None
    ocr_text: str | None
    transcript: str | None
    expires_at: datetime | None
    importance: int
    created_at: datetime
    updated_at: datetime


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    color: str | None
    kind: str


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    household_id: uuid.UUID
    title: str | None
    type: str
    status: str
    summary: str | None
    ai_summary: str | None
    created_by: uuid.UUID | None
    owner_member_id: uuid.UUID | None
    visibility: str
    pinned: bool
    occurred_at: datetime | None
    expires_at: datetime | None
    location: dict[str, Any] | None
    parent_note_id: uuid.UUID | None
    extra: dict[str, Any]
    embedding_status: str
    created_at: datetime
    updated_at: datetime
    blocks: list[NoteBlockResponse] = Field(default_factory=list)
    tags: list[TagResponse] = Field(default_factory=list)


class NoteListResponse(BaseModel):
    items: list[NoteResponse]
    limit: int
    offset: int
