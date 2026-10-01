# FamilyOS 2027 — Note C: Freehand Whiteboard Tool (Slide-Out Canvas)

**Note**
```json
{
  "title": "Freehand Whiteboard — Slide-Out Canvas Tool with Themes, Layers, and Note Persistence",
  "type": "freeform",
  "status": "active",
  "visibility": "family",
  "pinned": false,
  "owner_member_id": null,
  "tags": ["tool", "whiteboard", "canvas", "drawing", "v1.1"],
  "summary": "A slide-out whiteboard panel callable from anywhere via the Tools menu or keyboard shortcut, without leaving the current note. Strokes persist as a new drawing block on the open note. Supports chalkboard/blueprint/whiteboard themes, layers, shape recognition, laser pointer, bookmarks, and export. Bounded canvas with pan and zoom.",
  "extra": { "doc_version": "1.0", "target_reader": "coding-agent", "depends_on": "Master Blueprint v1.1, Note A (Search), Note B (Reference Sets)" }
}
```

---

### Block 1 — `text` — What It Is and Why It Is Special

Most drawing apps are full-page. You leave what you were doing, draw, then come back. FamilyOS cannot work that way — the whiteboard exists to *support* the note you are already in, not to replace it.

**Design goals:**

1. **Never leaves the note.** Opening the whiteboard does not navigate, does not remount the note, does not lose unsaved edits, does not refresh the page. The note stays rendered underneath or beside it.
2. **Saves to the open note.** Every stroke belongs to a `drawing` block on a specific note. Close the panel, reopen the note, and the drawing is still there.
3. **Fast.** Open in < 100 ms. First stroke in < 50 ms. No spinner, no route transition.
4. **Feels like paper.** Pressure sensitivity, tilt (where available), chalky or smooth textures per theme.
5. **One tool, many jobs.** Doing maths homework, sketching a garden plan, jotting a shopping list, explaining fractions to a child, drawing a diagram during a meeting — same panel, different theme.
6. **Bounded but generous.** The logical canvas is large (4000×3000 by default, up to 16000×12000 if the admin raises the limit) but hard-capped so no one accidentally creates a 100 MP drawing that kills rendering on a tablet.
7. **Additive to the Note system.** The drawing is a block, like text or image. It participates in search, in tags, in the note renderer, in the agent's tool catalogue.

**Non-goals:** a Figma replacement. No real-time multi-user cursors, no component libraries, no automatic layout. If a family needs that, they export and use a dedicated tool.

---

### Block 2 — `text` — Where It Lives in the UI

The whiteboard is a **panel**, not a route. It is mounted once at the app shell level in `frontend-main` and toggled by state.

### Panel modes

| Mode | Layout | When |
|---|---|---|
| **`side-right`** (default) | 45% width on ≥1024 px, 100% on smaller. Note content shrinks via CSS grid. | Normal use — see the note and the drawing together |
| **`side-left`** | Mirrored | Left-handed users, or when the note has a right-side inspector |
| **`full`** | Full viewport, hides the app chrome | Long drawing sessions, maths working, teaching |
| **`floating`** | Draggable, resizable window | Phase 3 — picture-in-picture while reading two notes |

Docking is per-user preference, stored in `localStorage`.

### Open triggers

| Trigger | Result |
|---|---|
| Tools menu → Whiteboard | If a note is open, opens the panel with the note's last drawing block (or a new one). If no note is open, opens a picker: "attach to note…" |
| Keyboard `w` (global, not in an input) | Same as above |
| Command palette → "Whiteboard" | Same as above |
| Note block: click on a `drawing` block | Opens the panel with **that** block |
| Note block: "+ Add block → Drawing" | Creates a blank drawing block and opens the panel |
| Note action menu → "New drawing" | Creates a new drawing block and opens the panel |

### Close behavior

- `Esc` closes the panel if no tool is active.
- Clicking outside the panel on mobile closes it.
- Closing does **not** navigate. The note stays exactly where it was.
- The panel remembers its scroll/zoom state per block for the session.
- Autosave runs on close and on every 1.5 s of idle time (see Block 11).

### Layout mechanics (how "without refreshing" actually works)

- The app shell is a CSS grid: `grid-template-columns: [main] 1fr [panel] 0`.
- When the panel opens, `[panel]` becomes `minmax(360px, 45vw)` with a spring transition.
- The panel is a portal rendered at the shell, not inside the note component. It never causes the note subtree to unmount.
- Zustand store `useWhiteboard` holds all panel state. It is not tied to the route.
- The URL does **not** change on open (avoids Next.js router work). A "Copy link" button optionally generates `/notes/{id}?wb={block_id}` which, on load, opens the panel automatically.
- The note's editor is inert but not destroyed while the panel is open. Any pending debounced note save flushes before the panel opens.

