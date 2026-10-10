# FamilyOS 2027 — CR-001: Application UI & Navigation

**Change Request**
```json
{
  "title": "CR-001 — Application UI & Navigation",
  "type": "custom",
  "status": "active",
  "visibility": "parents",
  "pinned": true,
  "tags": ["ui", "ux", "frontend", "navigation", "cr", "v1.1"],
  "summary": "Complete UI layer for FamilyOS: auth (family picker + PIN), app shell with sidebar + command palette + slide-out panels, all pages, all widgets, and the four role-based surfaces (main, wall, kid, share). Single design system. Every backend capability reachable in three taps or fewer.",
  "extra": {
    "doc_version": "1.0",
    "reader": "coding-agent",
    "implements": ["Notes", "Search (A)", "Reference Sets (B)", "Whiteboard (C)", "Tagging (D)", "Transit", "Archify", "Chores", "Meals", "Vault", "Learning", "Hermes"]
  }
}
```

---

### Block 1 — `text` — Purpose & Scope

The backend is fully designed. The UI is not. This CR specifies the complete user-facing application: how a user logs in, how they move around, how every backend capability is reachable, and how the four distinct surfaces (main app, wall dashboard, kid portal, share links) are structured.

**This is not a design document about colors and fonts.** It is an implementation specification for the coding agent: what pages exist, what components compose them, what state lives where, what routes are deep-linkable, and what every user gesture does.

**Non-goals:** pixel-perfect visual design (the agent uses the shadcn/ui defaults with a Tailwind theme from §3), animation choreography (specified only where functional), internationalization beyond EN + zh-Hant (Phase 4).

---

### Block 2 — `text` — The Core UX Principles

Every decision in this CR traces back to these seven rules.

1. **Three-tap rule.** Every backend capability is reachable in three taps or fewer from the home screen. Tapping is the mental model; the third tap is the action itself, not navigation.
2. **Capture is instant.** From any screen, one gesture starts a capture. The capture sheet is never more than one tap away and never blocks on the network.
3. **Search is a keyboard away.** `Cmd/Ctrl+K` opens the command palette from anywhere. It searches notes, runs tools, navigates, and launches agent actions.
4. **Panels, not pages, for transient work.** The whiteboard, the Hermes chat, note preview, and quick capture are slide-out panels, not routes. They never unmount the page beneath.
5. **Same backend, four front doors.** The main app, wall, kid portal, and share links all speak to the same API. There is no forked logic — only different surfaces.
6. **The UI is registry-driven.** Menus, tools, and widgets come from manifests (Master Blueprint §19). New items appear without touching the shell.
7. **Nothing is hidden behind a hamburger that should be visible.** Primary navigation is always on screen on desktop; on mobile it is a bottom tab bar, not a drawer.

---

### Block 3 — `text` — Design System & Foundations

The design system is shadcn/ui + Tailwind. No custom component library. Everything else is composition.

### Theme tokens (CSS variables, dark-first)

```css
:root {
  /* Surfaces */
  --bg:            0 0% 100%;      /* light mode page */
  --surface:       0 0% 98%;       /* cards, panels */
  --surface-2:     0 0% 95%;       /* subtle contrast */

  /* Dark mode (default) */
  --bg-dark:       240 10% 3.9%;
  --surface-dark:  240 5% 8%;
  --surface-2-dark: 240 5% 12%;

  /* Text */
  --fg:            240 10% 3.9%;
  --fg-muted:      240 5% 45%;
  --fg-subtle:     240 5% 65%;

  /* Brand */
  --primary:       160 84% 39%;    /* teal-500, calm, works with chalkboard */
  --primary-fg:    0 0% 100%;

  /* Semantic */
  --success:       142 71% 45%;
  --warning:       38 92% 50%;
  --danger:        0 84% 60%;
  --info:          199 89% 48%;

  /* Expiry urgency (used by Expiry Dashboard + widgets) */
  --urgency-red:   0 84% 60%;
  --urgency-amber: 38 92% 50%;
  --urgency-yellow: 48 96% 53%;
  --urgency-grey:  240 5% 65%;

  /* Note type colors (used across graph, chips, badges) */
  --note-freeform:  199 89% 48%;
  --note-account:   268 70% 55%;
  --note-coupon:    340 82% 60%;
  --note-meeting:   160 84% 39%;
  --note-receipt:   38 92% 50%;
  --note-school:    220 70% 55%;
  --note-vault:     0 0% 45%;
  --note-meal:      28 80% 52%;
  --note-learning:  280 70% 55%;
  --note-chore:     142 71% 45%;
}

[data-theme="dark"] { /* default; toggled by preference */ }
```

### Typography

- **UI:** Inter (variable), fallback system-ui.
- **Long-form / reading:** Literata or Source Serif, optional, only in note read view.
- **Handwriting (whiteboard):** Kalam, Caveat.
- **Mono:** JetBrains Mono (code blocks, IDs, JSON).

### Iconography

- Lucide icons throughout. No custom icon set.
- Sized 16 (inline), 20 (button), 24 (nav), 32 (empty state).

### Spacing & radius

