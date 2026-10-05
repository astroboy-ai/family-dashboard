"""ARQ worker: consumes the ``jobs_outbox`` table.

The outbox pattern keeps enqueueing transactional with the write that produced
the job — ``app/services/notes.py`` and ``app/services/media.py`` insert a row in
the same transaction as the note/asset, so a job can never be lost or dispatched
for a rolled-back write.

Blueprints §9.2 status machine::

    pending → running → complete
                      ↘ failed (attempts < 3, backoff 30s / 5m / 30m)
                      ↘ dead   (attempts >= 3)

Every handler must be idempotent — a job may be retried after a crash between
the work and the status update.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import session_factory
from app.models import Household, JobOutbox, MediaAsset, NoteBlock
from app.services.ai_settings import resolve_ai_settings
from app.services.embedding_jobs import collect_note_chunks
from app.services.embeddings import EmbeddingClient, EmbeddingError
from app.services.notes import apply_block_search_tokens
from app.services.vision import VisionClient, VisionError

logger = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (30, 300, 1800)
POLL_INTERVAL_SECONDS = 5.0
BATCH_SIZE = 10


async def claim_jobs(session: AsyncSession, *, limit: int = BATCH_SIZE) -> list[JobOutbox]:
    """Atomically move up to *limit* due jobs from pending to running.

    ``FOR UPDATE SKIP LOCKED`` lets several workers run without handing the same
    job to two of them.
    """

    now = datetime.now(UTC)
    statement = (
        select(JobOutbox.id)
        .where(
            JobOutbox.status == "pending",
            JobOutbox.available_at <= now,
        )
        .order_by(JobOutbox.available_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    ids = list((await session.execute(statement)).scalars().all())
    if not ids:
        return []

    await session.execute(
        update(JobOutbox)
        .where(JobOutbox.id.in_(ids))
        .values(status="running", attempts=JobOutbox.attempts + 1)
    )
    await session.commit()

    rows = await session.execute(select(JobOutbox).where(JobOutbox.id.in_(ids)))
    return list(rows.scalars().all())


async def finish_job(session: AsyncSession, job: JobOutbox) -> None:
    await session.execute(
        update(JobOutbox)
        .where(JobOutbox.id == job.id)
        .values(status="complete", processed_at=datetime.now(UTC))
    )
    await session.commit()


async def fail_job(session: AsyncSession, job: JobOutbox, error: str) -> None:
    """Retry with backoff, or park the job as ``dead`` after MAX_ATTEMPTS."""

    # Capture values before any rollback expires the ORM instance.
    job_id = job.id
    job_topic = job.topic
    job_attempts = job.attempts
    job_payload = dict(job.payload or {})

    if job_attempts >= MAX_ATTEMPTS:
        status = "dead"
        available_at = datetime.now(UTC)
        logger.error("job_dead", job_id=str(job_id), topic=job_topic, error=error)
    else:
        status = "pending"
        delay = BACKOFF_SECONDS[min(job_attempts, len(BACKOFF_SECONDS) - 1)]
        available_at = datetime.now(UTC) + timedelta(seconds=delay)
        logger.warning("job_retry", job_id=str(job_id), topic=job_topic, delay=delay, error=error)

    job_payload["last_error"] = error[:1000]

    await session.execute(
        update(JobOutbox)
        .where(JobOutbox.id == job_id)
        .values(status=status, available_at=available_at, payload=job_payload)
    )
    await session.commit()


async def handle_embed_note(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Embed a note (and its blocks) and write ``embeddings`` rows.

    Idempotent: rows whose ``content_hash`` already matches are skipped, so a
    retry after a partial write does not duplicate work or spend API calls.
    """

    from app.models import Embedding, Household, Note

    note_id = payload.get("note_id")
    if not note_id:
        raise ValueError("embed.note job requires note_id")

    note = (
        await session.execute(select(Note).where(Note.id == uuid.UUID(str(note_id))))
    ).scalar_one_or_none()
    if note is None:
        logger.info("embed_note_skipped_missing", note_id=note_id)
        return

    household = (
        await session.execute(select(Household).where(Household.id == note.household_id))
    ).scalar_one_or_none()
    settings = resolve_ai_settings(household.settings if household else None)

    if not settings.enabled:
        logger.info("embed_note_skipped_disabled", note_id=note_id)
        return

    chunks = await collect_note_chunks(session, note)
    if not chunks:
        logger.info("embed_note_no_content", note_id=note_id)
        return

    client = EmbeddingClient(settings)
    written = 0

    for start in range(0, len(chunks), settings.embedding_batch_size):
        batch = chunks[start : start + settings.embedding_batch_size]

        # Skip anything already embedded with this model and unchanged content.
        hashes = {chunk.content_hash for chunk in batch}
        existing = set(
            (
                await session.execute(
                    select(Embedding.content_hash).where(
                        Embedding.owner_type.in_(["note", "block"]),
                        Embedding.owner_id.in_([chunk.owner_id for chunk in batch]),
                        Embedding.model == settings.embedding_model,
                        Embedding.content_hash.in_(hashes),
                    )
                )
            )
            .scalars()
            .all()
        )

        pending = [chunk for chunk in batch if chunk.content_hash not in existing]
        if not pending:
            continue

        try:
            result = await client.embed([chunk.content for chunk in pending])
        except EmbeddingError as error:
            raise RuntimeError(f"embedding failed for note {note_id}: {error}") from error

        for chunk, vector in zip(pending, result.vectors, strict=True):
            await session.execute(
                delete(Embedding).where(
                    Embedding.owner_type == chunk.owner_type,
                    Embedding.owner_id == chunk.owner_id,
                    Embedding.chunk_index == chunk.chunk_index,
                    Embedding.model == settings.embedding_model,
                )
            )
            session.add(
                Embedding(
                    household_id=note.household_id,
                    owner_type=chunk.owner_type,
                    owner_id=chunk.owner_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    model=settings.embedding_model,
                    dim=result.dim,
                    is_active=True,
                    embedding=vector,
                )
            )
            written += 1

        await session.commit()

    logger.info("embed_note_done", note_id=note_id, written=written)


