"""Service-layer smoke test for M4 Archify artifact import.

Runs inside the backend container against the real DB and storage, so it
exercises the same path a UI import takes. Cleans up after itself.

Covers:
  kind/MIME validation (accepts html, rejects a mismatch, rejects unknown)
  the 8 MB size cap
  bytes land in storage and are readable back byte-for-byte
  listing / fetch / rename / soft-delete
  one artifact cannot be read from another household
"""

import asyncio
import uuid

from sqlalchemy import select

from app.api.deps import Actor
from app.core.config import get_settings
from app.core.db import session_factory
from app.core.errors import AppError
from app.core.storage import S3CompatibleStorage
from app.models import FamilyMember, GraphArtifact
from app.services import graph_artifacts as artifacts_service

PASS, FAIL = [], []


def _storage() -> S3CompatibleStorage:
    """Build storage the way the worker does.

    ``get_storage`` is a FastAPI dependency, so it cannot be called directly
    outside a request. The worker constructs the client itself for exactly this
    reason; this smoke runs the same way.
    """

    settings = get_settings()
    return S3CompatibleStorage(
        internal_endpoint=settings.s3_endpoint,
        public_endpoint=settings.s3_public_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
    )


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{' — ' + detail if detail else ''}")


# A minimal but genuinely interactive artifact: inline JS that mutates the DOM.
SAMPLE_HTML = b"""<!doctype html>
<html><head><meta charset="utf-8"><title>Smoke graph</title></head>
<body><h1 id="t">graph</h1><script>document.getElementById('t').textContent='rendered';</script></body>
</html>"""


async def expect_error(coro, error_code: str) -> str:
    """Run *coro*, expecting an AppError carrying *error_code*. Returns detail."""

    try:
        await coro
    except AppError as error:
        if getattr(error, "error_code", None) == error_code:
            return ""
        return f"wrong code: {getattr(error, 'error_code', None)}"
    except Exception as error:  # noqa: BLE001
        return f"wrong type: {type(error).__name__}"
    return "no error raised"


