# Part 1 — Archify Gallery: Complete Design

**Archify Gallery** = the *archive* + *graphify* view. A single surface that lets a human (or the agent) browse the entire family knowledge base as an **interactive graph** — nodes are Notes, Blocks, Tags, Members, Media, and Events; edges are relations, shared tags, ownership, temporal adjacency, and semantic similarity. It is simultaneously a **gallery** (visual grid of media/notes) and a **graph** (topology of how everything connects).

It is not a separate data store. It is a **projection** of the Note system, exposed as a first-class tool through the same Tool Registry.

---

## A1. What Archify Visualizes

The graph is derived, never authored. Five layers, all optional and toggleable:

| Layer | Nodes | Edges | Source |
|---|---|---|---|
| **Relation** | notes | `note_relations` (typed) | explicit links |
| **Hierarchy** | notes | `parent_note_id` | nesting |
| **Tag** | notes ↔ tags | `note_tags` | tagging |
| **Semantic** | notes/blocks | cosine similarity > threshold | `embeddings` |
| **Temporal** | notes/events | `occurred_at` / `starts_at` adjacency | time |
| **Ownership** | notes ↔ members | `owner_member_id`, `created_by` | attribution |
| **Media** | notes ↔ media | `note_blocks.media_asset_id` | attachments |

**Default view** = Relation + Hierarchy + Tag, colored by type, sized by recency/importance.

---

## A2. Schema Additions

```sql
-- Saved graph presets (a "bookmark" of a view state)
graph_views(
  id uuid pk, household_id uuid not null,
  name text not null, description text,
  config jsonb not null,          -- {scope, node_types[], edge_types[], filters{}, layout, colors, cluster_by}
  is_shared bool default false,
  share_token text unique,
  created_by uuid references family_members(id),
  order_index int default 0,
  created_at timestamptz default now(), updated_at timestamptz default now()
);
create index on graph_views (household_id, order_index);

-- Precomputed 2D/3D projections of embeddings (UMAP / t-SNE / PCA)
graph_projections(
  id uuid pk, household_id uuid not null,
  method text not null,           -- 'umap' | 'tsne' | 'pca'
  params jsonb not null default '{}',
  dims smallint not null default 2,
  model text not null,            -- embedding model this was computed against
  node_count int, status text default 'pending',
  computed_at timestamptz, created_at timestamptz default now(),
  unique(household_id, method, model, params)
);

graph_node_positions(
  projection_id uuid references graph_projections(id) on delete cascade,
  owner_type text not null check (owner_type in ('note','block')),
  owner_id uuid not null,
  x real not null, y real not null, z real,
  cluster_id int,
  primary key (projection_id, owner_type, owner_id)
);
create index on graph_node_positions (projection_id, cluster_id);

-- Cached force-layout results for named views (avoid recomputing on every load)
graph_layout_cache(
  id uuid pk, household_id uuid not null,
  view_hash text not null,        -- sha256 of normalized config
  layout jsonb not null,          -- {nodes:[{id,x,y}], edges:[...] }
  node_count int, edge_count int,
  computed_at timestamptz default now(),
  unique(household_id, view_hash)
);
create index on graph_layout_cache (household_id, computed_at desc);
```

**Why cache layouts:** a 5k-node force simulation takes 10–30 s in the browser. Precomputing server-side and streaming positions makes the gallery feel instant. Cache is invalidated by `view_hash` (config change → new hash → recompute).

---

## A3. Backend API

| Endpoint | Purpose |
|---|---|
| `GET /api/graph` | Nodes + edges for a scope, with filters |
| `GET /api/graph/neighborhood/{type}/{id}?depth=2` | Ego graph around one node |
| `GET /api/graph/path?from={type}:{id}&to={type}:{id}&max_depth=4` | Shortest path |
| `GET /api/graph/clusters?method=umap\|hdbscan&min_size=3` | Semantic clusters |
| `GET /api/graph/stats` | Degree histogram, component count, density |
| `GET /api/graph/views` · `POST/PATCH/DELETE /api/graph/views/{id}` | Saved views CRUD |
| `POST /api/graph/views/{id}/share` · `DELETE …/share` | Share links |
| `GET /api/graph/views/{id}/layout` | Cached layout (or compute+stream SSE) |
| `GET /api/graph/export?format=png\|svg\|json\|graphml\|csv` | Export |
| `POST /api/graph/recompute` (admin) | Trigger projection + cache rebuild |

### Query parameters for `GET /api/graph`

```
scope          = all | recent | search:{q} | tag:{slug} | member:{id} | note:{id} | cluster:{id}
node_types     = note,block,tag,member,media,event    (default: note,tag)
edge_types     = relation,hierarchy,tag,semantic,temporal,ownership,media
depth          = int (for scope=note) default 1, max 4
semantic_thresh= float (0–1) default 0.72
limit          = int default 2000 (hard cap 20000)
since / until  = timestamptz
include_vault  = bool default false (parent-only, audited)
```

### Response shape

```json
{
  "nodes": [
    {"id": "note:uuid", "type": "note", "label": "Japan trip planning",
     "note_type": "freeform", "importance": 3, "created_at": "…",
     "size": 12.4, "color_key": "freeform", "tags": ["travel","2027"],
     "thumb_url": "…", "cluster_id": 4, "pinned": false}
  ],
  "edges": [
    {"id": "e1", "source": "note:a", "target": "note:b",
     "type": "relation", "relation_type": "references", "weight": 1.0}
  ],
  "meta": {"node_count": 412, "edge_count": 1308, "truncated": false,
           "projection_id": "…", "generated_at": "…"}
}
```

Response is streamed for large graphs (`Transfer-Encoding: chunked`) with a `meta` trailer.

---

## A4. Worker Jobs

| Job | Trigger | Output |
|---|---|---|
| `graph.project` | cron nightly 03:00 + on demand | `graph_projections` + `graph_node_positions` |
| `graph.layout` | on first request of a view, or nightly for pinned views | `graph_layout_cache` |
| `graph.cluster` | after `graph.project` | `cluster_id` per node |
| `graph.stats` | after `graph.project` | Redis cache, 1h TTL |

**Projection pipeline:**
1. Fetch all `embeddings` for the household (excluding vault).
2. UMAP → 2D (and 3D if `dims=3`).
3. HDBSCAN over the same vectors → cluster labels.
4. Write `graph_node_positions`.
5. Invalidate `graph_layout_cache` for affected views.

