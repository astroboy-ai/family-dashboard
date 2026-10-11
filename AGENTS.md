# FamilyOS Agent Instructions

This file provides guidance for AI agents (Hermes, Kururu, etc.) on how to interact with the FamilyOS system.

**This file is the single source of truth.** It is served live — edit it, deploy, and every agent sees the new instructions on its next call.

## How to Read These Instructions

Two equivalent ways, both requiring a valid agent token:

- **MCP tool**: `get_agent_instructions` — returns this file as text
- **HTTP**: `GET /internal/agent/instructions` — returns `{"instructions": "..."}`

Call one of these at session start instead of relying on cached copies.

## Authentication

- **MCP Endpoint (external)**: `https://familyos-mcp.logeebox.com/mcp/`
- **MCP Endpoint (internal, compose network)**: `http://familyos-backend:8000/mcp/`
- **Protocol**: Model Context Protocol (MCP) over Streamable HTTP
- **Auth**: `Authorization: Bearer <token>`, from the `device_tokens` table
- Each agent has its own token with specific scopes

Use the external endpoint. The internal hostname only resolves inside the Docker
compose network and will not work from your own machine.

**Keep the trailing slash.** The path without it (`/mcp`) answers with a 307
redirect to the canonical `/mcp/`. Some MCP clients do not follow redirects on
POST, and a redirect can drop the `Authorization` header — so connect to the
trailing-slash form directly.

### Getting a Token

Tokens are minted by the system administrator. Contact 子樂 (Lok) to obtain one.

An administrator mints a token inside the backend container — note that
`scripts/` is **not** copied into the image, so run the logic directly:

```bash
docker exec -w /app -e PYTHONPATH=/app familyos-backend-1 /app/.venv/bin/python -c "
import asyncio
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from app.core.db import session_factory
from app.models import DeviceToken, Household
from app.services.agent_tokens import generate_token, hash_token

async def main():
    async with session_factory() as s:
        hh = (await s.execute(select(Household).limit(1))).scalars().first()
        token = generate_token()
        s.add(DeviceToken(
            household_id=hh.id, member_id=None, label='Kururu',
            token_hash=hash_token(token), scopes=['notes.read', 'notes.write'],
            expires_at=datetime.now(UTC) + timedelta(days=365),
        ))
        await s.commit()
        print(token)

asyncio.run(main())
"
```

The raw token is printed **once** and never stored — only its SHA-256 hash is
kept, so it cannot be recovered later. Revoke by deleting the row.

### Scopes

| Scope | Grants |
| --- | --- |
| `notes.read` | Search and read family-visible notes |
| `notes.write` | Create notes, append blocks, upload media |
| `secrets.read` | List and read secrets in the household vault |
| `secrets.write` | Create and update secrets in the household vault |

A token without `notes.write` can still see the write tools listed, but calling
one returns `permission_denied` and the attempt is recorded in `agent_tool_calls`.
Publishing a tool is not the same as granting it.

**`secrets.read` / `secrets.write` are not the same as `notes.read.secrets`.**
The latter gates the *password blocks inside notes*; the former gates the *vault
itself*. A token that may read a note's password block is not automatically
allowed to enumerate the whole vault. Ask for the scope you actually need.

**There is no delete tool for the vault.** An agent may add and update secrets
but never remove one — revocation is a human action in the vault UI. Do not look
for a workaround; if a secret must go, ask 子樂.

## Available Tools

### Notes (read)

- **search_notes** — Search household notes by keyword or semantic query
  - Parameters: `query` (string), `limit` (int, default 10)
  - Returns: List of notes with title, summary, and relevance score

- **get_note** — Get full content of a specific note
  - Parameters: `note_id` (UUID)
  - Returns: Note with all blocks (text, images, etc.)

- **get_blocks** — Get blocks of a specific note
  - Parameters: `note_id` (UUID)
  - Returns: List of blocks with type and content

- **list_tags** — List all tags in the household
  - Parameters: none
  - Returns: List of tags with slug, name, and color

- **get_expiring_items** — Get items that are expiring soon
  - Parameters: `days` (int, default 7)
  - Returns: List of expiring items

### Writing (requires `notes.write` scope)

These tools change household data. They only work if your token carries the
`notes.write` scope — a token without it gets `permission_denied`, and the
attempt is recorded in the audit log either way.

- **upload_media** — Upload a file and get an `asset_id` to attach to a block
  - Parameters: `filename`, `mime`, `content_base64`, `description` (optional)
  - **Pass `description` when you have already analysed the file.** The system
    will then store your text and skip its own vision call entirely — do not
    upload a file you have described and let the system analyse it again.
  - Without a `description`, the local vision worker analyses images only.
  - **Size limit: about 3 MB per file.** The MCP transport caps a request body at
    4 MB and base64 inflates by ~33%, so a file above ~3 MB is rejected with HTTP
    413 before any tool code runs. This is a transport limit, not a storage one —
    a larger file needs an upload path outside `tools/call`.
  - Video and audio are stored but never analysed: the vision worker skips any
    asset whose kind is not `image`.

