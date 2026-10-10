# FamilyOS 2027 — Note: HK Transit Widget (Bus + MTR)

**Note**
```json
{
  "title": "HK Transit Widget — Bus & MTR Schedule Display",
  "type": "freeform",
  "status": "active",
  "visibility": "family",
  "pinned": false,
  "owner_member_id": null,
  "tags": ["widget", "transport", "hong-kong", "dashboard", "v1.1"],
  "summary": "Per-person transit widget for the Family Overview dashboard. Pulls real-time KMB/LWB, Citybus, GMB bus ETAs and MTR next-train arrivals from HK government open APIs. Configuration presets stored as JSON notes. One widget per family member per dashboard.",
  "extra": { "doc_version": "1.0", "target_reader": "coding-agent", "depends_on": "Master Blueprint v1.1" }
}
```

---

### Block 1 — `text` — Overview

**Purpose:** display live bus and MTR arrival times for a configurable set of stops/stations, scoped per family member and per dashboard. A parent sees their commute route; a child sees their school bus. Presets are defined as JSON configuration notes and can be shared between members.

**Scope (v1.0):**
- **Buses:** KMB (九巴), LWB (龍運), Citybus (城巴), GMB (綠色專線小巴).
- **Rail:** MTR Heavy Rail (10 lines).
- **Not in v1.0:** Light Rail, ferries, trams, NLB. Deferred to Phase 4.

**Surfaces:** Main app Family Overview (per-member widget), Wall Dashboard (ambulatory/rotating panel), Kid Portal (simplified single-stop view).

**Data source:** Hong Kong Government open APIs at `data.gov.hk` — no API key required for any endpoint used here. ⟦DECIDED⟧ No external SDK; direct HTTP calls with retry/cache.

---

### Block 2 — `text` — Data Sources & Endpoints

All endpoints are public, no authentication. All return JSON. All support English and Traditional Chinese via a `lang` query parameter where documented.

#### Buses

| Operator | Base URL | ETA Endpoint pattern | Static data |
|---|---|---|---|
| **KMB / LWB** | `https://data.etabus.gov.hk/v1/transport/kmb` | `/eta/{stop_id}/{route}/{service_type}` | `/route`, `/stop`, `/route-stop` |
| **Citybus** | `https://rt.data.gov.hk/v1.2/transport/citybus` | `/eta/{company_id}/{stop_id}/{route}` | `/route/{company_id}`, `/route/{company_id}/{route}`, `/stop/{stop_id}`, `/route-stop/{company_id}/{route}/{direction}` |
| **GMB** | `https://data.etagmb.gov.hk` | `/eta/stop/{stop_id}` | `/route`, `/route/{region}/{route}`, `/stop/{stop_id}` |

**KMB/LWB** provides 9 JSON resources: Route List, Route Data, Stop List, Stop Data, Route-Stop List, Route-Stop Data, ETA, Stop-ETA, Route-ETA. ETA updates every 1 minute; static data updates daily. The `stop_id` is a 16-character hex string (e.g. `C88E34E485B43EFB`). `service_type` is `1` (normal) or `2` (special variant).

**Citybus** `company_id` is `ctb` for Citybus, `nwfb` for New World First Bus (merged into Citybus branding but API remains separate). V2 API is available for public access. Base URL is `https://rt.data.gov.hk/`.

**GMB** covers all Green Minibus routes. Region codes: `HKI` (Hong Kong Island), `KLN` (Kowloon), `NT` (New Territories). The All Routes API is `/route`; ETA is `/eta/stop/{stop_id}`.

#### MTR Heavy Rail

| Endpoint | Purpose |
|---|---|
| `https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php?line={line}&sta={station}&lang=en` | Next-train arrivals |

Returns arrival times for up to the **next four trains** on all 10 heavy-rail lines: Airport Express, Tung Chung Line, Tuen Ma Line, Tseung Kwan O Line, East Rail Line, South Island Line, Tsuen Wan Line, Island Line, Kwun Tong Line, Disneyland Resort Line. Updates every 10 seconds.

**Line codes:** `AEL` (Airport Express), `TCL` (Tung Chung), `TML` (Tuen Ma), `TKL` (Tseung Kwan O), `EAL` (East Rail), `SIL` (South Island), `TWL` (Tsuen Wan), `ISL` (Island), `KTL` (Kwun Tong), `DRL` (Disneyland Resort).

