import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GraphViewCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    kind: str = Field(default="custom", max_length=32)
    config: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool = False

    @field_validator("name", "description", "kind", mode="before")
    @classmethod
    def _blank_to_default(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return "" if value == "" else value
        return value


class GraphViewPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    kind: str | None = Field(default=None, max_length=32)
    config: dict[str, Any] | None = None
    is_shared: bool | None = None
    order_index: int | None = None


class GraphViewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    kind: str
    config: dict[str, Any]
    is_shared: bool
    order_index: int
    created_at: datetime
    updated_at: datetime


class GraphViewListResponse(BaseModel):
    items: list[GraphViewResponse]
    total: int
