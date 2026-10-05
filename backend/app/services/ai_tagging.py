"""AI-powered metadata extraction and tag proposal.

Single LLM call per note that:
1. Extracts structured metadata (occurred_at, owner_member_id, location, type)
2. Proposes tags with confidence + evidence

The LLM returns JSON; we parse it and write to the appropriate fields.
Metadata goes into existing note columns (not tags).
Tags go into tag_proposals for human review.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FamilyMember, Household, Note, Tag, TagExclusion, TagProposal
from app.schemas.notes import TagProposalInput, TagProposalResponse
from app.services.ai_settings import AiSettings, resolve_ai_settings
from app.services.notes import get_excluded_tag_slugs
from app.services.tag_governance import propose_tags

logger = structlog.get_logger(__name__)

PROMPT_VERSION = "tag-v1"
MAX_TAGS = 8
LLM_TIMEOUT = 45.0


# ── Prompt ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a family knowledge system classifier. You receive a note with its blocks and existing tags, and you return JSON with two sections:

1. "metadata" — structured fields extracted from the note:
   - occurred_at: ISO 8601 datetime string or null (when the event/thing happened, not when the note was written)
   - owner_member_id: string UUID or null (the family member this note is about, if identifiable from context)
   - location: object with {name, latitude?, longitude?} or null
   - type: one of "freeform", "recipe", "receipt", "event", "reminder", "note", "document", "photo", "drawing", "table", "link", "audio", "video"

2. "tags" — array of up to 8 proposed tags, each with:
   - slug: lowercase-hyphenated tag name (e.g. "dinner-recipe", "emma-favourite")
   - confidence: 0.0 to 1.0
   - reason: one-line explanation of why this tag fits
   - kind: "topic" (general subject) or "facet" (specific attribute)
   - namespace: null (we use flat tags for now)

Rules:
- Prefer existing tags over new ones (check the provided existing tag list)
- Do not propose tags already on the note
- Do not propose tags in the exclusion list
- If a tag would only apply because of a single ambiguous word, lower confidence below 0.4
- For metadata: only fill fields you are confident about; use null when uncertain
- occurred_at: extract from text like "on 2026-10-15" or "next Tuesday" — convert to ISO 8601
- owner_member_id: only if the note explicitly mentions a family member by name AND that name matches the provided member list

Return ONLY valid JSON, no markdown fences, no extra text."""


def _build_user_prompt(
    note: Note,
    blocks: list[dict[str, Any]],
    existing_tags: list[str],
    members: list[dict[str, str]],
    excluded_slugs: set[str],
) -> str:
    parts = [f"Title: {note.title or '(no title'}"]
    if note.summary:
        parts.append(f"Summary: {note.summary}")

    # Block content (text, OCR, transcripts, AI descriptions)
    for i, block in enumerate(blocks):
        btype = block.get("type", "unknown")
        data = block.get("data", {})
        text_content = block.get("text_content") or data.get("text") or ""
        ocr_text = block.get("ocr_text") or ""
        ai_desc = block.get("ai_description") or ""
        transcript = block.get("transcript") or ""

        if btype == "text" and text_content:
            parts.append(f"Block {i} (text): {text_content[:500]}")
        elif btype == "table" and data.get("rows"):
            rows = data["rows"][:5]  # first 5 rows
            parts.append(f"Block {i} (table): {json.dumps(rows, ensure_ascii=False)[:500]}")
        elif btype == "drawing" and ai_desc:
            parts.append(f"Block {i} (drawing): {ai_desc[:200]}")
        elif btype == "photo" and ai_desc:
            parts.append(f"Block {i} (photo): {ai_desc[:200]}")
        elif btype == "link" and data.get("url"):
            parts.append(f"Block {i} (link): {data['url']}")
        elif btype == "audio" and transcript:
            parts.append(f"Block {i} (audio transcript): {transcript[:300]}")
        elif ocr_text:
            parts.append(f"Block {i} ({btype} OCR): {ocr_text[:300]}")

    if existing_tags:
        parts.append(f"Existing tags: {', '.join(existing_tags)}")
    if members:
        member_list = ", ".join(f"{m['name']} (id: {m['id']})" for m in members)
        parts.append(f"Family members: {member_list}")
    if excluded_slugs:
        parts.append(f"Excluded tags (never propose): {', '.join(sorted(excluded_slugs))}")

    return "\n\n".join(parts)


# ── LLM call ───────────────────────────────────────────────────────