---

### Block 3 — `text` — Data Model

The whiteboard stores a **vector stroke model**, not a raster image. Raster loses editability, undo, layer independence, and honest zoom. The vector model is the source of truth; PNG is a derived artifact.

### New block type: `drawing`

Added to the block type catalogue (Master Blueprint §6.3).

```json
{
  "version": 1,
  "theme": "chalkboard_green",
  "canvas": { "width": 4000, "height": 3000, "unit": "px" },
  "viewport": { "x": 0, "y": 0, "zoom": 1.0, "rotation": 0 },
  "grid": { "mode": "dot", "spacing": 40, "visible": false, "snap": false },
  "layers": [
    { "id": "bg",   "name": "Background", "visible": true, "locked": true },
    { "id": "main", "name": "Main",       "visible": true, "locked": false },
    { "id": "anno", "name": "Annotations","visible": true, "locked": false }
  ],
  "active_layer": "main",
  "strokes": [
    {
      "id": "s1",
      "layer": "main",
      "tool": "pen",
      "color": "#f4f4f0",
      "width": 3.0,
      "opacity": 1.0,
      "texture": "chalk",
      "seed": 12345,
      "points": [[120, 340, 0.62], [124, 342, 0.71], [128, 345, 0.68]],
      "bbox": [120, 340, 480, 620],
      "created_at": "2026-09-30T09:12:00Z"
    }
  ],
  "shapes": [
    {
      "id": "sh1", "layer": "main", "type": "rectangle",
      "x": 800, "y": 400, "w": 320, "h": 180,
      "stroke": "#7fe3c3", "stroke_width": 3, "fill": "none",
      "rotation": 0
    }
  ],
  "texts": [
    {
      "id": "t1", "layer": "main",
      "x": 200, "y": 200, "text": "Fractions",
      "font": "Inter 24 bold", "color": "#ffe066", "rotation": 0
    }
  ],
  "bookmarks": [
    { "id": "b1", "x": 100, "y": 200, "zoom": 2.0, "label": "long division" }
  ],
  "meta": {
    "last_edited_by": "uuid-dad",
    "stroke_count": 42,
    "shape_count": 3,
    "text_count": 1,
    "size_bytes": 8421,
    "updated_at": "2026-09-30T09:12:00Z"
  }
}
```

### Why this shape

- **Points as `[x, y, pressure]`** — pressure is optional; brush width interpolates.
- **`bbox` per stroke** — enables fast hit-testing for the eraser and for selection without scanning every point.
- **`seed`** — for texture (chalk, pencil) so re-renders are deterministic.
- **Separate `shapes` and `texts`** — they are first-class objects, editable after creation, not frozen into strokes.
- **`viewport` persisted** — reopening a drawing shows it where you left it.
- **`bookmarks`** — save positions and jump between them, useful for a long maths solution.

### Block field mapping

| `note_blocks` column | Value |
|---|---|
| `type` | `drawing` |
| `data` | the JSON above (or, if large, a pointer — see Block 4) |
| `text_content` | plain-text summary for FTS: theme + counts + any text objects |
| `ocr_text` | populated by the vision enrichment pass |
| `ai_description` | populated by the vision enrichment pass |
| `media_asset_id` | the rendered PNG thumbnail (for inline display and vision) |

---

### Block 4 — `text` — Storage Strategy

Two tiers, decided at save time by size.

**Small drawing** (strokes JSON < 500 KB and stroke count < 5,000):
- Strokes stored **inline** in `note_blocks.data.strokes`.
- Thumbnail PNG stored as a `media_asset` and referenced by `data.thumb_media_id`.

**Large drawing** (either threshold exceeded):
- Strokes JSON uploaded to object storage at `{hh}/drawings/{block_id}/strokes.json` (compressed, gzip by default).
- `note_blocks.data` becomes `{ "asset_id": "...", "thumb_media_id": "...", "stroke_count": N, "size_bytes": N, "theme": "..." }`.
- The panel fetches and decompresses on open, with a loading shim.

**Rationale:** most drawings are tiny (a few KB). Inline storage keeps them transactionally consistent with the note and avoids an object-store round trip on every open. Only genuinely large drawings (a full-page maths scratchpad with thousands of strokes) spill to the object store, and those are rare.