**Scale guard:** if `node_count > 50_000`, downsample by importance+recency before projecting, and mark the projection `sampled=true` (surfaced in UI).

---

## A5. Agent Tools (new, added to §14)

| Tool | Params | Mutates | Notes |
|---|---|---|---|
| `graph_overview` | `scope?, limit=200` | N | Returns top nodes + edges by centrality |
| `graph_neighborhood` | `node_type, node_id, depth=2, node_types?` | N | Ego graph |
| `graph_path` | `from, to, max_depth=4` | N | Shortest path, human-readable |
| `graph_clusters` | `method='umap', min_size=3, query?` | N | Semantic clusters with labels |
| `semantic_neighbors` | `note_id, k=10` | N | k-NN over embeddings |
| `explain_connection` | `a, b` | N | "These two notes are connected because…" |
| `create_graph_view` | `name, config` | **Y** | Save a preset |
| `list_graph_views` | — | N | |

`graph_path` and `explain_connection` are what make Hermes dramatically more useful: *"How is the Japan trip note connected to the school fee note?"* → path: `japan_trip → tagged travel → shared tag with → school_trip_2027 → references → school_fees`.

**Tool registration example:**

```python
# app/agent/tools/graph.py
class ExplainConnectionParams(BaseModel):
    a: str   # "note:uuid"
    b: str

@register(
    name="explain_connection",
    description="Explain how two entities are connected in the family knowledge graph.",
    category="graph",
    params=ExplainConnectionParams,
    permissions=["notes.read"],
)
async def explain_connection(p: ExplainConnectionParams, ctx: ToolContext) -> ToolResult:
    path = await graph_service.shortest_path(ctx.household_id, p.a, p.b, max_depth=4)
    return ToolResult(ok=True, data=graph_service.explain(path, ctx))
```

---

## A6. Frontend Architecture

**Route:** `/graph` in `frontend-main`. Shareable read-only at `/graph/share/{token}`.

**Stack addition:** `sigma.js` + `graphology` (WebGL, scales to 100k nodes), `d3-force` for server-parallel layouts, `@react-spring/web` for transitions, `umap`-projected positions from the API.

| Component | Responsibility |
|---|---|
| `GraphCanvas` | sigma.js renderer, camera, LOD, hit-testing |
| `GraphControls` | filters, node/edge type toggles, semantic threshold slider |
| `NodeInspector` | side panel: preview, open note, related items |
| `ClusterLegend` | color legend by cluster / type / member |
| `ViewManager` | save / load / share named views |
| `MiniMap` | overview with viewport rectangle |
| `TimelineScrubber` | filter by `occurred_at` range, animated play |
| `LayoutPicker` | force / radial / timeline / semantic / cluster / tree |
| `GalleryGrid` | alternate mode: visual grid with edge overlays |

### Modes (one page, switchable)

1. **Graph** — pure topology (default).
2. **Gallery** — masonry grid of note/media thumbnails; edges drawn as thin arcs between cards on hover/selection. *This is the "gallery" half of Archify.*
3. **Timeline** — notes positioned by `occurred_at` on X, cluster on Y.
4. **Clusters** — semantic clusters as bubbles; drill in to expand.
5. **Radial** — selected node at center, rings by hop distance.
6. **Tree** — hierarchy via `parent_note_id` (folder-like).

### Interaction model

| Action | Behavior |
|---|---|
| Hover node | highlight neighbors, dim rest, show tooltip |
| Click node | open `NodeInspector`, load preview |
| Double-click | open the note in a new pane |
| Right-click | context menu: pin, tag, relate, hide, expand |
| Drag | reposition (local only unless saved) |
| Scroll | zoom; at LOD threshold, labels fade, thumbs appear |
| Shift+drag | box select → bulk actions |
| `/` | focus search inside graph (live-filter nodes) |
| `g` `f` `t` `c` | jump to Graph / Force / Timeline / Clusters |
| `Esc` | clear selection |

### Performance rules
- Render via WebGL only (`sigma.js`); fall back to canvas 2D below 2k nodes on low-end devices.
- Server-computed layout → browser never runs a full force sim on load.
- LOD: below zoom `z<0.3` render dots only; `0.3–0.8` add labels; `>0.8` add thumbnails.
- Edge bundling for the Tag and Semantic layers when edge count > 5k.
- Virtualize the `GalleryGrid` with `@tanstack/react-virtual`.
- Web Worker for local re-layout after a filter change (so UI never blocks).

---

## A7. Permissions & Privacy

- `include_vault=false` is enforced **server-side**, always, unless the caller is a parent and explicitly passes `true`.
- Vault nodes, when included, render with a distinct lock icon and a blur until clicked; clicking requires a fresh re-auth (session re-confirmation, not just a token check).
- Every `include_vault=true` graph request writes an `audit_log` row.
- Semantic edges never connect to vault nodes unless both endpoints are visible to the caller.
- Share links carry the *viewer's* permission scope, not the creator's: a babysitter share of a graph shows only `visibility='family'` nodes.

---

## A8. Wall & Kid Integration

- **Wall widget `KnowledgeGraphWidget`** — rotating slow-pan of the last 30 days of activity, plus a "constellation" of recent captures. Read-only, 60 s refresh, no interaction.
- **Kid Portal "Constellation"** — the child's own learning topics as stars; connecting lines show topic prerequisites; completed topics glow. Uses the same graph API scoped to `member:{child_id}` with `node_types=learning_topic`.

---

## A9. Manifest Entries

```ts
// frontend-main/lib/registry.ts
{
  id: "archify-gallery",
  name: "Archify Gallery",
  category: "knowledge",
  icon: "network",
  route: "/graph",
  roles: ["parent", "child"],
  order: 30,
  enabled: true,
  surfaces: ["main", "wall"],
  toolSlug: "graph_overview",
}
```

```ts
// widget manifest
{
  id: "knowledge-graph",
  name: "Knowledge Graph",
  surfaces: ["wall"],
  component: "KnowledgeGraphWidget",
  dataSource: "/api/graph?scope=recent&limit=200",
  refreshSeconds: 60,
  size: "lg",
  roles: ["parent", "child", "guest"],
}
```

---

## A10. Phase Placement