**Station codes** are short uppercase strings (e.g. `ADM` Admiralty, `CEN` Central, `TST` Tsim Sha Tsui, `MOK` Mong Kok). The full station list is bundled as a static seed file in the backend (see Block 4).

#### Response shapes (abbreviated)

**KMB ETA:**
```json
{
  "type": "ETA",
  "version": "1.0",
  "generated_timestamp": "2026-09-29T08:32:00+08:00",
  "data": [
    {
      "co": "KMB",
      "route": "960",
      "dir": "O",
      "service_type": 1,
      "seq": 12,
      "dest_tc": "灣仔北",
      "dest_en": "Wan Chai North",
      "eta_seq": 1,
      "eta": "2026-09-29T08:35:00+08:00",
      "rmk_tc": "",
      "rmk_en": ""
    }
  ]
}
```

**Citybus ETA:**
```json
{
  "type": "ETA",
  "version": "1.0",
  "generated_timestamp": "2026-09-29T08:32:00+08:00",
  "data": [
    {
      "co": "CTB",
      "route": "A11",
      "dir": "O",
      "seq": 8,
      "dest_tc": "機場",
      "dest_en": "Airport",
      "eta_seq": 1,
      "eta": "2026-09-29T08:34:00+08:00",
      "rmk_tc": "",
      "rmk_en": ""
    }
  ]
}
```

**GMB ETA:**
```json
{
  "type": "GMB",
  "version": "1.0",
  "generated_timestamp": "2026-09-29T08:32:00+08:00",
  "data": [
    {
      "route": "1",
      "region": "HKI",
      "dir": "O",
      "service_type": 1,
      "seq": 5,
      "dest_tc": "中環",
      "dest_en": "Central",
      "eta_seq": 1,
      "eta": "2026-09-29T08:36:00+08:00"
    }
  ]
}
```

**MTR Next Train:**
```json
{
  "sys_time": "2026-09-29T08:32:00+08:00",
  "curr_time": "2026-09-29T08:32:00+08:00",
  "data": {
    "ISL-ADM": {
      "curr_time": "2026-09-29T08:32:00+08:00",
      "sys_time": "2026-09-29T08:32:00+08:00",
      "UP": [
        {"ttt": "2026-09-29T08:33:30+08:00", "valid": "Y", "plat": "4", "dest": "KET"},
        {"ttt": "2026-09-29T08:35:30+08:00", "valid": "Y", "plat": "4", "dest": "KET"}
      ],
      "DOWN": [
        {"ttt": "2026-09-29T08:33:00+08:00", "valid": "Y", "plat": "3", "dest": "CHW"}
      ]
    }
  }
}
```

`ttt` = train arrival time. `valid` = `Y` means the train is running; `N` means cancelled. `dest` is the station code of the terminus. `plat` is the platform.

---

### Block 3 — `text` — Schema Additions

Two new tables. Presets are stored as `notes` of type `custom` with `extra.category='transit_preset'` — but because presets need to be queried and linked efficiently, a light overlay table is justified.

```sql
-- Transit presets: a named, reusable configuration of stops/stations
transit_presets(
  id uuid pk, household_id uuid not null,
  name text not null,                        -- "Dad's commute", "School run"
  description text,
  note_id uuid references notes(id) on delete cascade,  -- preset body in a Note
  config jsonb not null,                     -- canonical JSON (see Block 5)
  owner_member_id uuid references family_members(id),   -- null = shared
  is_shared bool default false,
  created_by uuid references family_members(id),
  created_at timestamptz default now(), updated_at timestamptz default now(),
  unique(household_id, name)
);
create index on transit_presets (household_id, owner_member_id);

-- Per-member, per-dashboard widget bindings
transit_widgets(
  id uuid pk, household_id uuid not null,
  dashboard_surface text not null,           -- 'overview' | 'wall' | 'kid'
  member_id uuid references family_members(id),  -- whose widget (null = household-wide)
  preset_id uuid references transit_presets(id) on delete cascade,
  position int default 0,                    -- ordering on the dashboard
  display_mode text default 'compact',       -- 'compact' | 'expanded' | 'kid'
  max_items int default 3,                   -- per stop/station
  show_bus bool default true,
  show_mtr bool default true,
  enabled bool default true,
  created_at timestamptz default now(), updated_at timestamptz default now(),
  unique(household_id, dashboard_surface, member_id, preset_id)
);
create index on transit_widgets (household_id, dashboard_surface, member_id);
```

