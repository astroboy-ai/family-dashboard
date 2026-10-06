"""Service-layer smoke test for M2a (blocks), M3 (notifications), M4 (vault).

Runs inside the backend container against the real DB, so it exercises the same
code paths production uses. Creates its own note and cleans up after itself.

Covers:
  M2a  password block encryption at rest + scope-based masking
  M2a  thumbnail generation and EXIF extraction
  M3   notification create / dedupe / unread count / mark read
  M4   vault listing and secret visibility by scope
"""

import asyncio
import base64
import io
import uuid

from sqlalchemy import select

from app.api.deps import Actor
from app.core import secrets
from app.core.db import session_factory
from app.models import FamilyMember, Note, NoteBlock, Notification
from app.schemas.notes import NoteBlockInput, NoteCreateRequest
from app.services import notes as notes_service
from app.services import notifications as notif_service

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{' — ' + detail if detail else ''}")


async def main() -> None:
    async with session_factory() as session:
        member = (await session.execute(select(FamilyMember).limit(1))).scalar_one()
        base = dict(
            member_id=member.id,
            household_id=member.household_id,
            role=member.role,
            display_name=member.display_name or "smoke",
            timezone="Asia/Hong_Kong",
            locale="zh-HK",
        )
        # Parent: may read secrets. Child: may not.
        parent = Actor(**base, scopes=frozenset({"notes.read", "notes.write", "notes.read.secrets"}))
        plain = Actor(**base, scopes=frozenset({"notes.read", "notes.write"}))

        print("\n== M2a: password block encryption ==")

        note = await notes_service.create_note(
            session=session, actor=parent, payload=NoteCreateRequest(title="R2 smoke M2a/M3/M4", type="freeform")
        )
        print(f"  note: {note.id}")

        block = await notes_service.create_block(
            session=session,
            actor=parent,
            note_id=note.id,
            payload=NoteBlockInput(type="password", data={"value": "hunter2", "label": "wifi", "masked": True}),
        )

        # Read the raw row: the stored value must be ciphertext, not plaintext.
        raw = (
            await session.execute(select(NoteBlock).where(NoteBlock.id == block.id))
        ).scalar_one()
        stored = (raw.data or {}).get("value", "")
        check("plaintext not stored at rest", stored != "hunter2", f"stored={stored[:24]}…")
        check("stored value is our ciphertext", secrets.is_encrypted(stored))
        check("decrypts back to original", secrets.decrypt(stored) == "hunter2")
        check("data.encrypted flag set", (raw.data or {}).get("encrypted") is True)
        check("label preserved", (raw.data or {}).get("label") == "wifi")

        # Idempotence: re-encrypting must not double-wrap.
        again = notes_service._encrypt_password_data(dict(raw.data))
        check("re-encrypt is idempotent", secrets.decrypt(again["value"]) == "hunter2")

        # Scope masking on the read path.
        as_parent = await notes_service.list_blocks(session=session, actor=parent, note_id=note.id)
        p_block = next(b for b in as_parent if b.id == block.id)
        check("parent scope sees plaintext", p_block.data.get("value") == "hunter2")

        as_plain = await notes_service.list_blocks(session=session, actor=plain, note_id=note.id)
        c_block = next(b for b in as_plain if b.id == block.id)
        check("non-secret scope is masked", c_block.data.get("value") != "hunter2",
              f"value={c_block.data.get('value')!r}")

        # Non-password blocks must pass through untouched.
        text = await notes_service.create_block(
            session=session, actor=parent, note_id=note.id,
            payload=NoteBlockInput(type="text", text_content="plain text block"),
        )
        t_raw = (await session.execute(select(NoteBlock).where(NoteBlock.id == text.id))).scalar_one()
        check("text block not encrypted", t_raw.text_content == "plain text block")

        print("\n== M2a: imaging ==")
        try:
            from PIL import Image
            from app.services import imaging

            buf = io.BytesIO()
            Image.new("RGB", (1200, 800), (30, 90, 160)).save(buf, format="JPEG")
            jpeg = buf.getvalue()

            thumb = imaging.generate_thumbnail(jpeg, "image/jpeg")
            check("thumbnail generated", thumb is not None)
            if thumb:
                tb, tmime = thumb
                check("thumbnail smaller than source", len(tb) < len(jpeg),
                      f"{len(tb)} < {len(jpeg)} bytes")
                im = Image.open(io.BytesIO(tb))
                check("thumbnail within 512px", max(im.size) <= 512, f"size={im.size}")

            check("exif returns None when absent", imaging.read_exif(jpeg) is None)
        except ImportError as error:
            check("pillow importable", False, str(error))

        print("\n== M3: notifications ==")
        key = f"smoke:{uuid.uuid4()}"
        n1 = await notif_service.create_notification(
            session=session, household_id=parent.household_id, kind="smoke",
            title="Smoke notification", member_id=member.id, dedupe_key=key,
        )
        check("notification created", n1.id is not None)

        n2 = await notif_service.create_notification(
            session=session, household_id=parent.household_id, kind="smoke",
            title="Smoke notification (dup)", member_id=member.id, dedupe_key=key,
        )
        check("dedupe_key suppresses duplicate", n1.id == n2.id, f"{n1.id} == {n2.id}")

        dupes = (
            await session.execute(select(Notification).where(Notification.dedupe_key == key))
        ).scalars().all()
        check("exactly one row for dedupe key", len(dupes) == 1, f"count={len(dupes)}")

        before = await notif_service.get_unread_count(
            session=session, household_id=parent.household_id, member_id=member.id
        )
        check("unread count includes new notification", before >= 1, f"count={before}")

        listed = await notif_service.list_notifications(
            session=session, household_id=parent.household_id, member_id=member.id, limit=50
        )
        check("notification appears in list", any(n.id == n1.id for n in listed))

        marked = await notif_service.mark_as_read(
            session=session, notification_id=n1.id, member_id=member.id
        )
        check("mark_as_read sets read_at", marked is not None and marked.read_at is not None)

        after = await notif_service.get_unread_count(
            session=session, household_id=parent.household_id, member_id=member.id
        )
        check("unread count drops after read", after == before - 1, f"{before} -> {after}")

        allread = await notif_service.mark_all_as_read(
            session=session, household_id=parent.household_id, member_id=member.id
        )
        check("mark_all_as_read runs", allread >= 0, f"marked={allread}")

        print("\n== regression: inline password block via create_note ==")
        # A password block passed inline to create_note must be encrypted too —
        # it used to skip _encrypt_password_data and land as plaintext.
        inline_note = await notes_service.create_note(
            session=session,
            actor=parent,
            payload=NoteCreateRequest(
                title="R2 smoke inline password",
                type="freeform",
                blocks=[
                    NoteBlockInput(type="password", data={"value": "inline-secret", "label": "router"})
                ],
            ),
        )
        check("create_note with inline password block succeeds", inline_note is not None)
        inline_block = (
            await session.execute(
                select(NoteBlock).where(NoteBlock.note_id == inline_note.id)
            )
        ).scalars().one()
        inline_stored = (inline_block.data or {}).get("value", "")
        check("inline password encrypted at rest", inline_stored != "inline-secret",
              f"stored={inline_stored[:24]}…")
        check("inline password is our ciphertext", secrets.is_encrypted(inline_stored))
        check("inline password decrypts back", secrets.decrypt(inline_stored) == "inline-secret")

        # get_note must mask for a non-secret scope, exactly like list_blocks.
        got_parent = await notes_service.get_note(session=session, actor=parent, note_id=inline_note.id)
        pv = next(b for b in got_parent.blocks if b.type == "password")
        check("get_note reveals to secrets scope", pv.data.get("value") == "inline-secret")

        got_plain = await notes_service.get_note(session=session, actor=plain, note_id=inline_note.id)
        cv = next(b for b in got_plain.blocks if b.type == "password")
        check("get_note masks without secrets scope", cv.data.get("value") != "inline-secret",
              f"value={cv.data.get('value')!r}")

        # list_notes must mask too — it shares _note_response.
        listed_plain = await notes_service.list_notes(session=session, actor=plain, limit=200)
        row = next((n for n in listed_plain.items if n.id == inline_note.id), None)
        if row:
            lv = next((b for b in row.blocks if b.type == "password"), None)
            check("list_notes masks without secrets scope",
                  lv is not None and lv.data.get("value") != "inline-secret",
                  f"value={lv.data.get('value') if lv else None!r}")

        inline_row = (
            await session.execute(select(Note).where(Note.id == inline_note.id))
        ).scalar_one()
        from datetime import UTC as _UTC, datetime as _dt
        inline_row.deleted_at = _dt.now(_UTC)

        print("\n== M4: vault ==")
        from app.api.vault import list_password_blocks, get_password_block

        listed_vault = await list_password_blocks(actor=parent, session=session)
        check("vault lists the password block", any(r.id == block.id for r in listed_vault),
              f"{len(listed_vault)} blocks")

        row = next((r for r in listed_vault if r.id == block.id), None)
        if row:
            check("vault row carries note title", row.note_title == "R2 smoke M2a/M3/M4")
            check("vault row does NOT expose value", not hasattr(row, "value") or getattr(row, "value", None) is None)

        detail_parent = await get_password_block(block_id=block.id, actor=parent, session=session)
        check("vault detail reveals to secrets scope", detail_parent.value == "hunter2")

        detail_plain = await get_password_block(block_id=block.id, actor=plain, session=session)
        check("vault detail masks without scope", detail_plain.value is None,
              f"value={detail_plain.value!r}")

        # Cleanup: soft-delete the note and drop the smoke notification.
        note_row = (await session.execute(select(Note).where(Note.id == note.id))).scalar_one()
        from datetime import UTC, datetime
        note_row.deleted_at = datetime.now(UTC)
        await session.delete(n1)
        await session.commit()
        print("\n  cleanup done")

    print(f"\n{'=' * 46}\n  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("  FAILED: " + ", ".join(FAIL))
    print("=" * 46)


asyncio.run(main())
