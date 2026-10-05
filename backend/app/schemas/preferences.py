from typing import Any

from pydantic import BaseModel, Field


class MemberPreferences(BaseModel):
    """Per-member display settings.

    ``calendar_theme`` is intentionally separate from the system theme: a member
    can run the app in dark mode while their calendar stays light (or themed for
    a child). Values are free-form strings so new themes need no migration.
    """

    calendar_theme: str | None = Field(default=None, max_length=32)
    calendar_stickers: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class MemberPreferencesPatch(BaseModel):
    calendar_theme: str | None = Field(default=None, max_length=32)
    calendar_stickers: list[str] | None = None
    extra: dict[str, Any] | None = None
