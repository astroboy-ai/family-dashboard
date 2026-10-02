"""Admin settings: read and update household-scoped configuration.

Model choice, gateway URL and vector dimension live in
``households.settings["ai"]`` so an operator can switch embedding models from
the UI without a redeploy (CR-002). The API never returns secret values — only
whether one is set.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.models import Household
from app.services.ai_settings import SETTINGS_KEY, mask_ai_settings, resolve_ai_settings


router = APIRouter(prefix="/admin", tags=["admin"])


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
    """Merge the given AI settings into ``households.settings['ai']``.

    Changing ``embedding_model`` or ``embedding_dim`` leaves existing vectors in
    place but marks them inactive: search only compares vectors from the active
    generation, so stale rows are ignored until a re-embed runs.
    """

    require_admin(actor)
    household = await _load_household(session, actor)

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return {"ai": mask_ai_settings(resolve_ai_settings(household.settings)), "changed": []}

    settings = dict(household.settings or {})
    current = settings.get(SETTINGS_KEY)
    if not isinstance(current, dict):
        current = {}

    previous_model = current.get("embedding_model")
    previous_dim = current.get("embedding_dim")

    current.update(changes)
    settings[SETTINGS_KEY] = current
    # Reassign (rather than mutate) so SQLAlchemy notices the JSONB change.
    household.settings = settings
    await session.commit()

    model_changed = (
        ("embedding_model" in changes and changes["embedding_model"] != previous_model)
        or ("embedding_dim" in changes and changes["embedding_dim"] != previous_dim)
    )

    response: dict[str, Any] = {
        "ai": mask_ai_settings(resolve_ai_settings(household.settings)),
        "changed": sorted(changes),
    }
    if model_changed:
        response["reembed_required"] = True
        response["reembed_hint"] = (
            "Embedding model or dimension changed. Existing vectors are inactive until "
            "POST /admin/reembed completes."
        )
    return response


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
