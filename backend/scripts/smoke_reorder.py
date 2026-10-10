"""Smoke test for block reordering and per-block drawing isolation (CR-3/CR-4).

Runs inside the backend container against the live HTTP API.

Covers:
1. reorder returns 200 and the new order survives a re-read;
2. reorder rejects a partial id list;
3. reorder is idempotent for the same order;
4. two drawing blocks keep independent stroke data (the CR-3a regression).
"""

import asyncio
import uuid

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import session_factory
from app.core.security import create_access_token
from app.models import FamilyMember, Note
from app.services.sessions import issue_session

BASE = "http://127.0.0.1:8000"
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{' — ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


async def main() -> None:
    settings = get_settings()
    async with session_factory() as session:
        member = (
            await session.execute(select(FamilyMember).where(FamilyMember.is_active.is_(True)).limit(1))
        ).scalar_one()
        issued = await issue_session(session=session, member=member, user_agent="reorder-smoke")
        token = issued.refresh_token
        assert token is not None
        access = create_access_token(
            member_id=str(member.id),
            household_id=str(member.household_id),
            settings=settings,
        )

    headers = {"Cookie": f"access_token={access}"}

    async with httpx.AsyncClient(base_url=BASE, timeout=30.0, headers=headers) as client:
        # --- set up a throwaway note with three blocks --------------------
        r = await client.post("/api/notes", json={"title": "reorder smoke", "type": "freeform"})
        check("note created", r.status_code == 201, f"got {r.status_code} {r.text[:140]}")
        note_id = r.json()["id"]

        ids: list[str] = []
        for label in ("first", "second", "third"):
            r = await client.post(
                f"/api/notes/{note_id}/blocks",
                json={"type": "text", "text_content": label},
            )
            check(f"block '{label}' created", r.status_code == 201, f"got {r.status_code}")
            ids.append(r.json()["id"])

        # --- 1. reorder persists -------------------------------------------
        wanted = [ids[2], ids[0], ids[1]]
        r = await client.post(f"/api/notes/{note_id}/reorder", json={"block_ids": wanted})
        check("reorder returns 200", r.status_code == 200, f"got {r.status_code} {r.text[:160]}")
        if r.status_code == 200:
            check(
                "reorder response is in the new order",
                [b["id"] for b in r.json()] == wanted,
                str([b["id"] for b in r.json()])[:120],
            )

        r = await client.get(f"/api/notes/{note_id}")
        persisted = [b["id"] for b in r.json()["blocks"]]
        check("new order survives a re-read", persisted == wanted, str(persisted)[:140])

        # --- 2. a partial list is rejected ---------------------------------
        r = await client.post(f"/api/notes/{note_id}/reorder", json={"block_ids": ids[:2]})
        check("partial reorder rejected", r.status_code in (400, 422), f"got {r.status_code}")

        # --- 3. same order again is a no-op, not an error ------------------
        r = await client.post(f"/api/notes/{note_id}/reorder", json={"block_ids": wanted})
        check("idempotent reorder", r.status_code == 200, f"got {r.status_code}")

        # --- 4. drawing blocks stay independent ----------------------------
        stroke_a = [{"id": "a", "color": "#fff", "width": 3, "points": [{"x": 1, "y": 1}, {"x": 9, "y": 9}]}]
        stroke_b = [{"id": "b", "color": "#f00", "width": 5, "points": [{"x": 2, "y": 2}]}]

        r = await client.post(
            f"/api/notes/{note_id}/blocks",
            json={"type": "drawing", "text_content": "board A", "data": {"strokes": stroke_a, "theme": "chalkboard_green"}},
        )
        check("drawing A created", r.status_code == 201, f"got {r.status_code}")
        draw_a = r.json()["id"]

        r = await client.post(
            f"/api/notes/{note_id}/blocks",
            json={"type": "drawing", "text_content": "board B", "data": {"strokes": stroke_b, "theme": "whiteboard"}},
        )
        check("drawing B created", r.status_code == 201, f"got {r.status_code}")
        draw_b = r.json()["id"]

        check("two distinct drawing blocks", draw_a != draw_b)

        r = await client.get(f"/api/notes/{note_id}")
        blocks = {b["id"]: b for b in r.json()["blocks"]}
        check(
            "drawing A keeps its own strokes",
            len(blocks[draw_a]["data"].get("strokes", [])) == 1,
            str(len(blocks[draw_a]["data"].get("strokes", []))),
        )
        check(
            "drawing B keeps its own strokes",
            len(blocks[draw_b]["data"].get("strokes", [])) == 1,
            str(len(blocks[draw_b]["data"].get("strokes", []))),
        )
        check(
            "drawing A and B are not the same data",
            blocks[draw_a]["data"] != blocks[draw_b]["data"],
        )

        # --- cleanup -------------------------------------------------------
        r = await client.delete(f"/api/notes/{note_id}")
        check("cleanup deleted the note", r.status_code in (200, 204), f"got {r.status_code}")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        raise SystemExit(1)
    print("ALL REORDER + DRAWING TESTS PASSED")


asyncio.run(main())