| Phase | Scope |
|---|---|
| **Phase 2** | Basic graph: Relation + Hierarchy + Tag layers, force layout, NodeInspector, save views. No semantic layer yet (embeddings just landed). |
| **Phase 3** | Semantic layer (UMAP projection, HDBSCAN clusters), Gallery mode, Timeline mode, share links, agent tools (`graph_path`, `explain_connection`, `semantic_neighbors`). |
| **Phase 4** | 3D mode, cluster drill-down, cross-household graphs, real-time activity animation, GraphML export for external tools. |

## A11. Acceptance Criteria (Phase 2 baseline)
- [ ] Opening `/graph` on a 2,000-note household renders in < 2 s.
- [ ] Hover highlights neighbors; click opens inspector; double-click opens the note.
- [ ] Filters by tag, type, member, and date all work and are URL-encoded (deep-linkable).
- [ ] A view can be saved, named, and reopened with identical layout.
- [ ] A view can be shared via token with correct permission scoping.
- [ ] `graph_overview` and `graph_path` tools return correct data via `/internal/agent/tools`.
- [ ] Vault nodes are absent unless `include_vault=true` from a parent; that request is audited.

---

# Part 2 — The New Note

Below is the **Note record** as it would be stored in FamilyOS. It is a `freeform` note, `pinned=true`, `visibility=parents`, tagged `blueprint`, `v1.1`. The blocks contain the full updated master plan. This note is the artifact you hand to the coding agent.

---

**Note**
```json
{
  "title": "FamilyOS 2027 — Master Blueprint v1.1",
  "type": "freeform",
  "status": "active",
  "visibility": "parents",
  "pinned": true,
  "owner_member_id": null,
  "tags": ["blueprint", "architecture", "v1.1", "agent-ready"],
  "summary": "Definitive implementation blueprint for FamilyOS 2027. Notes+Blocks spine, Tool Registry for Hermes, three frontends, no nginx. v1.1 adds the Archify Gallery (knowledge graph surface).",
  "ai_summary": null,
  "extra": { "doc_version": "1.1", "supersedes": "1.0", "target_reader": "coding-agent" }
}
```

**Blocks**

---

### Block 1 — `text` — Preamble

> **FamilyOS 2027 — Master Blueprint v1.1**
> Supersedes v1.0. Adds §A: Archify Gallery. All other sections unchanged except where explicitly marked ⟦v1.1⟧.
> **Sections marked ⟦DECIDED⟧ are binding choices made to remove ambiguity. Change them in this document first, never in code.**
> **Rule for the coding agent:** never invent a parallel system. If a feature can be expressed as a Note, a Block, a Tool, a Manifest, or a Graph projection, it must be.

---

### Block 2 — `text` — §1 Vision & Principles

FamilyOS is a self-hosted family knowledge & operations system. It exists to make **capture effortless** and **retrieval instant** — for humans and for an AI agent.

**Goals:** (1) instant capture of anything; (2) family coordination; (3) extensibility without rewrites; (4) agent-ready by construction; (5) local-first, privacy-first.

**Binding principles:**
1. Backend and all UIs strictly separated.
2. Notes are the universal capture format.
3. Everything an AI might need is exposed only through the Tool Registry.
4. Tools & Games are deliberately easy to extend.
5. Dark, calm for capture; dense for overview.
6. Chores, expiry, meals, vault, **and the Archify graph** build on the Note model — never parallel systems.
7. Everything is auditable.
8. Local-first; AI degrades gracefully.
9. Idempotent by default.
10. Fail soft — a broken worker never blocks capture.

**Non-goals:** multi-tenant SaaS, collaborative editing, ERP/medical records, device control (we integrate Home Assistant), native mobile apps before Phase 4.

---

### Block 3 — `text` — §2 Glossary & Conventions

**Note** — universal capture object. **Block** — ordered typed content inside a Note. **Member** — a person. **Actor** — member, device, or agent. **Tool** — typed, registered backend capability. **Manifest** — declarative frontend entry. **Enrichment** — background OCR/ASR/LLM/embed. **Vault** — permission-gated overlay. **Wall** — ambient read-only dashboard. **Kid Portal** — simplified child UI. **Hermes** — agent runtime, no DB access. **Archify Gallery** — graph projection of the knowledge base (v1.1).

**Conventions:** DB `snake_case`, plural, uuid PKs, `timestamptz`, soft delete. Python `snake_case`/`PascalCase`. TS `kebab-case` routes. Tools `snake_case` verb-first. Manifest IDs `kebab-case`. All timestamps UTC; display in household timezone; week starts Monday (configurable).

---

### Block 4 — `text` — §3 Architecture (No Nginx)

```
┌──────────────────────── Docker network: familyos ────────────────────────┐
│  postgres+pgvector   redis   minio   embeddings(optional)                │
│         ▲              ▲       ▲            ▲                           │
│         └──────────────┼───────┼────────────┘                           │
│                        │       │                                        │
│              ┌─────────┴───────┴──────────┐                             │
│              │   backend (FastAPI :8000)  │                             │
│              │   REST /api/*              │                             │
│              │   Internal /internal/*     │                             │
│              │   Tool Registry            │                             │
│              └───────┬───────────┬────────┘                             │
│                      │           │                                      │
│           ┌──────────┴──┐   ┌────┴─────────┐                            │
│           │  worker     │   │  hermes      │                            │
│           │  (ARQ)      │   │  (:8100)     │                            │
│           └─────────────┘   └──────────────┘                            │
│                                                                          │
│   frontend-main(:3000)  frontend-wall(:3001)  frontend-kid(:3002)        │
└──────────────────────────────────────────────────────────────────────────┘
```

**Networking ⟦DECIDED⟧:** No nginx. Server-to-server uses `http://backend:8000`. Browser calls its own origin `/api/*`; each Next.js app rewrites `/api/* → http://backend:8000/api/*` (`next.config.ts`, `output:'standalone'`). This removes CORS, keeps the backend off the host in prod, and enables same-origin `httpOnly` cookies. Only frontend ports are published.

**Request paths:** `/api/*` (JWT or device token) · `/internal/agent/*` (service token, network-only) · `/internal/enrich/*` · `/healthz /readyz` · `/metrics`.

**Failure isolation:** redis down → outbox queues jobs, FTS still works. minio down → text capture works, media returns 503. hermes down → chat degrades, nothing else. embeddings down → `embedding_status='pending'`, backfilled later. **Graph projection worker down → Archify shows last cached layout, marked stale.**

---

### Block 5 — `text` — §4 Technology Stack