- 4px grid. Standard spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.
- Radius: `rounded-lg` (8px) for cards, `rounded-md` (6px) for inputs, `rounded-full` for chips and avatars.

### Motion

- Spring transitions for panel open/close (250ms).
- No motion for page transitions (Next.js defaults).
- `prefers-reduced-motion` respected everywhere.

### Density

- Two densities: `comfortable` (default) and `compact` (user toggle, for power users).
- Applies to lists, tables, and notes.

---

### Block 4 — `text` — Authentication & First Run

Login must be fast and family-friendly. Not a standard email/password form.

### Login page (`/login`)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│                    🏠  FamilyOS                              │
│                                                              │
│              Welcome back. Who's there?                      │
│                                                              │
│   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐          │
│   │  👨    │   │  👩    │   │  🧒    │   │  👶    │          │
│   │  Dad   │   │  Mum   │   │ Emma   │   │ Guest  │          │
│   └────────┘   └────────┘   └────────┘   └────────┘          │
│                                                              │
│              Or sign in with email →                         │
│                                                              │
│              [Pair a device]                                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Flow:**

1. **Family picker.** Shows avatars of all active `family_members` with role `parent` or `child`, plus a "Guest" option if guests are enabled. Fetched from `GET /api/auth/members` (unauthenticated, returns only avatar + display name + a `has_pin` boolean). This endpoint is rate-limited and does not leak emails or roles.
2. **Tap an avatar** → PIN pad appears (4–6 digits, big touch targets).
3. **Correct PIN** → `POST /api/auth/login` with `{member_id, pin}` → sets access + refresh cookies → redirects to `/`.
4. **Email login** link → traditional email + password form, for admins and for initial setup.
5. **Pair a device** → shows a 6-digit code the user enters at `/admin/devices` from an already-logged-in device. Used for wall tablets and kid tablets.

**PIN rules:**
- Parents set their own PIN at first login (or when created by another admin).
- Kids' PINs are set by a parent at creation.
- 5 failed attempts → 60-second lockout, visible countdown.
- PINs are stored as argon2 hashes, never recoverable, only resettable.

### First run (no members exist)

`/setup` wizard, one screen per step:

1. **Create the household:** name, timezone, locale, week start.
2. **Create the first parent:** display name, email, password, PIN.
3. **Add family members (optional):** name, role, avatar, PIN (children), email (parents).
4. **Choose AI provider:** Ollama (default, local) / OpenAI / None. If Ollama, show the model pull command.
5. **Done.** Seeds: default vault categories, transit reference sets, saved searches, home page widgets.

Setup is a route `/setup` that is only accessible when `family_members` is empty. Once any member exists, `/setup` returns 404.

### Session & logout

- Access token 15 min, refresh 30 days, both in `httpOnly` cookies (Master Blueprint §3.1).
- Refresh happens transparently in the API client on 401.
- Logout in the user menu, also revocable per-device from `/admin/devices`.
- The user menu shows: profile, switch member (kid↔parent on shared devices), settings, sign out.

---

### Block 5 — `text` — App Shell

One shell, used by `frontend-main`. The wall and kid portal have their own shells (Blocks 13, 14).

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ┌────────────────────────────┐  ┌─────────────────────────────────────┐│
│  │                            │  │                                     ││
│  │   SIDEBAR                  │  │   TOP BAR                           ││
│  │                            │  │   🔍 Search (Cmd+K)    🔔 3    👤 ▾ ││
│  │   🏠 Home                  │  ├─────────────────────────────────────┤│
│  │   ＋ Capture (button)      │  │                                     ││
│  │                            │  │                                     ││
│  │   📝 Notes                 │  │                                     ││
│  │   🔍 Search                │  │                                     ││
│  │   📅 Calendar              │  │   MAIN CONTENT                      ││
│  │   ✅ Tasks                 │  │                                     ││
│  │   🏆 Chores                │  │   (varies by route)                 ││
│  │   🍽 Meals                 │  │                                     ││
│  │   🎓 Learning              │  │                                     ││
│  │   🔐 Vault                 │  │                                     ││
│  │   🕸 Archify               │  │                                     ││
│  │   🛠 Tools                 │  │                                     ││
│  │   ✨ Hermes                │  │                                     ││
│  │                            │  │                                     ││
│  │   ─────────────            │  │                                     ││
│  │   🏷 Tags (Review · 12)    │  │                                     ││
│  │   ⚙ Settings               │  │                                     ││
│  │                            │  │                                     ││
│  │   ─────────────            │  │                                     ││
│  │   👤 Dad ▾                 │  │                                     ││
│  └────────────────────────────┘  └─────────────────────────────────────┘│
│                                                                         │
│   [ Slide-out panels appear over this: Whiteboard, Hermes, Capture ]    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Sidebar

- Fixed 240px width on desktop. Collapses to 64px (icon-only) via a toggle; preference persisted.
- **On mobile (<768px):** sidebar is replaced by a bottom tab bar with 5 items: Home, Notes, Search, Capture (center, elevated), More. "More" opens a sheet with the remaining nav.
- Nav items come from `lib/registry.ts` (core entries) + `GET /api/manifests` (extensible entries). Grouping is by `category`.
- Badge counts: Tags shows pending proposals; Hermes shows unread; Notes shows inbox count.
- The Capture button is always visible at the top of the sidebar and is elevated (primary color).

