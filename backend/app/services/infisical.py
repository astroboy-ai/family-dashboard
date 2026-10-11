"""Infisical API client — read and write secrets for the vault page.

The vault page is a thin UI over Infisical, not a second secret store: every
list, reveal, save and delete here is an Infisical API call. That keeps one
source of truth and means the console, the CLI and this page can never disagree.

Authentication uses the ``familyos-site`` machine identity (Universal Auth), so
the credentials in ``agent-credentials.md`` are the only thing that needs to
change when the token is rotated — nothing is hard-coded here.

Two deliberate limits:

* Only the identity's own project and environment are reachable, and only the
  paths this module is given. There is no "call any Infisical endpoint" escape
  hatch, so a bug in a route cannot turn into arbitrary access.
* Secret *values* are returned only by the explicit single-secret read used for
  reveal. Listing never carries a value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Infisical Universal Auth: exchange the machine identity's client id/secret for
# a short-lived access token. Tokens are cached in-process until they near
# expiry, so a page load does not perform two round trips.
LOGIN_PATH = "/api/v1/auth/universal-auth/login"
SECRETS_PATH = "/api/v3/secrets/raw"
FOLDERS_PATH = "/api/v1/folders"

# Refresh a little before the real expiry so an in-flight request never uses a
# token that expires mid-call.
_TOKEN_SAFETY_MARGIN_SECONDS = 30

# Secrets are small. Cap the body so a runaway paste cannot be used to push
# megabytes into the secret store through this page.
MAX_SECRET_VALUE_BYTES = 64 * 1024


class InfisicalError(RuntimeError):
    """A call to Infisical failed. The message is safe to show an operator."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SecretSummary:
    """A secret without its value — what a list view may show."""

    key: str
    path: str
    comment: str
    updated_at: str


@dataclass
class _Token:
    value: str
    expires_at: float


_token_cache: _Token | None = None


def _client_config() -> tuple[str, str, str]:
    """Return (base_url, client_id, client_secret) for the machine identity."""

    settings = get_settings()
    base_url = (getattr(settings, "infisical_internal_url", "") or "").rstrip("/")
    client_id = getattr(settings, "infisical_client_id", "") or ""
    client_secret = getattr(settings, "infisical_client_secret", "") or ""
    if not base_url or not client_id or not client_secret:
        raise InfisicalError(
            "Infisical is not configured: set INFISICAL_INTERNAL_URL, "
            "INFISICAL_CLIENT_ID and INFISICAL_CLIENT_SECRET."
        )
    return base_url, client_id, client_secret


async def _access_token() -> str:
    """Return a cached Universal Auth token, logging in when needed."""

    import time

    global _token_cache
    if _token_cache is not None and _token_cache.expires_at - _TOKEN_SAFETY_MARGIN_SECONDS > time.time():
        return _token_cache.value

    base_url, client_id, client_secret = _client_config()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{base_url}{LOGIN_PATH}",
            json={"clientId": client_id, "clientSecret": client_secret},
        )
    if response.status_code != 200:
        raise InfisicalError(
            f"Infisical login failed (HTTP {response.status_code}). Check the machine identity credentials.",
            response.status_code,
        )
    payload = response.json()
    token = payload.get("accessToken")
    if not token:
        raise InfisicalError("Infisical login returned no access token.")

    # `expiresIn` is seconds; fall back to a short window rather than caching a
    # token whose lifetime we do not know.
    expires_in = payload.get("expiresIn")
    ttl = float(expires_in) if isinstance(expires_in, (int, float)) and expires_in > 0 else 300.0
    _token_cache = _Token(value=token, expires_at=time.time() + ttl)
    return token


def _target() -> tuple[str, str, str]:
    """Return (base_url, project_id, environment) — the only place we ever write."""

    settings = get_settings()
    base_url, _, _ = _client_config()
    project_id = getattr(settings, "infisical_project_id", "") or ""
    environment = getattr(settings, "infisical_environment", "") or "prod"
    if not project_id:
        raise InfisicalError("Infisical project is not configured: set INFISICAL_PROJECT_ID.")
    return base_url, project_id, environment


