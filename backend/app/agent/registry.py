from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor


@dataclass(frozen=True)
class ToolContext:
    actor: Actor
    session: AsyncSession
    request_id: str


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    error_code: str | None = None
    meta: dict[str, Any] | None = None


ToolHandler = Callable[[BaseModel, ToolContext], Awaitable[ToolResult]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    category: str
    params_model: type[BaseModel]
    permissions: tuple[str, ...]
    mutates: bool
    handler: ToolHandler


registry: dict[str, ToolDefinition] = {}


def register(
    *,
    name: str,
    description: str,
    category: str,
    params: type[BaseModel],
    permissions: tuple[str, ...] = (),
    mutates: bool = False,
) -> Callable[[ToolHandler], ToolHandler]:
    def decorator(handler: ToolHandler) -> ToolHandler:
        if name in registry:
            raise ValueError(f"Tool is already registered: {name}")
        registry[name] = ToolDefinition(
            name=name,
            description=description,
            category=category,
            params_model=params,
            permissions=permissions,
            mutates=mutates,
            handler=handler,
        )
        return handler

    return decorator