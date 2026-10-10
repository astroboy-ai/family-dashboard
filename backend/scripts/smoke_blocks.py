"""Real service-layer smoke test for the new note block types (CR-003).

Runs inside the backend container so it uses the same DB, storage and settings
as production. Creates one note, adds a block of every tool type the drawer
exposes, patches a couple of them, then deletes the note.
"""

import asyncio
import uuid

from sqlalchemy import select

from app.api.deps import Actor
from app.core.db import session_factory
from app.models import FamilyMember, Note
from app.schemas.notes import NoteBlockInput, NoteBlockPatchRequest, NoteCreateRequest
from app.services import notes as notes_service

BLOCK_TYPES = [
    ("text", {"text_content": "smoke text"}),
    ("checkbox", {"data": {"checked": False}}),
    ("date", {"data": {"value": "2026-10-03"}}),
    ("time", {"data": {"value": "09:30", "duration_min": 45}}),
    ("currency", {"data": {"value": "128.50", "currency": "HKD"}}),
    ("password", {"data": {"value": "s3cret", "masked": True}}),
    ("location", {"data": {"latitude": 22.3193, "longitude": 114.1694}}),
    ("table", {"data": {"rows": [["a", "b"], ["c", "d"]], "columns": 2}}),
    ("reminder", {"data": {"remind_at": "2026-10-04T09:00", "done": False}}),
    ("lock", {"data": {"locked": True}}),
    ("link", {"text_content": "https://example.com", "data": {"target": "https://example.com"}}),
]


async def main() -> None:
    async with session_factory() as session:
        member = (
            await session.execute(select(FamilyMember).limit(1))
        ).scalar_one()
        actor = Actor(
            member_id=member.id,
            household_id=member.household_id,
            role=member.role,
            display_name=member.display_name or "smoke",
            timezone="Asia/Hong_Kong",
            locale="zh-HK",
            scopes=frozenset({"admin.members", "notes.write", "notes.read"}),
        )

        note = await notes_service.create_note(
            session=session,
            actor=actor,
            payload=NoteCreateRequest(title="R2 smoke test", type="freeform"),
        )
        print(f"note created: {note.id}")

        created = {}
        for block_type, extra in BLOCK_TYPES:
            payload = NoteBlockInput(type=block_type, **extra)
            block = await notes_service.create_block(
                session=session, actor=actor, note_id=note.id, payload=payload
            )
            created[block_type] = block
            print(f"  block {block_type:9s} -> {block.id}")

        # patch: toggle checkbox + fill currency value
        patched = await notes_service.update_block(
            session=session,
            actor=actor,
            block_id=created["checkbox"].id,
            payload=NoteBlockPatchRequest(data={"checked": True}),
        )
        assert patched.data.get("checked") is True, "checkbox patch failed"
        print("  patch checkbox OK")

        patched_time = await notes_service.update_block(
            session=session,
            actor=actor,
            block_id=created["time"].id,
            payload=NoteBlockPatchRequest(data={"value": "14:00", "duration_min": 90}),
        )
        assert patched_time.data.get("duration_min") == 90, "time patch failed"
        print("  patch time OK")

        # list
        blocks = await notes_service.list_blocks(session=session, actor=actor, note_id=note.id)
        assert len(blocks) == len(BLOCK_TYPES), f"expected {len(BLOCK_TYPES)} blocks, got {len(blocks)}"
        print(f"  list_blocks OK ({len(blocks)} blocks)")

        # delete one block
        await notes_service.delete_block(
            session=session, actor=actor, block_id=created["lock"].id
        )
        blocks = await notes_service.list_blocks(session=session, actor=actor, note_id=note.id)
        assert len(blocks) == len(BLOCK_TYPES) - 1, "block delete failed"
        print("  delete block OK")

        # cleanup
        note_row = (await session.execute(select(Note).where(Note.id == note.id))).scalar_one()
        await session.delete(note_row)
        await session.commit()
        print("cleanup OK")
        print("ALL SMOKE TESTS PASSED")


asyncio.run(main())
