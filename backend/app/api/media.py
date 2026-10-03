import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.core.storage import StorageBackend, get_storage
from app.schemas.media import MediaCompleteResponse, MediaPresignRequest, MediaPresignResponse
from app.services.media import complete_upload, create_upload, enqueue_enrichment, load_asset_for_download


router = APIRouter(prefix="/media", tags=["media"])


@router.post("/presign", response_model=MediaPresignResponse, status_code=201)
async def presign_media(
    payload: MediaPresignRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> dict[str, object]:
    return await create_upload(session=session, storage=storage, actor=actor, payload=payload)


@router.post("/{asset_id}/complete", response_model=MediaCompleteResponse)
async def complete_media_upload(
    asset_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> dict[str, object]:
    return await complete_upload(session=session, storage=storage, actor=actor, asset_id=asset_id)


@router.get("/{asset_id}/download")
async def download_media(
    asset_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> Response:
    asset = await load_asset_for_download(session=session, actor=actor, asset_id=asset_id)
    data = await storage.get(asset.storage_key)
    filename = asset.storage_key.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type=asset.mime or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/{asset_id}/enrich")
async def enrich_media(
    asset_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    return await enqueue_enrichment(session=session, actor=actor, asset_id=asset_id)