async def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One authenticated Infisical call, with errors turned into InfisicalError."""

    base_url, _, _ = _client_config()
    token = await _access_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.request(
            method,
            f"{base_url}{path}",
            headers=headers,
            json=json_body,
            params=params,
        )
    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            detail = body.get("message") or body.get("error") or ""
        except ValueError:
            detail = response.text[:200]
        # 401 on a cached token means it was revoked or expired early: drop the
        # cache so the next call logs in again instead of failing forever.
        global _token_cache
        if response.status_code == 401:
            _token_cache = None
        raise InfisicalError(
            f"Infisical {method} {path} failed (HTTP {response.status_code}){f': {detail}' if detail else ''}.",
            response.status_code,
        )
    if not response.content:
        return {}
    return response.json()


def _normalise_path(path: str | None) -> str:
    """Folders are absolute and start with a single slash. ``/`` is the root."""

    if not path or not path.strip() or path.strip() == "/":
        return "/"
    cleaned = "/" + path.strip().strip("/")
    if ".." in cleaned.split("/"):
        raise InfisicalError("Invalid folder path.")
    return cleaned


async def list_secrets(path: str = "/") -> list[SecretSummary]:
    """List the secrets in one folder. Never returns values."""

    base_url, project_id, environment = _target()
    folder = _normalise_path(path)
    params = {"workspaceId": project_id, "environment": environment}
    if folder != "/":
        params["secretPath"] = folder
    payload = await _request("GET", SECRETS_PATH, params=params)

    summaries: list[SecretSummary] = []
    for item in payload.get("secrets", []):
        key = item.get("secretKey")
        if not isinstance(key, str) or not key:
            continue
        summaries.append(
            SecretSummary(
                key=key,
                path=item.get("secretPath") or folder,
                comment=item.get("secretComment") or "",
                updated_at=item.get("updatedAt") or "",
            )
        )
    summaries.sort(key=lambda s: s.key.lower())
    return summaries


async def list_folders() -> list[str]:
    """Folder paths in the environment, root first. ``[]`` when none exist."""

    _, project_id, environment = _target()
    payload = await _request(
        "GET",
        FOLDERS_PATH,
        params={"workspaceId": project_id, "environment": environment},
    )
    paths = {"/"}
    for item in payload.get("folders", []):
        name = item.get("name")
        parent = item.get("parentPath")
        if not isinstance(name, str) or not name:
            continue
        if isinstance(parent, str) and parent.strip() and parent.strip() != "/":
            paths.add("/" + parent.strip().strip("/") + "/" + name)
        else:
            paths.add("/" + name)
    return sorted(paths)


async def get_secret(key: str, path: str = "/") -> str:
    """Read one secret's value. Only called for an explicit reveal."""

    _, project_id, environment = _target()
    folder = _normalise_path(path)
    params = {"workspaceId": project_id, "environment": environment}
    if folder != "/":
        params["secretPath"] = folder
    payload = await _request("GET", f"{SECRETS_PATH}/{key}", params=params)
    secret = payload.get("secret") or {}
    value = secret.get("secretValue")
    if not isinstance(value, str):
        raise InfisicalError(f"Secret '{key}' has no value.")
    return value


async def set_secret(
    key: str,
    value: str,
    path: str = "/",
    comment: str = "",
    *,
    create_only: bool = False,
) -> SecretSummary:
    """Create or overwrite one secret.

    Infisical answers 400 when the key already exists, so an update is a second
    call with PATCH rather than a separate code path at the caller.

    ``create_only`` refuses to touch an existing key: the editor's "leave blank
    to keep the current value" promise depends on it, because a blank value sent
    to PATCH would overwrite the secret with an empty string.
    """

    if not key.strip():
        raise InfisicalError("A key is required.")
    if "/" in key or "\\" in key:
        raise InfisicalError("A key cannot contain a slash.")

    if not create_only and len(value.encode("utf-8")) > MAX_SECRET_VALUE_BYTES:
        raise InfisicalError(
            f"Value is too large ({len(value.encode('utf-8'))} bytes); the limit is {MAX_SECRET_VALUE_BYTES}."
        )

    _, project_id, environment = _target()
    folder = _normalise_path(path)
    body: dict[str, Any] = {
        "workspaceId": project_id,
        "environment": environment,
        "secretValue": value,
    }
    if comment.strip():
        body["secretComment"] = comment.strip()
    if folder != "/":
        body["secretPath"] = folder

    if create_only:
        payload = await _request("POST", f"{SECRETS_PATH}/{key}", json_body=body)
        secret = payload.get("secret") or {}
        return SecretSummary(
            key=secret.get("secretKey") or key,
            path=secret.get("secretPath") or folder,
            comment=secret.get("secretComment") or "",
            updated_at=secret.get("updatedAt") or "",
        )

    try:
        payload = await _request("POST", f"{SECRETS_PATH}/{key}", json_body=body)
    except InfisicalError as error:
        # Infisical answers 400 (not 409) when the key already exists, and
        # updates go through PATCH — PUT is not routed at all.
        if error.status_code != 400 or "already exists" not in str(error):
            raise
        payload = await _request("PATCH", f"{SECRETS_PATH}/{key}", json_body=body)

    secret = payload.get("secret") or {}
    return SecretSummary(
        key=secret.get("secretKey") or key,
        path=secret.get("secretPath") or folder,
        comment=secret.get("secretComment") or "",
        updated_at=secret.get("updatedAt") or "",
    )


async def delete_secret(key: str, path: str = "/") -> None:
    """Delete one secret. A missing key is reported, not silently ignored."""

    _, project_id, environment = _target()
    folder = _normalise_path(path)
    body: dict[str, Any] = {"workspaceId": project_id, "environment": environment}
    if folder != "/":
        body["secretPath"] = folder
    await _request("DELETE", f"{SECRETS_PATH}/{key}", json_body=body)