**Why a preset is also a Note:** the preset body (description, screenshots of stops, notes about which exit to use) lives in the Note. The `config` JSON lives in the overlay for fast querying. This preserves the "everything is a Note" principle while keeping the widget API fast.

**Static seed data** (bundled, not in DB): MTR station list (code → name_en, name_tc, line_codes[]), MTR line list (code → name_en, name_tc, color). Bus stop and route static data is fetched on demand and cached in Redis (see Block 6).

---

### Block 4 — `text` — Configuration Preset (JSON)

A preset is the canonical JSON the widget reads. Stored in `transit_presets.config`. Editable via the Admin/Configuration page.

```json
{
  "version": 1,
  "name": "Dad's commute",
  "description": "Morning bus to MTR, evening train home",
  "owner_member_id": "uuid-dad",
  "default_display": "compact",
  "stops": [
    {
      "id": "local-1",
      "label": "Home bus stop",
      "type": "bus",
      "operator": "kmb",
      "stop_id": "C88E34E485B43EFB",
      "stop_name_en": "Nathan Road, Yau Ma Tei",
      "stop_name_tc": "彌敦道, 油麻地",
      "routes": [
        { "route": "960", "service_type": 1, "dir": "O", "label": "960 → Wan Chai" },
        { "route": "968", "service_type": 1, "dir": "O", "label": "968 → Causeway Bay" }
      ],
      "max_items": 2
    },
    {
      "id": "local-2",
      "label": "Admiralty MTR",
      "type": "mtr",
      "line": "ISL",
      "station": "ADM",
      "directions": ["DOWN"],
      "dest_label": "Towards Chai Wan",
      "max_items": 2
    }
  ],
  "display": {
    "show_seconds": false,
    "show_platform": true,
    "show_remarks": false,
    "refresh_interval_s": 30,
    "language": "en"
  }
}
```

**Field reference:**

| Field | Required | Notes |
|---|---|---|
| `version` | Y | Preset schema version; bump on breaking change |
| `owner_member_id` | N | null = shared across household |
| `stops[]` | Y | 1–10 entries (hard cap; UI warns above 6) |
| `stops[].type` | Y | `bus` \| `mtr` |
| `stops[].operator` | bus only | `kmb` \| `lwb` \| `ctb` \| `nwfb` \| `gmb` |
| `stops[].stop_id` | bus only | Operator-specific ID |
| `stops[].routes[]` | bus only | Filter to these routes; empty = all routes at this stop |
| `stops[].line` | mtr only | MTR line code |
| `stops[].station` | mtr only | MTR station code |
| `stops[].directions[]` | mtr only | `UP` \| `DOWN`; empty = both |
| `display.refresh_interval_s` | N | Default 30; min 15 (API update cadence) |

**Validation rules (enforced on save):**
- `stop_id` must match `^[A-F0-9]{16}$` for KMB/LWB.
- `station` must be in the bundled MTR station list.
- `line` must be one of the 10 heavy-rail codes.
- `routes` for a bus stop must exist in the operator's route-stop data (validated once on save, cached).
- Total stops ≤ 10. Total routes across all stops ≤ 30.

---

### Block 5 — `text` — Backend Service & API

`app/services/transit.py` — one service, four providers behind a common interface.

```python
class TransitProvider(Protocol):
    async def get_eta(self, stop_ref: StopRef, ctx: ToolContext) -> list[Arrival]: ...

class Arrival(BaseModel):
    mode: Literal["bus", "mtr"]
    operator: str
    route: str
    destination_en: str
    destination_tc: str
    eta_at: datetime           # UTC
    minutes_away: int
    platform: str | None
    remark_en: str | None
    remark_tc: str | None
    is_live: bool              # True if from API, False if from cache fallback
```