**Hard limits (server-enforced):**
- Canvas: max 16,000 × 12,000 logical px.
- Strokes per drawing: 20,000.
- Total JSON: 20 MB.
- Beyond limits: save is rejected with `error_code='drawing_too_large'` and a prompt to flatten the drawing (see Block 12, "Flatten").

**Flattening** converts existing strokes into a single background raster layer and clears the stroke list, preserving the picture while freeing the vector budget. Available from the panel's overflow menu.

---

### Block 5 — `text` — Schema Additions

The drawing does not need its own table — it is a block, and it reuses `media_assets`. Two small additions are useful.

```sql
-- Thumbnail reference for any block that renders as an image preview
-- (drawings, but also future structured blocks)
alter table note_blocks
  add column thumb_media_id uuid references media_assets(id);

-- Optional: per-user whiteboard preferences (docking, theme, brush presets)
whiteboard_preferences(
  id uuid pk,
  member_id uuid not null references family_members(id) on delete cascade,
  dock text not null default 'side-right',   -- side-right | side-left | full
  default_theme text not null default 'chalkboard_green',
  default_tool text not null default 'pen',
  brush_presets jsonb not null default '[]',
  recent_colors jsonb not null default '[]',
  show_grid_by_default bool default false,
  snap_to_grid bool default false,
  pressure_enabled bool default true,
  updated_at timestamptz default now(),
  unique(member_id)
);

-- Optional: per-note "last drawing" pointer, so reopening a note resumes the last drawing
-- (avoids scanning blocks; a small convenience)
-- Store in notes.extra: { "last_drawing_block_id": "uuid" }
```

The `thumb_media_id` column is generic and will be reused later by any block type that wants a preview.

**Persistence path:** the drawing JSON is written through the normal block-update endpoint. No new endpoint is needed for small drawings. Large drawings use a small dedicated endpoint (Block 9).

---

### Block 6 — `text` — Canvas Engine

### Rendering

- **`<canvas>` 2D** for the live layer, plus a **cached offscreen canvas** per layer for already-committed strokes.
- When a stroke is committed (pointer up), it is drawn once to the layer's offscreen canvas. Live drawing renders on top.
- Pan/zoom applies a transform to the canvas context; strokes are stored in **canvas coordinates**, not screen coordinates.
- **devicePixelRatio-aware** — crisp on retina and on iPad.
- **Request Animation Frame loop**, only active while there is work (idle = no frames).

### Coordinate system

- Logical canvas: `(0,0)` to `(width, height)`. Default 4000×3000.
- Viewport: `{ x, y, zoom }`. Screen point = `(canvas_point - viewport_xy) * zoom`.
- Zoom range: **0.05× to 16×**. Below 0.15×, strokes render as a single-color blob to save fill rate; above 8×, stroke widths scale down visually to keep lines readable.

### Viewport bounds

Panning is clamped so the user cannot lose the canvas. The visible viewport rectangle must always intersect the canvas rectangle expanded by 20% on each side. This prevents "where did my drawing go?" panics.

### Performance guards

- **Stroke decimation**: on pointer move, points are added only if they are > 1.2 px from the previous point. This keeps stroke point counts low without visible loss.
- **Bounding-box culling**: only strokes whose `bbox` intersects the visible rect are drawn.
- **Layer caching**: a layer's offscreen canvas is redrawn only when that layer changes.
- **Static view**: if the viewport is unchanged and no pointer is down, no rAF loop runs.
- **Hard cap**: if visible stroke count > 20,000, switch to a "flattened preview" mode that draws a single cached PNG until the user zooms in.

---

### Block 7 — `text` — Tools (Basic)

The toolbar. Left to right, top row.

| Tool | Icon | Behavior |
|---|---|---|
| **Select / Move** | cursor | Click a shape/stroke to select; drag to move; handles for resize/rotate on shapes |
| **Pen** | pen | Freehand stroke; pressure-aware; theme-dependent texture |
| **Highlighter** | highlighter | Wide, semi-transparent; drawn under pen strokes on the same layer |
| **Eraser (stroke)** | eraser | Tap or drag over a stroke to delete the whole stroke |
| **Eraser (pixel)** | soft eraser | Erases pixel-by-pixel; converts affected strokes into a raster patch on the same layer |
| **Line** | line | Straight line; hold `Shift` for 15° angle snap |
| **Arrow** | arrow | Same as line, with an arrowhead |
| **Rectangle** | square | Drag to size; hold `Shift` for square |
| **Ellipse** | circle | Drag to size; hold `Shift` for circle |
| **Triangle** | triangle | Drag to size |
| **Text** | type | Click to place a text cursor; supports multi-line; uses the theme font |
| **Pan** | hand | Drag the viewport (also: hold `Space` with any tool, or middle-mouse drag) |
| **Zoom** | magnifier | Click to zoom in; `Alt`+click to zoom out |