### Top bar

- **Search trigger** — a button that looks like an input, labeled "Search or ask… `⌘K`". Clicking opens the command palette.
- **Notifications bell** — popover with the last 10 notifications, mark-all-read, link to `/notifications`.
- **User menu** — profile, switch member, theme toggle (dark/light/system), density, settings, sign out.

### Slide-out panels

A panel layer, rendered at the shell level, controlled by Zustand stores. Panels slide in from a side, coexist with the page, and never remount it.

| Panel | Trigger | Width | Persists |
|---|---|---|---|
| **Capture** | `c` key, sidebar button, FAB | 480px | Note |
| **Whiteboard** | `w` key, Tools menu, drawing block click | 45% / full | Note |
| **Hermes** | `h` key, sidebar, command palette | 420px | Conversation |
| **Note preview** | Click a note reference anywhere | 560px | Note |
| **Command palette** | `⌘K` / `Ctrl+K` | 640px, centered | — |

Multiple panels can coexist (e.g. Hermes open beside whiteboard). They stack horizontally and squeeze the main content.

### Global keyboard map

| Key | Action |
|---|---|
| `⌘K` / `Ctrl+K` | Command palette |
| `c` | Open capture |
| `w` | Toggle whiteboard |
| `h` | Toggle Hermes |
| `/` | Focus the current page's primary search |
| `g` `h` | Go home |
| `g` `n` | Go notes |
| `g` `s` | Go search |
| `g` `c` | Go calendar |
| `g` `t` | Go tags |
| `g` `a` | Go archify |
| `Esc` | Close topmost panel / clear selection |
| `?` | Keyboard shortcut overlay |

`g`-prefixed shortcuts use a 1.5s timer. Any keypress cancels the sequence.

---

### Block 6 — `text` — Command Palette (`⌘K`)

The single most important UI affordance. It replaces dozens of clicks.

```
┌──────────────────────────────────────────────────────────┐
│  🔍  japan trip                                          │
├──────────────────────────────────────────────────────────┤
│  ACTIONS                                                 │
│   ＋ Create note "japan trip"                            │
│   🔍 Search everything for "japan trip"                  │
│   ✨ Ask Hermes about "japan trip"                       │
│                                                          │
│  NOTES                                                   │
│   📝 Japan trip 2027              freeform · 3 days ago  │
│   📝 Japan 2027 — flights         freeform · 1 week ago  │
│   📎 Japan visa scan              account · 2 months ago │
│                                                          │
│  TOOLS & GAMES                                           │
│   🛠 Resistor Calculator                                 │
│   🎨 Whiteboard                                          │
│                                                          │
│  NAVIGATE                                                │
│   📅 Calendar                                            │
│   🕸 Archify                                             │
└──────────────────────────────────────────────────────────┘
```

**Behavior:**
- Debounced live query (150ms) against a lightweight `/api/search?limit=8` + a client-side index of nav items, tools, and saved searches.
- Result groups are ordered: Actions → Notes → Tools → Navigate.
- `Enter` on a note opens it. `Cmd+Enter` opens it in the note preview panel. `Shift+Enter` opens it in a new browser tab.
- `Tab` cycles through result groups.
- Empty query shows: recent notes (last 5), pinned saved searches, and quick actions.
- The palette is a global singleton. Opening it never changes the URL.

---

### Block 7 — `text` — The Main Pages

Every page listed with its route, purpose, and primary components. The coding agent implements these in the order of §17 (Build Order).

### 7.1 `/` — Home (Family Overview)

A grid of widgets. Each widget is independently loading, independently refreshable, and reorderable by the user (drag handles in edit mode).

**Default layout (parent view):**
```
Row 1:  [ Today's schedule     ] [ Chores due today     ]
Row 2:  [ Expiring soon        ] [ Tag review (12)      ]
Row 3:  [ Recent captures      ] [ Saved searches       ]
Row 4:  [ Dinner tonight       ] [ Transit (mine)       ]
Row 5:  [ Points & rewards     ] [ AI tip               ]
```

**Default layout (child view):**
```
Row 1:  [ My missions today    ]
Row 2:  [ My points + rewards  ]
Row 3:  [ My transit            ] [ Today's schedule    ]
Row 4:  [ Continue learning    ]
```

**Widget contract** (from Blueprint §19.3):
```ts
{
  id: "expiring-soon",
  name: "Expiring Soon",
  surfaces: ["main", "wall"],
  component: "ExpiringSoonWidget",
  dataSource: "/api/expiry?days=30",
  refreshSeconds: 300,
  size: "md",
  roles: ["parent"],
  order: 20,
  enabled: true,
}
```

Widgets are rendered by `<WidgetHost manifest={...} />`, which handles loading, error, empty, and refresh states uniformly. No widget implements its own skeleton.