**Caching strategy (Redis):**
| Key | TTL | Notes |
|---|---|---|
| `transit:eta:{provider}:{stop_id}:{routes_hash}` | 25 s | Slightly under the 1-min bus cadence |
| `transit:eta:mtr:{line}:{station}` | 8 s | MTR updates every 10 s |
| `transit:static:kmb:stop:{stop_id}` | 24 h | Static stop data |
| `transit:static:kmb:route-stop:{route}` | 24 h | Route-stop mapping |
| `transit:static:ctb:stop:{stop_id}` | 24 h | |
| `transit:static:gmb:route:{region}:{route}` | 24 h | |
| `transit:stale:{key}` | 24 h | Last-known-good fallback |

**Stale-while-error:** if an upstream API fails, return the last cached value with `is_live=false` and a `stale_since` timestamp. The widget shows a muted clock icon. If no cached value exists, return `{ok: true, data: [], meta: {error: 'upstream_unavailable'}}` — the widget shows "—".

**Rate limiting:** per-household Redis token bucket, 60 requests/min total, 20 requests/min per provider. On exceed, serve cache and log `transit.rate_limited`.

**HTTP client:** `httpx.AsyncClient` with 5 s timeout, 2 retries (exponential 200 ms / 600 ms), circuit breaker per provider (5 failures in 60 s → open for 60 s).

#### API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/transit/presets` | List presets for household (filter by `member_id`) |
| `POST /api/transit/presets` | Create preset (validates config) |
| `GET/PATCH/DELETE /api/transit/presets/{id}` | CRUD |
| `POST /api/transit/presets/{id}/validate` | Dry-run validation against live static data |
| `GET /api/transit/eta?preset_id={id}` | Live arrivals for a preset (all stops, merged) |
| `GET /api/transit/eta/stop?type=bus&operator=kmb&stop_id=…&routes=960,968` | Ad-hoc single-stop ETA |
| `GET /api/transit/eta/station?line=ISL&station=ADM` | Ad-hoc MTR ETA |
| `GET /api/transit/widgets?surface=overview&member_id={id}` | Widget bindings for a dashboard |
| `POST/PATCH/DELETE /api/transit/widgets/{id}` | Manage bindings |
| `GET /api/transit/search/bus-stops?q={query}&operator=kmb` | Stop search for the config UI |
| `GET /api/transit/search/mtr-stations?q={query}` | Station search |
| `GET /api/transit/static/mtr-stations` | Full station list (bundled) |
| `GET /api/transit/static/mtr-lines` | Full line list (bundled) |

**Response for `GET /api/transit/eta?preset_id=…`:**
```json
{
  "preset_id": "uuid",
  "generated_at": "2026-09-29T00:32:00Z",
  "stops": [
    {
      "id": "local-1",
      "label": "Home bus stop",
      "type": "bus",
      "operator": "kmb",
      "arrivals": [
        {"mode":"bus","route":"960","destination_en":"Wan Chai North",
         "eta_at":"2026-09-29T00:35:00Z","minutes_away":3,
         "platform":null,"is_live":true,"remark_en":""}
      ],
      "is_live": true,
      "stale_since": null
    }
  ],
  "meta": {"sources_live": 2, "sources_cached": 0, "sources_failed": 0}
}
```

---

### Block 6 — `text` — Agent Tools

Four new tools in `app/agent/tools/transit.py`. All read-only (`mutates=False`).

| Tool | Params | Returns |
|---|---|---|
| `get_transit_arrivals` | `preset_id` OR (`type`, `operator`/`line`, `stop_id`/`station`) | Merged arrivals |
| `list_transit_presets` | `member_id?` | Preset list with names |
| `search_bus_stops` | `query`, `operator?` | Matching stops with IDs |
| `search_mtr_stations` | `query` | Matching stations with codes |

**Example registration:**
```python
class TransitArrivalsParams(BaseModel):
    preset_id: str | None = None
    type: Literal["bus", "mtr"] | None = None
    operator: str | None = None
    stop_id: str | None = None
    line: str | None = None
    station: str | None = None

@register(
    name="get_transit_arrivals",
    description="Get real-time bus or MTR arrivals for a saved preset or an ad-hoc stop/station.",
    category="transport",
    params=TransitArrivalsParams,
    permissions=["transit.read"],
)
async def get_transit_arrivals(p: TransitArrivalsParams, ctx: ToolContext) -> ToolResult:
    ...
```

**Scope:** `transit.read` is granted to all roles including `guest` and `device`. Presets are always scoped to the household; a child cannot read another member's private preset unless it is `is_shared=true`.