async def handle_media_enrich(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Describe an uploaded image with the vision model (``media.enrich``).

    Idempotent: skips an asset whose description is already stored, so a retry
    after a crash costs nothing. The description is written to the asset meta and
    mirrored onto every note block that references the asset, then the block's
    search tokens are rebuilt so the text becomes searchable.
    """

    raw_id = payload.get("asset_id")
    if not raw_id:
        raise ValueError("media.enrich job requires asset_id")
    try:
        asset_id = uuid.UUID(str(raw_id))
    except ValueError as error:
        raise ValueError(f"media.enrich job has an invalid asset_id: {raw_id!r}") from error

    asset = await session.get(MediaAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        logger.info("media_enrich_skipped_missing", asset_id=str(asset_id))
        return
    if asset.kind != "image":
        logger.info("media_enrich_skipped_not_image", asset_id=str(asset_id), kind=asset.kind)
        return
    if (asset.meta or {}).get("ai_description"):
        logger.info("media_enrich_skipped_done", asset_id=str(asset_id))
        return

    household = (
        await session.execute(select(Household).where(Household.id == asset.household_id))
    ).scalar_one_or_none()
    settings = resolve_ai_settings(household.settings if household else None)
    if not settings.enabled:
        logger.info("media_enrich_skipped_disabled", asset_id=str(asset_id))
        return

    from app.core.config import get_settings as _get_settings
    from app.core.storage import S3CompatibleStorage

    app_settings = _get_settings()
    storage = S3CompatibleStorage(
        internal_endpoint=app_settings.s3_endpoint,
        public_endpoint=app_settings.s3_public_endpoint,
        access_key=app_settings.s3_access_key,
        secret_key=app_settings.s3_secret_key,
        bucket=app_settings.s3_bucket,
    )
    try:
        data = await storage.get(asset.storage_key)
    except Exception as error:  # noqa: BLE001 - storage failure is a retryable job failure
        raise VisionError(f"could not read asset from storage: {error}") from error

    client = VisionClient(settings)
    result = await client.describe(data, mime=asset.mime or "image/jpeg")

    meta = dict(asset.meta or {})
    meta["ai_description"] = result.description
    meta["ai_model"] = result.model
    asset.meta = meta
    asset.enrichment_status = "complete"

    blocks = (
        await session.execute(select(NoteBlock).where(NoteBlock.media_asset_id == asset.id))
    ).scalars().all()
    for block in blocks:
        block.ai_description = result.description
        apply_block_search_tokens(block)

    await session.commit()
    logger.info(
        "media_enrich_done",
        asset_id=str(asset_id),
        model=result.model,
        blocks=len(blocks),
    )


async def handle_tag_propose(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Classify a note with AI: extract metadata + propose tags.

    Idempotent: skips if the note is missing or AI is disabled.
    """

    from app.models import Note
    from app.services.ai_tagging import (
        apply_metadata,
        classify_note,
        create_tag_proposals_from_classification,
    )

    note_id = payload.get("note_id")
    if not note_id:
        raise ValueError("tag.propose job requires note_id")

    note = (
        await session.execute(select(Note).where(Note.id == uuid.UUID(str(note_id))))
    ).scalar_one_or_none()
    if note is None:
        logger.info("tag_propose_skipped_missing", note_id=note_id)
        return

    household = (
        await session.execute(select(Household).where(Household.id == note.household_id))
    ).scalar_one_or_none()
    settings = resolve_ai_settings(household.settings if household else None)
    if not settings.enabled:
        logger.info("tag_propose_skipped_disabled", note_id=note_id)
        return

    result = await classify_note(
        session,
        note,
        actor_household_id=note.household_id,
    )

    # Apply metadata (occurred_at, owner_member_id, location, type)
    metadata = result.get("metadata", {})
    if metadata:
        await apply_metadata(session, note, metadata)

    # Create tag proposals
    tag_inputs = result.get("tags", [])
    if tag_inputs:
        await create_tag_proposals_from_classification(
            session,
            note,
            actor_household_id=note.household_id,
            tag_inputs=tag_inputs,
            model=result.get("model", settings.llm_model),
        )

    await session.commit()
    logger.info(
        "tag_propose_done",
        note_id=note_id,
        metadata_fields=list(metadata.keys()),
        tags_proposed=len(tag_inputs),
    )


HANDLERS = {
    "embed.note": handle_embed_note,
    "media.enrich": handle_media_enrich,
    "tag.propose": handle_tag_propose,
}


async def process_once() -> int:
    """Drain one batch. Returns the number of jobs handled."""

    async with session_factory() as session:
        jobs = await claim_jobs(session)
        for job in jobs:
            handler = HANDLERS.get(job.topic)
            if handler is None:
                await fail_job(session, job, f"no handler registered for topic {job.topic!r}")
                continue
            try:
                await handler(session, job.payload or {})
            except Exception as error:  # noqa: BLE001 - the outbox must not die
                await session.rollback()
                await fail_job(session, job, f"{type(error).__name__}: {error}")
            else:
                # Re-query the job: the handler committed, which expires the
                # instance. Reading job.id off the stale object would trigger a
                # lazy load — impossible under async SQLAlchemy (MissingGreenlet).
                fresh = (
                    await session.execute(select(JobOutbox).where(JobOutbox.id == job.id))
                ).scalar_one_or_none()
                if fresh is not None:
                    await finish_job(session, fresh)
        return len(jobs)


async def run_forever() -> None:
    logger.info("worker_started", topics=sorted(HANDLERS))
    while True:
        try:
            handled = await process_once()
        except Exception as error:  # noqa: BLE001
            import traceback
            logger.error(
                "worker_loop_error",
                error=f"{type(error).__name__}: {error}",
                traceback=traceback.format_exc(),
            )
            handled = 0
        if handled == 0:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