- **create_note** — Create a note, optionally with blocks and tags in one call
  - Parameters: `title`, `type`, `summary`, `owner_member_id` (optional),
    `expires_at` (optional), `occurred_at` (optional), `blocks` (array),
    `tags` (array)
  - `owner_member_id` names the member the note is for. Omit it for the
    household in general. Get member IDs from the household admin page.
  - Agents can only create **family-visible** notes. A request for
    `visibility: "parents"` is refused.

- **append_block** — Append one block to an existing note
  - Parameters: `note_id`, `type`, `text_content`, `media_asset_id` (optional),
    `data` (object), `caption`, `expires_at` (optional), `importance` (0–5)
  - Block types: `text`, `image`, `file`, `audio`, `date`, `time`, `currency`,
    `checkbox`, `table`, `password`, `location`, `drawing`, `reminder`
  - Attach an uploaded file by passing its `asset_id` as `media_asset_id`.

### The vault (requires `secrets.read` / `secrets.write`)

The household vault is an Infisical instance. It holds two kinds of thing:

1. **Secrets the family filed here directly** — API keys, logins, tokens.
2. **The values behind `{{secret:…}}` placeholders in notes** (see below).

| Tool | Scope | Does |
| --- | --- | --- |
| `list_vault_folders` | `secrets.read` | Folder paths, root first |
| `list_vault_secrets` | `secrets.read` | Keys/comments/updated-at in one folder — **never values** |
| `get_vault_secret` | `secrets.read` | One value |
| `set_vault_secret` | `secrets.write` | Create or update one key |

There is deliberately **no delete tool**. An agent may add and update; only a
human removes a secret.

#### `{{secret:…}}` — placeholders in notes

A note can hold a **Smart Text** block: free-form text where the sensitive parts
have been replaced by placeholders. This is what the family uses instead of
keeping passwords in plain note text.

```
Orange system:
manager
{{secret:sn-orange-password-7f3a91}}
```

**The placeholder is not the password.** It is a pointer. The real value lives in
the vault, and the note itself contains no secret at all — this is why the note
is safe to search, embed and read.

Rules for handling one:

- **Never treat the placeholder as the value.** If you need to *use* a credential
  — log in, call an API — resolve it with `get_vault_secret` first.
- **Never write a resolved value back into a note.** That defeats the whole
  design and puts the secret in the embedding index. When writing a note that
  needs a secret, either reuse the existing placeholder or call
  `set_vault_secret` and insert a fresh `{{secret:<key>}}`.
- **Preserve placeholders you are not touching.** Copy the block text verbatim.
- **Do not guess the value from the key name.** `sn-orange-password-7f3a91` tells
  you it is Orange's password, not what the password is.
- **A note's password block is different.** A block of type `password` stores a
  `vault_key` reference and the API resolves it for you when your token carries
  `notes.read.secrets`. You do not need to call `get_vault_secret` for those.

The key format is `sn-<label-slug>-<6hex>` for Smart Text and `pw-<block_id>` for
password blocks. Both live under `/notes/<note_id>`.

### Calendar (Coming Soon)

- **list_events** — List calendar events
- **create_event** — Create a new event
- **update_event** — Update an existing event
- **delete_event** — Delete an event

## Permissions

Agents are assigned scopes that determine what they can do:

| Scope | Description |
|-------|-------------|
| `notes.read` | Read notes and search |
| `notes.write` | Create notes, upload files, append blocks |
| `notes.read.secrets` | Read a note's `password` block values |
| `secrets.read` | List and read the household vault |
| `secrets.write` | Create and update vault secrets (never delete) |
| `calendar.read` | Read calendar events |
| `calendar.write` | Create and modify calendar events |

### How write access works

There is no per-call confirmation prompt. **The scope on your token is the
consent**: the operator granted `notes.write` when the token was minted. Every
write is recorded in `agent_tool_calls` with your agent name, the tool, the
parameters (secrets redacted) and the result.

Because of that, write carefully:

1. **Confirm the intent with the user before writing** unless they asked for it
   in the same conversation. You have the permission; that is not the same as
   having the instruction.
2. **Do not create duplicates.** Search first — `search_notes` — before creating
   a note that may already exist.
3. **Write family-visible content only.** Private and parent-only notes are not
   available to you, by design.
4. **Name the owner when it matters.** A voucher for 子樂 goes to 子樂, not to
   the household in general.

## Guidelines

### Read-Only Tools

Tools in the *Notes (read)* section never change data. The *Writing* tools do,
and require the `notes.write` scope — see "How write access works" above.

### Rate Limits

- 100 requests per minute per agent token
- Bulk operations should be batched

### Error Handling

- `permission_denied` — Token lacks required scope
- `unauthenticated` — Token invalid or expired
- `not_found` — Resource does not exist
- `vault_error` — The vault refused the call (bad path, unknown key, or the
  vault itself is unreachable). The message says which; do not retry blindly.

### Best Practices

1. **Always check tool availability** — Call `tools/list` first to see what's available
2. **Use semantic search** — `search_notes` supports both keyword and semantic queries
3. **Respect privacy** — Notes marked private to another member are not visible
4. **Cache tokens** — Tokens are long-lived; no need to re-authenticate frequently

## Examples

### Search for a note

```json
{
  "query": "birthday party",
  "limit": 5
}
```

### Get a specific note

```json
{
  "note_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

## Support

For issues or questions, contact 子樂 (Lok) or open an issue in the GitHub repository.