Backend: Python 3.12, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, Pydantic v2, `uv`.
Queue: **ARQ** ⟦DECIDED⟧ (async-native, Redis-only, built-in cron).
DB: Postgres 16 + pgvector + pg_trgm + unaccent + btree_gin.
Storage: **MinIO** in compose, local-disk capable behind `StorageBackend` protocol ⟦DECIDED⟧.
Embeddings: `bge-m3` @ 1024 dims via Ollama (default), OpenAI optional ⟦DECIDED⟧.
OCR: tesseract (default) or paddleocr. ASR: faster-whisper. Vision/LLM: ollama (llava/qwen2.5) or OpenAI.
Frontends: Next.js 15 App Router + React 19 + TS + Tailwind + shadcn/ui.
**⟦v1.1⟧ Graph rendering: `sigma.js` + `graphology` (WebGL), `d3-force` server-side, UMAP (Python `umap-learn`), HDBSCAN for clustering.**
Agent: Hermes FastAPI `:8100`, SSE streaming.
Testing: pytest + testcontainers, Playwright. Observability: structlog, Prometheus, optional OTel.

---

### Block 6 — `text` — §5 Repository Layout

```
familyos/
├── docker-compose.yml  docker-compose.dev.yml  .env.example  Makefile
├── docs/  (BLUEPRINT.md  DECISIONS.md  TOOLS.md  SCHEMA.md)
├── backend/
│   ├── pyproject.toml  Dockerfile  alembic.ini  alembic/
│   └── app/
│       ├── main.py
│       ├── core/       config security crypto db redis storage queue logging errors pagination time
│       ├── models/     household user member note block tag relation embedding media
│       │               event task school learning chore reward points meal shopping
│       │               vault home notification share tool audit job
│       │               graph        ⟦v1.1⟧
│       ├── schemas/
│       ├── api/        deps router auth members notes blocks media search
│       │               events tasks chores rewards meals shopping vault
│       │               school learning home notifications tools manifests share
│       │               graph        ⟦v1.1⟧
│       │               internal_agent
│       ├── services/   notes blocks media search enrichment expiry calendar tasks
│       │               chores rewards points meals shopping vault school learning
│       │               home notifications sharing audit
│       │               graph        ⟦v1.1⟧
│       │               providers/   (llm, ocr, asr, embedding)
│       ├── agent/
│       │   ├── registry.py  executor.py  context.py
│       │   └── tools/  notes search calendar tasks chores meals vault learning
│       │               expiry home media ingestion
│       │               graph        ⟦v1.1⟧
│       │               utilities/  games/
│       └── workers/    settings tasks_enrich tasks_media tasks_sync
│                       tasks_expiry tasks_digest
│                       tasks_graph  ⟦v1.1⟧
├── hermes/
├── frontend-main/  (app/, components/, lib/registry.ts, lib/graph/ ⟦v1.1⟧)
├── frontend-wall/  frontend-kid/
└── tools/
```

---

### Block 7 — `text` — §6 Notes & Blocks

**Note** fields: `id, household_id, title, type, status, summary, ai_summary, created_by, owner_member_id, visibility, pinned, occurred_at, expires_at, location jsonb, parent_note_id, extra jsonb, embedding_status, search_tsv, timestamps, deleted_at`.

Types: `freeform, account, coupon, meeting, map, timeline, vault, chore, meal, receipt, school_notice, learning, contact, medical, custom`.

**Block** fields: `id, note_id, order_index (gaps of 1000), type, text_content, media_asset_id, data jsonb, caption, ai_description, ocr_text, transcript, expires_at, importance, search_tsv, timestamps`.

Block types: `text, image, video, voice, file, link, account, coupon, meeting, map, timeline, vault, structured, checklist`. Each has a defined `data` shape and an enrichment path (see v1.0 §6.3 table).

**Quick Capture flow:** client → `POST /api/media/presign` → PUT to MinIO → `POST /api/notes` with `media_asset_ids` → note created `status='inbox'` → outbox row in same tx → ARQ enqueue post-commit → enrichment pipeline → searchable.

**Critical:** enqueue happens *after* commit via an outbox table (or `LISTEN/NOTIFY`). No lost jobs.

**Note vs domain rows:** domain records (chores, meals, events, vault items) are separate tables linking `note_id`. The Note is the journal; the domain row is operational state.

---

### Block 8 — `text` — §7 Database Schema (Key Tables)

Full DDL in v1.0 §7. Summary:

**Identity:** `households, users, family_members, device_tokens`.
**Notes core:** `notes, note_blocks, tags, note_tags, note_relations, embeddings(vector 1024, HNSW)`.
**Media:** `media_assets` (dedupe by sha256, enrichment_status).
**Calendar/tasks:** `events, tasks`.
**School/learning:** `school_notices, learning_subjects, learning_topics, learning_results, quizzes, study_sessions`.
**Chores/rewards:** `chores, chore_completions, rewards, reward_redemptions, points_ledger` (append-only authoritative; `points_cached` denormalized).
**Meals/shopping:** `meals, shopping_lists, shopping_items`.
**Vault:** `vault_categories, vault_items` (encrypted payload + wrapped DEK).
**Home/notifications/sharing:** `house_devices, notifications (dedupe_key), share_links`.
**Tools/audit/jobs:** `tools, agent_tool_calls, audit_log, jobs_outbox`.
**⟦v1.1⟧ Graph:** `graph_views, graph_projections, graph_node_positions, graph_layout_cache`.

All timestamps `timestamptz`; soft delete via `deleted_at`; `search_tsv` generated columns with GIN indexes.

---

### Block 9 — `text` — §8 Media & Storage

**Layout:** `{household_id}/media/{yyyy}/{mm}/{asset_id}/{original|thumb|poster|waveform}.{ext}`; vault media under `vault/` with unguessable paths.

**Presigned upload:** `POST /api/media/presign` (dedupe by sha256) → client PUT → `POST /api/media/{id}/complete` → verify → `enrichment_status='pending'` → enqueue.

**Derivatives:** images → thumb(400w)+preview(1600w), EXIF stripped; video → poster+thumb+duration+audio extract; audio → waveform+normalized m4a; pdf → page-1 thumb + text layer. Any → sha256.

**Vault encryption:** encrypted before upload with a per-asset DEK. Signed URLs, 5-min TTL, permission-checked.

---

### Block 10 — `text` — §9 Enrichment Pipeline

