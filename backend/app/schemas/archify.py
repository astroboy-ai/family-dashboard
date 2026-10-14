from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ArchifyDiagramCreateRequest(BaseModel):
    title: str | None = None
    type: str | None = None
    html: str = Field(..., min_length=1)


class ArchifyDiagramUpdateRequest(BaseModel):
    title: str | None = None
    type: str | None = None
    html: str | None = None


class ArchifyTagAttachRequest(BaseModel):
    slugs: list[str] = Field(..., min_length=1)


class ArchifyDiagramResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    type: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    tags: list[dict[str, str]] = []


class ArchifyDiagramDetailResponse(ArchifyDiagramResponse):
    html: str | None = None


class ArchifyListResponse(BaseModel):
    diagrams: list[ArchifyDiagramResponse]
