# FamilyOS Agent Instructions

This file provides guidance for AI agents (Hermes, Kururu, etc.) on how to interact with the FamilyOS system.

## Authentication

- **MCP Endpoint**: `http://familyos-backend:8000/mcp`
- **Protocol**: Model Context Protocol (MCP) over Streamable HTTP
- **Auth**: Bearer token from `device_tokens` table
- Each agent has its own token with specific scopes

### Getting a Token

Tokens are minted by the system administrator. Contact 子樂 (Lok) to obtain an agent token.

## Available Tools

### Notes

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
| `notes.write` | Create and modify notes |
| `calendar.read` | Read calendar events |
| `calendar.write` | Create and modify calendar events |

## Guidelines

### Read-Only Tools

Currently, all agent tools are **read-only**. Agents cannot modify household data. This is intentional — a remote agent should not change data without an explicit confirmation flow.

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