**Jobs:** `media.thumbnail, media.probe, ocr.image, asr.audio, vision.describe, extract.document, extract.structured, note.summarize, note.autotag, embed.note, embed.blocks, expiry.scan (cron), calendar.sync (cron 15m), digest.daily (cron 06:30), ⟦v1.1⟧ graph.project (cron 03:00), graph.layout, graph.cluster, graph.stats`.

**Status:** `pending → running → complete | failed(retry ×3 backoff 30s/5m/30m) | dead`. Aggregated to `notes.embedding_status` (`pending|partial|complete|failed|skipped`).

**Chunking:** note embedding = `title + summary + ai_summary + first 800 chars of concatenated block text`; block embeddings = ~512 tokens, 64 overlap; structured data stringified as `"key: value"`. **Never embedded:** `password_enc`, `totp_secret_enc`, vault payloads; vault notes searchable by title/tag only, permission-gated.

**Idempotency:** job key = `{kind}:{owner_id}:{content_hash}`. Per-household daily LLM budget; kill switch `AI_ENRICHMENT_ENABLED=false`; `LOCAL_ONLY=true` keeps OCR/ASR but disables LLM.

---

### Block 11 — `text` — §10 Search

**FTS:** `tsvector` GIN, weights A/B/C, `websearch_to_tsquery`, `pg_trgm` fuzzy fallback.

**Semantic:** cosine over HNSW index; `1 - (embedding <=> qvec)`.

**Embedding model ⟦DECIDED⟧:** `bge-m3` @ 1024 dims (multilingual, offline). Switching models requires a backfill job `embed.rebuild`; old-model rows marked stale; search filters to active model. **Never mix models in one index.**

**Hybrid (default for UI and Hermes):** RRF — FTS top 50 + vector top 50, `score(d)=Σ1/(60+rank)`, then filters. Robust to scale mismatch.

**Permissions:** visibility predicate applied to every search path (`family|parents|private`). Vault excluded unless `include_vault=true` and caller has `vault.read` + parent role.

---

### Block 12 — `text` — §11 Auth, Roles, Encryption

**Tokens:** access JWT 15 min, refresh 30 d rotating, device token 1 y (paired via short code), service token (static), share-link token (≤7 d, scoped). All cookies `httpOnly; SameSite=Lax`; `Secure` when TLS upstream.

**Roles:** `parent` (all + vault + admin + approve + award), `child` (own notes/chores, learning, rewards, kid tools), `guest` (read shared + calendar + guest tools), `device` (paired scopes).

**Scope enforcement in three layers:** API dependency, service layer, tool registry `permissions=[...]`.

**Vault:** requires `vault.read` + `vault_categories.min_role`; every read audited; agent `search_vault` additionally requires `role=parent`.

**Envelope encryption ⟦DECIDED⟧:** `MASTER_KEY →(HKDF) KEK per household →(wrap) DEK per item →(AES-256-GCM) ciphertext` with AAD `"{table}:{row_id}"`. Stored: `encrypted_payload, dek_wrapped, key_id`. Key rotation re-wraps DEKs only.

---

### Block 13 — `text` — §12 Agent Tool Registry

**Principle:** Hermes never issues SQL, never receives DB credentials. It sees only (1) tool names + JSON schemas, (2) tool results.

**Contract:** `ToolContext` (household, actor, role, scopes, tz, request_id, idempotency_key), `ToolResult` (ok, data, error, error_code, meta), `@register(name, description, category, params, permissions, mutates, result)`.

**Executor responsibilities** (the only path a tool runs): resolve → validate params → check permissions ⊆ scopes → if `mutates` and agent and no `confirm_token` return `confirmation_required` with preview → idempotency cache check → transaction → handler → commit → write `agent_tool_calls` (redacted params) → Prometheus metric → on error rollback + sanitized `internal_error`.

**Exposure:** `GET /internal/agent/tools`, `POST /internal/agent/tools/{name}`, `GET /internal/agent/tools/{name}/schema`. Service token required, network-only.

---

### Block 14 — `text` — §13 Hermes Agent

FastAPI `:8100`, `POST /chat` streams SSE (`token | tool_call | tool_result | final | confirmation_required`).

**Loop:** assemble context (system prompt, history, cheap semantic pre-pass) → LLM with tool schemas → on `tool_calls` invoke via `/internal/agent/tools/{name}` → append results → if `confirmation_required` surface a UI card and pause → loop max 8 iterations → stream final answer with citations.

**Guardrails:** no DB access · write confirmation surfaced through UI (not LLM) · scope ceiling = requesting member · 8-iteration cap · token budget with partial-answer fallback · retrieved content wrapped in `<untrusted_content>` and system prompt forbids following embedded instructions · vault writes UI-only until Phase 4 · 30 tool calls/min.

**Memory:** conversation in Postgres; long-term facts are **Notes tagged `agent-memory`** (user-visible, editable, deletable). No hidden vector store — Hermes's memory *is* the Note system.

---

### Block 15 — `text` — §14 Tool Catalogue

**Notes:** `search_notes, semantic_search, hybrid_search, get_note, get_blocks, create_note, append_block, update_note, delete_note, link_notes, add_tag, remove_tag`.
**Calendar/Tasks:** `list_events, create_event, update_event, list_tasks, create_task, complete_task`.
**Chores/Rewards:** `list_chores, create_chore, complete_chore, approve_chore, get_points_balance, award_points, list_rewards, redeem_reward`.
**Expiry:** `get_expiring_items(days=30), snooze_expiry`.
**Meals/Shopping:** `list_meals, plan_meal, generate_shopping_list, get_shopping_list, add_shopping_item, check_shopping_item, find_past_meals`.
**Vault:** `search_vault, get_vault_item` (read-only until Phase 4).
**Learning:** `search_learning_results, get_weak_topics, generate_quiz, log_study_session`.
**Media/Ingestion:** `ingest_media, extract_and_create, get_media_url, attach_media_to_note`.
**Home/System:** `get_home_status, list_tools, run_tool, get_family_overview`.
**Utilities/Games:** `resistor_calculator, json_parser, date_calculator, unit_converter, maths_revision`.

**⟦v1.1⟧ Graph:** `graph_overview, graph_neighborhood, graph_path, graph_clusters, semantic_neighbors, explain_connection, create_graph_view, list_graph_views`.

