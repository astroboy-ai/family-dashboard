"""Graph artifact service — imported Archify output files.

An artifact is a self-contained file produced outside FamilyOS: 萬事屋 / Kururu
emit a single interactive HTML with its own JS (motion, search, trace), and the
file is stored as-is and displayed in a sandboxed iframe. Re-rendering it
natively would discard the viewer that gives the output its value.

Why a separate table from ``graph_views``: a view is a configuration FamilyOS
renders itself and can be edited freely; an artifact is opaque content it only
displays. Keeping them apart means importing a file cannot break the native
graph page, and an artifact's bytes are never parsed or executed server-side.

Security note: the stored HTML is *never* executed on the FamilyOS origin. The
viewer puts it in an ``<iframe sandbox>`` with no ``allow-same-origin``, so it
runs in an opaque origin with no cookies, no storage access and no ability to
reach the API as the signed-in member. Uploads are restricted to a small set of
inert-or-self-contained MIME types for the same reason.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.core.errors import AppError
from app.core.storage import StorageBackend
from app.models import GraphArtifact, MediaAsset
from app.services.media import store_agent_upload

# Artifact kinds and the MIME types each accepts. HTML is the interactive case;
# the image/JSON kinds exist for a static export.
KIND_MIME: dict[str, set[str]] = {
    "html": {"text/html", "application/xhtml+xml"},
    "svg": {"image/svg+xml"},
    "png": {"image/png"},
    "json": {"application/json"},
}

MAX_ARTIFACT_BYTES = 8 * 1024 * 1024

KIND_EXTENSION: dict[str, str] = {
    "html": ".html",
    "svg": ".svg",
    "png": ".png",
    "json": ".json",
}


def _resolve_kind(mime: str, declared: str | None) -> str:
    """Work out the artifact kind, preferring the declared one when consistent.

    A caller that names the kind but sends a MIME that does not belong to it gets
    a 422 rather than a silently mismatched row.
    """

    normalised = (mime or "").split(";", 1)[0].strip().lower()
    if declared:
        kind = declared.strip().lower()
        if kind not in KIND_MIME:
            raise AppError(
                f"Unsupported artifact kind '{declared}'",
                status_code=422,
                error_code="unsupported_artifact_kind",
            )
        if normalised not in KIND_MIME[kind]:
            raise AppError(
                f"Kind '{kind}' does not accept MIME type '{mime}'",
                status_code=422,
                error_code="artifact_kind_mime_mismatch",
            )
        return kind

    for kind, mimes in KIND_MIME.items():
        if normalised in mimes:
            return kind
    raise AppError(
        f"Unsupported artifact MIME type '{mime}'",
        status_code=422,
        error_code="unsupported_artifact_mime",
    )


async def create_artifact(
    *,
    session: AsyncSession,
    storage: StorageBackend,
    actor: Actor,
    name: str,
    data: bytes,
    mime: str,
    kind: str | None = None,
    description: str = "",
    source: str = "manual",
    meta: dict | None = None,
) -> GraphArtifact:
    """Store an uploaded artifact and record it.

    The bytes go through the same media pipeline a note attachment uses, so an
    artifact is deduplicated by sha256 and served by the existing download route
    rather than a second storage path.
    """

    clean_name = (name or "").strip()
    if not clean_name:
        raise AppError("Artifact name is required", status_code=422, error_code="name_required")
    if not data:
        raise AppError("Artifact is empty", status_code=422, error_code="empty_artifact")
    if len(data) > MAX_ARTIFACT_BYTES:
        raise AppError(
            f"Artifact exceeds the {MAX_ARTIFACT_BYTES // (1024 * 1024)} MB limit",
            status_code=413,
            error_code="artifact_too_large",
        )

    resolved_kind = _resolve_kind(mime, kind)

    # Reuse the media pipeline so the file lives beside note attachments and is
    # reachable through the existing (authenticated) download endpoint.
    asset = await store_agent_upload(
        session=session,
        storage=storage,
        actor=actor,
        filename=f"{clean_name}{KIND_EXTENSION[resolved_kind]}",
        mime=mime,
        data=data,
        # An artifact is not analysed by the vision worker: it is either markup
        # or a static export, and there is nothing useful to describe.
        description=description or "Imported Archify artifact",
    )

    max_order = (
        await session.execute(
            select(func.max(GraphArtifact.order_index)).where(
                GraphArtifact.household_id == actor.household_id
            )
        )
    ).scalar_one_or_none() or 0

    artifact = GraphArtifact(
        id=uuid.uuid4(),
        household_id=actor.household_id,
        name=clean_name,
        description=description or "",
        kind=resolved_kind,
        media_asset_id=asset.id,
        source=(source or "manual")[:80],
        size_bytes=len(data),
        meta=meta or {},
        created_by=actor.member_id,
        order_index=max_order + 1000,
    )
    session.add(artifact)
    await session.commit()
    return artifact


async def list_artifacts(*, session: AsyncSession, actor: Actor) -> list[GraphArtifact]:
    result = await session.execute(
        select(GraphArtifact)
        .where(
            GraphArtifact.household_id == actor.household_id,
            GraphArtifact.deleted_at.is_(None),
        )
        .order_by(GraphArtifact.order_index, GraphArtifact.created_at)
    )
    return list(result.scalars().all())


async def get_artifact(
    *, session: AsyncSession, actor: Actor, artifact_id: uuid.UUID
) -> GraphArtifact:
    result = await session.execute(
        select(GraphArtifact).where(
            GraphArtifact.id == artifact_id,
            GraphArtifact.household_id == actor.household_id,
            GraphArtifact.deleted_at.is_(None),
        )
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise AppError("Artifact not found", status_code=404, error_code="not_found")
    return artifact


async def update_artifact(
    *,
    session: AsyncSession,
    actor: Actor,
    artifact_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    order_index: int | None = None,
) -> GraphArtifact:
    artifact = await get_artifact(session=session, actor=actor, artifact_id=artifact_id)
    if name is not None:
        clean = name.strip()
        if not clean:
            raise AppError("Artifact name is required", status_code=422, error_code="name_required")
        artifact.name = clean
    if description is not None:
        artifact.description = description
    if order_index is not None:
        artifact.order_index = order_index
    artifact.updated_at = datetime.now(UTC)
    await session.commit()
    return artifact


async def delete_artifact(
    *, session: AsyncSession, actor: Actor, artifact_id: uuid.UUID
) -> None:
    """Soft-delete the artifact row.

    The media asset is left alone: it may be shared with a note block through the
    sha256 dedupe, so removing it here could break a note that still references
    it. Only the artifact listing entry goes away.
    """

    artifact = await get_artifact(session=session, actor=actor, artifact_id=artifact_id)
    artifact.deleted_at = datetime.now(UTC)
    await session.commit()


async def artifact_media_asset(
    *, session: AsyncSession, actor: Actor, artifact_id: uuid.UUID
) -> MediaAsset:
    """The media asset backing an artifact, for the viewer to fetch bytes from."""

    artifact = await get_artifact(session=session, actor=actor, artifact_id=artifact_id)
    if artifact.media_asset_id is None:
        raise AppError("Artifact has no file", status_code=404, error_code="no_media")
    result = await session.execute(
        select(MediaAsset).where(
            MediaAsset.id == artifact.media_asset_id,
            MediaAsset.household_id == actor.household_id,
            MediaAsset.deleted_at.is_(None),
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise AppError("Artifact file not found", status_code=404, error_code="not_found")
    return asset
