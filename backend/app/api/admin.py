"""Admin settings: read and update household-scoped configuration.

Model choice, gateway URL, vector dimension and the storage upload origin live in
``households.settings`` so an operator can change them from the UI without a
redeploy (CR-002, CR-005). The API never returns secret values — only whether one
is set.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.core.storage import StorageBackend, get_storage
from app.models import Household
from app.services.ai_settings import SETTINGS_KEY, mask_ai_settings, resolve_ai_settings
from app.services.storage_settings import (
    SETTINGS_KEY as STORAGE_SETTINGS_KEY,
    mask_storage_settings,
    resolve_storage_settings,
)


router = APIRouter(prefix="/admin", tags=["admin"])


class StorageSettingsPatch(BaseModel):
    """Partial update for the storage section. Omitted fields are untouched."""

    public_endpoint: str | None = Field(default=None, max_length=500)
    bucket: str | None = Field(default=None, max_length=200)
    region: str | None = Field(default=None, max_length=64)

    @field_validator("*", mode="before")
    @classmethod
    def empty_to_none(cls, v: object) -> object:
        """Treat blank strings as "not set" so they don't overwrite with empty."""

        if isinstance(v, str) and not v.strip():
            return None
        return v


class AiSettingsPatch(BaseModel):
    """Partial update. Omitted fields are left untouched."""

    enabled: bool | None = None
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    embedding_model: str | None = Field(default=None, max_length=120)
    embedding_dim: int | None = Field(default=None, ge=1, le=8192)
    embedding_batch_size: int | None = Field(default=None, ge=1, le=256)
    llm_model: str | None = Field(default=None, max_length=120)
    vision_model: str | None = Field(default=None, max_length=120)
    # Nested rather than a second body parameter: two Pydantic params would make
    # FastAPI expect an embedded body and break the existing flat client payload.
    storage: StorageSettingsPatch | None = None


def require_admin(actor: Actor) -> None:
    if actor.role != "parent" or "admin.members" not in actor.scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Parent role required")


async def _load_household(session: AsyncSession, actor: Actor) -> Household:
    household = (
        await session.execute(select(Household).where(Household.id == actor.household_id))
    ).scalar_one_or_none()
    if household is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household not found")
    return household