**Rule:** adding a tool = write the function + decorator. Auto-discovery via `pkgutil.iter_modules`; registry cached in Redis with a version hash.

---

### Block 16 — `text` — §15 Four Pillars

**A. Chores & Rewards.** Tables `chores, chore_completions, rewards, reward_redemptions, points_ledger`. `chores.note_id` links to a Note for instructions/proof/comments. Flow: parent creates → child completes (optional photo) → parent approves → ledger row → `points_cached` updated → reward redeem → parent approves → negative ledger. Recurrence via RRULE, computed on the fly ⟦DECIDED⟧ (no materialization). Streaks computed, not stored.

**B. Expiry Tracking (Universal).** Sources: `notes.expires_at`, `note_blocks.expires_at`, `vault_items.expires_at`, `extra` fields. Dashboard colors 🔴≤7d, 🟠8–30d, 🟡31–90d, ⚪>90d. Nightly `expiry.scan` creates one notification per threshold per item via `dedupe_key`.

**C. Meals & Shopping.** `meals, shopping_lists, shopping_items`; `meals.note_id` → recipe Note (enables "what did we cook last time we had X?"). `generate_shopping_list(from_meal_ids)` merges/dedupes/categorizes. Dinner meals create calendar events for the Wall.

**D. Family Vault.** `vault_categories, vault_items` overlay on Notes of `type='vault'`, `visibility='parents'`. Categories: Identity, Medical, Insurance, Finance, Property, Kids' Documents, Vehicles, Travel, Other. Encryption §11. Share links scoped to one item/category, ≤7 d, optional PIN, audited. Expiry integration into (B). Agent read-only, parent-only.

---

### Block 17 — `text` — §16 Other Domains

**Calendar:** local + Google two-way sync, worker every 15 min, `(source, external_id)` unique. School notices with `due_date` create tasks; `action_required` creates notifications.

**School notices:** `school_notice` Note + `extract.structured` pulling school, child, dates, category, action, summary. Surfaced in Overview, Kid Portal, Wall.

**Learning Hub:** subjects → topics → results. Quizzes generated from topic Notes via `generate_quiz`. `get_weak_topics` powers Kid Portal "practice these 5 today".

**Home status:** read-only Home Assistant, 30 s Redis TTL, Wall widget. No control until Phase 3+ with explicit confirmation.

---

### Block 18 — `text` — §17 Notifications

`kind (expiry|chore|event|school|reward|digest|agent|system)`, `priority (1 urgent push, 2 in-app, 3 digest-only)`, `channel (inapp|webpush|email)`, `dedupe_key` unique per household, `scheduled_for`. Quiet hours 21:00–07:00 (priority 2/3 held; priority 1 delivers). Daily digest 06:30 household tz. Weekly digest Sun 18:00.

---

### Block 19 — `text` — §18 Frontend Architecture

Three apps: `frontend-main :3000` (full), `frontend-wall :3001` (ambient read-only), `frontend-kid :3002` (missions/learning/games). Shared Tailwind + shadcn (each app owns its own `components/ui/` ⟦DECIDED⟧ to avoid cross-app build coupling) + typed API client + manifest consumer.

**Main routes:** `/login / /notes /notes/[id] /notes/search /capture /calendar /chores /rewards /meals /learning /vault /vault/share/[token] /tools /tools/[slug] /notifications /admin` **⟦v1.1⟧ `/graph` `/graph/view/[id]` `/graph/share/[token]`**.

**Navigation is registry-driven** from `lib/registry.ts` + `GET /api/manifests`. New menu items require zero changes to `Sidebar.tsx`.

**Family Overview:** widget grid — today's events, chores due, expiring soon, school actions, dinner, recent captures, points, AI tip. Widgets registered like tools.

**Quick Capture:** PWA share target, global shortcut, sheet with text+camera+mic+file+structured. Optimistic UI with "processing…" shimmer; enrichment streams via SSE.

**Wall:** full-screen, no chrome, auto-rotating panels, SSE refresh, hard-reload nightly at 04:00 (memory hygiene). **⟦v1.1⟧** includes `KnowledgeGraphWidget`.

**Kid Portal:** Today / Learn / Play / Rewards tabs. **⟦v1.1⟧** includes the Constellation view.

---

### Block 20 — `text` — §19 Extensibility

**Backend tool:** write a `@register(...)` decorated function; done. Callable identically by UI (`POST /api/tools/{slug}/run`) and Hermes (`POST /internal/agent/tools/{name}`) with the same audit.

**Frontend manifest:**
```ts
{ id, name, category, icon, route, roles[], order, enabled, surfaces[], toolSlug }
```
The menu, route guard, and tool wiring are derived entirely from this object.

**Widget manifest:**
```ts
{ id, name, surfaces[], component, dataSource, refreshSeconds, size, roles }
```

**New section worked example ("Pets"):** add backend tools → add manifest → add pages reusing Note components → optional widget. **No core code changes.**

**Out-of-tree tools:** `tools/` with entry point `familyos.tools` for future independent repos.

---

### Block 21 — `text` — §20 API Surface

Full endpoint list in v1.0 §20. **⟦v1.1⟧ additions:**

| Endpoint | Purpose |
|---|---|
| `GET /api/graph` | nodes + edges with filters |
| `GET /api/graph/neighborhood/{type}/{id}` | ego graph |
| `GET /api/graph/path?from=&to=&max_depth=` | shortest path |
| `GET /api/graph/clusters?method=&min_size=` | semantic clusters |
| `GET /api/graph/stats` | degree histogram, components, density |
| `GET/POST/PATCH/DELETE /api/graph/views[/{id}]` | saved views |
| `POST/DELETE /api/graph/views/{id}/share` | share links |
| `GET /api/graph/views/{id}/layout` | cached layout (SSE compute on miss) |
| `GET /api/graph/export?format=png\|svg\|json\|graphml\|csv` | export |
| `POST /api/graph/recompute` (admin) | rebuild projection + cache |

---

### Block 22 — `text` — §21 Docker Compose & Environment

Compose services: `postgres (pgvector/pgvector:pg16)`, `redis (7-alpine, appendonly)`, `minio`, `minio-init`, `backend`, `worker (arq)`, `hermes`, `frontend-main`, `frontend-wall`, `frontend-kid`, optional `ollama` (profile `ai`).

