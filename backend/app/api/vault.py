"""Vault API — list and manage password blocks across all notes.

Also the write path into Infisical: the vault page's secret editor is a thin UI
over the household secret store, so these routes call ``services.infisical``
rather than keeping a second copy of anything.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.models import Household, Note, NoteBlock
from app.services.infisical import (
    InfisicalError,
    delete_secret,
    get_secret,
    list_folders,
    list_secrets,
    set_secret,
)
from app.services.notes import _serialize_block
from app.services.secrets_settings import resolve_secrets_settings

router = APIRouter(prefix="/vault", tags=["vault"])


class PasswordBlockResponse(BaseModel):
    id: uuid.UUID
    note_id: uuid.UUID
    note_title: str | None
    label: str | None
    encrypted: bool
    masked: bool
    created_at: str
    updated_at: str


class PasswordBlockDetailResponse(PasswordBlockResponse):
    value: str | None = None


@router.get("/console")
async def get_secrets_console(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    """Where to load the embedded secrets console from.

    Readable by any signed-in member — unlike ``/admin/settings``, which is
    parent-only — because the vault page is visible to the whole household.
    Only the location of the store is returned, never a secret value.
    """

    household = (
        await session.execute(select(Household).where(Household.id == actor.household_id))
    ).scalar_one_or_none()
    resolved = resolve_secrets_settings(household.settings if household else None)
    return {
        "public_url": resolved.public_url,
        "internal_url": resolved.internal_url,
        "project_slug": resolved.project_slug,
        "environment": resolved.environment,
        "browser_reachable": resolved.browser_reachable,
    }


@router.get("/password-blocks", response_model=list[PasswordBlockResponse])
async def list_password_blocks(
    actor: Annotated[Actor, Depends(get_current_actor)] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
):
    """List all password blocks in the household."""

    result = await session.execute(
        select(NoteBlock, Note.title)
        .join(Note, NoteBlock.note_id == Note.id)
        .where(
            Note.household_id == actor.household_id,
            Note.deleted_at.is_(None),
            NoteBlock.type == "password",
        )
        .order_by(NoteBlock.created_at.desc())
    )
    rows = result.all()
    return [
        PasswordBlockResponse(
            id=block.id,
            note_id=block.note_id,
            note_title=title,
            label=str((block.data or {}).get("label") or ""),
            encrypted=(block.data or {}).get("encrypted", False),
            masked=(block.data or {}).get("masked", False),
            created_at=block.created_at.isoformat(),
            updated_at=block.updated_at.isoformat(),
        )
        for block, title in rows
    ]


@router.get("/password-blocks/{block_id}", response_model=PasswordBlockDetailResponse)
async def get_password_block(
    block_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
):
    """Get a single password block, with value if the caller has secrets scope."""

    result = await session.execute(
        select(NoteBlock, Note.title)
        .join(Note, NoteBlock.note_id == Note.id)
        .where(
            NoteBlock.id == block_id,
            Note.household_id == actor.household_id,
            Note.deleted_at.is_(None),
            NoteBlock.type == "password",
        )
    )
    row = result.first()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Password block not found")

    block, title = row
    can_read_secrets = "notes.read.secrets" in actor.scopes
    serialized = _serialize_block(block, can_read_secrets=can_read_secrets)

    return PasswordBlockDetailResponse(
        id=block.id,
        note_id=block.note_id,
        note_title=title,
        label=str((block.data or {}).get("label") or ""),
        encrypted=(block.data or {}).get("encrypted", False),
        masked=(block.data or {}).get("masked", False),
        created_at=block.created_at.isoformat(),
        updated_at=block.updated_at.isoformat(),
        value=serialized.data.get("value") if can_read_secrets else None,
    )


# --- Infisical secrets -------------------------------------------------------
#
# The vault page's secret editor. Every route here is a pass-through to
# services.infisical; nothing is cached or duplicated locally, so the console,
# the CLI and this page always agree.


class SecretSummaryResponse(BaseModel):
    key: str
    path: str
    comment: str
    updated_at: str


class SecretWriteRequest(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    value: str
    path: str = "/"
    comment: str = ""


class SecretValueResponse(BaseModel):
    key: str
    path: str
    value: str


def _require_secrets_scope(actor: Actor) -> None:
    """Guard every secret route.

    Read and write are separate scopes: a member who may see the vault list
    still cannot reveal or change a value without the matching scope.
    """

    if "secrets.read" not in actor.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Secrets scope required",
        )


def _require_secrets_write(actor: Actor) -> None:
    if "secrets.write" not in actor.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Secrets write scope required",
        )


def _infisical_http_error(error: InfisicalError) -> HTTPException:
    """Map an Infisical failure onto a status the page can act on."""

    if error.status_code == 404:
        return HTTPException(status_code=404, detail=str(error))
    if error.status_code in (401, 403):
        # The machine identity is misconfigured, not the caller: say so plainly
        # instead of returning a 403 that looks like a permission problem.
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Secret store rejected the service identity: {error}",
        )
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))


@router.get("/secrets", response_model=list[SecretSummaryResponse])
async def list_vault_secrets(
    actor: Annotated[Actor, Depends(get_current_actor)],
    path: Annotated[str, Query(max_length=500)] = "/",
) -> list[SecretSummaryResponse]:
    """List secrets in one folder. Values are never included."""

    _require_secrets_scope(actor)
    try:
        secrets = await list_secrets(path)
    except InfisicalError as error:
        raise _infisical_http_error(error) from error
    return [
        SecretSummaryResponse(
            key=item.key, path=item.path, comment=item.comment, updated_at=item.updated_at
        )
        for item in secrets
    ]


@router.get("/secrets/folders", response_model=list[str])
async def list_vault_folders(
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[str]:
    """Folder paths available in the environment, root first."""

    _require_secrets_scope(actor)
    try:
        return await list_folders()
    except InfisicalError as error:
        raise _infisical_http_error(error) from error


@router.get("/secrets/value", response_model=SecretValueResponse)
async def reveal_vault_secret(
    actor: Annotated[Actor, Depends(get_current_actor)],
    key: Annotated[str, Query(min_length=1, max_length=200)],
    path: Annotated[str, Query(max_length=500)] = "/",
) -> SecretValueResponse:
    """Read one secret's value. This is the only route that returns a value."""

    _require_secrets_scope(actor)
    try:
        value = await get_secret(key, path)
    except InfisicalError as error:
        raise _infisical_http_error(error) from error
    return SecretValueResponse(key=key, path=path, value=value)


@router.put("/secrets", response_model=SecretSummaryResponse)
async def write_vault_secret(
    payload: SecretWriteRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> SecretSummaryResponse:
    """Create or update one secret."""

    _require_secrets_scope(actor)
    _require_secrets_write(actor)
    try:
        saved = await set_secret(payload.key, payload.value, payload.path, payload.comment)
    except InfisicalError as error:
        raise _infisical_http_error(error) from error
    return SecretSummaryResponse(
        key=saved.key, path=saved.path, comment=saved.comment, updated_at=saved.updated_at
    )


@router.delete("/secrets", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vault_secret(
    actor: Annotated[Actor, Depends(get_current_actor)],
    key: Annotated[str, Query(min_length=1, max_length=200)],
    path: Annotated[str, Query(max_length=500)] = "/",
) -> None:
    """Delete one secret."""

    _require_secrets_scope(actor)
    _require_secrets_write(actor)
    try:
        await delete_secret(key, path)
    except InfisicalError as error:
        raise _infisical_http_error(error) from error
