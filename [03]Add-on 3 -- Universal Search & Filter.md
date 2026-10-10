# FamilyOS 2027 — Note A: Universal Search & Filter

**Note**
```json
{
  "title": "Universal Search & Filter — Dedicated Search Surface",
  "type": "freeform",
  "status": "active",
  "visibility": "family",
  "pinned": false,
  "owner_member_id": null,
  "tags": ["search", "filter", "ui", "facets", "v1.1"],
  "summary": "Dedicated /search page with hybrid ranking, faceted filters, saved searches, deep-linkable URL state, and bulk actions. Complements the inline search in Notes list. Also adds faceted filter primitives usable by every list view in the app.",
  "extra": { "doc_version": "1.0", "target_reader": "coding-agent", "depends_on": "Master Blueprint v1.1 §10" }
}
```

---

### Block 1 — `text` — Why a Separate Page

The Notes list already has an inline search box. That is not enough. A dedicated `/search` page exists because:

1. **Faceted filtering** needs vertical space — dozens of tags, multiple types, date ranges, member filters, media presence, expiry window, visibility.
2. **Deep-linkable state** — you want to send "all school notices with action required from last month" as a URL to your partner.
3. **Saved searches** — recurring queries ("all receipts this quarter", "everything tagged Japan") become first-class objects.
4. **Bulk actions** — retag 40 notes at once, archive, move to a folder.
5. **Cross-entity results** — search hits notes *and* blocks *and* events *and* vault items (permission-gated) in one view.
6. **Query transparency** — show the user *why* each result ranked where it did (matched in title? semantic similarity? tag?).

The inline search in `/notes` remains for quick scoping. `/search` is the power tool.

---