**`x-backend-env` shared anchor** for DATABASE_URL, REDIS_URL, S3_*, SERVICE_TOKEN, MASTER_KEY, TZ. Backend not published in prod; dev profile publishes 8000. Healthchecks on postgres and redis gate backend startup. Backend command: `alembic upgrade head && uvicorn ...`.

**`.env.example`** covers: core secrets (POSTGRES_PASSWORD, MINIO_ROOT_USER/PASSWORD, SERVICE_TOKEN, MASTER_KEY, JWT_SECRET), household (name, TZ, locale), AI (`AI_ENRICHMENT_ENABLED, LLM_PROVIDER, OLLAMA_URL, LLM_MODEL, VISION_MODEL, EMBEDDING_PROVIDER, EMBEDDING_MODEL=bge-m3, EMBEDDING_DIM=1024, OCR_PROVIDER, ASR_PROVIDER/ASR_MODEL, OPENAI_API_KEY`), integrations (`GOOGLE_CALENDAR_*, HOME_ASSISTANT_*`).

**⟦v1.1⟧ graph worker has no new env;** projection uses the existing embedding provider.

---

### Block 23 — `text` — §22 Cross-Cutting Concerns

**Observability:** structlog JSON; Prometheus counters `http_requests_total, tool_calls_total{tool,status}, enrichment_jobs_total{kind,status}, enrichment_queue_depth, embedding_backlog, vault_access_total, agent_tokens_total` **⟦v1.1⟧ `graph_projection_duration_seconds`, `graph_request_nodes`, `graph_layout_cache_hits_total`**; optional OTel.

**Testing:** unit (services, tools, chunking, crypto, permissions); integration (testcontainers Postgres, visibility tests); tool-contract tests (schema valid, permission enforced, idempotency honored, audit row written); Playwright E2E (capture→enrich→search, chore→approve→points, expiry dashboard, vault share, **⟦v1.1⟧ graph render + filter + save view + share**); migration round-trip. **Permission matrix test:** every tool × every role → assert allow/deny. **Prompt-injection suite:** notes containing "ignore previous instructions…" must not trigger tool calls.

**Backups:** nightly `pg_dump` + `mc mirror`; retention 7d/4w/12m; documented and rehearsed restore drill quarterly.

**Security checklist:** secrets from env only; backend off host; cookies `httpOnly/Secure/SameSite=Lax`; rate limits on `/auth/login` and `/internal/*`; vault reads audited and audit table append-only; CI asserts `hermes/` has no `psycopg`/`asyncpg` import; upload MIME sniffing + size cap + image re-encode; dependency scanning.

---

### Block 24 — `text` — §23 Roadmap

**Phase 1 — Foundation + Notes.** Docker Compose, backend skeleton, Alembic 0001 (core tables), auth + roles, media presign→complete→thumbnail, Notes CRUD + blocks + reorder + tags + visibility, FTS search, Quick Capture UI, Notes UI, Google Calendar sync, Admin skeleton, **Tool Registry + 13 Phase-1 tools**, Family Overview with 4 widgets, `/internal/agent/*` + smoke script.

*Acceptance:* capture text+photo+voice <5 s; find by tag/keyword/type; account+coupon blocks with expiry; Google-synced calendar; `agent_smoke.py` returns a correct note ID; Overview renders on phone+desktop; `docker compose up -d` onboards in <10 min.

**Phase 2.** Enrichment live (OCR/ASR/vision/summary/autotag/embed). Hybrid search in UI. School notice extraction. Expiry Dashboard + nightly scan. Vault + encryption + share links. Chores/Rewards full loop. Meals + Shopping + `generate_shopping_list`. Learning Hub skeleton. Wall Dashboard (6 panels). Tools & Games menu + 4 utilities. **⟦v1.1⟧ Archify Gallery v1: Relation + Hierarchy + Tag layers, force layout, NodeInspector, save views.**

**Phase 3.** Hermes chat UI (SSE, tool cards, confirmations). Multi-hop reasoning. Home Assistant read + Wall home widget. Kid Portal full build + maths game. Star map, solar system, spelling trainer. Predictive briefing. Voice polish. **⟦v1.1⟧ Archify semantic layer (UMAP + HDBSCAN), Gallery mode, Timeline mode, share links, agent tools `graph_path`/`explain_connection`/`semantic_neighbors`.**

**Phase 4+.** Conversation as first-class surface. WhatsApp/eClass/email ingestion. Multi-household sharing. Advanced gamification + allowance. Offline wall. Vault write tools with hardware-key confirmation. Plugin marketplace. **⟦v1.1⟧ 3D graph, cluster drill-down, cross-household graphs, live activity animation, GraphML export.**

---

### Block 25 — `text` — §24 Build Order (do in order, no skipping)

1. Compose + `.env.example` + Makefile → `make health` OK.
2. Backend skeleton (`main.py`, `core/config,db,logging,errors`) → `/healthz`+`/readyz` respond, JSON logs.
3. Models (base, household, user, member, note, block, tag, relation, media, audit) → clean autogenerate.
4. Alembic 0001 + compose runs `upgrade head` → fresh DB migrates; `downgrade -1` works.
5. Auth (`core/security.py`, `api/auth.py`, `api/deps.py`) → login→cookie→`/auth/me`; scope denial tested.
6. Storage + media → presign→PUT→complete→thumb job.
7. Notes service + API + blocks + reorder + tags + visibility → integration tests pass.
8. Search (FTS + filters) + `GET /search` → ranked results with snippets.
9. Tool registry + executor + `/internal/agent/*` + first 6 tools → smoke script passes; `agent_tool_calls` rows exist.
10. `frontend-main` skeleton (Next 15, Tailwind, shadcn, rewrites, auth pages, sidebar from registry) → browser login works.
11. Capture + Notes UI → end-to-end capture and edit.
12. Google Calendar sync + Calendar UI.
13. Family Overview + widget registry + 4 widgets.
14. Admin skeleton + audit viewer.
15. Phase 1 Playwright acceptance script → all §23 Phase-1 checkboxes automated.

**⟦v1.1⟧ Phase 2.5 (after step 15):** graph schema migration → `graph_service` (relation/hierarchy/tag layers) → `GET /api/graph` → `/graph` page with sigma.js → NodeInspector → save/share views → `graph_overview` + `graph_path` tools → semantic layer in Phase 3.

---

### Block 26 — `text` — §A Archify Gallery (v1.1 Addition)