@router.get("/settings")
async def get_admin_settings(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    require_admin(actor)
    household = await _load_household(session, actor)
    resolved = resolve_ai_settings(household.settings)
    return {
        "ai": mask_ai_settings(resolved),
        "storage": mask_storage_settings(resolve_storage_settings(household.settings)),
        "household": {
            "name": household.name,
            "timezone": household.timezone,
            "locale": household.locale,
            "week_starts_on": household.week_starts_on,
        },
    }


@router.patch("/settings")
async def patch_admin_settings(
    payload: AiSettingsPatch,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Merge the given AI and storage settings into ``households.settings``.

    Changing ``embedding_model`` or ``embedding_dim`` leaves existing vectors in
    place but marks them inactive: search only compares vectors from the active
    generation, so stale rows are ignored until a re-embed runs.
    """

    require_admin(actor)
    household = await _load_household(session, actor)

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    # Serialized explicitly: exclude_none=True at the top level would drop
    # storage=None, making it impossible to clear an override back to the env
    # default.
    storage_field = payload.storage
    storage_changes = (
        storage_field.model_dump(exclude_unset=True, exclude_none=False)
        if storage_field is not None
        else {}
    )
    changes.pop("storage", None)

    if not changes and not storage_changes:
        return {
            "ai": mask_ai_settings(resolve_ai_settings(household.settings)),
            "storage": mask_storage_settings(resolve_storage_settings(household.settings)),
            "changed": [],
        }

    settings = dict(household.settings or {})

    previous_model = None
    previous_dim = None
    if changes:
        current = settings.get(SETTINGS_KEY)
        if not isinstance(current, dict):
            current = {}
        previous_model = current.get("embedding_model")
        previous_dim = current.get("embedding_dim")
        current.update(changes)
        settings[SETTINGS_KEY] = current

    if storage_changes:
        storage_current = settings.get(STORAGE_SETTINGS_KEY)
        if not isinstance(storage_current, dict):
            storage_current = {}
        storage_current.update(storage_changes)
        settings[STORAGE_SETTINGS_KEY] = storage_current

    # Reassign (rather than mutate) so SQLAlchemy notices the JSONB change.
    household.settings = settings
    # Force SQLAlchemy to detect the JSONB change — assigning a new dict does
    # not always trigger an UPDATE on its own.
    flag_modified(household, "settings")
    await session.commit()

    model_changed = (
        ("embedding_model" in changes and changes["embedding_model"] != previous_model)
        or ("embedding_dim" in changes and changes["embedding_dim"] != previous_dim)
    )

    response: dict[str, Any] = {
        "ai": mask_ai_settings(resolve_ai_settings(household.settings)),
        "storage": mask_storage_settings(resolve_storage_settings(household.settings)),
        "changed": sorted([*changes, *storage_changes]),
    }
    if model_changed:
        response["reembed_required"] = True
        response["reembed_hint"] = (
            "Embedding model or dimension changed. Existing vectors are inactive until "
            "POST /admin/reembed completes."
        )
    return response


@router.post("/storage/test")
async def test_storage_settings(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> dict[str, Any]:
    """Check the resolved upload origin actually works, before relying on it.

    Two things are verified, because they fail differently:

    1. the backend can sign a URL against the configured public origin;
    2. that URL is plausibly reachable from a browser — a loopback host signs
       fine but always fails in a real browser, which is the exact bug that
       produced "failed to fetch" on upload.

    The returned ``upload_url`` is what the admin page PUTs a tiny probe file to,
    so the check also exercises the tunnel end to end.
    """

    require_admin(actor)
    household = await _load_household(session, actor)
    resolved = resolve_storage_settings(household.settings)

    result: dict[str, Any] = {
        "public_endpoint": resolved.public_endpoint,
        "bucket": resolved.bucket,
        "browser_reachable": resolved.browser_reachable,
        "upload_url": None,
        "probe_key": None,
        "warnings": [],
    }

    if not resolved.browser_reachable:
        result["warnings"].append(
            "The public endpoint is a loopback address, which points at the visitor's "
            "own machine. Uploads will fall back to the relay endpoint until a public "
            "hostname is set."
        )

    try:
        key = f"_probe/{uuid.uuid4()}.txt"
        signing_storage = (
            storage.with_public_endpoint(resolved.public_endpoint, resolved.bucket)
            if hasattr(storage, "with_public_endpoint")
            else storage
        )
        result["upload_url"] = await signing_storage.presign_put(
            key, expires=timedelta(minutes=5)
        )
        result["probe_key"] = key
    except Exception as error:  # noqa: BLE001 - report, never raise, on a diagnostic
        result["warnings"].append(f"Could not sign an upload URL: {type(error).__name__}: {error}")

    # The internal path must keep working regardless of the public origin.
    try:
        await storage.check()
        result["internal_ok"] = True
    except Exception as error:  # noqa: BLE001
        result["internal_ok"] = False
        result["warnings"].append(f"Internal storage unreachable: {type(error).__name__}: {error}")

    result["ok"] = result["internal_ok"] and result["upload_url"] is not None
    return result


@router.post("/reembed")
async def trigger_reembed(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Queue a re-embed of every note in the household.

    Marks current vectors inactive first, so search never mixes generations
    while the rebuild runs.
    """

    require_admin(actor)

    from app.models import Embedding, JobOutbox, Note

    await session.execute(
        Embedding.__table__.update()
        .where(
            Embedding.household_id == actor.household_id,
            Embedding.is_active.is_(True),
        )
        .values(is_active=False)
    )

    note_ids = list(
        (
            await session.execute(
                select(Note.id).where(
                    Note.household_id == actor.household_id,
                    Note.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    for note_id in note_ids:
        session.add(
            JobOutbox(
                id=uuid.uuid4(),
                topic="embed.note",
                payload={"note_id": str(note_id)},
            )
        )

    await session.commit()
    return {"queued": len(note_ids)}