**Widget catalogue for Home:**
| Widget | Role | Data source |
|---|---|---|
| Today's schedule | all | `/api/events?from=today` |
| Chores due today | all | `/api/chores?due=today` |
| Expiring soon | parent | `/api/expiry?days=30` |
| Tag review | parent | `/api/tags/proposals?status=pending` |
| Recent captures | all | `/api/notes?status=inbox&limit=5` |
| Saved searches | all | `/api/saved-searches?pinned=true` |
| Dinner tonight | all | `/api/meals?date=today&slot=dinner` |
| Transit (mine) | all | `/api/transit/eta?preset_id=…` |
| Points & rewards | parent, child | `/api/points/summary` |
| AI tip | parent | `/api/agent/tip` |
| School actions | parent | `/api/school/notices?action_required=true` |
| Knowledge graph (mini) | parent | `/api/graph?scope=recent&limit=50` |

**Edit mode:** toggle in the top right of the page. Widgets get drag handles, hide buttons, and a "add widget" card. Layout persisted per member in `whiteboard_preferences`-style `dashboard_preferences` (or simply in `localStorage` in Phase 1, server-side in Phase 2).

### 7.2 `/notes` — Notes Inbox & List

**Default view: Inbox** (notes with `status='inbox'`, ordered by `updated_at desc`).

Layout:
```
┌─────────────────────────────────────────────────────────────┐
│  Notes           [Inbox] [All] [By type ▾] [Sort: Recent ▾] │
│  Filter: [type ▾] [tag ▾] [member ▾] [date ▾]    🔍 inline  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 📷 Wellcome receipt            receipt · 2h ago    │    │
│  │    #groceries #finance                              │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ 📝 Japan trip 2027             freeform · 3d ago   │    │
│  │    #travel #2027                                    │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ ✏️ Maths homework              drawing · 5d ago     │    │
│  │    [thumbnail]                                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  [Load more]                                                │
└─────────────────────────────────────────────────────────────┘
```

- **Inline search** is a lightweight filter on the current list. A link "Open in full search →" passes the current filters to `/search`.
- **Row click** opens the note in the main content area (a route change to `/notes/{id}`).
- **Cmd+click** opens the note preview panel (no navigation).
- **Right-click** opens a context menu: open, preview, pin, archive, delete, add tag, copy link, open whiteboard (if applicable).
- **Bulk select** via checkbox; toolbar appears with actions from Note A §9.
- **Density toggle** in the header (comfortable / compact).
- **List / gallery / timeline** view switch. Gallery only shows media notes; timeline groups by month.

### 7.3 `/notes/[id]` — Note Detail