**Concept:** the *archive* + *graphify* view — a single surface presenting the entire family knowledge base as an interactive graph and gallery. Not a separate store: a projection of Notes, Blocks, Tags, Members, Media, Events.

**Layers (toggleable):** Relation (`note_relations`), Hierarchy (`parent_note_id`), Tag (`note_tags`), Semantic (cosine over `embeddings`), Temporal, Ownership, Media. Default = Relation + Hierarchy + Tag, colored by type, sized by recency/importance.

**Schema additions:** `graph_views (saved presets + share_token)`, `graph_projections (method/params/model/status)`, `graph_node_positions (projection_id, owner_type, owner_id, x/y/z, cluster_id)`, `graph_layout_cache (view_hash, layout jsonb)`.

**API:** `GET /api/graph` (+ `neighborhood`, `path`, `clusters`, `stats`), CRUD `views`, `share`, `layout` (SSE compute on miss), `export (png|svg|json|graphml|csv)`, admin `recompute`.

**Workers:** `graph.project` (nightly 03:00: UMAP → 2D/3D + HDBSCAN → positions), `graph.layout` (on-demand + nightly for pinned views, cache by `view_hash`), `graph.cluster`, `graph.stats`. Scale guard: downsample >50k nodes by importance+recency.

**Agent tools (new):** `graph_overview, graph_neighborhood, graph_path, graph_clusters, semantic_neighbors, explain_connection, create_graph_view (mutates), list_graph_views`.

**Frontend:** `/graph` in main app, `/graph/share/[token]` public read-only. Stack: `sigma.js` + `graphology` (WebGL) + server-side `d3-force` + `@react-spring/web`. Components: `GraphCanvas, GraphControls, NodeInspector, ClusterLegend, ViewManager, MiniMap, TimelineScrubber, LayoutPicker, GalleryGrid`.

**Modes:** Graph (topology) · **Gallery** (masonry grid of thumbnails with hover edges — the "gallery" half) · Timeline · Clusters · Radial · Tree.

**Interaction:** hover highlights neighbors; click → inspector; double-click → open note; right-click context menu; shift+drag box select; `/` filter; `g f t c` jump; `Esc` clear. **Performance:** WebGL only; server-computed layout; LOD (dots → labels → thumbnails by zoom); edge bundling >5k edges; virtualized gallery; Web Worker for local re-layout.

**Permissions:** `include_vault=false` enforced server-side unless parent; vault nodes render locked+blurred, click requires re-auth; every `include_vault=true` request audited; semantic edges never connect vault nodes unless both endpoints visible; share links inherit viewer scope, not creator scope.

**Wall/Kid:** `KnowledgeGraphWidget` (rotating 30-day activity constellation, read-only, 60 s refresh). Kid Portal "Constellation" — learning topics as stars, prerequisites as edges, completed topics glow.

**Manifests:**
```ts
{ id:"archify-gallery", name:"Archify Gallery", category:"knowledge", icon:"network",
  route:"/graph", roles:["parent","child"], order:30, enabled:true,
  surfaces:["main","wall"], toolSlug:"graph_overview" }

{ id:"knowledge-graph", name:"Knowledge Graph", surfaces:["wall"],
  component:"KnowledgeGraphWidget", dataSource:"/api/graph?scope=recent&limit=200",
  refreshSeconds:60, size:"lg", roles:["parent","child","guest"] }
```

**Phase placement:** Phase 2 = Relation+Hierarchy+Tag + force + inspector + save views. Phase 3 = semantic layer + Gallery + Timeline + share + agent tools. Phase 4 = 3D + cluster drill-down + cross-household + live animation + GraphML.

**Acceptance (Phase 2 baseline):** `/graph` renders 2,000 notes <2 s; hover/click/double-click work; filters by tag/type/member/date are URL-encoded; save + reopen view preserves layout; share scoped correctly; `graph_overview` + `graph_path` work via `/internal/agent/tools`; vault nodes absent unless `include_vault=true` from a parent and the request is audited.

---

### Block 27 — `text` — §25 Decision Log

D1 no nginx (Next rewrites) · D2 ARQ over Celery · D3 MinIO default, local-disk capable · D4 `bge-m3` @ 1024 · D5 hybrid RRF default · D6 vault = Notes + overlay · D7 agent zero DB creds · D8 mutating tools require confirmation · D9 `points_ledger` append-only authoritative · D10 device pairing short code → long-lived scoped token · D11 recurring chores computed on the fly · D12 Hermes memory *is* the Note system · D13 vault writes UI-only until Phase 4 · **⟦v1.1⟧ D14 Archify is a projection, never a store** · **⟦v1.1⟧ D15 graph layouts are computed server-side and cached by `view_hash`** · **⟦v1.1⟧ D16 semantic graph layer is opt-in and off by default until Phase 3**.

**Open questions:** Google Calendar scope (shared vs per-member, Phase 1 step 12) · share-link PIN required for vault? (Phase 2) · notification TLS termination (Phase 2 §17) · ASR `base` vs `small` (Phase 2) · guest accounts vs scoped share links (Phase 2) · will `household_id` ever hold >1 row (affects indexes) · **⟦v1.1⟧** default semantic threshold (0.72 proposed; tune on real data) · **⟦v1.1⟧** max node count before mandatory downsampling (50k proposed).

---

### Block 28 — `text` — §26 One-Paragraph Summary

Build a FastAPI + Postgres/pgvector + Redis + MinIO backend where **Notes and typed Blocks are the universal data model**, exposed through REST to three separate Next.js frontends (main, wall, kid) that reach the backend via server-side `/api/*` rewrites — no nginx. Enrich every capture asynchronously (OCR, ASR, vision, summary, auto-tag, embedding) via ARQ workers. Expose every capability to the agent through a **typed Tool Registry** with permission checks, idempotency, confirmation-on-write, and full audit — Hermes never touches the database. Build chores, expiry, meals, and vault as **thin overlays** on Notes, and build the **Archify Gallery** as a **projection** of Notes/Blocks/Tags/Members/Media — never a parallel store. Make new tools, games, menus, and widgets **purely additive** through backend decorators and frontend manifests. Start with Phase 1 step 1 (§24) and do not proceed until each step's tests pass.

---

**End of Note.**
`status='active'` · `pinned=true` · `tags=['blueprint','architecture','v1.1','agent-ready']` · `embedding_status='pending'` (enrichment will embed it once the pipeline is live, making the blueprint itself searchable from within FamilyOS — eating our own dogfood).