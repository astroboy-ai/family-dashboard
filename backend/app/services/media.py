import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.core.errors import AppError
from app.core.storage import StorageBackend
from app.models import JobOutbox, MediaAsset
from app.schemas.media import MediaPresignRequest

# Relay uploads buffer the whole body in memory, so they are capped well below
# what a presigned direct-to-S3 PUT can carry.
MAX_RELAY_BYTES = 64 * 1024 * 1024


def _media_kind(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    return "file"


def _storage_key(household_id: uuid.UUID, asset_id: uuid.UUID, filename: str) -> str:
    suffix = Path(Path(filename).name).suffix.lower()
    if not suffix or len(suffix) > 12 or not suffix[1:].isalnum():
        suffix = ".bin"
    now = datetime.now(UTC)
    return f"{household_id}/media/{now:%Y}/{now:%m}/{asset_id}/original{suffix}"


async def create_upload(
    *,
    session: AsyncSession,
    storage: StorageBackend,
    actor: Actor,
    payload: MediaPresignRequest,
) -> dict[str, object]:
    existing_result = await session.execute(
        select(MediaAsset).where(
            MediaAsset.household_id == actor.household_id,
            MediaAsset.sha256 == payload.sha256,
            MediaAsset.deleted_at.is_(None),
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return {
            "asset_id": existing.id,
            "upload_url": None,
            "fields": {},
            "deduplicated": True,
        }

    asset_id = uuid.uuid4()
    key = _storage_key(actor.household_id, asset_id, payload.filename)
    try:
        upload_url = await storage.presign_put(key, expires=timedelta(minutes=10))
    except Exception as error:
        raise AppError(
            "Media storage is unavailable",
            status_code=503,
            error_code="storage_unavailable",
        ) from error

    asset = MediaAsset(
        id=asset_id,
        household_id=actor.household_id,
        kind=_media_kind(payload.mime),
        storage_key=key,
        mime=payload.mime,
        size_bytes=payload.size,
        sha256=payload.sha256,
        uploaded_by=actor.member_id,
        enrichment_status="uploading",
        meta={"original_filename": Path(payload.filename).name},
    )
    session.add(asset)
    await session.commit()
    return {
        "asset_id": asset.id,
        "upload_url": upload_url,
        "fields": {"Content-Type": payload.mime},
        "deduplicated": False,
    }


async def store_upload_bytes(
    *,
    session: AsyncSession,
    storage: StorageBackend,
    actor: Actor,
    asset_id: uuid.UUID,
    data: bytes,
) -> dict[str, object]:
    """Store *data* as the asset's object (the relay upload path).

    Used when the browser cannot reach the presigned S3 URL. The declared size on
    the asset record must match, otherwise the object is discarded and the caller
    gets a 422 — the same guarantee the presigned path gives via ``stat``.
    """

    asset = await _load_asset(session=session, actor=actor, asset_id=asset_id)

    if asset.enrichment_status != "uploading":
        return {
            "asset_id": asset.id,
            "status": asset.enrichment_status,
            "queued": False,
            "already_complete": True,
        }

    if len(data) != asset.size_bytes:
        raise AppError(
            f"Uploaded {len(data)} bytes but {asset.size_bytes} were declared",
            status_code=422,
            error_code="upload_size_mismatch",
        )

    import io

    try:
        await storage.put(
            asset.storage_key,
            io.BytesIO(data),
            size=len(data),
            content_type=asset.mime or "application/octet-stream",
        )
    except Exception as error:  # noqa: BLE001 - surface as a clean 503
        raise AppError(
            "Media storage is unavailable",
            status_code=503,
            error_code="storage_unavailable",
        ) from error

    return await complete_upload(
        session=session, storage=storage, actor=actor, asset_id=asset_id
    )


async def _load_asset(
    *, session: AsyncSession, actor: Actor, asset_id: uuid.UUID
) -> MediaAsset:
    result = await session.execute(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.household_id == actor.household_id,
            MediaAsset.deleted_at.is_(None),
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise AppError("Media asset not found", status_code=404, error_code="not_found")
    return asset


async def complete_upload(
    *,
    session: AsyncSession,
    storage: StorageBackend,
    actor: Actor,
    asset_id: uuid.UUID,
) -> dict[str, object]:
    result = await session.execute(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.household_id == actor.household_id,
            MediaAsset.deleted_at.is_(None),
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise AppError("Media asset not found", status_code=404, error_code="not_found")

    if asset.enrichment_status != "uploading":
        return {
            "asset_id": asset.id,
            "status": asset.enrichment_status,
            "queued": False,
            "already_complete": True,
        }

    try:
        stored = await storage.stat(asset.storage_key)
    except Exception as error:
        raise AppError(
            "Media storage is unavailable",
            status_code=503,
            error_code="storage_unavailable",
        ) from error
    if stored is None:
        raise AppError(
            "Uploaded object was not found",
            status_code=409,
            error_code="upload_missing",
        )
    if stored.size != asset.size_bytes:
        try:
            await storage.delete(asset.storage_key)
        finally:
            raise AppError(
                "Uploaded object size does not match the declared size",
                status_code=422,
                error_code="upload_size_mismatch",
            )

    asset.enrichment_status = "pending"
    session.add(
        JobOutbox(
            topic="media.thumbnail",
            payload={"asset_id": str(asset.id)},
        )
    )
    await session.commit()
    return {"asset_id": asset.id, "status": "pending", "queued": True}

async def load_asset_for_download(
    *,
    session: AsyncSession,
    actor: Actor,
    asset_id: uuid.UUID,
) -> MediaAsset:
    result = await session.execute(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.household_id == actor.household_id,
            MediaAsset.deleted_at.is_(None),
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise AppError("Media asset not found", status_code=404, error_code="not_found")
    return asset


async def enqueue_enrichment(
    *,
    session: AsyncSession,
    actor: Actor,
    asset_id: uuid.UUID,
) -> dict[str, object]:
    """Queue a vision description for an uploaded image (``media.enrich``).

    Idempotent: a second request for an asset already described returns
    ``queued: false`` instead of spending another vision call.
    """

    asset = await load_asset_for_download(session=session, actor=actor, asset_id=asset_id)
    if asset.kind != "image":
        raise AppError(
            "Only image assets can be enriched",
            status_code=422,
            error_code="not_an_image",
        )
    if (asset.meta or {}).get("ai_description"):
        return {"asset_id": asset.id, "queued": False, "already_described": True}

    pending = await session.execute(
        select(JobOutbox.id).where(
            JobOutbox.topic == "media.enrich",
            JobOutbox.status.in_(("pending", "running")),
            JobOutbox.payload["asset_id"].astext == str(asset.id),
        )
    )
    if pending.first() is not None:
        return {"asset_id": asset.id, "queued": False, "already_queued": True}

    session.add(JobOutbox(topic="media.enrich", payload={"asset_id": str(asset.id)}))
    await session.commit()
    return {"asset_id": asset.id, "queued": True}