async def main() -> None:
    storage = _storage()

    async with session_factory() as session:
        member = (await session.execute(select(FamilyMember).limit(1))).scalar_one()
        actor = Actor(
            member_id=member.id,
            household_id=member.household_id,
            role=member.role,
            display_name=member.display_name or "smoke",
            timezone="Asia/Hong_Kong",
            locale="zh-HK",
            scopes=frozenset({"notes.read", "notes.write"}),
        )

        print("\n== M4: artifact import ==")
        artifact = await artifacts_service.create_artifact(
            session=session,
            storage=storage,
            actor=actor,
            name="Smoke Archify",
            data=SAMPLE_HTML,
            mime="text/html",
            source="smoke",
        )
        check("artifact created", artifact.id is not None)
        check("kind resolved to html", artifact.kind == "html", f"kind={artifact.kind}")
        check("size recorded", artifact.size_bytes == len(SAMPLE_HTML), f"{artifact.size_bytes} bytes")
        check("media asset linked", artifact.media_asset_id is not None)
        check("source recorded", artifact.source == "smoke")

        # The bytes must round-trip: an artifact that cannot be read back is
        # useless to the viewer.
        asset = await artifacts_service.artifact_media_asset(
            session=session, actor=actor, artifact_id=artifact.id
        )
        stored_bytes = await storage.get(asset.storage_key)
        check("bytes round-trip through storage", stored_bytes == SAMPLE_HTML,
              f"{len(stored_bytes)} bytes")
        check("stored mime is html", asset.mime == "text/html", f"mime={asset.mime}")
        check("filename keeps the .html extension",
              str((asset.meta or {}).get("original_filename", "")).endswith(".html"),
              f"name={(asset.meta or {}).get('original_filename')}")

        print("\n== validation ==")
        detail = await expect_error(
            artifacts_service.create_artifact(
                session=session, storage=storage, actor=actor,
                name="bad", data=b"x", mime="text/plain", kind="html",
            ),
            "artifact_kind_mime_mismatch",
        )
        check("kind/MIME mismatch rejected", detail == "", detail)

        detail = await expect_error(
            artifacts_service.create_artifact(
                session=session, storage=storage, actor=actor,
                name="bad", data=b"x", mime="application/pdf",
            ),
            "unsupported_artifact_mime",
        )
        check("unknown MIME rejected", detail == "", detail)

        detail = await expect_error(
            artifacts_service.create_artifact(
                session=session, storage=storage, actor=actor,
                name="bad", data=b"x", mime="text/html", kind="exe",
            ),
            "unsupported_artifact_kind",
        )
        check("unknown kind rejected", detail == "", detail)

        detail = await expect_error(
            artifacts_service.create_artifact(
                session=session, storage=storage, actor=actor,
                name="", data=b"x", mime="text/html",
            ),
            "name_required",
        )
        check("blank name rejected", detail == "", detail)

        detail = await expect_error(
            artifacts_service.create_artifact(
                session=session, storage=storage, actor=actor,
                name="empty", data=b"", mime="text/html",
            ),
            "empty_artifact",
        )
        check("empty file rejected", detail == "", detail)

        detail = await expect_error(
            artifacts_service.create_artifact(
                session=session, storage=storage, actor=actor,
                name="huge", data=b"x" * (artifacts_service.MAX_ARTIFACT_BYTES + 1),
                mime="text/html",
            ),
            "artifact_too_large",
        )
        check("oversize file rejected", detail == "", detail)

        # A kind that is inferred rather than declared must work too — the UI
        # sends only the file.
        png = await artifacts_service.create_artifact(
            session=session, storage=storage, actor=actor,
            name="Smoke PNG", data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, mime="image/png",
        )
        check("kind inferred from MIME", png.kind == "png", f"kind={png.kind}")

        print("\n== listing, rename, delete ==")
        listed = await artifacts_service.list_artifacts(session=session, actor=actor)
        ids = {a.id for a in listed}
        check("both artifacts listed", {artifact.id, png.id} <= ids, f"{len(listed)} listed")

        renamed = await artifacts_service.update_artifact(
            session=session, actor=actor, artifact_id=artifact.id, name="Renamed smoke"
        )
        check("rename applied", renamed.name == "Renamed smoke", f"name={renamed.name}")

        detail = await expect_error(
            artifacts_service.update_artifact(
                session=session, actor=actor, artifact_id=artifact.id, name="   "
            ),
            "name_required",
        )
        check("rename to blank rejected", detail == "", detail)

        await artifacts_service.delete_artifact(
            session=session, actor=actor, artifact_id=png.id
        )
        listed_after = await artifacts_service.list_artifacts(session=session, actor=actor)
        check("deleted artifact leaves the list",
              png.id not in {a.id for a in listed_after})

        detail = await expect_error(
            artifacts_service.get_artifact(session=session, actor=actor, artifact_id=png.id),
            "not_found",
        )
        check("deleted artifact is not fetchable", detail == "", detail)

        # The media asset must survive the artifact delete: sha256 dedupe means
        # a note block may still reference it.
        still_there = await storage.get(asset.storage_key)
        check("underlying file kept after artifact delete", still_there == SAMPLE_HTML)

        print("\n== household isolation ==")
        other = Actor(
            member_id=None,
            household_id=uuid.uuid4(),  # a household this actor does not belong to
            role="parent",
            display_name="other",
            timezone="Asia/Hong_Kong",
            locale="zh-HK",
            scopes=frozenset({"notes.read"}),
        )
        detail = await expect_error(
            artifacts_service.get_artifact(session=session, actor=other, artifact_id=artifact.id),
            "not_found",
        )
        check("another household cannot read the artifact", detail == "", detail)

        # Cleanup.
        await artifacts_service.delete_artifact(
            session=session, actor=actor, artifact_id=artifact.id
        )
        leftovers = (
            await session.execute(
                select(GraphArtifact).where(
                    GraphArtifact.id.in_([artifact.id, png.id])
                )
            )
        ).scalars().all()
        check("rows soft-deleted, not hard-deleted", all(r.deleted_at is not None for r in leftovers),
              f"{len(leftovers)} rows")
        print("\n  cleanup done")

    print(f"\n{'=' * 46}\n  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("  FAILED: " + ", ".join(FAIL))
    print("=" * 46)


asyncio.run(main())
