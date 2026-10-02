"""AI / embedding configuration resolved from household settings.

Model choice, gateway URL, API key and vector dimension live in
``households.settings["ai"]`` rather than in the process environment, so an
operator can switch embedding models from the admin page without a redeploy
(see CR-002). The environment only carries bootstrap values.

Precedence: household setting → environment default.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings

SETTINGS_KEY = "ai"

# Household override keys (stored under households.settings["ai"]).
DEFAULTS: dict[str, object] = {
    "enabled": True,
    "base_url": "http://litellm_proxy:4000",
    "api_key": "",
    "embedding_model": "gemini/text-embedding-004",
    "embedding_dim": 768,
    "embedding_batch_size": 16,
    "llm_model": "gemini/gemini-3.5-flash",
    "vision_model": "",
}

# Environment fallbacks, keyed by the Settings attribute that holds them.
ENV_FALLBACKS: dict[str, str] = {
    "base_url": "llm_base_url",
    "api_key": "llm_api_key",
    "embedding_model": "embedding_model",
    "embedding_dim": "embedding_dim",
}

# Fields whose values must never be echoed back through the admin API.
SECRET_FIELDS = frozenset({"api_key"})


@dataclass(frozen=True)
class AiSettings:
    enabled: bool
    base_url: str
    api_key: str
    embedding_model: str
    embedding_dim: int
    embedding_batch_size: int
    llm_model: str
    vision_model: str


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def resolve_ai_settings(household_settings: dict | None) -> AiSettings:
    """Merge household overrides over environment defaults."""

    overrides = (household_settings or {}).get(SETTINGS_KEY)
    if not isinstance(overrides, dict):
        overrides = {}

    env = get_settings()

    def pick(name: str) -> object:
        value = overrides.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            env_attr = ENV_FALLBACKS.get(name)
            if env_attr:
                return getattr(env, env_attr, DEFAULTS[name])
            return DEFAULTS[name]
        return value

    return AiSettings(
        enabled=_coerce_bool(pick("enabled"), bool(DEFAULTS["enabled"])),
        base_url=str(pick("base_url") or DEFAULTS["base_url"]),
        api_key=str(overrides.get("api_key") or getattr(env, "llm_api_key", "") or ""),
        embedding_model=str(pick("embedding_model") or DEFAULTS["embedding_model"]),
        embedding_dim=_coerce_int(pick("embedding_dim"), int(DEFAULTS["embedding_dim"])),
        embedding_batch_size=max(1, _coerce_int(pick("embedding_batch_size"), int(DEFAULTS["embedding_batch_size"]))),
        llm_model=str(pick("llm_model") or DEFAULTS["llm_model"]),
        vision_model=str(pick("vision_model") or DEFAULTS["vision_model"]),
    )


def mask_ai_settings(settings: AiSettings) -> dict[str, object]:
    """Serializable view for the admin API — secrets replaced by a boolean."""

    return {
        "enabled": settings.enabled,
        "base_url": settings.base_url,
        "api_key_set": bool(settings.api_key),
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "embedding_batch_size": settings.embedding_batch_size,
        "llm_model": settings.llm_model,
        "vision_model": settings.vision_model,
    }
