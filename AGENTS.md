# FamilyOS Agent Instructions

This file provides guidance for AI agents (Hermes, Kururu, etc.) on how to interact with the FamilyOS system.

**This file is the single source of truth.** It is served live — edit it, deploy, and every agent sees the new instructions on its next call.

## How to Read These Instructions

Two equivalent ways, both requiring a valid agent token:

- **MCP tool**: `get_agent_instructions` — returns this file as text
- **HTTP**: `GET /internal/agent/instructions` — returns `{"instructions": "..."}`

Call one of these at session start instead of relying on cached copies.

## Authentication

- **MCP Endpoint**: `http://familyos-backend:8000/mcp`
- **Protocol**: Model Context Protocol (MCP) over Streamable HTTP
- **Auth**: Bearer token from `device_tokens` table
- Each agent has its own token with specific scopes

### Getting a Token

Tokens are minted by the system administrator. Contact 子樂 (Lok) to obtain an agent token.

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
  - Limit: keep uploads under ~64 MB (base64 inflates by ~33%).

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
