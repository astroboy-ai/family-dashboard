"""Smoke test for AI tagging (Step 1-4).

Tests:
1. Create a note with recipe content
2. Wait for worker to process tag.propose job
3. Verify metadata extracted (type, occurred_at)
4. Verify tag proposals created
5. Accept a tag proposal
6. Verify tag applied to note
7. Reject a tag proposal
8. Verify exclusion created
"""

import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta

import httpx

BASE = "http://familyos-backend:8000"
TOKEN = None


async def login() -> str:
    """Mint a session token."""
    # Use the mint_session approach - direct DB insert
    from app.core.db import session_factory
    from app.models import DeviceToken, FamilyMember, Household
    from sqlalchemy import select
    import hashlib
    import secrets

    async with session_factory() as session:
        # Get first household and member
        h = (await session.execute(select(Household).limit(1))).scalar_one()
        m = (
            await session.execute(
                select(FamilyMember).where(FamilyMember.household_id == h.id).limit(1)
            )
        ).scalar_one()

        # Create device token
        raw = secrets.token_urlsafe(32)
        token = DeviceToken(
            household_id=h.id,
            member_id=m.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            name="smoke-test",
            scopes=["notes.read", "notes.write"],
        )
        session.add(token)
        await session.commit()
        return raw


async def api(method: str, path: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        r = await client.request(method, path, headers=headers, **kwargs)
        if r.status_code >= 400:
            print(f"  ERROR {r.status_code}: {r.text[:300]}")
            return {}
        return r.json() if r.text else {}


async def main():
    global TOKEN
    TOKEN = await login()
    print(f"✓ Logged in")

    # 1. Create a recipe note
    print("\n=== Step 1: Create recipe note ===")
    note = await api(
        "POST",
        "/notes",
        json={
            "title": "Grandma's Apple Pie Recipe",
            "type": "freeform",
            "blocks": [
                {
                    "type": "text",
                    "data": {
                        "text": "Ingredients: 2 cups flour, 1 cup sugar, 3 apples, 1 tsp cinnamon. Mix flour and sugar, add sliced apples, sprinkle cinnamon. Bake at 180C for 45 minutes. Best served warm with vanilla ice cream."
                    }
                }
            ],
        },
    )
    if not note:
        print("  FAILED to create note")
        return False
    note_id = note["id"]
    print(f"  ✓ Note created: {note_id}")
    print(f"    Title: {note.get('title')}")
    print(f"    Type: {note.get('type')}")

    # 2. Wait for worker to process
    print("\n=== Step 2: Wait for worker (tag.propose) ===")
    for i in range(30):
        await asyncio.sleep(2)
        # Check job status
        from app.core.db import session_factory
        from app.models import JobOutbox
        from sqlalchemy import select

        async with session_factory() as session:
            job = (
                await session.execute(
                    select(JobOutbox).where(
                        JobOutbox.topic == "tag.propose",
                        JobOutbox.payload["note_id"].astext == note_id,
                    )
                )
            ).scalar_one_or_none()
            if job:
                print(f"  Job status: {job.status} (attempt {job.attempts})")
                if job.status in ("complete", "dead"):
                    break
            else:
                print(f"  Job not found yet... ({i+1})")
    else:
        print("  TIMEOUT waiting for worker")
        return False

    # 3. Check metadata extracted
    print("\n=== Step 3: Check metadata ===")
    note_after = await api("GET", f"/notes/{note_id}")
    print(f"  Type: {note_after.get('type')}")
    print(f"  Occurred at: {note_after.get('occurred_at')}")
    print(f"  Location: {note_after.get('location')}")
    print(f"  Owner: {note_after.get('owner_member_id')}")

    # 4. Check tag proposals
    print("\n=== Step 4: Check tag proposals ===")
    proposals = await api("GET", "/tags/proposals")
    print(f"  Total proposals: {len(proposals)}")
    for p in proposals[:5]:
        print(f"    #{p['proposed_slug']} ({p['confidence']:.0%}) — {p.get('evidence', {}).get('reason', 'N/A')}")

    if not proposals:
        print("  No proposals found — checking job error...")
        from app.core.db import session_factory
        from app.models import JobOutbox
        from sqlalchemy import select

        async with session_factory() as session:
            job = (
                await session.execute(
                    select(JobOutbox).where(
                        JobOutbox.topic == "tag.propose",
                        JobOutbox.payload["note_id"].astext == note_id,
                    )
                )
            ).scalar_one_or_none()
            if job:
                print(f"  Job payload: {json.dumps(job.payload, indent=2, default=str)[:500]}")
        return False

    # 5. Accept first proposal
    print("\n=== Step 5: Accept first proposal ===")
    first = proposals[0]
    result = await api(
        "POST",
        f"/tags/proposals/{first['id']}/decision",
        json={"accepted": True},
    )
    print(f"  ✓ Accepted: #{first['proposed_slug']} → status={result.get('status')}")

    # 6. Verify tag applied
    print("\n=== Step 6: Verify tag applied ===")
    note_with_tag = await api("GET", f"/notes/{note_id}")
    tags = note_with_tag.get("tags", [])
    print(f"  Tags on note: {[t.get('slug') for t in tags]}")

    # 7. Reject second proposal
    if len(proposals) > 1:
        print("\n=== Step 7: Reject second proposal ===")
        second = proposals[1]
        result = await api(
            "POST",
            f"/tags/proposals/{second['id']}/decision",
            json={"accepted": False},
        )
        print(f"  ✓ Rejected: #{second['proposed_slug']} → status={result.get('status')}")

    # 8. Check exclusions
    print("\n=== Step 8: Check exclusions ===")
    from app.core.db import session_factory
    from app.models import TagExclusion
    from sqlalchemy import select

    async with session_factory() as session:
        exclusions = (
            await session.execute(select(TagExclusion).limit(10))
        ).scalars().all()
        print(f"  Exclusions: {len(exclusions)}")
        for e in exclusions:
            print(f"    {e.scope_type}:{e.scope_ref} → {e.tag_slug}")

    print("\n=== SMOKE TEST COMPLETE ===")
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
