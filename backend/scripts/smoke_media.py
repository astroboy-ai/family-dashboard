"""Real smoke test for media upload -> download -> enrich queue (CR-003).

Uses LocalDiskStorage-free path: uploads through the service layer against the
same S3 backend the app uses, then reads it back via storage.get() and queues a
media.enrich job.
"""

import asyncio
import hashlib
import io
import uuid

from sqlalchemy import select

from app.api.deps import Actor
from app.core.config import get_settings
from app.core.db import session_factory
from app.core.storage import S3CompatibleStorage
from app.models import FamilyMember, JobOutbox, MediaAsset
from app.schemas.media import MediaPresignRequest
from app.services import media as media_service


def storage_from_settings() -> S3CompatibleStorage:
    s = get_settings()
    return S3CompatibleStorage(
        internal_endpoint=s.s3_endpoint,
        public_endpoint=s.s3_public_endpoint,
        access_key=s.s3_access_key,
        secret_key=s.s3_secret_key,
        bucket=s.s3_bucket,
    )


# 1x1 transparent PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


async def main() -> None:
    storage = storage_from_settings()
    await storage.check()
    print("storage reachable")

    async with session_factory() as session:
        member = (await session.execute(select(FamilyMember).limit(1))).scalar_one()
        actor = Actor(
            member_id=member.id,
            household_id=member.household_id,
            role=member.role,
            display_name=member.display_name or "smoke",
            timezone="Asia/Hong_Kong",
            locale="zh-HK",
            scopes=frozenset({"admin.members", "notes.write", "notes.read"}),
        )

        sha = hashlib.sha256(PNG).hexdigest()
        presigned = await media_service.create_upload(
            session=session,
            storage=storage,
            actor=actor,
            payload=MediaPresignRequest(
                filename="smoke.png", mime="image/png", size=len(PNG), sha256=sha
            ),
        )
        asset_id = presigned["asset_id"]
        print(f"presign OK: asset_id={asset_id} dedup={presigned.get('deduplicated')}")

        # Upload directly through the storage backend (same path the browser PUT takes).
        asset = (await session.execute(select(MediaAsset).where(MediaAsset.id == asset_id))).scalar_one()
        await storage.put(asset.storage_key, io.BytesIO(PNG), size=len(PNG), content_type="image/png")
        print("put OK")

        completed = await media_service.complete_upload(
            session=session, storage=storage, actor=actor, asset_id=asset_id
        )
        print(f"complete OK: {completed}")

        # download path used by GET /api/media/{id}/download
        loaded = await media_service.load_asset_for_download(
            session=session, actor=actor, asset_id=asset_id
        )
        data = await storage.get(loaded.storage_key)
        assert data == PNG, "downloaded bytes differ from uploaded bytes"
        print(f"download OK: {len(data)} bytes, mime={loaded.mime}")

        # enrich queue
        queued = await media_service.enqueue_enrichment(
            session=session, actor=actor, asset_id=asset_id
        )
        print(f"enrich queue: {queued}")
        queued_again = await media_service.enqueue_enrichment(
            session=session, actor=actor, asset_id=asset_id
        )
        assert queued_again.get("queued") is False, "enrich was not idempotent"
        print("enrich idempotency OK")

        jobs = (
            await session.execute(
                select(JobOutbox).where(JobOutbox.topic == "media.enrich")
            )
        ).scalars().all()
        print(f"media.enrich jobs in outbox: {len(jobs)}")

        # cleanup
        for job in jobs:
            if (job.payload or {}).get("asset_id") == str(asset_id):
                await session.delete(job)
        await session.delete(loaded)
        await session.commit()
        await storage.delete(asset.storage_key)
        print("cleanup OK")
        print("MEDIA SMOKE TESTS PASSED")


asyncio.run(main())
