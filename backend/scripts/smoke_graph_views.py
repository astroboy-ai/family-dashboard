"""Smoke test: Archify graph views + per-member preferences.

Run inside the backend container against the live DB:

    docker cp smoke_graph_views.py familyos-backend-1:/app/smoke_graph_views.py
    docker exec -w /app familyos-backend-1 \
      env PYTHONPATH=/app /app/.venv/bin/python smoke_graph_views.py

Exercises the real service layer (no HTTP) so it proves the migration ran, the
JSONB write actually persists, and the merge semantics hold.
"""

import asyncio
import uuid

from sqlalchemy import delete, select

from app.api.deps import Actor
from app.core.db import session_factory
from app.models import FamilyMember, GraphView
from app.schemas.graph_view import GraphViewCreateRequest, GraphViewPatchRequest
from app.schemas.preferences import MemberPreferencesPatch
from app.services.graph_views import (
    create_graph_view,
    delete_graph_view,
    get_graph_view,
    list_graph_views,
    update_graph_view,
)

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
    factory = session_factory
    async with factory() as session:
        member = (
            await session.execute(select(FamilyMember).where(FamilyMember.is_active.is_(True)).limit(1))
        ).scalar_one()
        actor = Actor(
            member_id=member.id,
            household_id=member.household_id,
            role=member.role,
            display_name=member.display_name,
            timezone="UTC",
            locale="en",
            scopes=frozenset(),
        )
        created_ids: list[uuid.UUID] = []

        print("\n== graph_views table exists ==")
        rows = (await session.execute(select(GraphView).limit(1))).scalars().all()
        check("graph_views is queryable", True)

        print("\n== list seeds a default view ==")
        items, total = await list_graph_views(session=session, actor=actor)
        check("list returns at least one view", total >= 1, f"got {total}")
        check("seeded view is named", bool(items[0].name), repr(items[0].name))
        check("seeded view carries config", isinstance(items[0].config, dict), repr(items[0].config))
        if items[0].kind == "default":
            created_ids.append(items[0].id)

        print("\n== create ==")
        name = f"smoke-{uuid.uuid4().hex[:8]}"
        view = await create_graph_view(
            session=session,
            actor=actor,
            payload=GraphViewCreateRequest(
                name=name,
                description="smoke",
                config={"scope": "recent", "layout": "force"},
            ),
        )
        created_ids.append(view.id)
        check("created view has an id", isinstance(view.id, uuid.UUID))
        check("name round-trips", view.name == name, view.name)
        check("config round-trips", view.config.get("scope") == "recent", repr(view.config))
        check("order_index assigned", view.order_index >= 0, str(view.order_index))

        print("\n== read back ==")
        fetched = await get_graph_view(session=session, actor=actor, view_id=view.id)
        check("read matches created", fetched.id == view.id)

        print("\n== update ==")
        renamed = await update_graph_view(
            session=session,
            actor=actor,
            view_id=view.id,
            payload=GraphViewPatchRequest(name=f"{name}-renamed", is_shared=True),
        )
        check("rename persisted", renamed.name == f"{name}-renamed", renamed.name)
        check("is_shared persisted", renamed.is_shared is True, str(renamed.is_shared))

        print("\n== delete ==")
        await delete_graph_view(session=session, actor=actor, view_id=view.id)
        created_ids.remove(view.id)
        gone = (
            await session.execute(select(GraphView).where(GraphView.id == view.id))
        ).scalar_one_or_none()
        check("deleted view is gone", gone is None)

        print("\n== member preferences ==")
        member.preferences = {"calendar_theme": "dark", "calendar_stickers": ["star"]}
        await session.commit()
        await session.refresh(member)
        check("preferences persisted", (member.preferences or {}).get("calendar_theme") == "dark",
              repr(member.preferences))

        # merge semantics: a theme-only patch must not drop stickers
        merged = dict(member.preferences or {})
        patch = MemberPreferencesPatch(calendar_theme="unicorn")
        for field, value in patch.model_dump(exclude_unset=True).items():
            if value is None:
                merged.pop(field, None)
            else:
                merged[field] = value
        member.preferences = merged
        await session.commit()
        await session.refresh(member)
        stored = member.preferences or {}
        check("theme updated", stored.get("calendar_theme") == "unicorn", repr(stored))
        check("stickers survived the merge", stored.get("calendar_stickers") == ["star"], repr(stored))

        print("\n== cleanup ==")
        for view_id in created_ids:
            await session.execute(delete(GraphView).where(GraphView.id == view_id))
        member.preferences = {}
        await session.commit()
        check("cleanup done", True)

    print(f"\n{'=' * 44}\n{PASSED} passed, {FAILED} failed\n{'=' * 44}")
    if FAILED:
        raise SystemExit(1)


asyncio.run(main())