The most-used screen after Home. Layout:

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back    Japan trip 2027            ⋯  📌  🔗  👁  💬    │
├─────────────────────────────────────────────────────────────┤
│  Type: freeform · Status: active · Owner: Dad               │
│  Tags: #travel #2027 ✦ #planning  + add                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Block 1: text]                                            │
│  Flying to Tokyo on Mar 15. Return Mar 25.                  │
│                                                             │
│  [Block 2: image]                                           │
│  [thumbnail of itinerary]                                   │
│  Caption: "Draft itinerary"                                 │
│                                                             │
│  [Block 3: checklist]                                       │
│  ☐ Book flights                                             │
│  ☑ Renew passport                                           │
│  ☐ Notify school                                            │
│                                                             │
│  [Block 4: drawing]                                         │
│  [thumbnail of sketch]  [Open whiteboard]                   │
│                                                             │
│  + Add block  ▾                                             │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Activity: edited 5 min ago · 2 comments · 1 relation       │
└─────────────────────────────────────────────────────────────┘
```

**Right rail (collapsible, desktop only):**
- Metadata (dates, owner, visibility, expiry).
- Related notes.
- Extracted entities (people, dates, amounts, from enrichment).
- Backlinks ("referenced by 2 notes").

**Block editor:**
- Inline editing per block. Click to edit, blur to save (debounced 800ms).
- Drag handle on the left to reorder.
- `+ Add block` opens a menu of block types.
- Image/video/voice blocks upload inline.
- Drawing blocks open the whiteboard panel.
- Structured blocks (account, coupon, meeting) render as forms.

**Actions menu (`⋯`):**
- Pin / unpin
- Change type
- Change status
- Change visibility
- Add expiry
- Create event from note
- Create task from note
- Export (Markdown, PDF, JSON)
- Duplicate
- Move to folder
- Delete

**Tag chips:**
- Human tags: normal.
- AI tags: with a small ✦ badge.
- Click a chip → menu: remove, exclude here, exclude wider, copy.
- "+ N proposed" chip → popover with pending proposals for this note.

**Comments:** a lightweight thread at the bottom, per member. Phase 2.

### 7.4 `/notes/search` → redirects to `/search`

### 7.5 `/search` — Full Search (Note A)

Already specified in Note A §2. Implementation contract: the page state is a single filter JSON, the URL is the source of truth, and the page has three vertical zones (query bar, filter chips, results + facets).

### 7.6 `/calendar` — Calendar & Tasks

Two views on one page, switchable:

**Calendar view:**
- Month (default) / Week / Day / Agenda.
- Google Calendar events + local events overlaid.
- Click an empty slot → create event dialog.
- Click an event → preview popover, "open note" if linked.
- Drag to reschedule (writes to Google if the source is Google).
- Toggle per-calendar visibility.
- Color by member.

**Tasks view:**
- A flat list grouped by due date (Overdue, Today, This week, Later, No due date).
- Inline check-off.
- Drag to reorder within a group.
- Assign, due, priority via a compact row editor.
- "Add task" at the top, `Enter` saves and creates another.

**Sidebar (right):**
- Mini calendar.
- "Today's tasks" widget.
- "Tomorrow" peek.

### 7.7 `/chores` — Chores Board

Two views: **Board** (kanban by status) and **By member** (columns per child).

Card shows: chore title, assignee avatar, due, points, status.
Drag between columns changes status (with permission).
Click a card → detail panel: description, proof photos, completion history, approve button (parent).

Tabs at top: Active · Pending approval · Completed this week.

### 7.8 `/rewards` — Rewards Store

Grid of rewards as cards with cost, stock, image.
Parent view: manage rewards (add/edit/delete), see redemptions pending approval.
Child view: browse, redeem (with confirmation), see balance.

### 7.9 `/meals` — Meal Planner & Shopping

Two-column: week planner (7 days × 4 slots) on the left, shopping list on the right.
- Click a slot → search or add a meal. Linked to a recipe note or free-form.
- "Generate shopping list" from selected meals.
- Shopping list checkable inline, with category grouping.
- Shopping lists are their own entities, accessible from `/shopping`.

### 7.10 `/learning` — Learning Hub

For parents: subjects, topics, results table, weak topics, progress charts.
For children: "Today's practice" card, topic list with stars, quizzes, study streak.

### 7.11 `/vault` — Family Vault (parent only)

Category grid → item list → item detail with reveal-on-tap for sensitive fields.
Share link generator on each item.
Expiry integration: items with `expires_at` show urgency.

### 7.12 `/graph` — Archify Gallery (Note C of the graph addition)

The full spec is in the Archify Gallery design. Route, panels, and modes as specified.

### 7.13 `/tools` — Tools & Games Menu

A grid of cards, one per manifest with `surfaces` containing `main`. Search box at the top. Categories: utility, game, learning, family.
Clicking a card routes to `/tools/{slug}` or dispatches an action (e.g. whiteboard).

### 7.14 `/tools/[slug]` — Tool Page

Renders the tool's `component`. Each tool page is self-contained. Common chrome: title, description, back button, "Add to Home" (adds a widget if the tool provides one).

### 7.15 `/tags/review` — Tag Review (Note D)

The proposal queue UI from Note D §11.

### 7.16 `/tags/hygiene` — Tag Hygiene (Note D, parent only)

The consolidation page from Note D §13.

### 7.17 `/hermes` — Hermes Chat

Also available as a slide-out panel. The route shows the same content full-width.

Layout: conversation list on the left (Phase 3), chat on the right.
Messages render tool-call cards inline. Confirmation-required cards for mutating tools.
Attachments: drag-drop or paste images to send to Hermes.

### 7.18 `/notifications`

A flat list, grouped by day, with filters (unread, priority). Clicking a notification navigates to its `ref_type`/`ref_id`.

### 7.19 `/settings` — Settings (parent only, except profile)

Sub-pages:
- `/settings/profile` — own display name, avatar, PIN, theme, density.
- `/settings/household` — name, timezone, locale, week start, quiet hours.
- `/settings/members` — add/edit/delete members, set roles.
- `/settings/devices` — list, pair new, revoke.
- `/settings/ai` — provider, model, enrichment toggles, budget, kill switch.
- `/settings/transit` — presets (Block 9 of the Transit note).
- `/settings/tags` — style profile, exclusions, forbidden tags, auto-accept rules.
- `/settings/whiteboard` — themes, brush presets, canvas limits.
- `/settings/storage` — usage, backups, retention.

### 7.20 `/admin` — Admin (parent only)

- `/admin/audit` — audit log viewer with filters.
- `/admin/reference` — Reference Sets (Note B §11).
- `/admin/reference/[key]` — set detail with history.
- `/admin/jobs` — background job queue: pending, running, failed, dead.
- `/admin/metrics` — Prometheus snapshot, embeddings backlog, storage.
- `/admin/import` — bulk import (Phase 4).

---

### Block 8 — `text` — Quick Capture (The Capture Sheet)

The capture sheet is the highest-traffic UI in the system. It must be fast and never block.

```
┌──────────────────────────────────────────────────────────────┐
│  Capture                                            ✕        │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  What's on your mind?                                  │  │
│  │                                                        │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Type: freeform ▾     Tags: + add                            │
│                                                              │
│  📷 Camera    🎤 Voice    📎 File    ✅ Checklist    🎨 Draw │
│                                                              │
│  Recent: #travel  #school  #finance                          │
│                                                              │
│                          [Discard]   [Save]                  │
└──────────────────────────────────────────────────────────────┘
```

- **Autofocus** on the textarea when opened.
- **Cmd+Enter** saves.
- **Attachments** are added inline as chips above the footer. Media uploads start immediately (presigned) while the user keeps typing.
- **Save** creates the note, closes the sheet, shows a toast with "Open" and "Undo".
- **Offline:** the note is stored in IndexedDB and synced when online. The toast shows "Saved offline — will sync".
- **PWA share target:** the OS share sheet triggers the capture sheet with pre-filled content.

---

### Block 9 — `text` — Notifications & Toasts

**Toast** appears bottom-right (desktop) or top (mobile), auto-dismisses in 4s, never blocks input.
Kinds: success (green), warning (amber), error (red), info (neutral), progress (with cancel).

**Notification bell** popover lists recent notifications; clicking a row navigates and marks read.
The notifications page has the full list.

**Push (Phase 3):** web push via the service worker, opt-in per device, respects quiet hours.

---

### Block 10 — `text` — State Management

| Kind | Tool | Where |
|---|---|---|
| Server state | TanStack Query | All API reads |
| URL state | `nuqs` or Next.js search params | Filters, search, tab selection, panel-open flags |
| UI state (panels) | Zustand | `useWhiteboard`, `useHermes`, `useCapture`, `useCommandPalette` |
| Session | React Context | Actor, household, theme |
| Form state | React Hook Form + Zod | All forms, validated against backend schemas |
| Local persistence | `localStorage` for preferences; IndexedDB for offline queue |

**Rule:** anything that survives a refresh or a share must be in the URL. Anything that does not must be in Zustand or TanStack Query.

---

### Block 11 — `text` — The API Client

One typed client (`lib/api.ts`), generated types from the backend OpenAPI schema (`openapi-typescript`).

- All requests go through `fetch` with `credentials: 'include'`.
- Retries: 2 on network errors and 5xx, exponential backoff.
- 401 → transparent refresh, then retry once; on failure, redirect to `/login`.
- Errors surface as a typed `ApiError` with `error_code` and a human message.
- Queries use TanStack Query keys built from the endpoint + params, with a small helper to avoid typos.

**Rule:** no component calls `fetch` directly. Every call goes through `api.ts`.

---

### Block 12 — `text` — Empty, Loading & Error States

Every list, panel, and page implements four states uniformly.

| State | Rule |
|---|---|
| **Loading** | Skeleton that mimics the final layout's shape. Never a spinner unless the shape is unknown. |
| **Empty** | Illustration + one-sentence explanation + one primary action. Never just "No results." |
| **Error** | Short message, "Retry" button, and a "Copy details" link for support. Never a stack trace. |
| **Partial** | If some data loads and some fails (e.g. a widget on Home), the widget shows an error but the page does not. |

Examples:
- Empty notes: "Nothing here yet. Tap **Capture** to save your first note."
- Empty search: "No results for `japan`. Try fewer words, or ask Hermes."
- Error widget: "Couldn't load chores. [Retry]"

---

### Block 13 — `text` — Wall Dashboard (`frontend-wall`)

A separate Next.js app, its own shell. Read-only. Unattended.

**Layout:** full-screen, no chrome, dark theme, large text.

Panels rotate every 20s or display in a fixed grid (user choice).
Default grid:
```
┌─────────────────────┬─────────────────────┬─────────────────┐
│  CLOCK + WEATHER    │  TODAY'S SCHEDULE   │  TRANSIT        │
│  08:32 Mon 29 Sep   │  09:00 School       │  🚌 3 min       │
│  ☀ 24° Hong Kong    │  14:30 Piano        │  🚇 5 min       │
│                     │                     │                 │
├─────────────────────┼─────────────────────┼─────────────────┤
│  CHORES DUE         │  DINNER TONIGHT     │  EXPIRING SOON  │
│  Emma 2 · Ben 1     │  Spaghetti bolognese│  Milk · 2 days  │
│                     │                     │  Visa · 30 days │
├─────────────────────┼─────────────────────┼─────────────────┤
│  FAMILY PRESENCE    │  KNOWLEDGE GRAPH    │  AI TIP         │
│  Dad · Emma home    │  [mini constellation]│ "Emma's maths  │
│  Mum out            │                     │  improved 12%"  │
└─────────────────────┴─────────────────────┴─────────────────┘
```

**Wall-specific behaviors:**
- Panels refresh on their own cadence (SSE for transit, polling for others).
- Auto-hide the cursor after 10s of inactivity.
- Hard-reload the page nightly at 04:00 (memory hygiene).
- No interactive elements. Tapping does nothing.
- Pair via `/settings/devices` — the wall device gets a scoped token with `transit.read`, `events.read`, `chores.read`, `expiry.read`, but nothing that writes.

---

### Block 14 — `text` — Kid Portal (`frontend-kid`)

A separate Next.js app. Child-only. Big touch targets. Bright, playful, not noisy.

**Bottom tab bar:** Today · Learn · Play · Rewards.

### 14.1 Today

```
┌─────────────────────────────────────────────┐
│  Hi Emma!  ⭐ 42 points                     │
├─────────────────────────────────────────────┤
│  TODAY                                      │
│  ┌─────────────────────────────────────┐    │
│  │ 🎒 School                            │    │
│  │ 08:30 - 15:30                        │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  MISSIONS                                   │
│  ┌─────────────────────────────────────┐    │
│  │ ✅ Make your bed           +2  ☐    │    │
│  │ ✅ Feed the cat            +1  ☐    │    │
│  │ 📚 Read for 20 minutes     +5  ☐    │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  TRANSIT                                    │
│  ┌─────────────────────────────────────┐    │
│  │ 🚌 960 to school    in 3 min        │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

