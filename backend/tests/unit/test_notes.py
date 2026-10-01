from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy.dialects import postgresql
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.core.errors import AppError
from app.models import AuditLog, JobOutbox, Note
from app.main import create_app
from app.schemas.notes import NoteBlockInput, NoteCreateRequest
from app.services.notes import (
    create_note,
    get_note,
    note_access_clause,
    reorder_blocks,
    suggest_ai_tags,
)


class FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class FakeResult:
    def __init__(self, value: object | None = None, values: list[object] | None = None) -> None:
        self.value = value
        self.values = values or ([] if value is None else [value])

    def scalar_one_or_none(self) -> object | None:
        return self.value

    def scalars(self) -> FakeScalars:
        return FakeScalars(self.values)


class FakeSession:
    def __init__(self, results: list[FakeResult] | None = None) -> None:
        self.results = list(results or [])
        self.added: list[object] = []
        self.commit_count = 0
        self.flush_count = 0

    async def execute(self, _: object) -> FakeResult:
        return self.results.pop(0) if self.results else FakeResult()

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def commit(self) -> None:
        self.commit_count += 1

    async def delete(self, _: object) -> None:
        return None


def make_actor(role: str, scopes: set[str]) -> Actor:
    return Actor(
        member_id=uuid.uuid4(),
        household_id=uuid.uuid4(),
        role=role,
        display_name=role.title(),
        timezone="Asia/Hong_Kong",
        locale="en",
        scopes=frozenset(scopes),
    )