**Hermes use cases enabled:**
- "When's the next bus to Wan Chai?"
- "What time do I need to leave to catch the 08:45 train?"
- "Are there any delays on the Island Line right now?"

---

### Block 7 — `text` — Frontend: Widget Design

#### Routes

| Route | Purpose |
|---|---|
| `/settings/transit` | Preset management (parents) |
| `/settings/transit/new` | Create preset |
| `/settings/transit/[id]` | Edit preset |
| `/settings/transit/widgets` | Bind presets to dashboards/members |

#### Widget component

`components/widgets/TransitWidget.tsx` — one component, three display modes driven by `transit_widgets.display_mode`.

**Compact (default, Overview):**
```
┌─────────────────────────────────────────┐
│ 🚌 Home bus stop                     ●  │
│ 960  Wan Chai North              3 min  │
│ 968  Causeway Bay                 9 min  │
├─────────────────────────────────────────┤
│ 🚇 Admiralty MTR                     ●  │
│ Island Line → Chai Wan          2 min   │
│ Island Line → Chai Wan          5 min   │
│ Platform 4                              │
└─────────────────────────────────────────┘
```

**Expanded:**
Shows all arrivals (up to `max_items` per stop), platform numbers, remarks, and a "last updated" relative timestamp. Refreshes every 30 s with a subtle progress ring.

**Kid mode:**
Larger text, one stop only (the first), emoji per mode, no technical detail.
```
🚌 960 to Wan Chai
   arriving in 3 minutes
```

#### Refresh mechanism

- Client-side polling at `display.refresh_interval_s` (default 30 s, min 15 s).
- **Pause when tab is hidden** (`document.visibilityState`).
- **Backoff on error:** 30 s → 60 s → 120 s → cap 300 s, reset on success.
- **SSE alternative (Phase 3):** `GET /api/transit/stream?preset_id=…` pushes updates every 15 s. Reduces battery and request count on the Wall.

#### State

Managed by TanStack Query with `staleTime: refresh_interval_s * 1000`, `refetchInterval` matching, and `refetchIntervalInBackground: false`.

#### Visual states

| State | Indicator |
|---|---|
| Live | Green dot, "Updated just now" |
| Cached (stale) | Amber dot, "Updated 4 min ago" |
| Failed | Grey dot, "—" for each arrival |
| No arrivals | "No upcoming buses" (service ended) |

---

### Block 8 — `text` — Dashboard Integration (Per Person)

**Per-member widget binding.** `transit_widgets` rows define which preset appears on which surface for which member.

**Family Overview:** parents see their own transit widget plus any household-shared widgets. Children see only their own (or shared) widgets. Guests see shared widgets only.

**Wall Dashboard:** a single `TransitWidget` rotated into the panel carousel, showing the household-wide or most-active member's preset. Read-only, no interaction. Refreshes every 30 s via SSE (Phase 3) or polling (Phase 2).

**Kid Portal:** a simplified `TransitWidget` in `kid` display mode, bound to the child's preset (e.g. "school bus"). If no preset exists for the child, the widget is hidden.

**Ordering:** `transit_widgets.position` orders widgets within the Overview grid. The Overview page fetches `/api/transit/widgets?surface=overview&member_id={actor}` and renders them interleaved with other widgets (chores, expiry, etc.) by position.

**Manifest entry:**
```ts
{
  id: "transit-widget",
  name: "Transit",
  surfaces: ["overview", "wall", "kid"],
  component: "TransitWidget",
  dataSource: "/api/transit/eta",
  refreshSeconds: 30,
  size: "md",
  roles: ["parent", "child", "guest"],
  configurable: true,
  configRoute: "/settings/transit/widgets",
}
```

---

### Block 9 — `text` — Configuration Page UX

`/settings/transit` — parent-only. List of presets with name, owner, stop count, and "edit"/"delete" actions.

`/settings/transit/[id]` — the editor:

