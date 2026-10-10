import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.models import Note, NoteRelation, Tag, note_tags
from app.schemas.graph import GraphEdge, GraphNode, GraphResponse
from app.services.notes import note_access_clause


def build_graph_note_statement(*, actor: Actor, scope: str, limit: int) -> Select[tuple[Note]]:
    statement = select(Note).where(
        Note.household_id == actor.household_id,
        Note.deleted_at.is_(None),
        note_access_clause(actor),
    )
    if scope == "recent":
        statement = statement.order_by(Note.updated_at.desc())
    elif scope.startswith("tag:"):
        tag_slug = scope.removeprefix("tag:").strip()
        statement = statement.where(
            Note.id.in_(
                select(note_tags.c.note_id)
                .join(Tag, Tag.id == note_tags.c.tag_id)
                .where(Tag.household_id == actor.household_id, Tag.slug == tag_slug)
            )
        )
    elif scope.startswith("member:"):
        member_id = uuid.UUID(scope.removeprefix("member:").strip())
        statement = statement.where(or_(Note.owner_member_id == member_id, Note.created_by == member_id))
    elif scope.startswith("note:"):
        note_id = uuid.UUID(scope.removeprefix("note:").strip())
        statement = statement.where(Note.id == note_id)
    elif scope.startswith("search:"):
        query = scope.removeprefix("search:").strip()
        if query:
            statement = statement.where(Note.search_tsv.op("@@")(func.websearch_to_tsquery("simple", query)))
    elif scope != "all":
        raise ValueError("Unsupported graph scope")
    if scope != "recent":
        statement = statement.order_by(Note.updated_at.desc())
    return statement.limit(limit)


async def get_graph(*, session: AsyncSession, actor: Actor, scope: str = "all", limit: int = 2000) -> GraphResponse:
    note_result = await session.execute(build_graph_note_statement(actor=actor, scope=scope, limit=limit))
    notes = list(note_result.scalars().all())
    note_ids = [note.id for note in notes]
    if not notes:
        return GraphResponse(nodes=[], edges=[], meta={"node_count": 0, "edge_count": 0, "truncated": False, "generated_at": datetime.now(UTC).isoformat()})

    tags_result = await session.execute(
        select(note_tags.c.note_id, Tag)
        .join(Tag, Tag.id == note_tags.c.tag_id)
        .where(note_tags.c.note_id.in_(note_ids), Tag.household_id == actor.household_id)
    )
    note_tags_map: dict[uuid.UUID, list[Tag]] = {note_id: [] for note_id in note_ids}
    for note_id, tag in tags_result.all():
        note_tags_map[note_id].append(tag)

    relation_result = await session.execute(
        select(NoteRelation)
        .join(Note, Note.id == NoteRelation.from_note_id)
        .where(
            Note.household_id == actor.household_id,
            NoteRelation.from_note_id.in_(note_ids),
            NoteRelation.to_note_id.in_(note_ids),
        )
    )
    relations = list(relation_result.scalars().all())

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    tag_nodes: dict[uuid.UUID, Tag] = {}
    for note in notes:
        note_key = f"note:{note.id}"
        tags = note_tags_map[note.id]
        nodes.append(
            GraphNode(
                id=note_key,
                type="note",
                label=(note.title or "Untitled note")[:160],
                note_type=note.type,
                pinned=note.pinned,
                tags=[tag.slug for tag in tags],
            )
        )
        if note.parent_note_id in note_ids:
            edges.append(
                GraphEdge(
                    id=f"hierarchy:{note.parent_note_id}:{note.id}",
                    source=f"note:{note.parent_note_id}",
                    target=note_key,
                    type="hierarchy",
                    relation_type="parent",
                )
            )
        for tag in tags:
            tag_nodes[tag.id] = tag
            edges.append(
                GraphEdge(
                    id=f"tag:{note.id}:{tag.id}",
                    source=note_key,
                    target=f"tag:{tag.id}",
                    type="tag",
                )
            )

    nodes.extend(
        GraphNode(id=f"tag:{tag.id}", type="tag", label=f"#{tag.slug}")
        for tag in tag_nodes.values()
    )
    edges.extend(
        GraphEdge(
            id=f"relation:{relation.id}",
            source=f"note:{relation.from_note_id}",
            target=f"note:{relation.to_note_id}",
            type="relation",
            relation_type=relation.relation_type,
        )
        for relation in relations
    )
    return GraphResponse(
        nodes=nodes,
        edges=edges,
        meta={
            "node_count": len(nodes),
            "edge_count": len(edges),
            "truncated": len(notes) == limit,
            "generated_at": datetime.now(UTC).isoformat(),
        },
    )