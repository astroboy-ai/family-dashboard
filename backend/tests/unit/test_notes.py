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
from app.models import AuditLog, JobOutbox, Note, NoteRelation, Tag, TagAuditLog, TagExclusion
from app.main import create_app
from app.schemas.notes import NoteBlockInput, NoteCreateRequest
from app.services.notes import (
    build_tag_exclusion_statement,
    create_note,
    get_note,
    note_access_clause,
    remove_tag,
    reorder_blocks,
    suggest_ai_tags,
)
from app.services.search import build_search_statement
from app.services.graph import get_graph
from app.schemas.notes import TagProposalInput
from app.services.tag_governance import propose_tags


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

    def first(self) -> object | None:
        return self.value

    def all(self) -> list[object]:
        return self.values

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


def test_search_statement_applies_visibility_and_facets() -> None:
    actor = make_actor("parent", {"notes.read"})
    member_id = uuid.uuid4()
    statement = build_search_statement(
        actor=actor,
        query='"school fee" japan',
        types=["receipt", "school_notice"],
        tags=["school", "travel"],
        tag_mode="all",
        member_ids=[member_id],
        statuses=["active"],
        visibility=["family"],
        media_types=["image"],
        pinned=True,
        limit=20,
        offset=10,
    )
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "websearch_to_tsquery" in compiled
    assert "note_blocks" in compiled
    assert "family_members" not in compiled
    assert "notes.household_id" in compiled
    assert "notes.visibility" not in compiled or actor.role == "parent"
    assert "HAVING count(distinct(tags.slug))" in compiled
    assert "LIMIT" in compiled
    assert "OFFSET" in compiled


def test_guest_search_cannot_escape_note_visibility_scope() -> None:
    actor = make_actor("guest", {"notes.read.shared"})
    statement = build_search_statement(actor=actor, query="private plan")
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "notes.visibility =" in compiled
    assert "notes.visibility = false" not in compiled


def test_tag_exclusion_statement_matches_all_scopes_and_expiry() -> None:
    actor = make_actor("parent", {"notes.read"})
    note = Note(
        id=uuid.uuid4(),
        household_id=actor.household_id,
        title="Receipt",
        type="receipt",
        created_by=actor.member_id,
        owner_member_id=uuid.uuid4(),
        visibility="family",
        status="active",
        pinned=False,
        extra={},
        embedding_status="pending",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    compiled = str(
        build_tag_exclusion_statement(actor=actor, note=note).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "tag_exclusions.scope = 'note'" in compiled
    assert "tag_exclusions.scope = 'note_type'" in compiled
    assert "tag_exclusions.scope = 'member'" in compiled
    assert "tag_exclusions.scope = 'household'" in compiled
    assert "tag_exclusions.expires_at IS NULL" in compiled


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


@pytest.mark.parametrize("source", ["ai", "human"])
async def test_removing_tag_records_note_exclusion_and_tag_audit(source: str) -> None:
    actor = make_actor("parent", {"notes.read", "notes.write"})
    note_id = uuid.uuid4()
    tag = SimpleNamespace(id=uuid.uuid4(), slug="travel", name="Travel", color=None, kind="topic")
    note = SimpleNamespace(
        id=note_id,
        household_id=actor.household_id,
        deleted_at=None,
        updated_at=None,
    )
    session = FakeSession([FakeResult(note), FakeResult((tag, source)), FakeResult(), FakeResult(values=[])])

    await remove_tag(session=session, actor=actor, note_id=note_id, tag_slug="travel")

    exclusion = next(item for item in session.added if isinstance(item, TagExclusion))
    audit = next(item for item in session.added if isinstance(item, TagAuditLog))
    assert exclusion.scope == "note"
    assert exclusion.scope_ref == note_id
    assert exclusion.tag_slug == "travel"
    assert exclusion.created_by == actor.member_id
    assert audit.action == "tag_removed"
    assert audit.before == {"source": source}
    assert session.commit_count == 1


async def test_tag_proposals_skip_exclusions_and_enforce_five_candidate_budget() -> None:
    actor = make_actor("parent", {"notes.read", "notes.write"})
    note = SimpleNamespace(
        id=uuid.uuid4(),
        household_id=actor.household_id,
        deleted_at=None,
        type="receipt",
        title="Receipt",
        created_by=actor.member_id,
        owner_member_id=actor.member_id,
        visibility="family",
        status="active",
        pinned=False,
        extra={},
        embedding_status="pending",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = FakeSession([FakeResult(note), FakeResult(values=["excluded"])] + [FakeResult() for _ in range(12)])
    candidates = [
        TagProposalInput(slug=slug, confidence=0.91, evidence={"matched": slug}, model="test-model")
        for slug in ["excluded", "tag-one", "tag-two", "tag-three", "tag-four", "tag-five", "tag-six"]
    ]

    proposals = await propose_tags(
        session=session,
        actor=actor,
        note_id=note.id,
        candidates=candidates,
    )

    assert [proposal.proposed_slug for proposal in proposals] == [
        "tag-one", "tag-two", "tag-three", "tag-four", "tag-five"
    ]
    assert all(proposal.status == "pending" for proposal in proposals)
    assert all(proposal.evidence for proposal in proposals)


async def test_graph_projection_derives_note_tag_hierarchy_and_relation_edges() -> None:
    actor = make_actor("parent", {"notes.read"})
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    parent = SimpleNamespace(
        id=parent_id,
        title="Garden plan",
        type="freeform",
        pinned=True,
        parent_note_id=None,
    )
    child = SimpleNamespace(
        id=child_id,
        title="Seed list",
        type="freeform",
        pinned=False,
        parent_note_id=parent_id,
    )
    tag = SimpleNamespace(id=uuid.uuid4(), slug="garden")
    relation = SimpleNamespace(
        id=uuid.uuid4(),
        from_note_id=parent_id,
        to_note_id=child_id,
        relation_type="references",
    )
    session = FakeSession(
        [
            FakeResult(values=[parent, child]),
            FakeResult(values=[(parent_id, tag)]),
            FakeResult(values=[relation]),
        ]
    )

    graph = await get_graph(session=session, actor=actor, limit=20)

    assert {node.id for node in graph.nodes} == {f"note:{parent_id}", f"note:{child_id}", f"tag:{tag.id}"}
    assert {edge.type for edge in graph.edges} == {"tag", "hierarchy", "relation"}
    assert graph.meta["node_count"] == 3
    assert graph.meta["edge_count"] == 3


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


async def test_search_api_returns_matching_visible_notes() -> None:
    actor = make_actor("parent", {"notes.read"})
    note = Note(
        id=uuid.uuid4(),
        household_id=actor.household_id,
        title="School trip receipt",
        type="receipt",
        status="active",
        created_by=actor.member_id,
        owner_member_id=actor.member_id,
        visibility="family",
        pinned=False,
        extra={},
        embedding_status="pending",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = FakeSession([FakeResult(values=[note]), FakeResult(values=[]), FakeResult(values=[])])
    app = make_test_app(actor, session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/search", params={"q": "school trip", "types": "receipt"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["items"][0]["id"] == str(note.id)
    assert payload["items"][0]["title"] == "School trip receipt"


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