1. **Preset name** + optional description.
2. **Owner** — dropdown: "Shared" or a specific member.
3. **Stops** — repeatable cards. Each card:
   - **Type toggle:** Bus / MTR.
   - **Bus:** operator dropdown → stop search (typeahead, queries `/api/transit/search/bus-stops`) → route multi-select (populated from the stop's routes).
   - **MTR:** line dropdown → station search (typeahead, queries `/api/transit/search/mtr-stations`) → direction checkboxes (Up / Down / Both).
   - **Label** — free text ("Home bus stop").
   - **Max items** — 1–4.
4. **Display options** — language (EN / TC), show platform, show remarks, refresh interval.
5. **Live preview** — right-hand panel renders the `TransitWidget` with the current draft config against live data.
6. **Save** → validates → writes `transit_presets` + the Note body.

**Widget binding page:** `/settings/transit/widgets` — a simple matrix: rows = presets, columns = surfaces (Overview / Wall / Kid), cells = member dropdown. Drag to reorder within a surface.

**Import/Export:** presets export as `.json` (the `config` object) and import via file or paste. This is how you "pre-configure with JSON" — you can hand a JSON file to a family member or check it into a shared folder.

---

### Block 10 — `text` — Error Handling & Edge Cases

| Case | Behavior |
|---|---|
| Upstream API timeout | Retry ×2, then serve stale cache; widget shows amber |
| Upstream API 5xx | Circuit breaker opens 60 s; serve stale; log `transit.upstream_error` |
| No cache + upstream down | Widget shows "—" per arrival; grey dot |
| `stop_id` no longer valid (route changed) | Static validation on save catches it; at runtime, empty arrivals + a one-time notification "Preset 'X' needs updating" |
| MTR `valid: "N"` | Arrival is filtered out (train cancelled) |
| MTR `ttt` in the past | Filtered out; if all filtered, show "No upcoming trains" |
| GMB route not in region | Validation error on save |
| Rate limit hit | Serve cache; no user-visible error unless cache is empty |
| Household timezone ≠ HKT | All API times are HKT; backend converts to UTC; frontend displays in household timezone |
| DST | Hong Kong has no DST; no handling needed |

**Service alerts:** the MTR API returns `valid: "N"` for disruptions. The widget shows a small warning icon if more than one upcoming train is invalid. A full disruption feed (MTR service alerts) is deferred to Phase 4.

---

### Block 11 — `text` — Phase Placement & Dependencies

| Phase | Deliverable |
|---|---|
| **Phase 2** | Backend service (`transit.py`) + providers (KMB, Citybus, GMB, MTR) + caching + API endpoints + agent tools `get_transit_arrivals`, `search_bus_stops`, `search_mtr_stations`. Config page. Compact `TransitWidget` on Overview. |
| **Phase 3** | Wall widget, Kid widget, expanded mode, SSE streaming, `list_transit_presets` tool, import/export, widget binding matrix UI. |
| **Phase 4** | Light Rail, ferries, NLB, MTR service alerts, disruption push notifications, multi-stop "journey" view (bus → MTR → walk), ETA history sparkline. |

**Dependencies:**
- Phase 2 transit work depends on Phase 1 completion (auth, notes, tool registry, widget registry).
- No new infrastructure. Uses existing Redis, existing HTTP client patterns, existing widget manifest system.
- No API keys required. No external accounts. Fully offline-degradable (cached static data survives; live ETA requires internet).

---

### Block 12 — `text` — Acceptance Criteria (Phase 2)

- [ ] A parent can create a preset with one KMB stop (two routes) and one MTR station, save it, and see live arrivals within 5 seconds.
- [ ] The widget shows `minutes_away` correctly for KMB, Citybus, GMB, and MTR.
- [ ] Refreshing is paused when the browser tab is hidden and resumes on focus.
- [ ] When the upstream API is unreachable, the widget shows the last cached arrivals with an amber "stale" indicator.
- [ ] `get_transit_arrivals` returns correct data via `/internal/agent/tools` for both bus and MTR.
- [ ] A preset can be exported as JSON and re-imported on another device with identical behavior.
- [ ] Per-member binding: Dad sees his preset, child sees theirs; shared presets appear for both.
- [ ] MTR arrivals show platform numbers; cancelled trains (`valid: "N"`) are filtered out.
- [ ] Preset validation rejects an invalid MTR station code and an invalid KMB `stop_id` format.
- [ ] Rate limiting does not cause a user-visible failure under normal family usage (≤ 3 members, ≤ 4 presets).

---

**End of Note.**
`status='active'` · `pinned=false` · `tags=['widget','transport','hong-kong','dashboard','v1.1']` · `visibility='family'`