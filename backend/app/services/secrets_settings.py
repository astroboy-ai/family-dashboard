"""Secrets (Infisical) configuration resolved from household settings.

Infisical is the default secrets store for this deployment. Two URLs matter and
they are not the same thing:

* ``internal_url`` — the Docker-network address the *backend* uses to reach
  Infisical (e.g. ``http://172.18.0.26:8080``). Never exposed to a browser.
* ``public_url`` — the HTTPS hostname a *browser* can load, used for the
  embedded console on the vault page.

Both live in ``households.settings["secrets"]`` so an operator can repoint them
from the admin page without a redeploy.

Precedence: household setting → environment default.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings

SETTINGS_KEY = "secrets"

DEFAULTS: dict[str, str] = {
    # Docker-network address of the Infisical backend container.
    "internal_url": "http://172.18.0.26:8080",
    # Browser-facing hostname for the embedded console.
    "public_url": "https://pizza.pointdowncreative.com",
    # Infisical project that holds this deployment's secrets.
    "project_id": "da76df22-6491-410f-9f81-66879159a79a",
    "project_slug": "logeebox",
    "environment": "prod",
}

ENV_FALLBACKS: dict[str, str] = {
    "internal_url": "infisical_internal_url",
    "public_url": "infisical_public_url",
    "project_id": "infisical_project_id",
    "project_slug": "infisical_project_slug",
    "environment": "infisical_environment",
}


@dataclass(frozen=True)
class SecretsSettings:
    internal_url: str
    public_url: str
    project_id: str
    project_slug: str
    environment: str
    # True when the public URL is an HTTPS host a browser can actually load.
    browser_reachable: bool


def _coerce_str(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _env_default(field: str) -> str:
    """Environment fallback, so a deployment can override without a DB row."""

    fallback = ENV_FALLBACKS.get(field)
    if fallback:
        value = getattr(get_settings(), fallback, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return DEFAULTS[field]


def _is_browser_reachable(url: str) -> bool:
    """A browser can load it only over https, and not on a loopback host."""

    lowered = url.lower()
    if not lowered.startswith("https://"):
        return False
    host = lowered[len("https://") :].split("/")[0].split(":")[0]
    return host not in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def resolve_secrets_settings(household_settings: dict | None) -> SecretsSettings:
    """Merge household secrets overrides over environment defaults."""

    overrides = (household_settings or {}).get(SETTINGS_KEY)
    if not isinstance(overrides, dict):
        overrides = {}

    resolved = {
        field: _coerce_str(overrides.get(field), _env_default(field)) for field in DEFAULTS
    }

    return SecretsSettings(
        internal_url=resolved["internal_url"],
        public_url=resolved["public_url"],
        project_id=resolved["project_id"],
        project_slug=resolved["project_slug"],
        environment=resolved["environment"],
        browser_reachable=_is_browser_reachable(resolved["public_url"]),
    )


def mask_secrets_settings(settings: SecretsSettings) -> dict[str, object]:
    """Serializable form for the admin API.

    No secret *values* pass through here — only where the store lives. Client
    IDs and secrets for machine identities stay in the credentials file on the
    server and are never sent to a browser.
    """

    return {
        "internal_url": settings.internal_url,
        "public_url": settings.public_url,
        "project_id": settings.project_id,
        "project_slug": settings.project_slug,
        "environment": settings.environment,
        "browser_reachable": settings.browser_reachable,
    }