### Color & width

- **Color palette** — theme-driven (see Block 8). Up to 8 quick colors plus a "recent" row of 5.
- **Width slider** — 1 to 40 px logical, with 4 quick presets.
- **Opacity** — for pen and highlighter.

### Undo / Redo

- Stroke-level undo. Stack depth: 200 operations. Persisted in memory only (not across reload).
- `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z`.

### Clear

- "Clear layer" (current layer only) and "Clear all" (whole drawing).
- Both require confirmation; both are undoable.

---

### Block 8 — `text` — Tools (The "Little Bit Advanced")

Six features that take the whiteboard from "usable" to "pleasant". None are essential; all are one-tap away.

### 1. Shape recognition

- After drawing a rough line, rectangle, ellipse, triangle, or arrow, hold the pointer still for **350 ms** and the stroke snaps to a clean shape.
- Implementation: fit the point sequence to each candidate shape, pick the best fit under a tolerance; if none fit well, leave the stroke untouched.
- No ML. Pure geometry. Runs client-side in < 2 ms.
- Disabled by default? ⟦DECIDED⟧ **On by default** — it is the feature that most makes the board feel "smart". A toggle exists in settings.

### 2. Ruler mode

- Toggle in the toolbar. When active, a straight-line guide follows the pointer; strokes snap to it and to 15° increments.
- The guide can be repositioned and rotated with the pointer.
- Useful for axes, tables, and technical sketches.

### 3. Laser pointer

- While held (or while the tool is active), strokes are drawn in a bright color and fade over 2 seconds.
- Laser strokes are **never persisted** — they are ephemeral, session-only.
- Ideal for explaining something on the wall dashboard or during a family meeting.

### 4. Bookmarks

- Save the current viewport (x, y, zoom) with a name.
- Panel shows a small "bookmarks" chip row; click to jump.
- `[` and `]` cycle through bookmarks.
- Useful for a long maths solution or a multi-step diagram.

### 5. Grid modes

- `none` (default), `dot`, `square`, `graph` (10 small + 1 bold), `isometric`.
- Grid renders under strokes, above background.
- **Snap to grid** toggle — when on, new strokes and shapes snap their anchor points to grid intersections.
- Grid spacing configurable (default 40 px logical).

### 6. Layers

- Three layers by default: **Background**, **Main**, **Annotations**.
- Each layer: visible toggle, lock toggle, opacity (0–100%), clear, merge down.
- Active layer receives new strokes. Locked layers are inert.
- Add up to **5** layers total.
- Purpose-built use case: trace over an image on Background, draw on Main, annotate on Annotations. Or: solve on Main, mark mistakes on Annotations.

### Bonus: presentation mode

- `F` toggles full-screen presentation mode: hides toolbar, hides UI chrome, keeps only the canvas.
- Arrow keys page through bookmarks.
- `Esc` exits.
- Good for the wall dashboard and for family teaching moments.

---

### Block 9 — `text` — Themes

Themes define the canvas background, the quick-palette colors, the default brush texture, and the default font.

### Built-in themes

| ID | Name | Background | Palette | Texture |
|---|---|---|---|---|
| **`chalkboard_green`** | Chalkboard (green) | `#1e3a2f` deep forest green with subtle noise and vignette | White, Yellow, Pink, Cyan, Mint, Orange, Lilac, Chalk-grey | Chalk — grainy, slightly irregular edge, low-opacity halo |
| `chalkboard_black` | Chalkboard (black) | `#0e0e10` | Same as above | Chalk |
| `whiteboard` | Whiteboard | `#f7f7f4` | Black, Blue, Red, Green, Orange, Purple, Grey, Brown | Marker — smooth, slight opacity layering at overlaps |
| `blueprint` | Blueprint | `#0b1f3a` with a faint grid | White, Cyan, Yellow, Light blue | Drafting pen — thin, crisp |
| `kraft` | Kraft paper | `#e8d9b8` with paper grain | Charcoal, Sepia, Dark red, Dark green | Pencil — slightly rough |
| `dark_neon` | Dark neon | `#0a0a0f` | Neon cyan, magenta, lime, amber, white | Neon — glow halo, brighter core |
| `kids` | Kids | `#fff5e6` | Bright red, blue, yellow, green, pink, purple | Crayon — very grainy, chunky |

