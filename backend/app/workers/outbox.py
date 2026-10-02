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
from app.models import JobOutbox
from app.services.ai_settings import resolve_ai_settings
from app.services.embedding_jobs import collect_note_chunks
from app.services.embeddings import EmbeddingClient, EmbeddingError

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

    if job.attempts >= MAX_ATTEMPTS:
        status = "dead"
        available_at = datetime.now(UTC)
        logger.error("job_dead", job_id=str(job.id), topic=job.topic, error=error)
    else:
        status = "pending"
        delay = BACKOFF_SECONDS[min(job.attempts, len(BACKOFF_SECONDS) - 1)]
        available_at = datetime.now(UTC) + timedelta(seconds=delay)
        logger.warning("job_retry", job_id=str(job.id), topic=job.topic, delay=delay, error=error)

    payload = dict(job.payload or {})
    payload["last_error"] = error[:1000]

    await session.execute(
        update(JobOutbox)
        .where(JobOutbox.id == job.id)
        .values(status=status, available_at=available_at, payload=payload)
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


HANDLERS = {
    "embed.note": handle_embed_note,
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
                await finish_job(session, job)
        return len(jobs)


async def run_forever() -> None:
    logger.info("worker_started", topics=sorted(HANDLERS))
    while True:
        try:
            handled = await process_once()
        except Exception as error:  # noqa: BLE001
            logger.error("worker_loop_error", error=f"{type(error).__name__}: {error}")
            handled = 0
        if handled == 0:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
