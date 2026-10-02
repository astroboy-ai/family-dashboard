"""Hybrid retrieval: keyword (FTS) + semantic (pgvector), fused with RRF.

The two channels fail in opposite directions — FTS misses paraphrase and
cross-language matches, vectors miss exact identifiers (order numbers, names,
dates) — so we run both and fuse the *rankings* rather than the scores:

    RRF(d) = Σ 1 / (k + rank_i(d))          k = 60

Scores are never combined directly because BM25 ``ts_rank_cd`` and cosine
distance are on unrelated scales and need normalisation that would have to be
retuned per corpus.

Access control is applied **inside** the SQL for every channel, never after
retrieval, so a caller cannot receive a row it is not allowed to see even if the
ranking logic is wrong.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import Float, Select, func, or_, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession
from pgvector.sqlalchemy import Vector

from app.api.deps import Actor
from app.core.text import build_query_text
from app.models import Embedding, Note, NoteBlock
from app.services.notes import note_access_clause

RRF_K = 60
DEFAULT_CHANNEL_LIMIT = 50


@dataclass
class Candidate:
    """One note plus the evidence for why it ranked where it did."""

    note_id: uuid.UUID
    keyword_rank: int | None = None
    semantic_rank: int | None = None
    score: float = 0.0
    sources: list[str] = field(default_factory=list)

    def add_keyword(self, rank: int) -> None:
        self.keyword_rank = rank
        if "keyword" not in self.sources:
            self.sources.append("keyword")

    def add_semantic(self, rank: int) -> None:
        self.semantic_rank = rank
        if "semantic" not in self.sources:
            self.sources.append("semantic")


def _fuse(candidates: dict[uuid.UUID, Candidate]) -> list[Candidate]:
    for candidate in candidates.values():
        score = 0.0
        if candidate.keyword_rank is not None:
            score += 1.0 / (RRF_K + candidate.keyword_rank)
        if candidate.semantic_rank is not None:
            score += 1.0 / (RRF_K + candidate.semantic_rank)
        candidate.score = score
    return sorted(candidates.values(), key=lambda item: item.score, reverse=True)


def keyword_statement(
    *,
    actor: Actor,
    query: str,
    limit: int = DEFAULT_CHANNEL_LIMIT,
    types: list[str] | None = None,
    statuses: list[str] | None = None,
    visibility: list[str] | None = None,
    member_ids: list[uuid.UUID] | None = None,
) -> Select[tuple[uuid.UUID]]:
    """Notes matching *query* through the tokenized FTS columns."""

    tokenized = build_query_text(query)
    tsquery = func.websearch_to_tsquery("simple", tokenized)

    block_match = (
        select(NoteBlock.id)
        .where(NoteBlock.note_id == Note.id, NoteBlock.search_tsv.op("@@")(tsquery))
        .exists()
    )

    statement = (
        select(Note.id)
        .where(
            Note.household_id == actor.household_id,
            Note.deleted_at.is_(None),
            note_access_clause(actor),
            or_(Note.search_tsv.op("@@")(tsquery), block_match),
        )
        .order_by(func.ts_rank_cd(Note.search_tsv, tsquery).desc(), Note.updated_at.desc())
        .limit(limit)
    )

    if types:
        statement = statement.where(Note.type.in_(types))
    if statuses:
        statement = statement.where(Note.status.in_(statuses))
    if visibility:
        statement = statement.where(Note.visibility.in_(visibility))
    if member_ids:
        statement = statement.where(
            or_(Note.created_by.in_(member_ids), Note.owner_member_id.in_(member_ids))
        )
    return statement


def semantic_statement(
    *,
    actor: Actor,
    query_vector: list[float],
    dim: int,
    limit: int = DEFAULT_CHANNEL_LIMIT,
    types: list[str] | None = None,
    statuses: list[str] | None = None,
    visibility: list[str] | None = None,
    member_ids: list[uuid.UUID] | None = None,
) -> Select[tuple[uuid.UUID, float]]:
    """Notes whose nearest embedding is closest to *query_vector*.

    Only rows from the active embedding generation are considered
    (``is_active`` and ``dim``), because comparing vectors produced by different
    models yields meaningless distances.

    The cast in ``ORDER BY`` matches the partial expression HNSW index
    ``((embedding::vector(N)) vector_cosine_ops) WHERE dim = N AND is_active``,
    so the planner can use the index rather than scanning every row.
    """

    # pgvector's `<=>` returns a float, but SQLAlchemy infers the *left*
    # operand's type (Vector), so the result processor would try to parse the
    # distance as a vector and crash. Coerce the expression to Float explicitly.
    cast_distance = type_coerce(
        func.cast(Embedding.embedding, Vector(dim)).op("<=>")(query_vector),
        Float,
    )

    # A note may have several chunks; keep its best-scoring one.
    best_per_note = (
        select(
            Embedding.owner_id.label("note_id"),
            func.min(cast_distance).label("distance"),
        )
        .where(
            Embedding.household_id == actor.household_id,
            Embedding.is_active.is_(True),
            Embedding.dim == dim,
            Embedding.owner_type == "note",
        )
        .group_by(Embedding.owner_id)
        .subquery()
    )

    statement = (
        select(Note.id, best_per_note.c.distance)
        .join(best_per_note, best_per_note.c.note_id == Note.id)
        .where(
            Note.household_id == actor.household_id,
            Note.deleted_at.is_(None),
            note_access_clause(actor),
        )
        .order_by(best_per_note.c.distance.asc())
        .limit(limit)
    )

    if types:
        statement = statement.where(Note.type.in_(types))
    if statuses:
        statement = statement.where(Note.status.in_(statuses))
    if visibility:
        statement = statement.where(Note.visibility.in_(visibility))
    if member_ids:
        statement = statement.where(
            or_(Note.created_by.in_(member_ids), Note.owner_member_id.in_(member_ids))
        )
    return statement


async def hybrid_search(
    *,
    session: AsyncSession,
    actor: Actor,
    query: str,
    query_vector: list[float] | None = None,
    dim: int | None = None,
    mode: str = "hybrid",
    limit: int = 50,
    channel_limit: int = DEFAULT_CHANNEL_LIMIT,
    **filters: object,
) -> dict[str, object]:
    """Run the requested channel(s) and return fused note ids with evidence."""

    if mode not in {"keyword", "semantic", "hybrid"}:
        raise ValueError(f"unsupported search mode: {mode}")

    candidates: dict[uuid.UUID, Candidate] = {}
    timings: dict[str, float] = {}

    if mode in {"keyword", "hybrid"} and query.strip():
        statement = keyword_statement(
            actor=actor, query=query, limit=channel_limit, **filters  # type: ignore[arg-type]
        )
        rows = (await session.execute(statement)).scalars().all()
        for rank, note_id in enumerate(rows, start=1):
            candidates.setdefault(note_id, Candidate(note_id=note_id)).add_keyword(rank)

    if mode in {"semantic", "hybrid"} and query_vector and dim:
        statement = semantic_statement(
            actor=actor,
            query_vector=query_vector,
            dim=dim,
            limit=channel_limit,
            **filters,  # type: ignore[arg-type]
        )
        rows = (await session.execute(statement)).all()
        for rank, (note_id, _distance) in enumerate(rows, start=1):
            candidates.setdefault(note_id, Candidate(note_id=note_id)).add_semantic(rank)

    fused = _fuse(candidates)[:limit]

    return {
        "items": [
            {
                "note_id": candidate.note_id,
                "score": candidate.score,
                "sources": candidate.sources,
                "keyword_rank": candidate.keyword_rank,
                "semantic_rank": candidate.semantic_rank,
            }
            for candidate in fused
        ],
        "mode": mode,
        "candidates": len(candidates),
        "timings": timings,
    }
