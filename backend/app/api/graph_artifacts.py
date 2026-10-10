"""Archify artifact API — import and manage externally produced Archify files.

An artifact is a self-contained HTML/PNG/SVG/JSON produced outside FamilyOS
(萬事屋 / Kururu) and displayed in the Archify page inside a sandboxed iframe.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.core.storage import StorageBackend, get_storage
from app.services.graph_artifacts import (
    MAX_ARTIFACT_BYTES,
    create_artifact,
    delete_artifact,
    get_artifact,
    list_artifacts,
    update_artifact,
)

router = APIRouter(prefix="/graph/artifacts", tags=["graph-artifacts"])


class ArtifactResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    kind: str
    media_asset_id: uuid.UUID | None
    source: str
    size_bytes: int
    meta: dict
    order_index: int
    created_at: str
    updated_at: str


class ArtifactListResponse(BaseModel):
    items: list[ArtifactResponse]
    total: int


class ArtifactPatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    order_index: int | None = None


def _to_response(artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact.id,
        name=artifact.name,
        description=artifact.description,
        kind=artifact.kind,
        media_asset_id=artifact.media_asset_id,
        source=artifact.source,
        size_bytes=artifact.size_bytes,
        meta=artifact.meta or {},
        order_index=artifact.order_index,
        created_at=artifact.created_at.isoformat(),
        updated_at=artifact.updated_at.isoformat(),
    )


@router.get("", response_model=ArtifactListResponse)
async def get_artifacts(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArtifactListResponse:
    items = await list_artifacts(session=session, actor=actor)
    return ArtifactListResponse(items=[_to_response(a) for a in items], total=len(items))


@router.post("", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def post_artifact(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    kind: Annotated[str | None, Form()] = None,
    source: Annotated[str, Form()] = "manual",
) -> ArtifactResponse:
    """Import an Archify artifact.

    Multipart upload rather than base64 JSON: an interactive Archify HTML can run
    to megabytes, and the MCP transport's 4 MB body cap does not apply here — the
    browser talks to this endpoint directly.
    """

    data = await file.read()
    if len(data) > MAX_ARTIFACT_BYTES:
        from app.core.errors import AppError

        raise AppError(
            f"Artifact exceeds the {MAX_ARTIFACT_BYTES // (1024 * 1024)} MB limit",
            status_code=413,
            error_code="artifact_too_large",
        )

    artifact = await create_artifact(
        session=session,
        storage=storage,
        actor=actor,
        name=name or (file.filename or "Untitled artifact"),
        data=data,
        mime=file.content_type or "application/octet-stream",
        kind=kind,
        description=description,
        source=source,
    )
    return _to_response(artifact)


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def read_artifact(
    artifact_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArtifactResponse:
    artifact = await get_artifact(session=session, actor=actor, artifact_id=artifact_id)
    return _to_response(artifact)


@router.patch("/{artifact_id}", response_model=ArtifactResponse)
async def patch_artifact(
    artifact_id: uuid.UUID,
    payload: ArtifactPatchRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArtifactResponse:
    artifact = await update_artifact(
        session=session,
        actor=actor,
        artifact_id=artifact_id,
        name=payload.name,
        description=payload.description,
        order_index=payload.order_index,
    )
    return _to_response(artifact)


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_artifact(
    artifact_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await delete_artifact(session=session, actor=actor, artifact_id=artifact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