def test_child_visibility_allows_family_and_own_private_notes_only() -> None:
    actor = make_actor("child", {"notes.read.own"})

    sql = str(
        note_access_clause(actor).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "visibility = 'family'" in sql
    assert "visibility = 'private'" in sql
    assert "created_by" in sql
    assert "owner_member_id" in sql
    assert "parents" not in sql


def test_guest_without_shared_scope_cannot_read_notes() -> None:
    actor = make_actor("guest", set())

    assert str(note_access_clause(actor)) == "false"


async def test_create_note_persists_block_and_normalized_tag() -> None:
    actor = make_actor("child", {"notes.write.own"})
    session = FakeSession([FakeResult(), FakeResult()])
    payload = NoteCreateRequest(
        title="Maths homework",
        blocks=[NoteBlockInput(type="text", text_content="Fractions")],
        tags=["  School   Fees  "],
    )

    response = await create_note(session=session, actor=actor, payload=payload)

    assert response.title == "Maths homework"
    assert response.owner_member_id == actor.member_id
    assert response.created_by == actor.member_id
    assert response.blocks[0].order_index == 1000
    assert response.blocks[0].text_content == "Fractions"
    assert response.tags[0].name == "School Fees"
    assert response.tags[0].slug == "school-fees"
    assert session.commit_count == 1
    assert sum(isinstance(item, JobOutbox) for item in session.added) == 1
    assert sum(isinstance(item, AuditLog) for item in session.added) == 1


async def test_create_note_accepts_drawing_block_with_thumbnail() -> None:
    actor = make_actor("parent", {"notes.write"})
    session = FakeSession([FakeResult(), FakeResult()])
    thumb_id = uuid.uuid4()
    payload = NoteCreateRequest(
        title="Garden plan",
        blocks=[
            NoteBlockInput(
                type="drawing",
                text_content="Chalkboard plan for raised beds",
                thumb_media_id=thumb_id,
                data={
                    "theme": "chalkboard_green",
                    "strokes": [{"id": "s1", "points": [[10, 20, 0.5], [15, 25, 0.6]]}],
                },
            )
        ],
    )

    response = await create_note(session=session, actor=actor, payload=payload)

    assert response.blocks[0].type == "drawing"
    assert response.blocks[0].thumb_media_id == thumb_id
    assert response.blocks[0].text_content == "Chalkboard plan for raised beds"
    assert response.blocks[0].data["theme"] == "chalkboard_green"
    assert session.commit_count == 1


def test_suggest_ai_tags_uses_note_context() -> None:
    suggestions = suggest_ai_tags(
        "School field trip to Japan",
        "Packing list for flights, snacks, and tourist spots in Kyoto.",
        existing=["family"],
    )

    assert "travel" in suggestions
    assert "school" in suggestions
    assert "family" not in suggestions
    assert suggestions[0] == "travel"


async def test_reorder_requires_every_block_exactly_once() -> None:
    actor = make_actor("parent", {"notes.read", "notes.write"})
    note_id = uuid.uuid4()
    block_a_id = uuid.uuid4()
    block_b_id = uuid.uuid4()
    note = SimpleNamespace(
        id=note_id,
        household_id=actor.household_id,
        deleted_at=None,
        updated_at=None,
    )
    block_a = SimpleNamespace(id=block_a_id, note_id=note_id, order_index=1000)
    block_b = SimpleNamespace(id=block_b_id, note_id=note_id, order_index=2000)
    session = FakeSession([FakeResult(note), FakeResult(values=[block_a, block_b])])

    with pytest.raises(AppError, match="every block") as error:
        await reorder_blocks(
            session=session,
            actor=actor,
            note_id=note_id,
            block_ids=[block_a_id],
        )

    assert error.value.error_code == "invalid_block_order"
    assert session.commit_count == 0


async def test_reorder_moves_all_blocks_in_requested_order() -> None:
    actor = make_actor("parent", {"notes.read", "notes.write"})
    note_id = uuid.uuid4()
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    note = SimpleNamespace(
        id=note_id,
        household_id=actor.household_id,
        deleted_at=None,
        updated_at=None,
    )
    block_defaults = {
        "type": "text",
        "text_content": None,
        "media_asset_id": None,
        "data": {},
        "caption": None,
        "ai_description": None,
        "ocr_text": None,
        "transcript": None,
        "expires_at": None,
        "importance": 0,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    first = SimpleNamespace(id=first_id, note_id=note_id, order_index=1000, **block_defaults)
    second = SimpleNamespace(id=second_id, note_id=note_id, order_index=2000, **block_defaults)
    session = FakeSession([FakeResult(note), FakeResult(values=[first, second])])

    reordered = await reorder_blocks(
        session=session,
        actor=actor,
        note_id=note_id,
        block_ids=[second_id, first_id],
    )

    assert [block.id for block in reordered] == [second_id, first_id]
    assert [block.order_index for block in reordered] == [1000, 2000]
    assert session.flush_count == 1
    assert session.commit_count == 1


async def test_hidden_note_is_reported_as_not_found() -> None:
    actor = make_actor("guest", {"notes.read.shared"})
    session = FakeSession([FakeResult()])

    with pytest.raises(AppError) as error:
        await get_note(session=session, actor=actor, note_id=uuid.uuid4())

    assert error.value.status_code == 404
    assert error.value.error_code == "not_found"


async def test_child_cannot_write_another_members_note() -> None:
    actor = make_actor("child", {"notes.write.own"})
    session = FakeSession([FakeResult()])

    with pytest.raises(AppError) as error:
        await get_note(session=session, actor=actor, note_id=uuid.uuid4())

    assert error.value.status_code == 404


def make_test_app(actor: Actor, session: FakeSession) -> FastAPI:
    async def unused_probe() -> None:
        return None

    app = create_app(readiness_probes={"database": unused_probe})

    async def override_session() -> AsyncIterator[FakeSession]:
        yield session

    app.dependency_overrides[get_current_actor] = lambda: actor
    app.dependency_overrides[get_session] = override_session
    return app


async def test_create_note_api_returns_note_and_block() -> None:
    actor = make_actor("parent", {"notes.read", "notes.write"})
    session = FakeSession()
    app = make_test_app(actor, session)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/notes",
            json={
                "title": "Family plan",
                "blocks": [{"type": "text", "text_content": "First block"}],
                "tags": ["Planning"],
            },
        )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["title"] == "Family plan"
    assert data["blocks"][0]["text_content"] == "First block"
    assert data["blocks"][0]["order_index"] == 1000
    assert data["tags"][0]["slug"] == "planning"
    assert session.commit_count == 1


async def test_guest_cannot_read_private_note_api() -> None:
    actor = make_actor("guest", {"notes.read.shared"})
    session = FakeSession([FakeResult()])
    app = make_test_app(actor, session)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/notes/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_note_patch_and_soft_delete_api() -> None:
    actor = make_actor("parent", {"notes.read", "notes.write"})
    note = Note(
        id=uuid.uuid4(),
        household_id=actor.household_id,
        title="Before",
        type="freeform",
        status="inbox",
        created_by=actor.member_id,
        owner_member_id=actor.member_id,
        visibility="family",
        pinned=False,
        extra={},
        embedding_status="pending",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = FakeSession(
        [FakeResult(note), FakeResult(values=[]), FakeResult(values=[]), FakeResult(note)]
    )
    app = make_test_app(actor, session)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        patched = await client.patch(
            f"/api/notes/{note.id}",
            json={"title": "After", "pinned": True},
        )
        deleted = await client.delete(f"/api/notes/{note.id}")

    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "After"
    assert patched.json()["pinned"] is True
    assert deleted.status_code == 204
    assert note.deleted_at is not None
    assert session.commit_count == 2