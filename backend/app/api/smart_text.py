"""Smart Text preview and save endpoints for the agent workflow.

The operator's agent prepares messy text with magic tags around secrets, then
needs two things from FamilyOS:

1. **Preview** — cross-check: "you tagged N, but the rules found M more"
2. **Save** — verify: extract tagged values, write to vault, replace placeholders

Both are REST (the agent uses HTTP) and exposed as MCP tools.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.services import secret_detector, smart_text

router = APIRouter(prefix="/api/smart-text", tags=["smart-text"])


class PreviewRequest(BaseModel):
    """Text to scan for secrets (with or without magic tags)."""

    text: str = Field(..., description="The text to scan")


class SaveRequest(BaseModel):
    """Save a Smart Text block with magic-tagged secrets."""

    note_id: str = Field(..., description="The note to append the block to")
    text: str = Field(..., description="Text with [[secret]]…[[/secret]] around secrets")
    caption: str | None = Field(None, description="Optional caption for the block")
    secrets: list[smart_text.SecretInput] | None = Field(
        None,
        description="Explicit secret list. If omitted, secrets are extracted from magic tags.",
    )


class PreviewResponse(BaseModel):
    """Preview result: what the rules found, what's tagged, what's not."""

    findings: list[dict]
    untagged: list[dict]
    tagged_only: list[dict]
    placeholder_keys: list[str]
    counts: dict


class SaveResponse(BaseModel):
    """Save result: block created, secrets written to vault."""

    ok: bool
    block_id: str | None = None
    vault_path: str | None = None
    secrets: list[dict] = []
    message: str | None = None


@router.post("/preview", response_model=PreviewResponse)
async def preview_smart_text(req: PreviewRequest):
    """Scan text and report findings — the cross-check before saving.

    The agent sends its prepared text (with magic tags). The server runs the
    same detector as the browser and returns:

    - `findings` — all candidates (tagged + untagged)
    - `untagged` — secrets the rules found but the agent did not mark
    - `tagged_only` — magic-tagged values the rules would not have flagged
    - `placeholder_keys` — existing {{secret:…}} placeholders in the text

    The agent reviews `untagged` and either adds magic tags or confirms the
    text is complete.
    """
    if not req.text.strip():
        raise HTTPException(400, "Text is required")

    result = secret_detector.preview(req.text)
    return result.to_dict()


@router.post("/save", response_model=SaveResponse)
async def save_smart_text(
    req: SaveRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Save a Smart Text block with magic-tagged secrets.

    The flow:
    1. Detect all secrets (from magic tags and rules)
    2. Extract values from magic tags
    3. Write each value to the vault
    4. Replace every occurrence with {{secret:<key>}}
    5. Strip magic tag markers
    6. Create the Smart Text block

    If `secrets` is provided, those are used directly (bypassing magic tag
    extraction). If not, the server extracts from `[[secret]]…[[/secret]]`.
    """
    from app.schemas.notes import NoteBlockInput
    from app.services.notes import create_block

    import uuid

    if not req.text.strip():
        raise HTTPException(400, "Text is required")

    note_uuid = uuid.UUID(req.note_id)

    # Determine secrets: explicit list or extract from magic tags
    if req.secrets:
        secrets = [smart_text.SecretInput(**s) for s in req.secrets]
    else:
        findings = secret_detector.detect_secrets(req.text)
        tagged = [f for f in findings if f.manual]

        if not tagged:
            raise HTTPException(
                400,
                "No magic-tagged secrets found. Wrap secrets in [[secret]]…[[/secret]] "
                "or provide an explicit secrets list.",
            )

        secrets = [
            smart_text.SecretInput(
                label=f.label,
                value=f.value,
                type=f.type if f.type != "manual" else "other",
            )
            for f in tagged
        ]

    # Write secrets to vault and replace with placeholders
    text_content, built, vault_path = await smart_text.build_smart_text(
        note_id=note_uuid,
        text=req.text,
        secrets_in=secrets,
    )

    # Strip magic tag markers (values are now in the vault)
    text_content = secret_detector.strip_magic_tags(text_content)

    # Create the block
    block_input = NoteBlockInput(
        type="smart_text",
        text_content=text_content,
        caption=req.caption,
        data={"secrets": smart_text.secrets_index(built), "vault_path": vault_path},
    )

    block = await create_block(
        session=session,
        actor=actor,
        note_id=note_uuid,
        payload=block_input,
    )

    return SaveResponse(
        ok=True,
        block_id=str(block.id),
        vault_path=vault_path,
        secrets=[
            {
                "key": s.key,
                "label": s.label,
                "placeholder": s.placeholder,
            }
            for s in built
        ],
    )
