"""Vault API — list and manage password blocks across all notes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.models import Note, NoteBlock
from app.services.notes import _serialize_block

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