- Chores tap-to-complete. Photo proof optional (front camera, one tap).
- Transit widget shows the child's own preset (from `/settings/transit/widgets`).

### 14.2 Learn

Subjects as cards. Inside a subject, topics with stars (1–3). Click a topic → practice quiz or a study session timer.

### 14.3 Play

Grid of games from the registry (`surfaces` includes `kid`). Includes maths games generated from the child's weak topics, the constellation view of learning topics (Archify Kid mode), and any utility tools marked kid-safe.

### 14.4 Rewards

Balance at top. Reward cards below. Tap a card → confirmation → parent approval notification.

### 14.5 Constraints

- No access to Notes, Vault, Admin.
- No settings beyond theme (light/dark) and sound toggle.
- The child cannot see other members' chores or rewards.
- The child cannot search the family knowledge base.

---

### Block 15 — `text` — Share Links (`/share/[token]`)

A public route, no auth, scoped by the share token.

Share links render one of:
- A note (read-only, in the note renderer).
- A vault item (with re-auth prompt if `sensitivity='high'`).
- A saved search (read-only).
- A graph view (read-only).

Common chrome: family name, "Shared by Dad", expiry countdown, "Powered by FamilyOS."
No editing, no navigation back into the app.

---

### Block 16 — `text` — Mobile & PWA

