import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agent.registry import ToolContext, ToolResult, register
from app.core.errors import AppError
from app.services.media import store_agent_upload
from app.services.notes import (
    create_block,
    create_note,
    get_note,
    list_blocks,
    list_tags,
    note_access_clause,
)
from app.services.search import search_notes


class SearchNotesParams(BaseModel):
    model_config = {"extra": "forbid"}

    query: str = Field(default="", max_length=500)
    types: list[str] | None = None
    tags: list[str] | None = None
    statuses: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=50)


class NoteIdParams(BaseModel):
    note_id: uuid.UUID


class GetNoteParams(NoteIdParams):
    include_blocks: bool = True


class GetBlocksParams(NoteIdParams):
    types: list[str] | None = None


class NoParams(BaseModel):
    pass


class ExpiringItemsParams(BaseModel):
    days: int = Field(default=30, ge=1, le=365)
    types: list[str] | None = None


@register(
    name="search_notes",
    description="Search visible household notes by text, type, tag, and status.",
    category="notes",
    params=SearchNotesParams,
    permissions=("notes.read",),
)
async def search_notes_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = SearchNotesParams.model_validate(params)
    result = await search_notes(
        session=context.session,
        actor=context.actor,
        query=values.query,
        types=values.types,
        tags=values.tags,
        statuses=values.statuses,
        limit=values.limit,
        offset=0,
    )
    return ToolResult(ok=True, data=result["items"], meta={"count": len(result["items"])})


@register(
    name="get_note",
    description="Read one visible note, optionally including its blocks.",
    category="notes",
    params=GetNoteParams,
    permissions=("notes.read",),
)
async def get_note_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = GetNoteParams.model_validate(params)
    note = await get_note(session=context.session, actor=context.actor, note_id=values.note_id)
    if not values.include_blocks:
        note = note.model_copy(update={"blocks": []})
    return ToolResult(ok=True, data=note)


@register(
    name="get_blocks",
    description="Read blocks belonging to a visible note.",
    category="notes",
    params=GetBlocksParams,
    permissions=("notes.read",),
)
async def get_blocks_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    values = GetBlocksParams.model_validate(params)
    blocks = await list_blocks(session=context.session, actor=context.actor, note_id=values.note_id)
    if values.types:
        blocks = [block for block in blocks if block.type in values.types]
    return ToolResult(ok=True, data=blocks, meta={"count": len(blocks)})


@register(
    name="list_tags",
    description="List household tags visible to the requesting member.",
    category="notes",
    params=NoParams,
    permissions=("notes.read",),
)
async def list_tags_tool(_: BaseModel, context: ToolContext) -> ToolResult:
    tags = await list_tags(session=context.session, actor=context.actor)
    return ToolResult(ok=True, data=tags, meta={"count": len(tags)})


@register(
    name="get_expiring_items",
    description="List visible notes that expire within the next number of days.",
    category="expiry",
    params=ExpiringItemsParams,
    permissions=("notes.read",),
)
async def get_expiring_items_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.models import Note

    values = ExpiringItemsParams.model_validate(params)
    statement = (
        select(Note)
        .where(
            Note.household_id == context.actor.household_id,
            Note.deleted_at.is_(None),
            note_access_clause(context.actor),
            Note.expires_at.between(datetime.now(UTC), datetime.now(UTC) + timedelta(days=values.days)),
        )
    )
    if values.types:
        statement = statement.where(Note.type.in_(values.types))
    result = await context.session.execute(statement)
    notes = result.scalars().all()
    return ToolResult(ok=True, data=notes, meta={"count": len(notes)})


# ── Write tools ──────────────────────────────────────────────────────────────
#
# These require an explicit ``notes.write`` scope on the calling token. Minting
# a token with that scope is the operator's consent; there is no per-call
# confirmation prompt. Every call lands in ``agent_tool_calls`` for audit.