### The `chalkboard_green` theme (the requested one)

This is the flagship theme and should be tuned carefully.

**Background:**
- Base: `#1e3a2f`.
- Subtle procedural noise (a pre-generated 512×512 tile, low opacity) for a worn-board feel.
- Radial vignette darkening the corners by ~12%.
- Very faint horizontal dust streaks (optional, off by default).

**Chalk texture for strokes:**
- Render the stroke path with a base color at full opacity.
- Overlay a second pass with a jittered path (seed-driven, ±0.6 px) at 40% opacity.
- Add a soft glow (2 px blur, 20% opacity) for the halo effect of chalk dust.
- Optionally: draw 1–3 "grain" dots per 10 px of path, ±1.5 px, at 15% opacity.

The texture is applied on the offscreen layer at commit time, so it is rendered once, not every frame.

**Palette:**
- `#f4f4f0` White chalk (default)
- `#ffe066` Yellow chalk
- `#ff8fab` Pink chalk
- `#7fe3c3` Mint chalk
- `#8ecbff` Cyan chalk
- `#ffa94d` Orange chalk
- `#c8b6ff` Lilac chalk
- `#9aa0a6` Chalk grey

**Font:** `Kalam`, `Caveat`, or fallback to `Inter` italic. Bundled locally; no external font CDN.

### Custom themes

- Users with `parent` role can create a custom theme on `/settings/whiteboard/themes`.
- A custom theme defines: background color or uploaded image, palette, texture preset, font, grid style.
- Custom themes are Notes of `type='custom'`, `extra.category='whiteboard_theme'`, and are stored as Reference Set items so the AI can enumerate them (see Note B).

### Theme switching