- All pages responsive. Breakpoints: `sm:640 md:768 lg:1024 xl:1280`.
- Bottom tab bar below `md`.
- Capture is the center tab, elevated, opens the sheet.
- Whiteboard panel is full-width on mobile.
- PWA install prompt after the second visit.
- Share target registered: receiving a URL, image, or text opens the capture sheet.
- Offline: home page, recent notes, and capture work offline. Writes queue in IndexedDB. An online indicator appears in the top bar when offline.

---

### Block 17 — `text` — Build Order for the Coding Agent

Do these in order. Do not proceed until each step's tests pass.

| # | Deliverable | Definition of done |
|---|---|---|
| 1 | `frontend-main` skeleton: Next 15, Tailwind, shadcn, dark theme, rewrites to backend | A blank page renders with the correct font and colors |
| 2 | Login page: family picker + PIN pad + email login + setup wizard | A user can log in with a PIN; a fresh install reaches `/setup` |
| 3 | App shell: sidebar, top bar, panel container, mobile bottom tabs | Navigating between empty placeholder routes works |
| 4 | Command palette with nav + recent notes | `⌘K` opens it; `Enter` navigates |
| 5 | API client + TanStack Query provider + auth refresh | A protected route redirects when unauthenticated |
| 6 | Capture sheet | A note can be created end-to-end and appears in `/notes` |
| 7 | Notes list + note detail + block renderer + block editor | All block types render; text and image blocks are editable |
| 8 | Tags: chips, AI badge, evidence tooltip, add/remove, exclude menu | Tagging a note and removing a tag work end-to-end |
| 9 | Search page (Note A): query bar, filters, results, URL state | Deep-linkable search works |
| 10 | Home page + widget host + 4 widgets (events, chores, expiry, recent) | Widgets load and refresh independently |
| 11 | Calendar + Tasks page | Events from Google appear; tasks can be created and completed |
| 12 | Chores + Rewards (parent + child views) | A chore can be completed and approved; points update |
| 13 | Meals + Shopping | A meal can be planned and a shopping list generated |
| 14 | Vault (parent) + share link | A vault item can be created, viewed, and shared |
| 15 | Whiteboard panel (Note C) | A drawing can be created and saved to a note |
| 16 | Archify `/graph` (Phase 2 baseline) | 2,000-note graph renders in < 2s |
| 17 | Transit widget + preset editor | A preset can be configured and shows live arrivals |
| 18 | Tag review + hygiene pages | Proposals can be accepted and rejected |
| 19 | Hermes chat (panel + page) | A message can be sent and a tool result rendered |
| 20 | Wall dashboard app | Read-only panels render and refresh |
| 21 | Kid portal app | Today, Learn, Play, Rewards all work |
| 22 | Settings + Admin (all sub-pages) | Every backend setting is reachable |
| 23 | PWA + offline capture + share target | Capture works offline; install prompt appears |
| 24 | Playwright E2E for the Phase 1 acceptance script | All acceptance criteria automated |

---

### Block 18 — `text` — Acceptance Criteria

**Login**
- [ ] A returning user reaches Home in ≤ 3 seconds from opening `/login`, using only a family avatar tap and a 4-digit PIN.
- [ ] A fresh install shows `/setup` and creates a working household in ≤ 5 screens.
- [ ] A wall tablet pairs via a 6-digit code and receives a scoped token.
- [ ] 5 failed PIN attempts lock the account for 60 seconds with a visible countdown.
- [ ] The email login path exists for admins.

