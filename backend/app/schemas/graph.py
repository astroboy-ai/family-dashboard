from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    note_type: str | None = None
    pinned: bool = False
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    relation_type: str | None = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    meta: dict[str, Any]