- Theme is per-drawing (stored in the block's `data.theme`), not per-user.
- Changing the theme re-renders the background and recolors only strokes that use **theme-managed palette colors**. Custom hex colors stay as-is.
- A per-user default theme exists in `whiteboard_preferences`.

---

### Block 10 — `text` — Zoom, Pan, and Viewport

### Zoom

- **Mouse:** scroll wheel / trackpad pinch → zoom toward the pointer.
- **Touch:** two-finger pinch → zoom toward the midpoint.
- **Keyboard:** `+` / `-` → zoom toward viewport center; `0` → reset to 100%; `1` → fit to screen.
- **UI:** a zoom indicator with a slider; click to type a percentage.

Range: **0.05× to 16×**.

### Pan

- **Mouse:** middle-mouse drag, or `Space` + drag, or the Pan tool.
- **Touch:** two-finger drag, or the Pan tool.
- **Keyboard:** arrow keys move the viewport by 20 px; `Shift+arrow` by 200 px.
- **UI:** a small minimap in the panel's corner, showing the whole canvas and the current viewport rectangle; drag the rectangle to pan.

### Minimap

- Renders a downscaled preview of the drawing (bounding box of all content, or the full canvas if empty).
- Viewport rectangle overlay. Drag to move; wheel to zoom.
- Toggleable; on by default for canvases > 2000×2000.
- Essential on large canvases — without it, users lose their place.

### Fit-to-content

- `1` fits the bounding box of all content to the viewport.
- If the drawing is empty, fits the full canvas.

### Coordinate clamping

- The viewport rectangle must always intersect the canvas rect expanded by 20%.
- This means you cannot scroll past the edge into void, but you *can* see a bit of edge context.
- Zoom out clamps to 0.05× — you can never make the drawing disappear.

---

### Block 11 — `text` — Persistence & Autosave

### Save triggers

| Event | Action |
|---|---|
| Pointer up (stroke finished) | Add to in-memory history, mark dirty |
| Idle 1.5 s after last change | Debounced autosave |
| Panel close | Immediate save, flush pending |
| Note navigation | Flush before navigation |
| Browser `visibilitychange` to hidden | Flush |
| Explicit `Ctrl/Cmd+S` | Immediate save |

### Save payload

- Small drawing: `PATCH /api/blocks/{block_id}` with the updated `data` field.
- Large drawing: `POST /api/blocks/{block_id}/drawing/asset` (multipart, gzip), which stores the JSON in object storage and updates `data.asset_id`.
- Thumbnail: on save, the client renders the current drawing to a PNG at 1× (or 2× for retina) and uploads it if changed. `data.thumb_media_id` is updated.

The thumbnail render happens in a **Web Worker** off the main thread to avoid jank.

### Conflict handling

- Each drawing has an implicit `updated_at` from the block.
- On save, the client sends `If-Unmodified-Since: {last_seen_updated_at}`.
- If the server responds `409 Conflict` (another device saved in the meantime), the client shows a non-blocking notice: "This drawing was updated elsewhere. Reload to merge or keep mine." Options:
  - **Reload theirs** (discard local unsaved)
  - **Keep mine** (overwrite; last-write-wins)
  - **Save as copy** (creates a new block with the local version)
- A Redis lock per block (30 s TTL) prevents the same device from racing itself across two tabs.

### Offline

- The drawing editor works offline. Edits are queued in IndexedDB.
- On reconnect, the queue flushes in order.
- Conflicts use the same resolution UI.

### Storage hygiene

- Drawings are subject to the same soft-delete and backup rules as other blocks.
- Large drawings' objects are garbage-collected when the block is hard-deleted (or when the note is).

---

### Block 12 — `text` — Enrichment & AI Understanding

A drawing is not just for the human. The enrichment pipeline processes it so Hermes can reason about it later.

### Enrichment jobs

| Job | Input | Output |
|---|---|---|
| `media.thumbnail` | thumb media asset | standard derivatives |
| `vision.describe` | thumb PNG | `note_blocks.ai_description` — a natural-language description |
| `ocr.drawing` | thumb PNG | `note_blocks.ocr_text` — text found in the drawing (handwritten or typed) |
| `note.summarize` | parent note | existing pipeline picks up the block's text |

**Vision prompt** (for `vision.describe`): describe the drawing in 2–4 sentences — what it depicts, any visible text, and its apparent purpose (maths working, diagram, list, sketch). Do not guess at intent beyond what is visible.

**OCR:** for chalk and pencil strokes, general OCR works poorly. Two paths:
- ⟦DECIDED⟧ **Primary:** the vision model (llava/qwen-vl) reads the text. It handles messy handwriting far better than classic OCR.
- **Fallback:** Tesseract, used only if the vision model is disabled.

The output lands in `ocr_text`, which is indexed for full-text search. So "find the drawing where I wrote the quadratic formula" works.

### Math-aware mode (Phase 3)

- If the drawing's parent note is tagged `maths` or the drawing's `meta.purpose == 'maths'`, run a **maths-specific OCR** pass using a lightweight model (e.g. pix2tex or a LaTeX-OCR variant).
- The result is stored as a `maths_latex` field in `data.derived`.
- It appears as a "Copy as LaTeX" action in the drawing's context menu.
- Optional; disabled by default. Admin can enable in settings.

### Vector-level indexing (future)

- Strokes are not useful to an LLM directly, but they *are* useful for local features: counting, bbox extraction, and finding "the drawing with a red circle around something."
- Phase 4: index shape types and colors into a lightweight `data.index` object for structured queries like "drawings containing an arrow from left to right."

---

### Block 13 — `text` — Agent Tools

The whiteboard participates in the Tool Registry like everything else. New tools in `app/agent/tools/drawing.py`.

| Tool | Params | Mutates | Notes |
|---|---|---|---|
| `list_drawings` | `note_id?`, `member_id?`, `since?` | N | Returns drawing blocks with thumbnails |
| `get_drawing` | `block_id` | N | Returns the drawing data (large drawings return a summary + thumbnail URL) |
| `get_drawing_summary` | `block_id` | N | Returns the AI description, OCR text, counts, theme, and a thumbnail URL |
| `render_drawing_png` | `block_id`, `scale=1`, `background=true` | N | Returns a freshly rendered PNG URL |
| `create_note_with_drawing` | `title?`, `theme?` | **Y** | Creates a note with a blank drawing block |
| `append_drawing_block` | `note_id`, `theme?` | **Y** | Adds a blank drawing block to an existing note |
| `delete_drawing` | `block_id` | **Y** | Soft-deletes the block |

**What Hermes can do with these:**

- "Show me the drawing from Emma's maths homework" → `list_drawings` filtered by member, then `get_drawing_summary` for each.
- "What's on the whiteboard on the fridge note?" → `get_drawing_summary`.
- "Make a new note called 'Garden plan' with a blank whiteboard" → `create_note_with_drawing`.
- "Describe the diagram in the network notes from last week" → search → `get_drawing_summary`.

**What Hermes cannot do (by design):**
- It cannot edit strokes. Editing a drawing programmatically is not in Phase 1–3. This avoids the risk of an agent producing nonsense or destructive edits to a child's homework.
- Phase 4 may add `annotate_drawing` (append a highlight/circle/arrow) as a **mutating** tool with mandatory user confirmation.

**Permissions:** all drawing tools require `notes.read` (or `notes.write` for the mutating ones).

---

### Block 14 — `text` — Save-to-Note Flow (the Key Requirement)

The whiteboard saves to the *currently open note*. The flow, exactly:

```
1. Panel open, note "Maths homework 2026-09-30" is open.
   The panel resolves its target: notes.extra.last_drawing_block_id
      → if set and the block still exists → open that block
      → else → create a new drawing block on this note

2. User draws. Autosave runs every 1.5 s of idle.

3. On close:
   a. Flush pending changes.
   b. Render thumbnail PNG (Web Worker).
   c. Upload thumbnail if changed.
   d. PATCH block with final data + thumb_media_id.
   e. Update notes.extra.last_drawing_block_id = block_id.
   f. Panel animates closed. Note is untouched (no remount).

4. In the note renderer, the drawing block shows:
   - The thumbnail as a preview (with a soft drop shadow)
   - A small "✏️ Open whiteboard" button
   - A "⋯" menu: Export, Copy PNG, Delete, Duplicate

5. Clicking the preview reopens the panel with that block.
```

**If no note is open** (e.g. the panel was opened from the Tools menu on the home screen):
- The panel shows a small header: "Attach to note…"
- A searchable note picker appears (uses the Note A search).
- Selecting a note creates (or resumes) a drawing block on it.
- Or: "Create new note" creates a note titled after the current date and attaches the drawing.

**Multiple drawings per note** are allowed. The note renderer shows them in `order_index` order like any other block. The "last drawing" pointer is a convenience, not a constraint.

**Cross-note reuse** is via **Copy** / **Paste** in the panel, or the "Duplicate to another note" action.

---

### Block 15 — `text` — Menu & Keyboard Shortcuts

### Menu entry (registry-driven)

```ts
// frontend-main/lib/registry.ts
{
  id: "whiteboard",
  name: "Whiteboard",
  category: "utility",
  icon: "presentation",
  route: null,                       // ← no route; opens the panel
  action: "open_whiteboard",         // ← dispatched to the shell
  roles: ["parent", "child"],
  order: 5,
  enabled: true,
  surfaces: ["main", "kid"],
  toolSlug: "create_note_with_drawing",
  keywords: ["draw", "sketch", "board", "canvas", "chalkboard"],
}
```

The `action: "open_whiteboard"` is what makes this "call up from menu without refreshing". The sidebar/menu dispatches the action; the shell's whiteboard controller opens the panel. No navigation.

### Global shortcuts

| Shortcut | Action |
|---|---|
| `w` | Open/close whiteboard (ignored while focused in an input) |
| `Esc` | Close panel (or clear tool, or exit presentation mode — layered) |
| `F` | Toggle full-screen panel |
| `[` / `]` | Dock left / right |
| `P` | Pen · `H` Highlighter · `E` Eraser · `V` Select · `L` Line · `R` Rectangle · `O` Ellipse · `A` Arrow · `T` Text · `Space` Pan |
| `Ctrl/Cmd+Z` / `Ctrl/Cmd+Shift+Z` | Undo / Redo |
| `Ctrl/Cmd+S` | Force save |
| `Ctrl/Cmd+E` | Export PNG |
| `Ctrl/Cmd+C` / `Ctrl/Cmd+V` | Copy / paste selection (internal); outside selection, copies the whole canvas as PNG to the system clipboard |
| `1` | Fit to content · `0` Reset zoom |
| `+` / `-` | Zoom in / out |
| Arrows | Pan (with `Shift`, larger step) |
| `G` | Toggle grid |
| `M` | Toggle minimap |

Shortcuts are listed in a "?" overlay inside the panel.

### Kid mode differences

- Simplified toolbar: Pen, Eraser, Color, Clear, Undo.
- No layers, no shapes, no text, no laser.
- Larger hit targets.
- Palette is the `kids` theme's, regardless of the parent's chosen theme.
- Exports are auto-saved as a thumbnail on the note, and optionally shared to a parent for a "nice work!" reaction.

---

### Block 16 — `text` — Integration with the Note Renderer

The `drawing` block is rendered inline in the note like any other block.

```
┌──────────────────────────────────────┐
│  ✏️  Drawing · Chalkboard         ⋯  │
│  ┌────────────────────────────────┐  │
│  │  [thumbnail image]             │  │
│  │                                │  │
│  └────────────────────────────────┘  │
│  42 strokes · updated 3 min ago      │
│  [Open whiteboard]                   │
└──────────────────────────────────────┘
```

- The thumbnail is lazy-loaded.
- Click → opens the panel with that block.
- In the note's read-only preview (share links, wall), the drawing shows as a static image.
- In search results, drawings show the thumbnail + AI description.

**Embedding for search:** the block's `text_content` is auto-generated as `"{theme} drawing — {N} strokes, {N} shapes, {N} texts"` plus any text objects inlined. This gives FTS a foothold. The AI description and OCR text give semantic search a much richer signal.

---

### Block 17 — `text` — Phase Placement & Acceptance

**Phase 2:**
- `drawing` block type + schema migration (`thumb_media_id` on `note_blocks`).
- Canvas engine (pen, highlighter, eraser, line, rect, ellipse, text, pan/zoom).
- Themes: `chalkboard_green`, `chalkboard_black`, `whiteboard`, `kids`.
- Slide-out panel with side-right, side-left, full modes.
- Save to note, autosave, thumbnail rendering, note renderer integration.
- Menu entry + `w` shortcut.
- Enrichment: `vision.describe` + OCR via vision model.

**Phase 3:**
- Advanced tools: shape recognition, ruler, laser, bookmarks, grid modes, layers.
- Themes: `blueprint`, `kraft`, `dark_neon`.
- Presentation mode.
- Export PNG/SVG/JSON. Import JSON.
- Agent tools: `list_drawings`, `get_drawing_summary`, `create_note_with_drawing`, `append_drawing_block`.
- Whiteboard preferences per user.
- Floating window mode.
- Maths-aware OCR (opt-in).

**Phase 4:**
- Real-time multi-user whiteboard (same household) — WebSocket sync.
- `annotate_drawing` agent tool (mutating, with confirmation).
- Cross-note drawing references and reuse.
- Vector feature indexing.

**Acceptance (Phase 2):**
- [ ] Pressing `w` anywhere in the app opens the panel in < 100 ms without a page reload or route change.
- [ ] Opening the panel does not lose unsaved text in the current note.
- [ ] Closing the panel saves the drawing to the current note's block within 500 ms.
- [ ] Reopening the same note shows the drawing in the block list with a correct thumbnail.
- [ ] The chalkboard theme renders with the chalky texture and the 8-color palette.
- [ ] Undo/redo works up to 200 operations.
- [ ] The canvas pans and zooms with correct clamping; the minimap tracks the viewport.
- [ ] Autosave fires within 2 s of the last stroke and is idempotent on repeated calls.
- [ ] A conflict from two devices shows the resolution UI and never silently loses data.
- [ ] A drawing's AI description appears in the block within 60 s of saving, and the drawing is findable by search on that description.
- [ ] `create_note_with_drawing` returns a new note with a blank drawing block via `/internal/agent/tools`.
- [ ] Kid mode shows the simplified toolbar and does not expose layers or shapes.

---

### Block 18 — `text` — Design Notes for the Coding Agent

A few things that are easy to get wrong:

1. **The panel must be a portal at the shell level**, not a child of the note route. If it renders inside the note component, any state change in the note can unmount it and lose unsaved strokes.
2. **Coordinates are canvas-space, not screen-space.** The single most common bug in canvas editors is storing screen coordinates and then breaking on pan/zoom. Store logical points; transform on render.
3. **Do not re-render committed strokes every frame.** Use an offscreen canvas per layer.
4. **Do not block the main thread on save.** Thumbnail rendering and gzip compression go in a Web Worker.
5. **Do not poll for save.** Debounce on idle + flush on visibility change + flush on close. That is enough.
6. **Do not trust the browser's pointer events for pressure.** Fall back to velocity-derived pressure when `pressure === 0` on non-pressure devices, so the pen does not look dead on desktop.
7. **Never autosave on every point.** That would hammer the backend. Save on stroke-end + idle, never per-point.
8. **The theme is a property of the drawing, not the user.** A user with a chalkboard preference can still receive a whiteboard drawing from someone else.
9. **The chalk texture must be rendered once, into the layer's offscreen canvas at commit time.** Recomputing the jittered path every frame is the difference between 60 fps and 5 fps.
10. **The "no refresh" requirement is a UX contract.** If any code path causes the note component to remount when the panel opens, it is a bug — treat it as a P1 regression.

---

**End of Note C.**
`status='active'` · `pinned=false` · `tags=['tool','whiteboard','canvas','drawing','v1.1']` · `visibility='family'`