### Block 2 — `text` — Page Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ┌──────────────────────────────────────────────────┐  ┌───────────────┐ │
│  │ 🔍  japan trip school fees                       │  │ Save search   │ │
│  └──────────────────────────────────────────────────┘  └───────────────┘ │
│                                                                          │
│  Mode: ( ) Keyword  ( ) Semantic  (•) Hybrid     Sort: Relevance ▾      │
│                                                                          │
│  ┌─── Filters ────────────────────────────────────────────────────────┐ │
│  │ Type: [freeform ×] [school_notice ×] [+ add]                       │ │
│  │ Tags: [#travel ×] [#2027 ×] [#finance ×] [+ add]                   │ │
│  │ Member: [Dad ×] [Emma ×] [+ add]                                   │ │
│  │ Date: [2026-01-01] → [2026-12-31]  ○ occurred  ○ created  ○ updated│ │
│  │ Has media: [Any] [Image] [Voice] [Video] [File]                    │ │
│  │ Expiry: [Any] [≤7d] [≤30d] [≤90d] [Expired] [No expiry]            │ │
│  │ Visibility: [family] [parents] [private] [vault — parent only]     │ │
│  │ Status: [inbox] [active] [done] [archived]                         │ │
│  │                                                                     │ │
│  │ [Clear all]                                        [Save as preset]│ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  412 results · 0.18 s · sources: fts 50, semantic 50, merged 88         │
│                                                                          │
│  ┌─── Results ────────────────────────────────────┐  ┌── Facets ──────┐ │
│  │ [ ] Japan trip planning            freeform    │  │ Type           │ │
│  │     matched: title, semantic 0.89              │  │  freeform  182 │ │
│  │     3 days ago · #travel #2027                 │  │  receipt    64 │ │
│  │  [ ] School fee 2027-01            school_note │  │  coupon     41 │ │
│  │     matched: block ocr, tag finance            │  │  meeting    23 │ │
│  │     2 weeks ago · #finance #school             │  │  …             │ │
│  │  [ ] …                                          │  │ Tags           │ │
│  │                                                 │  │  #travel    18 │ │
│  │                                                 │  │  #school    14 │ │
│  │                                                 │  │  …             │ │
│  │                                                 │  │ Members        │ │
│  │                                                 │  │  Dad        96 │ │
│  │                                                 │  │  …             │ │
│  └─────────────────────────────────────────────────┘  └────────────────┘ │
│                                                                          │
│  Bulk: [Tag ▾] [Move to folder ▾] [Archive] [Export ▾]  (3 selected)     │
└──────────────────────────────────────────────────────────────────────────┘
```

**Layout rules:**
- Query bar is sticky at top.
- Filter chip row is collapsible; collapsed shows a summary count ("5 filters").
- Facet panel is collapsible on mobile (becomes a bottom sheet).
- Result density toggle: comfortable / compact / gallery.
- Keyboard: `/` focuses query, `f` opens filter panel, `s` saves, `Esc` clears selection.

---

### Block 3 — `text` — Filter Model (Canonical JSON)

The filter state is a single JSON object. This same object is:
- Serialized into the URL query string (base64url-encoded when >200 chars).
- Sent to the backend as the `filters` field of `POST /api/search`.
- Stored verbatim in `saved_searches.config`.

```json
{
  "q": "japan trip school fees",
  "mode": "hybrid",
  "filters": {
    "types": ["freeform", "school_notice"],
    "tags": ["travel", "2027"],
    "tag_mode": "any",
    "member_ids": ["uuid-dad", "uuid-emma"],
    "member_role": "any",
    "date": {
      "field": "occurred_at",
      "from": "2026-01-01",
      "to": "2026-12-31"
    },
    "has_media": ["image", "voice"],
    "expiry": "within_30d",
    "status": ["inbox", "active"],
    "visibility": ["family", "parents"],
    "has_blocks_of_type": ["receipt", "coupon"],
    "pinned": null,
    "archived": false,
    "include_vault": false
  },
  "sort": "relevance",
  "limit": 50,
  "cursor": null
}
```

**Field reference:**

| Field | Values | Notes |
|---|---|---|
| `q` | string | Empty = browse mode (no ranking, sort by chosen field) |
| `mode` | `keyword` \| `semantic` \| `hybrid` | Default `hybrid` |
| `types[]` | Note types | Empty = all |
| `tags[]` | Tag slugs | |
| `tag_mode` | `any` \| `all` | Default `any` |
| `member_ids[]` | Member UUIDs | Matches `owner_member_id` OR `created_by` (toggleable) |
| `date.field` | `occurred_at` \| `created_at` \| `updated_at` \| `expires_at` | Default `updated_at` |
| `has_media[]` | `image` \| `voice` \| `video` \| `file` | |
| `expiry` | `any` \| `none` \| `expired` \| `within_7d` \| `within_30d` \| `within_90d` \| `beyond_90d` | |
| `status[]` | Note statuses | |
| `visibility[]` | `family` \| `parents` \| `private` | Vault is separate |
| `has_blocks_of_type[]` | Block types | |
| `pinned` | `null` \| `true` \| `false` | |
| `archived` | bool | Default false |
| `include_vault` | bool | Parent-only, audited |
| `sort` | `relevance` \| `updated_desc` \| `created_desc` \| `occurred_desc` \| `occurred_asc` \| `expiry_asc` \| `title_asc` | |
| `limit` | int ≤ 200 | Cursor pagination |

---

### Block 4 — `text` — Backend Query Pipeline

`app/services/search.py` — one service, two entry points (`search()` and `facets()`).

```
POST /api/search
  1. Parse + validate filters against a Pydantic SearchFilters model
  2. Apply visibility predicate (family / parents / private + vault gate)
  3. If mode in (keyword, hybrid):
       build tsquery via websearch_to_tsquery
       run FTS → top 50 candidates
  4. If mode in (semantic, hybrid):
       embed the query (cached 5 min by query hash)
       HNSW cosine → top 50 candidates
  5. Merge via RRF:  score(d) = Σ 1/(60 + rank_i(d))
  6. Apply filters as SQL WHERE on the merged candidate set
  7. Join tags, blocks count, media presence, member info
  8. Sort by chosen field (or by RRF score if relevance)
  9. Return page + total count + facets + timing
```

**Facets** are computed in the same request unless the query is expensive. `GET /api/search/facets` computes facets alone (used when the user changes only a facet filter, to avoid re-running ranking).

Facet counts respect **all other filters** — this is the "faceted search" invariant. If you filter to `type=receipt`, the Tag facet only shows tags that appear on receipts.

**Performance guardrails:**
- Hard cap of 10,000 candidate rows before filtering.
- If `include_vault=false` (default), vault notes are excluded via an indexed `WHERE visibility <> 'private_vault'` clause, not post-filtered.
- Facet queries run in parallel (`asyncio.gather`).
- Result set is cached in Redis for 30 s keyed by `sha256(normalized_query_json)`.

---

### Block 5 — `text` — Schema Additions

```sql
-- Saved searches: first-class objects, also Notes
saved_searches(
  id uuid pk, household_id uuid not null,
  name text not null, description text,
  note_id uuid references notes(id) on delete cascade,
  config jsonb not null,               -- the canonical filter JSON
  owner_member_id uuid references family_members(id),
  is_shared bool default false,
  is_pinned bool default false,
  run_count int default 0,
  last_run_at timestamptz,
  order_index int default 0,
  created_by uuid references family_members(id),
  created_at timestamptz default now(), updated_at timestamptz default now(),
  unique(household_id, owner_member_id, name)
);
create index on saved_searches (household_id, owner_member_id, order_index);
create index on saved_searches (household_id, is_shared) where is_shared;

-- Optional: precomputed facet materialization for large households
facet_cache(
  household_id uuid not null,
  facet_key text not null,             -- 'type' | 'tag' | 'member' | 'media'
  filter_hash text not null,           -- sha256 of filters used
  payload jsonb not null,
  computed_at timestamptz default now(),
  primary key (household_id, facet_key, filter_hash)
);
```

**Saved searches are also Notes.** The `note_id` points to a Note of `type='custom'`, `extra.category='saved_search'` whose blocks hold a description, notes about why the search exists, and optional pinned results. This preserves the "everything is a Note" principle and lets Hermes find saved searches the same way it finds anything else.

---

### Block 6 — `text` — URL State (Deep Linking)

Every search is a URL. This is non-negotiable — it is how families share queries.

**Short form (readable):**
```
/search?q=japan+trip&type=freeform&tag=travel&tag=2027&member=uuid-dad&from=2026-01-01&to=2026-12-31&mode=hybrid&sort=relevance
```

**Long form (base64url JSON, when the filter set is complex):**
```
/search?f=eyJxIjoiamFwYW4gdHJpcCIsIm1vZGUiOiJoeWJyaWQiLCJmaWx0ZXJzIjp7Li4ufX0
```

**Rules:**
- On mount, `/search` parses `f` if present, else parses the readable params.
- Every filter change updates the URL via `history.replaceState` (no navigation, no scroll jump).
- Clicking "Copy link" copies the full URL.
- Opening a URL restores the exact filter state and runs the query.
- A saved search stores the same JSON, so a URL and a saved search are interchangeable.

---

### Block 7 — `text` — Result Presentation

Each result row shows:

| Element | Source |
|---|---|
| Title (or derived from first block) | `notes.title` / fallback |
| Type badge | `notes.type` |
| Snippet | matched region from FTS, or first 120 chars of `ai_summary`/`summary` |
| Match reasons | e.g. `title (A)`, `semantic 0.89`, `tag:travel`, `block ocr` |
| Timestamp | `updated_at` by default, or the filtered date field |
| Tags | up to 5, with "+N more" |
| Owner avatar | `owner_member_id` |
| Media thumbnail | first image block, if any |
| Expiry pill | if `expires_at` is set and within 90 days |

**View modes:**
- **List** (default) — dense, one row per note.
- **Gallery** — masonry grid of thumbnails; only for results with media.
- **Timeline** — grouped by month/year, sorted by `occurred_at`.
- **Compact** — table-like; columns configurable.

**Match reason transparency** is mandatory. Users must know why a result appeared, or they will not trust semantic search.

---

### Block 8 — `text` — Saved Searches UX

**Where saved searches appear:**
- Sidebar under a "Saved" section (pinned first).
- Overview dashboard widget (top 3 pinned searches, showing count + click-through).
- The `/search` page itself, as a chip row above filters.
- In Hermes: `list_saved_searches` tool returns them, and Hermes can run one by ID.

**Actions:**
- Save current query as a new saved search.
- Rename, edit description, change sharing.
- Delete (soft).
- Pin / unpin.
- "Run now" — increments `run_count`.

**Preset examples shipped with the system:**
- "Inbox" — `status=inbox`, sort `updated_desc`
- "Expiring this month" — `expiry=within_30d`
- "Receipts this quarter" — `type=receipt`, date range this quarter
- "School actions" — `type=school_notice`, `has_blocks_of_type=checklist`, `status=active`
- "Vault documents expiring" — `include_vault=true`, `expiry=within_90d` (parent-only)

These are seeded on household creation and can be edited or deleted.

---

### Block 9 — `text` — Bulk Actions

When one or more results are selected (checkbox in the row), a bulk action bar appears:

| Action | Effect | Confirmation |
|---|---|---|
| **Add tag** | Append a tag to every selected note | — |
| **Remove tag** | Remove a tag | — |
| **Archive** | `status='archived'` | — |
| **Unarchive** | `status='active'` | — |
| **Move to folder** | Sets `parent_note_id` | — |
| **Change visibility** | `family` / `parents` / `private` | Yes (parents-only if raising to parents) |
| **Set expiry** | Sets `expires_at` | — |
| **Delete** | Soft delete | Yes |
| **Export** | JSON / CSV / Markdown of selected notes | — |
| **Create event from notes** | Creates one calendar event per note | Yes |

Bulk actions are implemented as **tools** in the registry (`bulk_tag_notes`, `bulk_archive_notes`, etc.) so the agent can perform them too, with the same confirmation flow.

---

### Block 10 — `text` — Agent Tools

New tools in `app/agent/tools/search.py` and `app/agent/tools/saved_searches.py`:

| Tool | Params | Mutates |
|---|---|---|
| `search` | the full filter JSON + `limit` | N |
| `facets` | `filters` | N |
| `save_search` | `name, config, is_shared?` | Y |
| `list_saved_searches` | `member_id?` | N |
| `run_saved_search` | `saved_search_id, limit?` | N |
| `delete_saved_search` | `id` | Y |
| `bulk_tag_notes` | `note_ids[], add[], remove[]` | Y |
| `bulk_archive_notes` | `note_ids[]` | Y |

**Why this matters for Hermes:** Hermes can now answer *"Show me everything tagged Japan with a photo, from the last 6 months, that isn't archived"* by constructing a filter JSON and calling `search`. And it can *create* a saved search on the user's behalf — "save this as 'Japan planning'" — turning a one-off query into a persistent view.

**Important:** Hermes must not invent filter values. Before using a type, tag, member, or status value, it should call `get_reference_set('note_types')` (see Note B) or `list_tags` to confirm the value exists.

---

### Block 11 — `text` — Integration with Existing Surfaces

| Surface | Integration |
|---|---|
| `/notes` list | Has its own lightweight filter bar; a "Open in full search →" link passes current filters via the `f` param |
| Family Overview | "Saved searches" widget (up to 3 pinned, shows counts) |
| Wall | A rotating "Saved search" panel — e.g. "School actions this week" (read-only) |
| Kid Portal | No full search; a simplified `search_notes` scoped to the child's own notes + shared family notes |
| Command palette (`Cmd+K`) | Typing a query runs a lightweight `/api/search?limit=8` and shows top 5 in a dropdown; `Enter` opens `/search` with the query |

---

### Block 12 — `text` — Phase Placement & Acceptance

**Phase 1:** `POST /api/search` with keyword + tag + type + date filters. `/search` page with query bar, type/tag/member/date filters, list view, URL state. Deep-linkable.

**Phase 2:** Facets panel, saved searches (CRUD + sidebar), bulk actions, gallery/timeline views, semantic and hybrid modes (once embeddings are live), Overview widget, command palette integration.

**Phase 3:** `search` + `save_search` + `run_saved_search` agent tools, facet caching, saved-search sharing.

**Acceptance (Phase 2):**
- [ ] A query returns results in < 300 ms at 10,000 notes.
- [ ] URL round-trips: copy URL → open in a new tab → identical results and filter state.
- [ ] Facet counts update correctly as filters are applied.
- [ ] A saved search can be created, shared, pinned, and run from the sidebar.
- [ ] Bulk tag 20 notes in one action; all update optimistically and correctly.
- [ ] Vault notes are absent unless `include_vault=true` from a parent; the request is audited.
- [ ] `search` and `run_saved_search` tools return correct data via `/internal/agent/tools`.
- [ ] Hermes can create a saved search from a natural-language request.

---

**End of Note A.**
`status='active'` · `pinned=false` · `tags=['search','filter','ui','facets','v1.1']`

---

# FamilyOS 2027 — Note B: Dynamic Master Data & AI Change Awareness

**Note**
```json
{
  "title": "Dynamic Master Data & AI Change Awareness — Reference Sets, Capabilities, and the Hermes Freshness Guide",
  "type": "freeform",
  "status": "active",
  "visibility": "parents",
  "pinned": false,
  "owner_member_id": null,
  "tags": ["master-data", "reference-data", "agent", "capabilities", "v1.1"],
  "summary": "Every list the system treats as authoritative (MTR stations, bus routes, note types, tags, subjects, vault categories, tool registry, enums) lives in a versioned Reference Set. Hermes discovers them, validates against them, and subscribes to changes so it never acts on stale data. Includes the Hermes Freshness Guide.",
  "extra": { "doc_version": "1.0", "target_reader": "coding-agent", "depends_on": "Master Blueprint v1.1, Note A" }
}
```

---

### Block 1 — `text` — The Problem

The system has many **master lists** — authoritative sets of values that other data references:

- MTR stations and lines (updated by the government API when new stations open)
- Bus routes and stops (updated daily by KMB/Citybus/GMB static feeds)
- Note types, block types, statuses, visibilities (updated when the schema evolves)
- Tags (grown organically by users)
- Family members (added/removed)
- Learning subjects and topics (created and renamed)
- Vault categories (configured and reorganized)
- Tool registry entries (new tools and games added at runtime)
- Manifest entries (menu items and widgets)
- Enum values used by tools (`display_mode`, `sort`, `operator`, `region`)

**If Hermes caches any of these in its prompt and they change, the agent silently becomes wrong.** It will propose an MTR station that no longer exists, create a note with an invalid type, or call a tool that was removed.

**If a human edits a master list, they expect the AI to know immediately.** Not after a container restart.

The solution is a **Reference Set** abstraction: every master list is a named, versioned, queryable, subscribable object. Hermes treats it as the source of truth and the system publishes changes to it.

---

### Block 2 — `text` — Design Principles

1. **Every master list is a Reference Set.** No master list lives in code, config files, or the prompt. If it is authoritative, it is a Reference Set.
2. **Every Reference Set has a version.** A monotonically increasing integer per set, per household.
3. **Every change is logged.** `reference_changes` is append-only.
4. **Every change is published.** SSE event + Redis pub/sub + (optionally) a webhook.
5. **Hermes validates before it acts.** No tool accepts an unvalidated reference value.
6. **Hermes subscribes, not polls.** At session start it fetches; during a session it listens.
7. **Stale is an error, not a warning.** If Hermes uses a value that changed since it fetched, the tool returns `error_code: 'stale_reference'` and Hermes refetches once and retries.
8. **Humans can see and edit every set.** Admin page lists all Reference Sets, their versions, when they last changed, and what changed.

---

### Block 3 — `text` — Schema

```sql
-- A named, versioned master list
reference_sets(
  id uuid pk, household_id uuid not null,
  key text not null,                   -- 'mtr_stations', 'note_types', 'tags', ...
  name text not null,                  -- human label
  description text,
  kind text not null,                  -- 'static' | 'api' | 'admin' | 'derived'
  source text,                         -- URL or 'internal'
  source_ttl_s int,                    -- refresh cadence; null = manual
  payload jsonb,                       -- small sets: full data inline
  payload_checksum text,               -- sha256 of canonicalized payload
  version int not null default 1,
  item_count int,
  schema jsonb,                        -- JSON Schema for items (for validation)
  is_public bool default true,         -- whether non-parent roles can read
  is_frozen bool default false,        -- if true, refresh is skipped
  updated_at timestamptz not null default now(),
  last_checked_at timestamptz,
  unique(household_id, key)
);
create index on reference_sets (household_id, key);
create index on reference_sets (kind, source_ttl_s) where source_ttl_s is not null and not is_frozen;

-- Large sets: items stored as rows for indexed lookup
reference_items(
  id uuid pk,
  set_id uuid not null references reference_sets(id) on delete cascade,
  code text not null,                  -- canonical ID (e.g. 'ADM', 'C88E34E485B43EFB')
  label_en text, label_tc text,
  data jsonb not null default '{}',    -- full item payload
  order_index int default 0,
  active bool default true,
  created_at timestamptz default now(), updated_at timestamptz default now(),
  unique(set_id, code)
);
create index on reference_items (set_id, active, order_index);
create index on reference_items (set_id, code);
create index on reference_items using gin (data jsonb_path_ops);
create index on reference_items using gin ((label_en || ' ' || coalesce(label_tc,'')) gin_trgm_ops);

-- Append-only change log
reference_changes(
  id uuid pk,
  household_id uuid not null,
  set_key text not null,
  from_version int,
  to_version int not null,
  change_kind text not null,           -- 'add' | 'update' | 'remove' | 'replace'
  item_code text,                      -- null for a full replace
  before jsonb,                        -- redacted if large
  after jsonb,
  detected_by text,                    -- 'scheduler' | 'admin' | 'startup' | 'manual'
  detected_at timestamptz not null default now()
);
create index on reference_changes (household_id, set_key, to_version desc);
create index on reference_changes (household_id, detected_at desc);

-- Capability snapshot: the single document Hermes fetches at session start
capability_snapshots(
  id uuid pk, household_id uuid not null,
  version int not null,
  payload jsonb not null,              -- see Block 5
  checksum text not null,
  generated_at timestamptz not null default now(),
  unique(household_id, version)
);
create index on capability_snapshots (household_id, version desc);
```

**Two storage tiers:**
- Small sets (< ~200 items, low churn): stored inline in `reference_sets.payload`. Example: `note_types`, `block_types`, `vault_categories`, `transit_operators`.
- Large sets (> ~200 items, high churn): stored in `reference_items`. Example: `mtr_stations`, `kmb_routes`, `ctb_routes`, `gmb_routes`, `tags`, `learning_topics`.

Both tiers expose the same API. The service decides storage at write time based on item count.

---

### Block 4 — `text` — The Reference Set Catalogue

Every master list in the system, with its key, kind, source, and refresh cadence.

| Key | Kind | Source | TTL | Storage |
|---|---|---|---|---|
| `note_types` | static | internal | manual | inline |
| `block_types` | static | internal | manual | inline |
| `note_statuses` | static | internal | manual | inline |
| `visibility_levels` | static | internal | manual | inline |
| `chore_recurrence_presets` | static | internal | manual | inline |
| `meal_slots` | admin | internal | manual | inline |
| `vault_categories` | admin | internal | manual | rows |
| `tags` | derived | `tags` table | 5 min | rows |
| `family_members` | derived | `family_members` table | 1 min | rows |
| `learning_subjects` | admin | internal | manual | rows |
| `learning_topics` | admin | internal | manual | rows |
| `transit_operators` | static | internal | manual | inline |
| `transit_regions` | static | internal | manual | inline |
| `transit_display_modes` | static | internal | manual | inline |
| `mtr_lines` | api | MTR API + bundled | 24 h | inline |
| `mtr_stations` | api | MTR API + bundled | 24 h | rows |
| `kmb_routes` | api | KMB static | 24 h | rows |
| `kmb_stops` | api | KMB static | 24 h | rows |
| `ctb_routes` | api | Citybus static | 24 h | rows |
| `ctb_stops` | api | Citybus static | 24 h | rows |
| `gmb_routes` | api | GMB static | 24 h | rows |
| `gmb_stops` | api | GMB static | 24 h | rows |
| `tools` | derived | `tools` table | 1 min | rows |
| `manifests` | derived | static + DB | 1 min | rows |
| `widget_surfaces` | static | internal | manual | inline |
| `notification_kinds` | static | internal | manual | inline |
| `tool_categories` | static | internal | manual | inline |
| `home_assistant_entities` | api | HA REST | 5 min | rows |

**Derived sets** (tags, members, tools) are materialized from their source tables by a short-TTL job. They exist so Hermes has one uniform interface — it never needs to know that tags come from a table and MTR stations come from an API.

---

### Block 5 — `text` — The Capability Snapshot

The single document Hermes fetches at session start. It is a **materialized view** of everything the agent needs to know about the household's current state.

```json
{
  "version": 148,
  "generated_at": "2026-09-29T00:30:00Z",
  "household": {
    "id": "uuid",
    "name": "Our Family",
    "timezone": "Asia/Hong_Kong",
    "locale": "en",
    "week_starts_on": "monday"
  },
  "actor": {
    "member_id": "uuid-dad",
    "role": "parent",
    "scopes": ["notes.read", "notes.write", "vault.read", "..."]
  },
  "tools": [
    {"name": "search", "category": "search", "mutates": false, "version": 3},
    {"name": "get_transit_arrivals", "category": "transport", "mutates": false, "version": 1},
    {"name": "create_note", "category": "notes", "mutates": true, "version": 2}
  ],
  "reference_sets": [
    {"key": "note_types", "version": 1, "updated_at": "...", "item_count": 15},
    {"key": "mtr_stations", "version": 4, "updated_at": "...", "item_count": 98},
    {"key": "mtr_lines", "version": 1, "updated_at": "...", "item_count": 10},
    {"key": "kmb_routes", "version": 12, "updated_at": "...", "item_count": 1408},
    {"key": "tags", "version": 87, "updated_at": "...", "item_count": 214},
    {"key": "family_members", "version": 3, "updated_at": "...", "item_count": 5},
    {"key": "vault_categories", "version": 2, "updated_at": "...", "item_count": 9}
  ],
  "enums": {
    "note_status": ["inbox", "active", "done", "archived", "expired"],
    "visibility": ["family", "parents", "private"],
    "transit_display_mode": ["compact", "expanded", "kid"],
    "sort": ["relevance", "updated_desc", "created_desc", "occurred_desc", "occurred_asc", "expiry_asc", "title_asc"]
  },
  "manifests": [
    {"id": "archify-gallery", "route": "/graph", "roles": ["parent", "child"]},
    {"id": "transit-widget", "surfaces": ["overview", "wall", "kid"]}
  ],
  "checksum": "sha256:..."
}
```

**Why one document:** Hermes makes **one** request at session start, not twenty. The document is small (typically < 50 KB), cacheable, and diffable.

**Versioning:** `version` increments whenever *any* constituent reference set, tool, or manifest changes. Hermes stores the version it last fetched. On each new user turn, it can cheaply check `GET /internal/agent/capabilities/version` (returns just the integer); if unchanged, its cached snapshot is valid.

---

### Block 6 — `text` — Publishing Flow (Human Edits)

When a human (or a worker) changes a master list, the system must publish that change.

```
Admin edits vault_categories (adds "Travel Documents")
        │
        ▼
services.reference.update_set(household, 'vault_categories', ...)
        │
        ├─ 1. Validate against set.schema (JSON Schema)
        ├─ 2. Compute new payload_checksum
        ├─ 3. If unchanged → update last_checked_at only, return
        ├─ 4. Diff old vs new (item-level add/update/remove)
        ├─ 5. Write reference_changes rows (one per changed item)
        ├─ 6. Bump reference_sets.version
        ├─ 7. Write to reference_items (large sets only)
        ├─ 8. Invalidate Redis caches for this set
        ├─ 9. Publish SSE event to /internal/agent/stream/changes
        ├─ 10. Publish to Redis pub/sub channel `ref:changed`
        ├─ 11. Invalidate capability snapshot (bump its version)
        └─ 12. Audit log entry
```

**Every step is transactional** except 9–11, which are best-effort (Redis pub/sub and SSE can be missed and recovered from on next fetch).

**Every master list mutation in the codebase must go through `reference.update_set`.** This is enforced by convention and by a test that greps for direct writes to `reference_items` outside the service module.

---

### Block 7 — `text` — Publishing Flow (API-Sourced Sets)

Bus routes and MTR stations come from external APIs. A cron worker refreshes them.

```
Every 24h: worker reference.refresh runs for all api-kind sets
        │
        ▼
For each set:
  ├─ Fetch source (HTTP, with retry + circuit breaker)
  ├─ Parse and canonicalize
  ├─ Compute checksum
  ├─ If checksum == current → update last_checked_at, done
  └─ If checksum differs:
      ├─ Diff (item-level)
      ├─ Write reference_changes
      ├─ Bump version
      ├─ Replace reference_items
      ├─ Invalidate caches
      ├─ Publish SSE + pub/sub
      └─ Notify admins: "MTR stations updated: 2 added, 0 removed"
```

**Admins get a notification when an API-sourced set changes.** This is important: a new MTR station opening is not just a data update, it is news. The notification links to a diff view.

**Manual re-check:** `POST /api/admin/reference/{key}/refresh` forces an immediate refresh. Useful when a user reports a missing station.

**Freeze:** `POST /api/admin/reference/{key}/freeze` stops automatic refresh. Useful when an upstream API is broken and the admin wants to keep the last known good data.

---

### Block 8 — `text` — Change Detection & the Diff

**Diff algorithm** for large sets:
1. Load current items into a dict keyed by `code`.
2. Load new items into a dict keyed by `code`.
3. `added = new - current`
4. `removed = current - new`
5. `updated = {code for code in both if data differs}`
6. Write one `reference_changes` row per item.

**Diff algorithm** for inline sets (small):
1. Canonicalize both payloads (sorted keys, sorted arrays by `code`).
2. Compute a JSON Patch (RFC 6902) between old and new.
3. Store the patch in `reference_changes.before/after` as `{patch: [...]}`.
4. This is cheaper than item-level diffing for small sets.

**Change kinds:**
| Kind | Meaning |
|---|---|
| `add` | Item did not exist before |
| `update` | Item exists; one or more fields changed |
| `remove` | Item no longer exists (soft: `active=false`) |
| `replace` | Whole set replaced (used when diff is too large to be meaningful) |

**Important:** removals are **soft**. `reference_items.active` is set to `false` rather than deleting the row. This preserves referential integrity — a Note that references `MTR-ADM` does not break if the station code is retired; instead the UI shows a "retired" badge.

---

### Block 9 — `text` — The Hermes Freshness Guide

This is the operational protocol Hermes follows. It is injected into the system prompt as a short instruction and backed by a detailed doc the agent can fetch.

### The short instruction (in the system prompt):

> You have access to a Capability Snapshot at `/internal/agent/capabilities`. It contains every tool, reference set, enum, and manifest currently available. Fetch it at session start. Before using any value from a reference set (a station code, a tag, a member ID, an enum value), validate it against that set with `/internal/agent/reference/{key}/validate`. If a tool returns `stale_reference`, refetch the set and retry once. Never invent IDs, enum values, or member references. If a value is not in the current set, ask the user; do not guess.

### The full protocol (fetchable via `GET /internal/agent/guide/freshness`):

**At session start:**
1. `GET /internal/agent/capabilities` → store the snapshot + its `version`.
2. Note the `version` in the conversation state.

**Before each user turn:**
3. `GET /internal/agent/capabilities/version` → returns `{version: N}`.
4. If `N == cached_version` → proceed with cached snapshot.
5. If `N > cached_version` → refetch the snapshot, diff mentally against the old one, and inform the user if a relevant set changed (e.g. "By the way, two new MTR stations were added since we last spoke").

**Before using a reference value:**
6. `POST /internal/agent/reference/{key}/validate` with `{value: "...", field: "code"}` → returns `{valid: true, item: {...}}` or `{valid: false, suggestions: [...]}`.
7. If invalid, use `suggestions` to offer alternatives, or ask the user.

**Before calling a tool:**
8. Confirm the tool is in the current snapshot's `tools` list.
9. Confirm the tool's `version` matches what the agent knows (if the agent has cached the schema).
10. Confirm the actor's `scopes` include the tool's required permissions.

**When a tool returns `stale_reference`:**
11. The tool tells you which set went stale.
12. Refetch that set: `GET /internal/agent/reference/{key}`.
13. Retry the tool call once.
14. If it fails again with `stale_reference`, surface the error to the user and stop retrying.

**When the user asks "what's new?":**
15. `GET /internal/agent/reference/changes?since={timestamp}` → returns all changes across all sets.
16. Summarize in natural language, grouped by set, most important first.

**When the user asks "what can you do?":**
17. Read from the cached snapshot's `tools` list, filtered by the actor's scopes. Never list tools the actor cannot use.

**On any uncertainty about a value:**
18. Do not guess. Fetch the set. Validate. Ask the user if ambiguous.

---

### Block 10 — `text` — Agent API Endpoints

All under `/internal/agent/*`, service-token only.

| Endpoint | Purpose |
|---|---|
| `GET /capabilities` | Full capability snapshot |
| `GET /capabilities/version` | Just the version integer (cheap) |
| `GET /capabilities/diff?from={version}&to={version}` | Structured diff between two snapshot versions |
| `GET /reference` | List all reference sets with metadata |
| `GET /reference/{key}` | Full items of one set |
| `GET /reference/{key}/item/{code}` | One item |
| `GET /reference/{key}/search?q=` | Fuzzy search within a set |
| `POST /reference/{key}/validate` | Validate a value against a set |
| `GET /reference/changes?since=&set_key=&limit=` | Change log |
| `GET /reference/{key}/changes?since=` | Change log for one set |
| `GET /stream/changes` (SSE) | Live stream of reference changes |
| `GET /guide/freshness` | This protocol, as a document |

**Validation response shape:**
```json
{
  "valid": false,
  "reason": "not_found",
  "suggestions": [
    {"code": "ADM", "label_en": "Admiralty", "label_tc": "金鐘", "score": 0.91},
    {"code": "ADW", "label_en": "Admiralty West (proposed)", "score": 0.74}
  ],
  "set_version": 4
}
```

Suggestions come from trigram similarity on `label_en`/`label_tc`, ranked by score. This is what lets Hermes gracefully handle typos and renamed stations.

**The `stale_reference` error code** is returned by any tool that accepted a reference value, if the value's set version has changed since the tool's last validation. Tools can opt out (e.g. tools that do not use reference values).

---

### Block 11 — `text` — Human-Facing Surfaces

**Admin: Reference Sets page** (`/admin/reference`)

| Column | Shows |
|---|---|
| Set key | `mtr_stations` |
| Name | "MTR Stations" |
| Kind | API / static / admin / derived |
| Items | 98 |
| Version | 4 |
| Last checked | 3 hours ago |
| Last changed | 2 weeks ago (2 added) |
| Actions | View · Refresh · Freeze · History |

**History view:** a timeline of changes for a set, each entry showing the diff (added/updated/removed items), who or what detected it, and when. Clicking a change shows the before/after of affected items.

**Manual edit view** (for `admin` kind sets only): a table editor for `vault_categories`, `learning_subjects`, `learning_topics`, `meal_slots`. Edits go through `reference.update_set`, so they generate changes and publish like anything else.

**Notifications:**
- API-sourced set changed → notification to all parents: "MTR Stations updated: 2 added."
- Admin-sourced set changed by another parent → notification to the other parents.
- Derived set changed → no notification (too noisy; tags change constantly).

**Search integration:** the `/search` page's tag facet and member facet read from the `tags` and `family_members` reference sets, so they always reflect current values.

**Config page integration:** the transit preset editor's stop/station search reads from `kmb_stops` / `mtr_stations`, so it always offers valid IDs.

---

### Block 12 — `text` — Worked Example: MTR Station Added

**Scenario:** In 2027 the MTR opens a new station. The MTR API updates. FamilyOS must reflect it — in the search UI, the transit preset editor, and Hermes's answers.

**T+0:** `reference.refresh` cron runs. Fetches `mtr_stations`. New checksum differs.

**T+1s:** Diff computed:
- `added`: 1 item (`code: "TKW"`, label "To Kwa Wan Extension")
- `updated`: 0
- `removed`: 0

**T+2s:** `reference_changes` row written. `mtr_stations.version` bumped from 4 to 5. Capability snapshot version bumped from 147 to 148. SSE event published.

**T+3s:** Cache invalidated. Notification sent to parents: "MTR Stations updated: 1 added — To Kwa Wan Extension."

**T+4s:** A parent opens `/settings/transit/new`. The station search now returns the new station. Its `code` is `TKW`.

**T+5s:** A parent asks Hermes: "Next train from the new To Kwa Wan Extension station?"
- Hermes checks its cached snapshot version (147).
- Calls `GET /capabilities/version` → 148. Different.
- Refetches `/capabilities` → sees `mtr_stations` at version 5.
- The tool `get_transit_arrivals` validates `station=TKW` against the current set → valid.
- Returns arrivals.

Without this system, Hermes would have confidently said "I don't know that station" — or worse, hallucinated a code — for the rest of the session.

---

### Block 13 — `text` — Worked Example: New Tag Created

**Scenario:** A user tags a note `#japan-2027`. Hermes is mid-conversation.

**T+0:** `services.reference.update_set('tags', ...)` runs (invoked by the tag service after a tag write).

**T+1s:** Diff: `tags` version 87 → 88, `added: {slug: "japan-2027"}`.

**T+2s:** SSE published. Capability snapshot version bumped.

**T+3s:** User asks Hermes: "Find everything tagged japan-2027."
- Hermes checks version: different.
- Refetches capabilities → sees the new tag.
- Calls `search` with `filters.tags = ["japan-2027"]` → returns results.

**If the user had asked before the tag existed,** Hermes would have validated `japan-2027` against the `tags` set, found it invalid, and either searched fuzzily (`suggestions`) or asked the user to confirm — instead of returning an empty result set and silently failing.

---

### Block 14 — `text` — Special Considerations

**Reconciliation on startup:** when the backend boots, it runs `reference.reconcile` — a job that checks every set's `last_checked_at` and refreshes anything past its TTL. This means a server that was down for a week catches up immediately.

**Reconciliation of derived sets:** derived sets (`tags`, `family_members`, `tools`) are recomputed from their source tables on every capability snapshot regeneration if their TTL has elapsed. This is cheap (indexed queries) and eliminates the risk of drift.

**Version monotonicity:** `version` is strictly increasing per set, per household. It never resets. If a set is fully replaced, version still increments.

**Checksum stability:** the checksum is computed on the **canonicalized** payload — keys sorted, arrays sorted by `code`, whitespace normalized. This ensures that cosmetic reorderings do not produce false changes.

**Redaction in change logs:** if an item contains sensitive fields (e.g. a vault category with a description containing a secret), `reference_changes.before/after` redacts those fields. Redaction rules are declared on the set's `schema`.

**Size limits:** `reference_items` is capped at 50,000 rows per set. KMB stops fit comfortably (~6,500). If a set ever exceeds this, it is stored as a compressed blob in `reference_sets.payload` and queried via an in-memory index rebuilt on load.

**Search integration for large sets:** `/internal/agent/reference/{key}/search?q=` uses trigram similarity on `label_en` and `label_tc`, capped at 20 results. This is what powers "find me the station for 'admiralty'".

**Conflict on concurrent edits:** `update_set` uses `SELECT ... FOR UPDATE` on the `reference_sets` row. The second writer waits, then re-runs the diff. Last-writer-wins at the item level; every write is logged.

**Backward compatibility:** when a reference set's schema changes (e.g. a new required field on `vault_categories`), `update_set` runs a schema migration on existing items, filling defaults for missing fields, and writes a `change_kind='replace'` entry. The old schema version is archived.

**No remote code execution:** reference sets are data, never code. A reference set cannot contain a script. This is enforced by validating all payloads against their JSON Schema and rejecting any field named `script`, `exec`, `code`, or `eval`.

---

### Block 15 — `text` — Agent Tools for Reference Data

New tools in `app/agent/tools/reference.py`:

| Tool | Params | Mutates |
|---|---|---|
| `list_reference_sets` | — | N |
| `get_reference_set` | `key` | N |
| `search_reference_set` | `key, query, limit=10` | N |
| `validate_reference_value` | `key, value, field='code'` | N |
| `get_reference_changes` | `since?, set_key?` | N |
| `get_capabilities` | — | N |
| `get_capabilities_version` | — | N |

All are `permissions=["reference.read"]`, granted to every role including `guest` and `device`. Reference data is not sensitive; it is the vocabulary of the system.

**Why these are tools and not just HTTP endpoints:** every capability Hermes uses must go through the Tool Registry. This keeps the audit trail complete and the permission model uniform. The `/internal/agent/reference/*` HTTP endpoints exist for performance (the capability snapshot) and for the SSE stream; the tool forms exist for the reasoning loop.

---

### Block 16 — `text` — Phase Placement & Acceptance

**Phase 1:** `reference_sets`, `reference_items`, `reference_changes` tables. `reference.update_set` service. Static sets seeded (`note_types`, `block_types`, `note_statuses`, `vault_categories`, `transit_operators`). `capability_snapshots` table and generation job. `/internal/agent/capabilities` + `/capabilities/version` + `/reference/{key}` + `/reference/{key}/validate`. The short freshness instruction injected into the Hermes system prompt.

**Phase 2:** API-sourced sets (`mtr_stations`, `mtr_lines`, `kmb_*`, `ctb_*`, `gmb_*`) with the 24 h refresh worker. Change notifications to parents. `/admin/reference` page with history view. `reference.reconcile` on startup. SSE stream `/internal/agent/stream/changes`. Full freshness guide fetchable at `/internal/agent/guide/freshness`.

**Phase 3:** `stale_reference` error code enforcement across tools. `get_reference_changes` tool. Capability diff endpoint. Home Assistant entities as a reference set. Derived set materialization for tools/manifests.

**Phase 4:** Cross-household reference sharing (e.g. a shared bus preset library). Reference set versioning with rollback (admin can revert to version N). Webhook publishing for external integrations.

**Acceptance (Phase 2):**
- [ ] `GET /internal/agent/capabilities` returns a complete snapshot in < 100 ms.
- [ ] `GET /internal/agent/capabilities/version` returns an integer in < 5 ms.
- [ ] Adding an MTR station via the API refresh updates the capability snapshot version within 60 s.
- [ ] A parent receives a notification when an API-sourced set changes.
- [ ] `POST /internal/agent/reference/mtr_stations/validate` correctly accepts `ADM` and rejects `XXX` with suggestions.
- [ ] Hermes, mid-conversation, correctly picks up a newly created tag without a session restart.
- [ ] `/admin/reference` shows the version history of every set with a readable diff.
- [ ] A schema change to `vault_categories` migrates existing items without data loss.
- [ ] `reference.update_set` is the only write path to `reference_items` (verified by a grep test in CI).
- [ ] The `stale_reference` error code path is exercised end-to-end: a tool called with a stale reference returns the code, Hermes refetches, and the retry succeeds.

---

### Block 17 — `text` — Why This Matters (The Meta-Point)

Most AI systems treat their vocabulary as static: it is baked into the prompt or the fine-tuning. This works until something changes.

FamilyOS treats its vocabulary as **live data with a version, a diff, and a subscription**. This has three consequences:

1. **Hermes is always correct about what exists right now**, not what existed when the container started.
2. **Humans edit master lists without coordinating with the AI** — the AI simply notices and adapts.
3. **Every change is auditable and reversible** — you can see exactly when the MTR added a station and what Hermes knew at that moment.

This is the difference between an assistant that is *sometimes right* and one that is *always grounded*. It is also what makes the system survive for years: master data changes constantly, and the system must bend without breaking.

The rule for the coding agent: **if it is a list, it is a Reference Set; if it changes, it publishes; if the agent uses it, the agent validates it first.**

---

**End of Note B.**
`status='active'` · `pinned=false` · `tags=['master-data','reference-data','agent','capabilities','v1.1']` · `visibility='parents'`