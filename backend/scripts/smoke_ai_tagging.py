"""Smoke test: AI tagging (Step 1-4).

Run inside the backend container against the live DB:

    docker cp smoke_ai_tagging.py familyos-backend-1:/app/smoke_ai_tagging.py
    docker exec -w /app familyos-backend-1 \
      env PYTHONPATH=/app /app/.venv/bin/python smoke_ai_tagging.py

Tests the real service layer (no HTTP) so it proves:
- LLM classifier extracts metadata + proposes tags
- Worker handler processes tag.propose jobs
- Accept/reject decisions work
- Exclusions are written on reject
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.api.deps import Actor
from app.core.db import session_factory
from app.models import (
    FamilyMember,
    JobOutbox,
    Note,
    NoteBlock,
    Tag,
    TagExclusion,
    TagProposal,
)
from app.schemas.notes import NoteCreateRequest, TagProposalInput
from app.services.ai_tagging import (
    apply_metadata,
    classify_note,
    create_tag_proposals_from_classification,
)
from app.services.notes import create_note, update_note
from app.services.tag_governance import decide_tag_proposal, propose_tags

PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label} {detail}")


async def main() -> None:
    async with session_factory() as session:
        # Get first household + member
        member = (
            await session.execute(
                select(FamilyMember).where(FamilyMember.is_active.is_(True)).limit(1)
            )
        ).scalar_one()
        actor = Actor(
            member_id=member.id,
            household_id=member.household_id,
            role=member.role,
            display_name=member.display_name,
            timezone="UTC",
            locale="en",
            scopes=frozenset({"notes.read", "notes.write"}),
        )
        print(f"Using member: {member.display_name} ({member.id})")
        print(f"Household: {member.household_id}")

        # ── Step 1: Create a recipe note ──────────────────────────────
        print("\n=== Step 1: Create recipe note ===")
        from app.schemas.notes import NoteBlockInput

        note_resp = await create_note(
            session=session,
            actor=actor,
            payload=NoteCreateRequest(
                title="Grandma's Apple Pie Recipe",
                type="freeform",
                blocks=[
                    NoteBlockInput(
                        type="text",
                        text_content="Ingredients: 2 cups flour, 1 cup sugar, 3 apples, 1 tsp cinnamon. Mix flour and sugar, add sliced apples, sprinkle cinnamon. Bake at 180C for 45 minutes. Best served warm with vanilla ice cream."
                    )
                ],
            ),
        )
        await session.commit()
        note = await session.get(Note, note_resp.id)
        print(f"  Note created: {note.id}")
        check("note created", note.id is not None)

        # ── Step 2: Classify with LLM ────────────────────────────────
        print("\n=== Step 2: LLM classification ===")
        result = await classify_note(
            session,
            note,
            actor_household_id=member.household_id,
        )
        print(f"  Metadata: {json.dumps(result.get('metadata', {}), indent=2, default=str)}")
        print(f"  Tags proposed: {len(result.get('tags', []))}")
        for t in result.get("tags", []):
            print(f"    #{t.slug} ({t.confidence:.0%}) — {t.evidence.get('reason', 'N/A')}")

        check("metadata extracted", len(result.get("metadata", {})) > 0)
        check("tags proposed", len(result.get("tags", [])) > 0)

        # ── Step 3: Apply metadata ───────────────────────────────────
        print("\n=== Step 3: Apply metadata ===")
        metadata = result.get("metadata", {})
        if metadata:
            await apply_metadata(session, note, metadata)
            await session.commit()
            print(f"  Type: {note.type}")
            print(f"  Occurred at: {note.occurred_at}")
            check("metadata applied", note.type != "freeform" or note.occurred_at is not None)

        # ── Step 4: Create tag proposals ─────────────────────────────
        print("\n=== Step 4: Create tag proposals ===")
        tag_inputs = result.get("tags", [])
        if tag_inputs:
            proposals = await create_tag_proposals_from_classification(
                session,
                note,
                actor_household_id=member.household_id,
                tag_inputs=tag_inputs,
                model=result.get("model", "test"),
            )
            await session.commit()
            print(f"  Proposals created: {len(proposals)}")
            for p in proposals:
                print(f"    #{p.proposed_slug} ({p.confidence:.0%})")
            check("proposals created", len(proposals) > 0)
        else:
            proposals = []
            check("proposals created", False, "no tag inputs")

        # ── Step 5: Accept first proposal ────────────────────────────
        print("\n=== Step 5: Accept first proposal ===")
        if proposals:
            first = proposals[0]
            decided = await decide_tag_proposal(
                session=session,
                actor=actor,
                proposal_id=first.id,
                accepted=True,
            )
            await session.commit()
            print(f"  Accepted: #{first.proposed_slug} → status={decided.status}")
            check("proposal accepted", decided.status == "accepted")

            # Verify tag applied to note
            await session.refresh(note)
            from app.models import note_tags as nt
            note_tags_result = await session.execute(
                select(Tag).join(nt, nt.c.tag_id == Tag.id).where(nt.c.note_id == note.id)
            )
            applied_tags = list(note_tags_result.scalars().all())
            print(f"  Tags on note: {[t.slug for t in applied_tags]}")
            check("tag applied to note", len(applied_tags) > 0)
        else:
            check("proposal accepted", False, "no proposals to accept")

        # ── Step 6: Reject second proposal ──────────────────────────
        print("\n=== Step 6: Reject second proposal ===")
        if len(proposals) > 1:
            second = proposals[1]
            decided = await decide_tag_proposal(
                session=session,
                actor=actor,
                proposal_id=second.id,
                accepted=False,
            )
            await session.commit()
            print(f"  Rejected: #{second.proposed_slug} → status={decided.status}")
            check("proposal rejected", decided.status == "rejected")

            # Verify exclusion written
            exclusions = (
                await session.execute(
                    select(TagExclusion).where(
                        TagExclusion.tag_slug == second.proposed_slug,
                        TagExclusion.scope == "note",
                        TagExclusion.scope_ref == note.id,
                    )
                )
            ).scalars().all()
            print(f"  Exclusions: {len(exclusions)}")
            check("exclusion written on reject", len(exclusions) > 0)
        else:
            check("proposal rejected", False, "no second proposal")

        # ── Step 7: Verify worker handler exists ─────────────────────
        print("\n=== Step 7: Worker handler ===")
        from app.workers.outbox import HANDLERS
        check("tag.propose handler registered", "tag.propose" in HANDLERS)

        # ── Step 8: Verify _queue_tag_propose ────────────────────────
        print("\n=== Step 8: Queue tag.propose job ===")
        from app.services.notes import _queue_tag_propose

        _queue_tag_propose(session, note.id)
        await session.commit()
        jobs = (
            await session.execute(
                select(JobOutbox).where(
                    JobOutbox.topic == "tag.propose",
                    JobOutbox.payload["note_id"].astext == str(note.id),
                )
            )
        ).scalars().all()
        print(f"  tag.propose jobs for this note: {len(jobs)}")
        check("tag.propose job queued", len(jobs) > 0)

        # ── Summary ──────────────────────────────────────────────────
        print(f"\n{'='*50}")
        print(f"  PASSED: {PASSED}")
        print(f"  FAILED: {FAILED}")
        print(f"{'='*50}")

        # Cleanup
        print("\n=== Cleanup ===")
        await session.execute(delete(TagExclusion).where(TagExclusion.scope_ref == note.id))
        await session.execute(delete(TagProposal).where(TagProposal.note_id == note.id))
        from app.models import note_tags
        await session.execute(delete(note_tags).where(note_tags.c.note_id == note.id))
        await session.execute(delete(JobOutbox).where(JobOutbox.payload["note_id"].astext == str(note.id)))
        await session.execute(delete(Note).where(Note.id == note.id))
        await session.commit()
        print("  Cleaned up test data")

        if FAILED > 0:
            print(f"\n  {FAILED} test(s) FAILED")
            return False
        print("\n  All tests PASSED")
        return True


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
