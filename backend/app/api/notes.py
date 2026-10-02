import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.schemas.notes import (
    NoteBlockInput,
    NoteBlockPatchRequest,
    NoteBlockResponse,
    NoteCreateRequest,
    NoteListResponse,
    NotePatchRequest,
    NoteResponse,
    NoteReorderRequest,
    NoteTagRequest,
    TagResponse,
    TagProposalDecision,
    TagProposalInput,
    TagProposalResponse,
)
from app.services.notes import (
    add_tag,
    create_block,
    create_note,
    delete_block,
    delete_note,
    get_note,
    list_blocks,
    list_notes,
    list_tags,
    remove_tag,
    reorder_blocks,
    update_block,
    update_note,
)
from app.services.tag_governance import decide_tag_proposal, list_pending_tag_proposals, propose_tags


notes_router = APIRouter(prefix="/notes", tags=["notes"])
blocks_router = APIRouter(prefix="/blocks", tags=["blocks"])
tags_router = APIRouter(prefix="/tags", tags=["tags"])

tag_proposals_router = APIRouter(prefix="/tags/proposals", tags=["tag-proposals"])


@notes_router.get("", response_model=NoteListResponse)
async def get_notes(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    note_type: str | None = Query(default=None, alias="type"),
    tag: str | None = None,
) -> NoteListResponse:
    return await list_notes(
        session=session,
        actor=actor,
        limit=limit,
        offset=offset,
        status=status_filter,
        note_type=note_type,
        tag=tag,
    )


@notes_router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def post_note(
    payload: NoteCreateRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteResponse:
    return await create_note(session=session, actor=actor, payload=payload)


@notes_router.get("/{note_id}", response_model=NoteResponse)
async def get_note_by_id(
    note_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteResponse:
    return await get_note(session=session, actor=actor, note_id=note_id)


@notes_router.patch("/{note_id}", response_model=NoteResponse)
async def patch_note(
    note_id: uuid.UUID,
    payload: NotePatchRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteResponse:
    return await update_note(session=session, actor=actor, note_id=note_id, payload=payload)


@notes_router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_note(
    note_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await delete_note(session=session, actor=actor, note_id=note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@notes_router.get("/{note_id}/blocks", response_model=list[NoteBlockResponse])
async def get_note_blocks(
    note_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[NoteBlockResponse]:
    return await list_blocks(session=session, actor=actor, note_id=note_id)


@notes_router.post(
    "/{note_id}/blocks",
    response_model=NoteBlockResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_note_block(
    note_id: uuid.UUID,
    payload: NoteBlockInput,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteBlockResponse:
    return await create_block(session=session, actor=actor, note_id=note_id, payload=payload)


@notes_router.post("/{note_id}/reorder", response_model=list[NoteBlockResponse])
async def post_note_reorder(
    note_id: uuid.UUID,
    payload: NoteReorderRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[NoteBlockResponse]:
    return await reorder_blocks(
        session=session,
        actor=actor,
        note_id=note_id,
        block_ids=payload.block_ids,
    )


@notes_router.post("/{note_id}/tags", response_model=list[TagResponse])
async def post_note_tag(
    note_id: uuid.UUID,
    payload: NoteTagRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TagResponse]:
    return await add_tag(session=session, actor=actor, note_id=note_id, payload=payload)


@notes_router.delete("/{note_id}/tags/{tag_slug}", response_model=list[TagResponse])
async def delete_note_tag(
    note_id: uuid.UUID,
    tag_slug: str,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TagResponse]:
    return await remove_tag(
        session=session,
        actor=actor,
        note_id=note_id,
        tag_slug=tag_slug,
    )


@blocks_router.patch("/{block_id}", response_model=NoteBlockResponse)
async def patch_block(
    block_id: uuid.UUID,
    payload: NoteBlockPatchRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteBlockResponse:
    return await update_block(session=session, actor=actor, block_id=block_id, payload=payload)


@blocks_router.delete("/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_block(
    block_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await delete_block(session=session, actor=actor, block_id=block_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@tags_router.get("", response_model=list[TagResponse])
async def get_tags(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TagResponse]:
    return await list_tags(session=session, actor=actor)


@notes_router.post("/{note_id}/tag-proposals", response_model=list[TagProposalResponse])
async def create_tag_proposals(
    note_id: uuid.UUID,
    payload: list[TagProposalInput],
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TagProposalResponse]:
    return await propose_tags(session=session, actor=actor, note_id=note_id, candidates=payload)


@tag_proposals_router.get("", response_model=list[TagProposalResponse])
async def get_tag_proposals(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    note_id: uuid.UUID | None = None,
) -> list[TagProposalResponse]:
    return await list_pending_tag_proposals(session=session, actor=actor, note_id=note_id)


@tag_proposals_router.post("/{proposal_id}/decision", response_model=TagProposalResponse)
async def post_tag_proposal_decision(
    proposal_id: uuid.UUID,
    payload: TagProposalDecision,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TagProposalResponse:
    return await decide_tag_proposal(
        session=session,
        actor=actor,
        proposal_id=proposal_id,
        accepted=payload.accepted,
    )