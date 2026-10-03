"""Storage configuration resolved from household settings.

The public upload origin is the one storage value that genuinely differs per
deployment and changes when a tunnel hostname is added, so it lives in
``households.settings["storage"]`` and is editable from the admin page — no
redeploy, no ``.env`` edit, no restart.

What stays in the environment: the *internal* endpoint and the S3 credentials.
Those describe how this host talks to its own object store, are never sent to a
browser, and are not something an operator should be pasting into a web form.

Precedence: household setting → environment default.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings

SETTINGS_KEY = "storage"

DEFAULTS: dict[str, object] = {
    "public_endpoint": "http://localhost:8333",
    "bucket": "familyos-media",
    "region": "us-east-1",
}

ENV_FALLBACKS: dict[str, str] = {
    "public_endpoint": "s3_public_endpoint",
    "bucket": "s3_bucket",
}


@dataclass(frozen=True)
class StorageSettings:
    public_endpoint: str
    bucket: str
    region: str
    # True when the resolved endpoint is one a browser can actually reach.
    browser_reachable: bool


def _coerce_str(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def resolve_storage_settings(household_settings: dict | None) -> StorageSettings:
    """Merge household storage overrides over environment defaults."""

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

    public_endpoint = _coerce_str(pick("public_endpoint"), str(DEFAULTS["public_endpoint"]))
    return StorageSettings(
        public_endpoint=public_endpoint,
        bucket=_coerce_str(pick("bucket"), str(DEFAULTS["bucket"])),
        region=_coerce_str(pick("region"), str(DEFAULTS["region"])),
        browser_reachable=_is_browser_reachable(public_endpoint),
    )


def _is_browser_reachable(endpoint: str) -> bool:
    """Whether a browser could plausibly PUT to this origin.

    ``localhost``/``127.0.0.1`` point at the *visitor's* machine, not the server,
    so presigned URLs built from them always fail in a browser. Loopback hosts
    therefore count as unreachable even though the backend itself can use them.
    """

    lowered = endpoint.strip().lower()
    if not lowered.startswith(("http://", "https://")):
        return False
    host = lowered.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
    return host not in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def mask_storage_settings(settings: StorageSettings) -> dict[str, object]:
    """Serializable view for the admin API (no secrets in this section)."""

    return {
        "public_endpoint": settings.public_endpoint,
        "bucket": settings.bucket,
        "region": settings.region,
        "browser_reachable": settings.browser_reachable,
    }
