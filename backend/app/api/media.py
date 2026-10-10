import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.core.storage import StorageBackend, get_storage
from app.schemas.media import MediaCompleteResponse, MediaPresignRequest, MediaPresignResponse
from app.services.media import (
    MAX_RELAY_BYTES,
    complete_upload,
    create_upload,
    enqueue_enrichment,
    load_asset_for_download,
    store_upload_bytes,
)


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


@router.put("/{asset_id}/content")
async def upload_media_content(
    asset_id: uuid.UUID,
    request: Request,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> dict[str, object]:
    """Relay upload: store the raw request body as the asset's object.

    Fallback for when the browser cannot reach the presigned S3 URL (no public
    endpoint configured, or mixed-content blocking). The declared length is
    checked against the asset record before the body is buffered.
    """

    declared = request.headers.get("content-length")
    if declared is None:
        raise HTTPException(
            status_code=status.HTTP_411_LENGTH_REQUIRED,
            detail="Content-Length is required",
        )
    try:
        size = int(declared)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Length"
        ) from error

    if size > MAX_RELAY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large for the relay endpoint; use the presigned upload",
        )

    body = await request.body()
    return await store_upload_bytes(
        session=session, storage=storage, actor=actor, asset_id=asset_id, data=body
    )


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


@router.get("/{asset_id}/thumbnail")
async def download_media_thumbnail(
    asset_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> Response:
    asset = await load_asset_for_download(session=session, actor=actor, asset_id=asset_id)
    if not asset.thumb_key:
        raise HTTPException(status_code=404, detail="No thumbnail for this asset")
    data = await storage.get(asset.thumb_key)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Content-Disposition": 'inline; filename="thumb.jpg"'},
    )


@router.get("/{asset_id}/exif")
async def get_media_exif(
    asset_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> dict[str, Any]:
    asset = await load_asset_for_download(session=session, actor=actor, asset_id=asset_id)
    data = await storage.get(asset.storage_key)
    from app.services.imaging import read_exif

    exif = read_exif(data)
    return {"exif": exif or {}}


@router.post("/{asset_id}/enrich")
async def enrich_media(
    asset_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    return await enqueue_enrichment(session=session, actor=actor, asset_id=asset_id)