**Navigation**
- [ ] Any backend capability is reachable in ≤ 3 taps from Home.
- [ ] `⌘K` opens the command palette from every page and searches notes, tools, and nav.
- [ ] The `g`-prefixed shortcuts work everywhere and cancel on timeout.
- [ ] The sidebar collapses and the preference persists across sessions.

**Panels**
- [ ] Opening the whiteboard, Hermes, or capture panel never causes the current page to remount.
- [ ] Two panels can be open simultaneously (whiteboard + Hermes) without layout breakage.
- [ ] Closing a panel returns focus to the last focused element in the page beneath.

**Pages**
- [ ] Home renders all enabled widgets, each independently loading and erroring.
- [ ] `/notes` supports list, gallery, and timeline views.
- [ ] `/notes/[id]` renders every block type and edits text and image blocks inline.
- [ ] `/search` round-trips its state through the URL.
- [ ] `/calendar` shows Google and local events and creates tasks.
- [ ] `/chores`, `/rewards`, `/meals`, `/vault`, `/learning` all complete their primary flow end-to-end.
- [ ] `/graph` (Archify) renders at 2,000 notes in < 2 seconds.
- [ ] `/tags/review` and `/tags/hygiene` are functional.
- [ ] `/hermes` sends and receives messages with inline tool cards.

**Surfaces**
- [ ] The wall dashboard runs unattended for 24 hours without a crash or memory leak.
- [ ] The kid portal is usable by a 6-year-old without adult help.
- [ ] A share link renders correctly to a logged-out browser.

**Cross-cutting**
- [ ] Every list has loading, empty, error, and partial states.
- [ ] The app is fully usable on a 375px-wide phone.
- [ ] The app installs as a PWA and captures offline.
- [ ] `prefers-reduced-motion` disables all non-essential animation.
- [ ] All pages pass a WCAG AA contrast check.

---

### Block 19 — `text` — Design Notes for the Coding Agent

1. **The three-tap rule is a hard constraint, not a guideline.** If a capability requires four taps, redesign it.

2. **Panels are at the shell, never at the page.** If the whiteboard is a child of the note route, it will unmount when the note route changes and the user will lose unsaved strokes. This is the single most likely bug to ship.

3. **The URL is the state.** Anything the user might share, bookmark, or refresh must be encoded in the URL. The command palette and panels are the only exceptions.

4. **One API client.** No `fetch` outside `lib/api.ts`. This is what makes retries, refresh, and error handling uniform.

5. **Every widget implements the same four states.** If a widget author writes their own spinner, the design system has failed.

6. **The design system is shadcn/ui and Tailwind, nothing more.** Resist the urge to build a custom component library. Composition is the point.

7. **The theme tokens in Block 3 are the contract.** When adding a new note type or urgency level, add a token, not a hardcoded color.

8. **The mobile bottom tab bar has exactly five items.** More leads to a sheet, not a drawer. Drawers hide things; sheets reveal them.

9. **Login must work on a 5-year-old iPad with a broken home button.** Big targets, no hover-only affordances, no hover-only navigation.

10. **The wall has no interaction, and this is a feature.** If a coding agent adds a tappable element to the wall, remove it. The wall exists to be looked at, not touched.

11. **The kid portal must be usable without reading English.** Icons, colors, and emoji carry the meaning; text is secondary.

12. **Share links are public.** They must not leak anything beyond the shared scope. Verify by logging out and opening every share kind.

13. **Accessibility is not optional.** Keyboard navigation, focus management on panel open/close, ARIA labels on icon-only buttons, and color-blind-safe urgency indicators (icons + color, not just color).

14. **The UI is registry-driven.** If adding a tool requires editing a nav file, the registry design has failed. New tools, new widgets, new menu items must appear purely from manifests.

15. **Do not ship a feature that has no empty state.** A user who lands on an empty page must be told what to do next.

---

### Block 20 — `text` — Out of Scope (For This CR)

- Real-time collaborative editing (Phase 4).
- Native mobile apps (Phase 4).
- Internationalization beyond EN + zh-Hant (Phase 4).
- Advanced theming beyond dark/light/system (Phase 4).
- Offline editing of notes (Phase 4; offline capture is in scope).
- Voice-first navigation (Phase 4).

---

### Block 21 — `text` — The Meta-Point

The backend was designed first because the data model is the hard part. But a family will judge FamilyOS by the UI — by whether capture is instant, by whether search finds what they meant, by whether the kid can tap a chore and see a star appear.

This CR exists to make the UI as disciplined as the backend. It is not a list of pages. It is a contract about how the user moves through the system: three taps, one gesture, one keyboard shortcut, and one rule about panels that must never be broken.

If the coding agent builds to this CR, a user will open FamilyOS on their phone, tap Capture, type a note, and never see a spinner.

That is the bar.

---

**End of CR-001.**
`status='active'` · `pinned=true` · `tags=['ui','ux','frontend','navigation','cr','v1.1']` · `visibility='parents'`