import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor
from app.core.errors import AppError
from app.models import Note, Tag, TagAuditLog, TagProposal, note_tags
from app.schemas.notes import TagProposalInput, TagProposalResponse
from app.services.notes import _get_note, get_excluded_tag_slugs


def normalize_proposed_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    slug = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        raise AppError("Tag proposal must contain letters or numbers", error_code="invalid_tag")
    return slug[:120]


async def propose_tags(
    *,
    session: AsyncSession,
    actor: Actor,
    note_id: uuid.UUID,
    candidates: list[TagProposalInput],
) -> list[TagProposalResponse]:
    note = await _get_note(session=session, actor=actor, note_id=note_id, write=True)
    excluded = await get_excluded_tag_slugs(session=session, actor=actor, note=note)
    candidates_by_slug: dict[str, TagProposalInput] = {}
    for candidate in candidates:
        slug = normalize_proposed_slug(candidate.slug)
        if slug not in excluded:
            candidates_by_slug.setdefault(slug, candidate)
        if len(candidates_by_slug) == 5:
            break

    created: list[TagProposal] = []
    for slug, candidate in candidates_by_slug.items():
        tag_result = await session.execute(
            select(Tag).where(Tag.household_id == actor.household_id, Tag.slug == slug)
        )
        tag = tag_result.scalar_one_or_none()
        if tag is not None:
            association = await session.execute(
                select(note_tags.c.note_id).where(note_tags.c.note_id == note.id, note_tags.c.tag_id == tag.id)
            )
            if association.first() is not None:
                continue
        proposal = TagProposal(
            id=uuid.uuid4(),
            household_id=actor.household_id,
            note_id=note.id,
            tag_id=tag.id if tag is not None else None,
            proposed_slug=slug,
            proposed_kind=candidate.kind,
            proposed_namespace=candidate.namespace,
            confidence=candidate.confidence,
            evidence=candidate.evidence,
            model=candidate.model,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(days=30),
            created_at=datetime.now(UTC),
        )
        session.add(proposal)
        created.append(proposal)
        session.add(
            TagAuditLog(
                id=uuid.uuid4(),
                household_id=actor.household_id,
                actor_type="ai",
                actor_id=None,
                action="tag_proposed",
                note_id=note.id,
                tag_slug=slug,
                after={"confidence": candidate.confidence, "evidence": candidate.evidence},
            )
        )

    await session.commit()
    return [TagProposalResponse.model_validate(proposal) for proposal in created]


async def list_pending_tag_proposals(
    *, session: AsyncSession, actor: Actor, note_id: uuid.UUID | None = None
) -> list[TagProposalResponse]:
    if actor.role != "parent" or "notes.read" not in actor.scopes:
        raise AppError("Permission denied", status_code=403, error_code="permission_denied")
    statement = select(TagProposal).where(
        TagProposal.household_id == actor.household_id,
        TagProposal.status == "pending",
    )
    if note_id is not None:
        statement = statement.where(TagProposal.note_id == note_id)
    result = await session.execute(statement.order_by(TagProposal.created_at.desc()).limit(100))
    return [TagProposalResponse.model_validate(proposal) for proposal in result.scalars().all()]


async def decide_tag_proposal(
    *,
    session: AsyncSession,
    actor: Actor,
    proposal_id: uuid.UUID,
    accepted: bool,
) -> TagProposalResponse:
    if actor.role != "parent" or "notes.write" not in actor.scopes:
        raise AppError("Permission denied", status_code=403, error_code="permission_denied")
    result = await session.execute(
        select(TagProposal)
        .where(
            TagProposal.id == proposal_id,
            TagProposal.household_id == actor.household_id,
            TagProposal.status == "pending",
        )
        .with_for_update()
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise AppError("Tag proposal not found", status_code=404, error_code="not_found")
    note_result = await session.execute(
        select(Note).where(
            Note.id == proposal.note_id,
            Note.household_id == actor.household_id,
            Note.deleted_at.is_(None),
        )
    )
    note = note_result.scalar_one_or_none()
    if note is None:
        raise AppError("Note not found", status_code=404, error_code="not_found")

    if accepted and proposal.proposed_slug in await get_excluded_tag_slugs(
        session=session,
        actor=actor,
        note=note,
    ):
        raise AppError(
            "This tag is excluded for the note and cannot be applied",
            status_code=409,
            error_code="tag_excluded",
        )

    now = datetime.now(UTC)
    proposal.status = "accepted" if accepted else "rejected"
    proposal.decided_by = actor.member_id
    proposal.decided_at = now
    if accepted:
        tag_result = await session.execute(
            select(Tag).where(Tag.household_id == actor.household_id, Tag.slug == proposal.proposed_slug)
        )
        tag = tag_result.scalar_one_or_none()
        if tag is None:
            tag = Tag(
                id=uuid.uuid4(),
                household_id=actor.household_id,
                name=proposal.proposed_slug.replace("-", " "),
                slug=proposal.proposed_slug,
                kind=proposal.proposed_kind,
                namespace=proposal.proposed_namespace,
                proposed=False,
                proposed_by="ai",
                last_used_at=now,
            )
            session.add(tag)
        await session.execute(
            pg_insert(note_tags)
            .values(
                note_id=note.id,
                tag_id=tag.id,
                source="ai",
                confidence=proposal.confidence,
                model=proposal.model,
                evidence=proposal.evidence,
                applied_at=now,
                applied_by=actor.member_id,
                approved_by_human=True,
            )
            .on_conflict_do_nothing()
        )
    else:
        # Rejected → write a note-level exclusion so the AI never proposes
        # this tag for this note again.
        from app.models import TagExclusion

        existing_exclusion = (
            await session.execute(
                select(TagExclusion).where(
                    TagExclusion.household_id == actor.household_id,
                    TagExclusion.tag_slug == proposal.proposed_slug,
                    TagExclusion.scope == "note",
                    TagExclusion.scope_ref == note.id,
                )
            )
        ).scalar_one_or_none()
        if existing_exclusion is None:
            session.add(
                TagExclusion(
                    household_id=actor.household_id,
                    tag_slug=proposal.proposed_slug,
                    scope="note",
                    scope_ref=note.id,
                    reason="user_rejected",
                    created_by=actor.member_id,
                )
            )
    session.add(
        TagAuditLog(
            id=uuid.uuid4(),
            household_id=actor.household_id,
            actor_type="human",
            actor_id=actor.member_id,
            action="proposal_accepted" if accepted else "proposal_rejected",
            note_id=note.id,
            tag_slug=proposal.proposed_slug,
            after={"proposal_id": str(proposal.id)},
        )
    )
    await session.commit()
    return TagProposalResponse.model_validate(proposal)