class UploadMediaParams(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime: str = Field(min_length=3, max_length=160)
    content_base64: str = Field(min_length=1)
    # Optional: an agent that already analysed the file (its own vision model)
    # passes the description here and no local vision call is queued.
    description: str | None = Field(default=None, max_length=8000)


class CreateNoteParams(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    type: str = Field(default="freeform", min_length=1, max_length=40)
    summary: str | None = None
    # The member this note is for. Omit for the household in general.
    owner_member_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    occurred_at: datetime | None = None
    blocks: list[dict] = Field(default_factory=list, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=30)


class AppendBlockParams(BaseModel):
    note_id: uuid.UUID
    type: str = Field(min_length=1, max_length=32)
    text_content: str | None = None
    media_asset_id: uuid.UUID | None = None
    data: dict = Field(default_factory=dict)
    caption: str | None = None
    expires_at: datetime | None = None
    importance: int = Field(default=0, ge=0, le=5)


@register(
    name="upload_media",
    description=(
        "Upload a file (image, PDF, any document) to the household store and get "
        "an asset_id to attach to a note block. Pass the file base64-encoded. If "
        "you have already analysed the file with your own vision model, put that "
        "text in `description` and the system will not analyse it again."
    ),
    category="media",
    params=UploadMediaParams,
    permissions=("notes.write",),
    mutates=True,
)
async def upload_media_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    import base64
    import binascii

    from app.core.config import get_settings
    from app.core.storage import S3CompatibleStorage

    values = UploadMediaParams.model_validate(params)
    try:
        data = base64.b64decode(values.content_base64, validate=True)
    except (binascii.Error, ValueError):
        return ToolResult(ok=False, error="content_base64 is not valid base64", error_code="invalid_params")

    if not data:
        return ToolResult(ok=False, error="Uploaded file is empty", error_code="invalid_params")

    # Build the storage backend directly: `get_storage` is a FastAPI dependency
    # and this path has no request to resolve it from.
    settings = get_settings()
    storage = S3CompatibleStorage(
        internal_endpoint=settings.s3_endpoint,
        public_endpoint=settings.s3_public_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
    )
    try:
        asset = await store_agent_upload(
            session=context.session,
            storage=storage,
            actor=context.actor,
            filename=values.filename,
            mime=values.mime,
            data=data,
            description=values.description,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(
        ok=True,
        data={"asset_id": str(asset.id), "mime": asset.mime, "size_bytes": asset.size_bytes},
    )


@register(
    name="create_note",
    description=(
        "Create a note for the household, optionally on behalf of a member. Blocks "
        "and tags can be set in the same call. Use this to record something you "
        "found or were told to remember."
    ),
    category="notes",
    params=CreateNoteParams,
    permissions=("notes.write",),
    mutates=True,
)
async def create_note_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.schemas.notes import NoteBlockInput, NoteCreateRequest

    values = CreateNoteParams.model_validate(params)
    payload = NoteCreateRequest(
        title=values.title,
        type=values.type,
        summary=values.summary,
        owner_member_id=values.owner_member_id,
        visibility="family",  # agents may only write family-visible notes
        expires_at=values.expires_at,
        occurred_at=values.occurred_at,
        blocks=[NoteBlockInput.model_validate(block) for block in values.blocks],
        tags=values.tags,
    )
    try:
        note = await create_note(session=context.session, actor=context.actor, payload=payload)
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(ok=True, data=note, meta={"note_id": str(note.id)})


# ── Vault tools ──────────────────────────────────────────────────────────────
#
# The household secret vault (Infisical). Scopes here are ``secrets.read`` and
# ``secrets.write`` — deliberately NOT ``notes.read.secrets``, which gates the
# *password blocks inside notes* and is a different surface. A token that may
# read a note's password block is not automatically allowed to enumerate the
# whole vault.
#
# **There is no delete tool.** The operator's decision: an agent may add and
# update secrets but never remove one. Revocation stays a human action in the
# vault UI. Do not add a delete tool without asking again.
#
# ``value`` is in the redaction list in ``executor._redact_params`` — the audit
# row must never hold a plaintext secret.


class ListVaultSecretsParams(BaseModel):
    path: str = Field(default="/", max_length=500)


class GetVaultSecretParams(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    path: str = Field(default="/", max_length=500)


class SetVaultSecretParams(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    # Named ``value`` rather than ``secret_value`` so it lands on the redaction
    # list; the audit row stores "[redacted]".
    value: str = Field(min_length=1, max_length=64 * 1024)
    path: str = Field(default="/", max_length=500)
    comment: str = Field(default="", max_length=500)


@register(
    name="list_vault_secrets",
    description=(
        "List secrets in the household vault folder. Returns keys, comments and "
        "update times — never values. Use this to discover what exists before "
        "reading or writing. Path '/' is the root; note folders are '/notes/<note_id>'."
    ),
    category="vault",
    params=ListVaultSecretsParams,
    permissions=("secrets.read",),
)
async def list_vault_secrets_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.services import infisical

    values = ListVaultSecretsParams.model_validate(params)
    try:
        summaries = await infisical.list_secrets(values.path)
    except infisical.InfisicalError as error:
        return ToolResult(ok=False, error=str(error), error_code="vault_error")
    return ToolResult(
        ok=True,
        data=[
            {"key": s.key, "path": s.path, "comment": s.comment, "updated_at": s.updated_at}
            for s in summaries
        ],
        meta={"count": len(summaries), "path": values.path},
    )


@register(
    name="get_vault_secret",
    description=(
        "Read one secret's value from the household vault. Requires the "
        "secrets.read scope. Every read is recorded in the audit log. Only call "
        "this when the value is actually needed for the task at hand."
    ),
    category="vault",
    params=GetVaultSecretParams,
    permissions=("secrets.read",),
)
async def get_vault_secret_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.services import infisical

    values = GetVaultSecretParams.model_validate(params)
    try:
        value = await infisical.get_secret(values.key, path=values.path)
    except infisical.InfisicalError as error:
        return ToolResult(ok=False, error=str(error), error_code="vault_error")
    return ToolResult(
        ok=True,
        data={"key": values.key, "path": values.path, "value": value},
        meta={"key": values.key, "path": values.path},
    )


@register(
    name="set_vault_secret",
    description=(
        "Create or update one secret in the household vault. Requires the "
        "secrets.write scope. Overwrites an existing key — read it first if you "
        "are not certain. There is no delete tool: removing a secret is a human "
        "action in the vault UI."
    ),
    category="vault",
    params=SetVaultSecretParams,
    permissions=("secrets.write",),
    mutates=True,
)
async def set_vault_secret_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.services import infisical

    values = SetVaultSecretParams.model_validate(params)
    try:
        # The vault has no mkdir -p and no folder-creation tool is exposed, so the
        # write has to create its own folder. Without this, an agent writing to a
        # new path gets an opaque HTTP 404 ("Folder ... not found") and no way to
        # fix it — Infisical rejects the write before it ever sees the key.
        await infisical.ensure_folder(values.path)
        summary = await infisical.set_secret(
            values.key,
            values.value,
            path=values.path,
            comment=values.comment,
        )
    except infisical.InfisicalError as error:
        return ToolResult(ok=False, error=str(error), error_code="vault_error")
    # Never echo the value back — the caller already has it.
    return ToolResult(
        ok=True,
        data={
            "key": summary.key,
            "path": summary.path,
            "comment": summary.comment,
            "updated_at": summary.updated_at,
        },
        meta={"key": summary.key, "path": summary.path},
    )


@register(
    name="list_vault_folders",
    description="List the folder paths in the household vault, root first.",
    category="vault",
    params=NoParams,
    permissions=("secrets.read",),
)
async def list_vault_folders_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.services import infisical

    try:
        folders = await infisical.list_folders()
    except infisical.InfisicalError as error:
        return ToolResult(ok=False, error=str(error), error_code="vault_error")
    return ToolResult(ok=True, data=folders, meta={"count": len(folders)})


# ── Editing tools ────────────────────────────────────────────────────────────
#
# The operator's agent has full access by explicit decision: she tidies a messy
# household, which means correcting, reorganising and removing. That is why
# ``delete_note`` and ``delete_block`` exist here while the *vault* deliberately
# has no delete tool — deleting a note is recoverable housekeeping, deleting a
# credential is not.


class UpdateNoteParams(BaseModel):
    note_id: uuid.UUID
    title: str | None = Field(default=None, max_length=500)
    summary: str | None = None
    status: str | None = Field(default=None, max_length=20)
    type: str | None = Field(default=None, max_length=40)
    owner_member_id: uuid.UUID | None = None
    pinned: bool | None = None
    occurred_at: datetime | None = None
    expires_at: datetime | None = None


class UpdateBlockParams(BaseModel):
    block_id: uuid.UUID
    text_content: str | None = None
    data: dict | None = None
    caption: str | None = None
    importance: int | None = Field(default=None, ge=0, le=5)


class BlockIdParams(BaseModel):
    block_id: uuid.UUID


class DeleteNoteParams(BaseModel):
    note_id: uuid.UUID


class ListMembersParams(BaseModel):
    include_inactive: bool = False


class AttachTagsParams(BaseModel):
    note_id: uuid.UUID
    # Added; tags not named here are left alone. Removal has its own tool so a
    # call cannot accidentally drop tags the caller never mentioned.
    add: list[str] = Field(default_factory=list, max_length=30)


class DetachTagsParams(BaseModel):
    note_id: uuid.UUID
    remove: list[str] = Field(min_length=1, max_length=30)


class PreviewSmartTextParams(BaseModel):
    text: str = Field(min_length=1, description="The text to scan for secrets")


class SaveSmartTextParams(BaseModel):
    note_id: uuid.UUID
    text: str = Field(min_length=1, description="Text with [[secret]]…[[/secret]] around secrets")
    caption: str | None = Field(default=None, max_length=500)
    secrets: list[dict] | None = Field(
        default=None,
        description="Explicit secret list. If omitted, secrets are extracted from magic tags.",
    )


class CreateSmartTextParams(BaseModel):
    note_id: uuid.UUID
    # The source text with the secrets still in it. Every occurrence of each
    # value is replaced by a placeholder.
    text: str = Field(min_length=1)
    secrets: list[dict] = Field(min_length=1, max_length=100)
    caption: str | None = Field(default=None, max_length=500)
    importance: int = Field(default=0, ge=0, le=5)


@register(
    name="update_note",
    description=(
        "Change a note's own fields: title, summary, status, type, owner, pinned, "
        "dates. Does not touch its blocks — use update_block for those. Only the "
        "fields you pass are changed."
    ),
    category="notes",
    params=UpdateNoteParams,
    permissions=("notes.write",),
    mutates=True,
)
async def update_note_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.schemas.notes import NotePatchRequest
    from app.services.notes import update_note

    values = UpdateNoteParams.model_validate(params)
    payload = NotePatchRequest(**{k: v for k, v in values.model_dump(exclude_unset=True, exclude={"note_id"}).items() if v is not None})
    try:
        note = await update_note(
            session=context.session,
            actor=context.actor,
            note_id=values.note_id,
            payload=payload,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(ok=True, data=note, meta={"note_id": str(note.id)})


@register(
    name="update_block",
    description=(
        "Change one block's content: its text, its structured data, its caption, "
        "or its importance. Use this to fix a typo, rewrite a summary or correct "
        "an image caption. Only the fields you pass are changed."
    ),
    category="notes",
    params=UpdateBlockParams,
    permissions=("notes.write",),
    mutates=True,
)
async def update_block_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.schemas.notes import NoteBlockPatchRequest
    from app.services.notes import update_block

    values = UpdateBlockParams.model_validate(params)
    payload = NoteBlockPatchRequest(**{k: v for k, v in values.model_dump(exclude_unset=True, exclude={"block_id"}).items() if v is not None})
    try:
        block = await update_block(
            session=context.session,
            actor=context.actor,
            block_id=values.block_id,
            payload=payload,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(ok=True, data=block, meta={"block_id": str(block.id)})


@register(
    name="delete_block",
    description=(
        "Delete one block from a note. Use this to remove a duplicate or a block "
        "that no longer belongs. This cannot be undone from the API — check the "
        "block_id is the one you mean before calling."
    ),
    category="notes",
    params=BlockIdParams,
    permissions=("notes.write",),
    mutates=True,
)
async def delete_block_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.services.notes import delete_block

    values = BlockIdParams.model_validate(params)
    try:
        await delete_block(session=context.session, actor=context.actor, block_id=values.block_id)
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(ok=True, data={"deleted": True}, meta={"block_id": str(values.block_id)})


@register(
    name="delete_note",
    description=(
        "Delete a whole note and its blocks. Use this only when the note is "
        "genuinely unwanted — to tidy up a duplicate or something you created by "
        "mistake. Check with search_notes and get_note first; this cannot be "
        "undone from the API."
    ),
    category="notes",
    params=DeleteNoteParams,
    permissions=("notes.write",),
    mutates=True,
)
async def delete_note_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.services.notes import delete_note

    values = DeleteNoteParams.model_validate(params)
    try:
        await delete_note(session=context.session, actor=context.actor, note_id=values.note_id)
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(ok=True, data={"deleted": True}, meta={"note_id": str(values.note_id)})


@register(
    name="list_members",
    description=(
        "List the household's family members with their IDs and roles. Call this "
        "to get the member_id that create_note and update_note expect in "
        "owner_member_id — for example to file a note against a particular child."
    ),
    category="household",
    params=ListMembersParams,
    permissions=("notes.read",),
)
async def list_members_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from sqlalchemy import select

    from app.models import FamilyMember

    values = ListMembersParams.model_validate(params)
    statement = select(FamilyMember).where(FamilyMember.household_id == context.actor.household_id)
    if not values.include_inactive:
        statement = statement.where(FamilyMember.is_active.is_(True))
    rows = (await context.session.execute(statement.order_by(FamilyMember.display_name))).scalars().all()
    return ToolResult(
        ok=True,
        data=[
            {
                "member_id": str(m.id),
                "display_name": m.display_name,
                "role": m.role,
                "is_active": m.is_active,
            }
            for m in rows
        ],
        meta={"count": len(rows)},
    )


@register(
    name="attach_tags",
    description=(
        "Add tags to a note. Existing tags are kept — this only adds. A tag that "
        "does not exist yet is created. Tags not named here are never removed; use "
        "detach_tags for that."
    ),
    category="notes",
    params=AttachTagsParams,
    permissions=("notes.write",),
    mutates=True,
)
async def attach_tags_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.schemas.notes import NoteTagRequest
    from app.services.notes import add_tag

    values = AttachTagsParams.model_validate(params)
    # The service takes one tag per call, so loop. A failure part-way leaves the
    # tags already added in place — that is the honest outcome, and the meta
    # count tells the caller how far it got.
    added: list[dict[str, str]] = []
    for name in values.add:
        try:
            tags = await add_tag(
                session=context.session,
                actor=context.actor,
                note_id=values.note_id,
                payload=NoteTagRequest(name=name),
            )
        except AppError as error:
            return ToolResult(
                ok=False,
                error=error.message,
                error_code=error.error_code,
                meta={"note_id": str(values.note_id), "added": added, "failed_on": name},
            )
        added = [{"slug": t.slug, "name": t.name} for t in tags]
    return ToolResult(
        ok=True,
        data=added,
        meta={"note_id": str(values.note_id), "added_count": len(values.add)},
    )


@register(
    name="detach_tags",
    description="Remove named tags from a note. Other tags are left alone.",
    category="notes",
    params=DetachTagsParams,
    permissions=("notes.write",),
    mutates=True,
)
async def detach_tags_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.services.notes import remove_tag

    values = DetachTagsParams.model_validate(params)
    remaining: list[dict[str, str]] = []
    for slug in values.remove:
        try:
            tags = await remove_tag(
                session=context.session,
                actor=context.actor,
                note_id=values.note_id,
                tag_slug=slug,
            )
        except AppError as error:
            return ToolResult(
                ok=False,
                error=error.message,
                error_code=error.error_code,
                meta={"note_id": str(values.note_id), "failed_on": slug},
            )
        remaining = [{"slug": t.slug, "name": t.name} for t in tags]
    return ToolResult(
        ok=True,
        data=remaining,
        meta={"note_id": str(values.note_id), "removed_count": len(values.remove)},
    )


@register(
    name="preview_smart_text",
    description=(
        "Scan text for secrets and report what was found — the cross-check before "
        "sending to FamilyOS. The agent prepares text with [[secret]]…[[/secret]] "
        "around secrets it identified; this endpoint runs the same detector as the "
        "browser and returns:\n"
        "- `findings` — all candidates (tagged + untagged)\n"
        "- `untagged` — secrets the rules found but the agent did not mark\n"
        "- `tagged_only` — magic-tagged values the rules would not have flagged\n"
        "- `placeholder_keys` — existing {{secret:…}} placeholders in the text\n\n"
        "The agent reviews `untagged` and either adds magic tags or confirms the "
        "text is complete, then calls `save_smart_text`."
    ),
    category="vault",
    params=PreviewSmartTextParams,
    permissions=("notes.read",),
    mutates=False,
)
async def preview_smart_text_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.services import secret_detector

    values = PreviewSmartTextParams.model_validate(params)
    if not values.text.strip():
        return ToolResult(ok=False, error="Text is required", error_code="invalid_params")

    result = secret_detector.preview(values.text)
    return ToolResult(ok=True, data=result.to_dict())


@register(
    name="save_smart_text",
    description=(
        "Save a Smart Text block with magic-tagged secrets. The flow:\n"
        "1. Detect all secrets (from magic tags and rules)\n"
        "2. Extract values from [[secret]]…[[/secret]]\n"
        "3. Write each value to the vault\n"
        "4. Replace every occurrence with {{secret:<key>}}\n"
        "5. Strip magic tag markers\n"
        "6. Create the Smart Text block\n\n"
        "If `secrets` is provided, those are used directly (bypassing magic tag "
        "extraction). If not, the server extracts from magic tags."
    ),
    category="vault",
    params=SaveSmartTextParams,
    permissions=("notes.write", "secrets.write"),
    mutates=True,
)
async def save_smart_text_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.schemas.notes import NoteBlockInput
    from app.services import secret_detector, smart_text
    from app.services.notes import create_block

    import uuid

    values = SaveSmartTextParams.model_validate(params)
    if not values.text.strip():
        return ToolResult(ok=False, error="Text is required", error_code="invalid_params")

    note_uuid = values.note_id

    # Determine secrets: explicit list or extract from magic tags
    if values.secrets:
        secrets_in = [smart_text.SecretInput(**s) for s in values.secrets]
    else:
        findings = secret_detector.detect_secrets(values.text)
        tagged = [f for f in findings if f.manual]

        if not tagged:
            return ToolResult(
                ok=False,
                error=(
                    "No magic-tagged secrets found. Wrap secrets in "
                    "[[secret]]…[[/secret]] or provide an explicit secrets list."
                ),
                error_code="invalid_params",
            )

        secrets_in = [
            smart_text.SecretInput(
                label=f.label,
                value=f.value,
                type=f.type if f.type != "manual" else "other",
            )
            for f in tagged
        ]

    try:
        text_content, built, vault_path = await smart_text.build_smart_text(
            note_id=note_uuid,
            text=values.text,
            secrets_in=secrets_in,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)

    # Strip magic tag markers (values are now in the vault)
    text_content = secret_detector.strip_magic_tags(text_content)

    block_input = NoteBlockInput(
        type="smart_text",
        text_content=text_content,
        caption=values.caption,
        data={"secrets": smart_text.secrets_index(built), "vault_path": vault_path},
    )

    try:
        block = await create_block(
            session=context.session,
            actor=context.actor,
            note_id=note_uuid,
            payload=block_input,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)

    return ToolResult(
        ok=True,
        data={
            "block_id": str(block.id),
            "vault_path": vault_path,
            "secrets": [
                {
                    "key": s.key,
                    "label": s.label,
                    "placeholder": s.placeholder,
                }
                for s in built
            ],
        },
    )


@register(
    name="create_smart_text_block",
    description=(
        "Append a Smart Text block: free-form text where the secrets you name are "
        "replaced by {{secret:<key>}} placeholders, with the values written to the "
        "vault. This is the correct way to file pasted text that contains "
        "passwords or keys — do NOT put a secret in a plain text block.\n\n"
        "`text` is the source with the secrets still in it; `secrets` is the list "
        "you identified, each {label, value, type, severity}. Every occurrence of "
        "each value is replaced. The stored note contains no secret — only labels "
        "and placeholders — so it stays safe to search and embed."
    ),
    category="vault",
    params=CreateSmartTextParams,
    permissions=("notes.write", "secrets.write"),
    mutates=True,
)
async def create_smart_text_block_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.schemas.notes import NoteBlockInput
    from app.services import smart_text
    from app.services.notes import create_block

    values = CreateSmartTextParams.model_validate(params)
    try:
        secrets_in = [smart_text.SecretInput(**item) for item in values.secrets]
    except TypeError as error:
        return ToolResult(
            ok=False,
            error=f"Each secret needs label and value ({error})",
            error_code="invalid_params",
        )

    try:
        text_content, built, vault_path = await smart_text.build_smart_text(
            note_id=values.note_id,
            text=values.text,
            secrets_in=secrets_in,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)

    payload = NoteBlockInput(
        type="smart_text",
        text_content=text_content,
        caption=values.caption,
        importance=values.importance,
        data={"secrets": smart_text.secrets_index(built), "vault_path": vault_path},
    )
    try:
        block = await create_block(
            session=context.session,
            actor=context.actor,
            note_id=values.note_id,
            payload=payload,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)

    # Never echo the values. The caller supplied them; what it needs back is the
    # mapping it will use to talk about them later.
    return ToolResult(
        ok=True,
        data={
            "block_id": str(block.id),
            "note_id": str(values.note_id),
            "vault_path": vault_path,
            "secrets": [
                {"label": b.label, "key": b.key, "placeholder": b.placeholder, "type": b.type}
                for b in built
            ],
        },
        meta={"block_id": str(block.id), "secret_count": len(built)},
    )


@register(
    name="append_block",
    description=(
        "Append one block to an existing note. Use this to attach a photo, a file, "
        "a text note, or a reminder to a note you or the family already have."
    ),
    category="notes",
    params=AppendBlockParams,
    permissions=("notes.write",),
    mutates=True,
)
async def append_block_tool(params: BaseModel, context: ToolContext) -> ToolResult:
    from app.schemas.notes import NoteBlockInput

    values = AppendBlockParams.model_validate(params)
    data = dict(values.data) if values.data else {}
    if values.media_asset_id:
        data["media_asset_id"] = str(values.media_asset_id)
    payload = NoteBlockInput(
        type=values.type,
        text_content=values.text_content,
        media_asset_id=values.media_asset_id,
        data=data,
        caption=values.caption,
        expires_at=values.expires_at,
        importance=values.importance,
    )
    try:
        block = await create_block(
            session=context.session,
            actor=context.actor,
            note_id=values.note_id,
            payload=payload,
        )
    except AppError as error:
        return ToolResult(ok=False, error=error.message, error_code=error.error_code)
    return ToolResult(ok=True, data=block, meta={"block_id": str(block.id)})