async def _call_llm(
    settings: AiSettings,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Call the LLM and parse JSON response."""

    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 1200,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        response = await client.post(
            f"{settings.base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"LLM returned {response.status_code}: {response.text[:400]}"
        )

    body = response.json()
    choices = body.get("choices")
    if not choices:
        raise RuntimeError("LLM returned no choices")

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("LLM returned empty content")

    # Strip markdown fences if present
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"LLM returned invalid JSON: {error}. Content: {content[:300]}") from error


# ── Main entry point ────────────────────────────────────────────────


async def classify_note(
    session: AsyncSession,
    note: Note,
    *,
    actor_household_id: uuid.UUID,
) -> dict[str, Any]:
    """Classify a note: extract metadata + propose tags.

    Returns a dict with:
    - metadata: {occurred_at, owner_member_id, location, type}
    - tags: list of TagProposalInput
    - model: model name used
    """

    # Gather context — blocks are in a separate table
    from app.models import NoteBlock

    blocks_result = await session.execute(
        select(NoteBlock).where(NoteBlock.note_id == note.id).order_by(NoteBlock.order_index)
    )
    blocks = []
    for b in blocks_result.scalars().all():
        blocks.append({
            "type": b.type,
            "data": b.data or {},
            "ocr_text": b.ocr_text,
            "ai_description": b.ai_description,
            "transcript": b.transcript,
        })

    # Existing tags on this note
    existing_tags_result = await session.execute(
        select(Tag.slug)
        .join(Note.__table__.c.note_tags)
        .where(Note.__table__.c.note_tags.c.note_id == note.id)
    )
    existing_tags = list(existing_tags_result.scalars().all())

    # Family members
    members_result = await session.execute(
        select(FamilyMember.id, FamilyMember.name).where(
            FamilyMember.household_id == actor_household_id
        )
    )
    members = [{"id": str(m.id), "name": m.name} for m in members_result.all()]

    # Excluded tags — construct a minimal actor for the governance check
    from app.api.deps import Actor
    governance_actor = Actor(
        member_id=note.created_by or note.owner_member_id or uuid.UUID(int=0),
        household_id=actor_household_id,
        role="parent",
        display_name="AI Tagger",
        timezone="UTC",
        locale="en",
        scopes=frozenset({"notes.read", "notes.write"}),
    )
    excluded = await get_excluded_tag_slugs(
        session=session,
        actor=governance_actor,
        note=note,
    )

    # Build prompt
    user_prompt = _build_user_prompt(note, blocks, existing_tags, members, excluded)

    # Get AI settings
    household = await session.get(Household, actor_household_id)
    settings = resolve_ai_settings(household.settings if household else None)

    if not settings.enabled:
        logger.info("ai_tagging_skipped_disabled", note_id=str(note.id))
        return {"metadata": {}, "tags": [], "model": "disabled"}

    # Call LLM
    result = await _call_llm(settings, SYSTEM_PROMPT, user_prompt)

    # Parse metadata
    metadata = result.get("metadata", {}) or {}
    parsed_metadata: dict[str, Any] = {}

    # occurred_at
    occ = metadata.get("occurred_at")
    if occ and isinstance(occ, str):
        try:
            parsed_metadata["occurred_at"] = datetime.fromisoformat(occ.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    # owner_member_id
    owner = metadata.get("owner_member_id")
    if owner and isinstance(owner, str):
        try:
            parsed_metadata["owner_member_id"] = uuid.UUID(owner)
        except (ValueError, TypeError):
            pass

    # location
    loc = metadata.get("location")
    if loc and isinstance(loc, dict) and loc.get("name"):
        parsed_metadata["location"] = loc

    # type
    ntype = metadata.get("type")
    if ntype and isinstance(ntype, str):
        parsed_metadata["type"] = ntype

    # Parse tags
    raw_tags = result.get("tags", []) or []
    tag_inputs: list[TagProposalInput] = []
    for t in raw_tags[:MAX_TAGS]:
        if not isinstance(t, dict):
            continue
        slug = t.get("slug", "").strip().lower()
        if not slug or slug in excluded:
            continue
        if slug in existing_tags:
            continue
        confidence = float(t.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        reason = t.get("reason", "")
        kind = t.get("kind", "topic")
        if kind not in ("topic", "facet"):
            kind = "topic"
        tag_inputs.append(
            TagProposalInput(
                slug=slug,
                confidence=confidence,
                evidence={"reason": reason, "prompt_version": PROMPT_VERSION},
                model=settings.llm_model,
                kind=kind,
            )
        )

    return {
        "metadata": parsed_metadata,
        "tags": tag_inputs,
        "model": settings.llm_model,
    }


async def apply_metadata(
    session: AsyncSession,
    note: Note,
    metadata: dict[str, Any],
) -> None:
    """Apply extracted metadata to the note (only non-null fields)."""

    if "occurred_at" in metadata and metadata["occurred_at"] is not None:
        note.occurred_at = metadata["occurred_at"]
    if "owner_member_id" in metadata and metadata["owner_member_id"] is not None:
        note.owner_member_id = metadata["owner_member_id"]
    if "location" in metadata and metadata["location"] is not None:
        note.location = metadata["location"]
    if "type" in metadata and metadata["type"] is not None:
        note.type = metadata["type"]


async def create_tag_proposals_from_classification(
    session: AsyncSession,
    note: Note,
    *,
    actor_household_id: uuid.UUID,
    tag_inputs: list[TagProposalInput],
    model: str,
) -> list[TagProposalResponse]:
    """Create tag proposals from classification results.

    Uses the existing propose_tags() to handle dedup, exclusion, etc.
    """

    if not tag_inputs:
        return []

    # We need an Actor for propose_tags — construct a minimal one
    from app.api.deps import Actor

    actor = Actor(
        member_id=note.created_by or note.owner_member_id or uuid.UUID(int=0),
        household_id=actor_household_id,
        role="parent",
        display_name="AI Tagger",
        timezone="UTC",
        locale="en",
        scopes=frozenset({"notes.read", "notes.write"}),
    )

    proposals = await propose_tags(
        session=session,
        actor=actor,
        note_id=note.id,
        candidates=tag_inputs,
    )

    return proposals
