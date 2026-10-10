# FamilyOS 2027 — Note D: AI-Assisted Tagging, Tag Hygiene & Exclusion Memory

**Note**
```json
{
  "title": "AI-Assisted Tagging, Tag Hygiene & Exclusion Memory — The Tag Governance System",
  "type": "freeform",
  "status": "active",
  "visibility": "parents",
  "pinned": false,
  "owner_member_id": null,
  "tags": ["tags", "agent", "governance", "classification", "v1.1"],
  "summary": "A full governance layer over tags. Human tags are sacred and never overwritten. AI tags are tiered by confidence, evidence-backed, budgeted, and reversible. Removed tags become permanent exclusions at per-note, per-type, per-member, or household scope. Includes a proposal queue, tag consolidation, hierarchy discovery, and a feedback loop that learns the household's tag style.",
  "extra": { "doc_version": "1.0", "target_reader": "coding-agent", "depends_on": "Master Blueprint v1.1, Note A (Search), Note B (Reference Sets)" }
}
```

---

### Block 1 — `text` — The Problem, Stated Precisely

The user's concern: *"I don't want tags or categories to become a mess."*

This is the correct concern. It is the failure mode of every tagging system ever built. The pattern is universal:

1. Users create tags freely.
2. Within months there are `#travel`, `#trip`, `#vacation`, `#holiday`, `#japan`, `#Japan2027`, `#japan-trip`, `#2027-japan`.
3. None of them mean what they meant last year.
4. Search degrades. Filtering degrades. The AI's vocabulary is polluted.
5. Users give up and stop tagging.

Adding an LLM to this problem without discipline makes it worse, not better — the model will happily invent 40 plausible-sounding tags a day. The result is tag entropy at machine speed.

**The goal is not "the AI tags everything." The goal is: the AI makes the tag set *smaller, more meaningful, and more trustworthy* over time, while the user's own tags remain exactly as they typed them.**

That inverts the naive design. Most AI tagging systems maximize coverage. This system maximizes **precision, consistency, and reversibility**.

---

### Block 2 — `text` — Ten Design Principles

1. **Human tags are sacred.** The AI never edits, renames, removes, or re-scores a tag a human added. Ever. Not in a batch job, not on edit, not "for cleanup."
2. **AI tags are tentative by default.** They are visible, filterable, and clearly marked. They can be suppressed per note, per type, per member, or globally.
3. **Nothing is silently applied at high stakes.** Low-confidence AI tags go into a *proposal queue*. Only high-confidence tags apply silently, and even those can be undone in one tap.
4. **Every AI tag carries evidence.** "Why did you tag this `#receipt`?" has a concrete, inspectable answer pointing at specific text, OCR, or a specific block.
5. **Removals are permanent.** A tag removed from a note by a human adds an exclusion at the narrowest useful scope. The AI will not propose it on that note again, ever.
6. **The tag pool is disciplined.** AI cannot invent tags freely. New tags are *proposed*; they become usable only after approval (configurable per household).
7. **Tags have budgets.** Every note has a hard cap on AI tags (default 5). This is the single most effective anti-entropy measure.
8. **Tag taxonomy is emergent, not imposed.** The system suggests hierarchy and merges from real usage; it never restructures the tag set without a human approving.
9. **The user's style is learned.** If the household uses lowercase-hyphenated English tags, the AI proposes in that style, not `CamelCase` or `snake_case`.
10. **Everything is reversible and audited.** Any AI tag action can be undone, and every action has a row in `tag_audit_log`.

---

### Block 3 — `text` — Better Ideas (What This Note Adds Beyond the Ask)

The user asked for: AI classifies → applies tags → respects removals → keeps things tidy. That baseline is fine. These ten ideas take it further.

**I1 — Tag provenance on every row.** Each `(note, tag)` relationship stores its `source` (`human` | `ai` | `system` | `imported`), `confidence`, and `evidence`. The UI can filter "show me only AI tags" or "show me only human tags." Search can weight them differently.

**I2 — Tag proposal queue, not silent creation.** New candidate tags from the AI do not become usable tags until approved (or, if the household allows, until confidence ≥ threshold). This is what stops the tag pool from exploding.

**I3 — Tag budget per note.** Cap AI tags at 5 by default (configurable). When a sixth candidate wants in, the system must either drop it or replace a lower-confidence tag. This forces the model to *choose*, which is exactly the behavior that produces good tags.

**I4 — Evidence chains.** Every AI tag links to the specific span of text, OCR line, or block that justified it. Clicking the tag shows the evidence. This is what makes the AI trustworthy — and it is what lets you verify in two seconds that the tag is wrong.

**I5 — Scoped exclusions.** A removal can be remembered at four scopes: this note, this note type for this member, this member, the whole household. The system picks the narrowest sensible scope and asks if you want it wider.

**I6 — Tag hierarchy discovery.** The AI observes that notes tagged `#japan-2027` are almost always also tagged `#travel` and proposes a parent relationship. Over time a light tree emerges from the flat list — without anyone having to design it upfront.

**I7 — Tag consolidation.** Duplicate and near-duplicate tags (`#trip` vs `#travel`) are detected by embedding similarity. Merges are proposed, previewed (with the list of affected notes), and executed with a redirect so nothing breaks.

**I8 — Style learning.** The system records the household's tag conventions — case, separator, language, average count per note, average length — and constrains AI proposals to that style.

**I9 — Trust decay on low use.** An AI tag applied once and never interacted with (not clicked, not searched for, not filtered by) over 90 days is a candidate for removal. This is the only auto-removal path, and it is off by default.

**I10 — "Never on this note type" shortcuts.** From the tag chip menu: "Never suggest this on any *receipt*." This is the most powerful exclusion scope and the one that keeps the tag set relevant per-domain.

---

### Block 4 — `text` — Tag Taxonomy Model

Tags in FamilyOS are not one thing. The system recognises four conceptual kinds. The distinction matters because the AI treats them differently.

| Kind | Example | Who sets it | AI behavior |
|---|---|---|---|
| **System tag** | `blueprint`, `agent-memory`, `vault` | Code / admin only | Never added or removed by AI |
| **Facet-like tag** | `who:emma`, `when:2027`, `status:active` | Human, or via facets | AI may add, but prefers a facet if one exists |
| **Topic tag** | `travel`, `japan`, `school-fees`, `maths` | Human, and AI with approval | AI's primary playground |
| **Ad-hoc tag** | `#neighbour-msg`, `#glasses-prescription` | Human, one-off | AI may suggest existing ones; may propose new only if explicitly allowed |

**Facet-like tags have a namespace prefix.** The convention is `namespace:value`:

- `who:` — people (redundant with `owner_member_id`, but useful for cross-references like "mentioned in this note")
- `when:` — years, months, events
- `place:` — locations
- `where:` — synonym, deprecated
- `topic:` — high-level category (`topic:finance`, `topic:health`)
- `source:` — origin (`source:school`, `source:email`, `source:whatsapp`)

Namespaces are optional. Free-form tags remain valid. The point is that *when the AI wants to add a who/where/when style tag*, it uses a namespace instead of inventing a flat one, which keeps the flat list clean.

**The AI is instructed to prefer existing facets and namespaced tags over inventing flat equivalents.** If a note has `owner_member_id=emma`, the AI does not propose `#emma`. It might propose `#who:dad` if Dad is mentioned in the text.

---

### Block 5 — `text` — Schema

Two existing tables gain columns; three new tables are added.

```sql
-- ── note_tags gains provenance ──────────────────────────────────────────
alter table note_tags
  add column source text not null default 'human'
       check (source in ('human','ai','system','imported')),
  add column confidence real,                    -- 0..1, null for human
  add column model text,                         -- which model produced it
  add column evidence jsonb default '{}',        -- see Block 7
  add column applied_at timestamptz default now(),
  add column applied_by uuid references family_members(id),
  add column last_verified_at timestamptz,       -- set on re-evaluation
  add column approved_by_human bool default true; -- false until reviewed (if suggestions are on)

create index on note_tags (note_id) where source = 'ai';
create index on note_tags (tag_id, source);

-- ── tags gains lifecycle metadata ───────────────────────────────────────
alter table tags
  add column kind text not null default 'topic'
       check (kind in ('system','facet','topic','adhoc')),
  add column namespace text,                     -- 'who','when','place','topic','source', or null
  add column canonical_slug text,                -- for merges: points to the surviving tag
  add column usage_count int default 0,          -- denormalized, updated by trigger
  add column ai_usage_count int default 0,
  add column proposed bool default false,        -- true until approved by a human
  add column proposed_by text,                   -- 'ai' | 'import' | 'system'
  add column first_seen_at timestamptz default now(),
  add column last_used_at timestamptz,
  add column retired_at timestamptz;

create index on tags (household_id, kind, retired_at);
create index on tags (household_id, canonical_slug) where canonical_slug is not null;
create index on tags (household_id, proposed) where proposed;

-- ── Tag exclusions: the memory of removals ─────────────────────────────
tag_exclusions(
  id uuid pk,
  household_id uuid not null,
  tag_id uuid references tags(id) on delete cascade,
  tag_slug text not null,                        -- denormalized for fast lookup
  scope text not null
    check (scope in ('note','note_type','member','household')),
  scope_ref uuid,                                -- note_id | member_id | null
  scope_note_type text,                          -- note type when scope='note_type'
  reason text,                                   -- 'user_removed' | 'user_never' | 'system'
  created_by uuid references family_members(id),
  created_at timestamptz default now(),
  expires_at timestamptz,                        -- null = forever (default)
  -- Enforce uniqueness per scope target
  unique(household_id, tag_slug, scope, scope_ref, scope_note_type)
);
create index on tag_exclusions (household_id, tag_slug);
create index on tag_exclusions (household_id, scope, scope_ref);
create index on tag_exclusions (household_id, scope, scope_note_type);

-- ── Pending AI tag proposals (the review queue) ────────────────────────
tag_proposals(
  id uuid pk,
  household_id uuid not null,
  note_id uuid not null references notes(id) on delete cascade,
  tag_id uuid references tags(id),               -- null if it's a new-tag proposal
  proposed_slug text not null,
  proposed_kind text not null default 'topic',
  proposed_namespace text,
  confidence real not null,
  evidence jsonb not null default '{}',
  model text not null,
  status text not null default 'pending'
    check (status in ('pending','accepted','rejected','expired','auto_applied')),
  decided_by uuid references family_members(id),
  decided_at timestamptz,
  expires_at timestamptz default (now() + interval '30 days'),
  created_at timestamptz default now()
);
create index on tag_proposals (household_id, status, created_at desc);
create index on tag_proposals (note_id, status);
create index on tag_proposals (household_id, proposed_slug, status);

-- ── Tag hierarchy (emergent, human-approved) ───────────────────────────
tag_relations(
  id uuid pk,
  household_id uuid not null,
  parent_tag_id uuid not null references tags(id) on delete cascade,
  child_tag_id uuid not null references tags(id) on delete cascade,
  relation text not null
    check (relation in ('parent_of','implies','related_to','deprecated_alias')),
  confidence real,
  proposed_by text,                              -- 'ai' | 'human'
  approved bool default false,
  created_at timestamptz default now(),
  unique(parent_tag_id, child_tag_id, relation)
);
create index on tag_relations (household_id, approved);

-- ── Merge history (redirects for renamed/merged tags) ──────────────────
tag_merges(
  id uuid pk,
  household_id uuid not null,
  from_tag_id uuid not null,
  to_tag_id uuid not null references tags(id),
  merged_by uuid references family_members(id),
  merged_at timestamptz default now(),
  notes_affected int,
  notes_relabeled int
);
create index on tag_merges (household_id, merged_at desc);

-- ── Audit log for every tag action ─────────────────────────────────────
tag_audit_log(
  id uuid pk,
  household_id uuid not null,
  actor_type text not null,                      -- 'human' | 'ai' | 'system'
  actor_id uuid,                                 -- member_id or null
  action text not null,                          -- see Block 12
  note_id uuid,
  tag_slug text,
  before jsonb,
  after jsonb,
  reason text,
  created_at timestamptz default now()
);
create index on tag_audit_log (household_id, created_at desc);
create index on tag_audit_log (household_id, note_id);
create index on tag_audit_log (household_id, tag_slug);

-- ── Household tag style profile (learned) ──────────────────────────────
tag_style_profile(
  household_id uuid pk,
  case_style text default 'lower',               -- 'lower' | 'title' | 'mixed'
  separator text default 'hyphen',               -- 'hyphen' | 'underscore' | 'space' | 'none'
  language text default 'en',                    -- 'en' | 'zh-hant' | 'mixed'
  avg_tags_per_note real default 3.0,
  max_tags_per_note int default 8,
  preferred_namespaces text[] default '{}',
  forbidden_chars text[] default '{}',
  samples jsonb default '[]',                    -- 20 representative human tags
  updated_at timestamptz default now()
);
```

**Every existing table gets a migration that backfills:** `note_tags.source='human'` for all existing rows (there was no AI tagging before), `tags.kind='topic'` (default), `tags.proposed=false`.

---

### Block 6 — `text` — The Tag Lifecycle

This is the state machine that everything else references.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          HUMAN ACTIONS                               │
│                                                                      │
│  Human adds a tag                                                    │
│    → note_tags row, source='human', confidence=null                  │
│    → If tag doesn't exist: create with kind='topic', proposed=false  │
│    → tag_audit_log: 'human_add'                                      │
│                                                                      │
│  Human removes a tag                                                 │
│    → note_tags row deleted                                           │
│    → If source='ai'  → add tag_exclusion (see Block 8)               │
│    → If source='human' → just remove; no exclusion (it was theirs)   │
│    → tag_audit_log: 'human_remove'                                   │
│                                                                      │
│  Human says "never again" from a chip menu                           │
│    → add tag_exclusion at the chosen scope                           │
│    → tag_audit_log: 'human_exclude'                                  │
│                                                                      │
│  Human approves a proposal                                           │
│    → tag_proposals.status='accepted'                                 │
│    → note_tags row, source='ai', approved_by_human=true              │
│    → If proposal was for a new tag: tags.proposed=false              │
│    → tag_audit_log: 'proposal_accepted'                              │
│                                                                      │
│  Human rejects a proposal                                            │
│    → tag_proposals.status='rejected'                                 │
│    → add tag_exclusion at scope='note' (default)                     │
│    → tag_audit_log: 'proposal_rejected'                              │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                           AI ACTIONS                                 │
│                                                                      │
│  AI evaluates a note (after enrichment or on edit)                   │
│    → builds candidates with confidence + evidence                    │
│    → filters through exclusions + budget + tag pool rules            │
│    → partitions:                                                     │
│        confidence ≥ 0.85  → auto-apply (source='ai', approved=false) │
│        0.60 ≤ c < 0.85    → proposal (status='pending')              │
│        c < 0.60           → discard silently                         │
│    → tag_audit_log: 'ai_apply' or 'ai_propose'                       │
│                                                                      │
│  AI re-evaluates on note edit                                        │
│    → only touches rows where source='ai' and approved_by_human=false │
│    → never touches human tags, never touches approved AI tags        │
│    → removes AI tags whose evidence no longer exists                 │
│    → adds new candidates through the same pipeline                   │
│                                                                      │
│  AI proposes a new tag (not in the pool)                             │
│    → tag_proposals row with tag_id=null, proposed_slug set           │
│    → Only if household setting 'allow_new_tag_proposals' = true      │
│    → Shown distinctly in the queue as "New tag"                      │
│                                                                      │
│  AI proposes a merge                                                 │
│    → tag_relations row with relation='related_to' (for review)       │
│    → Surfaced in the Tag Hygiene page (Block 13)                     │
│    → Never executed without a human                                  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**The three confidence bands are the heart of the system.** They are household-tunable in settings (Advanced → Tagging). Defaults above. A household that wants full control sets auto-apply to `never`; a household that trusts the AI lowers the threshold to 0.75.

---

### Block 7 — `text` — Evidence, Confidence & the Classifier

Every AI tag carries an `evidence` object. Its shape is deliberately concrete so the UI can render it and the user can verify it.

```json
{
  "matched_text": "Wellcome receipt — total HKD 342.50",
  "matched_block_id": "uuid",
  "matched_span": [0, 42],
  "signals": [
    { "type": "keyword", "value": "receipt", "weight": 0.4 },
    { "type": "keyword", "value": "HKD",     "weight": 0.2 },
    { "type": "ocr",     "value": "TOTAL",   "weight": 0.3 },
    { "type": "semantic","value": 0.86,      "weight": 0.3 },
    { "type": "prior",   "value": 0.12,      "weight": 0.1 }
  ],
  "model": "qwen2.5:7b",
  "prompt_version": "tag-v3",
  "evaluated_at": "2026-09-30T09:14:00Z"
}
```

**Signals** are what make the tag explainable. They are the *why*. The UI shows them as bullet points in the tag's tooltip and in the proposal queue.

**Confidence** is a calibrated score in `[0, 1]`. The classifier combines:
1. **Keyword presence** in title, body text, OCR, transcript.
2. **Semantic similarity** between the note's embedding and the tag's centroid embedding.
3. **Prior** — how often this tag has been applied to similar notes in this household.
4. **Co-occurrence** — the tag's association with other already-trusted tags on this note.
5. **Negative signals** — the note's blocks contain an explicit contradiction (e.g. "not a receipt").

The classifier is a small Python module, not a fresh LLM call per candidate. It runs after a single LLM call that returns a ranked candidate list with reasons. This keeps cost predictable.

**The LLM prompt** (system message, abbreviated):

> You are a tag classifier for a family knowledge system. You will receive a note with its blocks, existing tags, and the household tag style profile. Propose at most 8 candidate tags, each with a confidence 0–1 and a one-line reason. Rules: (1) never propose a tag on the exclusion list for this note, this note type, this member, or the household; (2) prefer existing tags over new ones; (3) prefer namespaced tags (`who:`, `when:`, `place:`, `topic:`) over flat equivalents for person/date/place concepts; (4) do not propose a tag already present on the note; (5) do not propose tags that duplicate a facet field (`type`, `status`, `owner_member_id`, `expires_at`); (6) if a tag would only apply because of a single ambiguous word, lower its confidence below 0.4; (7) respect the household style (case, separator, language).

The prompt is versioned (`prompt_version`), and changing it is a schema-adjacent event that invalidates old tag evaluations (they are re-evaluated lazily).

---

### Block 8 — `text` — The Exclusion System (The Key Requirement)

This is what the user specifically asked for: *"if I remove the tags the LLM should know it and never tag that again."*

The naive implementation is a per-note list. That is not enough, because the same frustration repeats across notes. The system uses **four scopes**, picks the narrowest sensible one by default, and lets the user widen it in one tap.

| Scope | Applies to | When it's chosen | Example |
|---|---|---|---|
| **note** | One specific note | Default when a user removes an AI tag from a note | "Not `#travel` on *this* note" |
| **note_type** | All notes of one type | Offered when the user has removed the same tag from 3+ notes of that type | "Never `#travel` on `receipt`" |
| **member** | All notes owned by or created by a member | Offered when the user tags notes for one person differently | "Never `#school` on Dad's notes" |
| **household** | Every note | Offered when the user chooses "Never suggest this anywhere" | "Never `#misc`" (banned outright) |

**Resolution order at evaluation time:**

```
Given a note N, a tag T, an actor A:
  if exclusion(N, T)             → skip
  if exclusion(N.type, T)        → skip
  if exclusion(N.owner_member_id, T) → skip
  if exclusion(A.id, T)          → skip
  if exclusion(household, T)     → skip
  else proceed to evaluate
```

**The "widen" interaction.** When a user removes an AI tag, a small toast appears: *"Noted. Never suggest `#travel` on this note."* with a `Wider…` link. Clicking it opens a menu:

- ⦿ This note only (default)
- ○ Every `receipt`
- ○ Everything owned by Emma
- ○ Everywhere (ban the tag entirely)
- ○ Just this once (no exclusion)

The default action (do nothing) records the exclusion at the narrowest scope. This is important — most removals are genuinely local, and recording them at household scope would be overkill and would degrade the AI's usefulness elsewhere.

**Auto-widening.** If the same `(tag, note_type)` removal happens 3 times within 30 days by the same user, the system *proposes* widening the exclusion to the `note_type` scope. It is a proposal, not an action.

**Expiry.** Exclusions default to permanent (`expires_at=null`). A household setting allows time-limited exclusions (e.g. 90 days), useful for seasonal tags like `#christmas`. The default is permanent because the user's stated intent is permanence.

**Reversal.** Exclusions are visible and reversible on `/settings/tags/exclusions`. A list of every exclusion, its scope, who created it, and when. One-click revoke.

**Exclusion propagation to the agent.** When Hermes builds a search or calls `create_note` with tags, it validates each tag against the note's exclusion set. If a user asks Hermes to tag a note and the tag is excluded, Hermes must refuse and say why: *"You've told me not to suggest `#travel` on this note before — do you want to override that?"*

---

### Block 9 — `text` — Tag Pool Discipline

The single biggest source of tag entropy is the AI inventing new tags. The system prevents this with four rules.

### Rule 1 — Prefer existing tags

The LLM receives the current tag pool (top 200 by usage) in its prompt. It is instructed to prefer existing tags over new ones. A new tag is proposed only when no existing tag is a good match.

### Rule 2 — New tags go through the proposal queue

A candidate tag that does not exist in the pool becomes a `tag_proposals` row with `tag_id=null`. It is shown in the queue as a **"New tag"** proposal — visually distinct from "Apply existing tag" proposals.

### Rule 3 — New tags have a higher bar

A new tag must clear a confidence threshold (default 0.75) that is **higher** than the auto-apply threshold for existing tags (0.85) *and* must survive a **cool-down**: it cannot be proposed on another note for 14 days unless approved. This kills the pattern of "AI discovers a new tag and applies it to 30 notes in a week."

### Rule 4 — New tags expire if unused

An unapproved new-tag proposal expires after 30 days. If a proposed tag is never approved and never re-proposed, it never enters the pool. The pool stays small.

### Rule 5 — `allow_new_tag_proposals` can be turned off entirely

A household setting. When off, the AI may only apply tags that already exist. This is the strictest mode and is the right default for a household that wants total control. Recommended default: **on**, but with the cool-down and expiry rules above.

---

### Block 10 — `text` — Budgets & Bounds

| Budget | Default | Configurable | Rationale |
|---|---|---|---|
| **Max AI tags per note** | 5 | Yes (0–15) | Forcing the model to choose produces better tags |
| **Max total tags per note** | 12 | Yes (5–30) | Prevents tag spam even by humans |
| **Max new-tag proposals per household per day** | 5 | Yes | Prevents proposal queue flooding |
| **Max proposals shown per note in the queue** | 8 | No | UI sanity |
| **Min confidence to auto-apply** | 0.85 | Yes | |
| **Min confidence to propose** | 0.60 | Yes | |
| **Cool-down before re-proposing a rejected tag on the same note** | 90 days | Yes | |

**Budget enforcement at evaluation time:** if the model returns 9 candidates, the classifier ranks them and keeps the top 5 (after removing duplicates and excluded tags). The rest are logged as `budget_dropped` in the audit log but not surfaced.

**When the note already has 12 tags (max) and the AI wants to add one:** it cannot. It may instead propose a **swap** — "to add `#school-fees`, remove `#finance`" — which the user can accept or reject. This is a Phase 3 nicety, not Phase 1.

---

### Block 11 — `text` — The Proposal Queue (Review Surface)

A dedicated page: `/tags/review`. Also a badge on the sidebar and an item in the Overview dashboard.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Tag Review · 23 pending                                    [⚙]      │
│                                                                      │
│  ┌─ Filters ─────────────────────────────────────────────────────┐  │
│  │ Note type: [all ▾]   Confidence: [≥0.60 ▾]   Age: [any ▾]     │  │
│  │ ▢ Show new-tag proposals   ▢ Show only high confidence         │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ School fee 2027-01            school_notice · 2 days ago       │  │
│  │                                                                │  │
│  │ Proposed:  #school-fees (0.91)  #finance (0.88)  #2027 (0.72) │  │
│  │ #parent-action (0.66)                                          │  │
│  │                                                                │  │
│  │ Evidence:                                                      │  │
│  │  • "#school-fees" — matched "school fee" in OCR of page 1     │  │
│  │  • "#finance" — matched "HKD 4,200 payable" in OCR            │  │
│  │  • "#2027" — matched "for the 2027 academic year"             │  │
│  │  • "#parent-action" — semantic match 0.71 to prior notices     │  │
│  │                                                                │  │
│  │ [Accept all] [Accept selected] [Reject all] [Open note]        │  │
│  │ ▢ Remember rejections                                      ▾  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ...                                                                 │
│                                                                      │
│  ┌─ Bulk ─────────────────────────────────────────────────────────┐  │
│  │ [Accept all ≥0.85]  [Accept all for selected note types]       │  │
│  │ [Reject all <0.70]  [Reject selected tags everywhere]          │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

**Per-proposal actions:** accept, reject, reject-and-exclude (at a chosen scope), open the note, edit the tag (rename before accepting).

**Bulk actions** are deliberately limited to two or three safe operations. Wholesale acceptance is discouraged; the point is to force a small amount of attention that keeps the tag set clean.

**Notifications.** Once a day (or on-demand), the household receives a digest: *"12 AI tag proposals are waiting; 7 are high-confidence."* — a single notification with a link, not one per proposal.

**Auto-accept rules** (optional, advanced). The household may configure: *"Auto-accept proposals with confidence ≥ 0.90 from the following tags: #receipt, #invoice, #school-notice."* This lets a family automate the boring cases while keeping the review queue for judgment calls.

---

### Block 12 — `text` — Feedback Loop (Learning the Household's Style)

The system records enough signal to learn three things:

### 1. Tag style

The `tag_style_profile` table accumulates observed human-tagged patterns:
- Case: does the household write `Travel` or `travel`?
- Separator: `school-fees`, `school_fees`, `school fees`, or `schoolfees`?
- Length: do they prefer short tags (`#tax`) or descriptive (`#income-tax-2027`)?
- Language: English, Traditional Chinese, mixed?
- Average tags per note.

After ~100 human-added tags, the profile is confident enough to constrain AI proposals. The LLM prompt includes the style profile as a directive, and proposals that violate it are auto-rejected.

### 2. Tag preferences per member

If Dad always tags his notes with `#work` and never with `#finance`, the system weights the model's candidates accordingly for Dad's notes.

### 3. Implicit rejection patterns

If the user rejects 4 of 4 proposals of `#work` on personal notes, the classifier sees `#work` → low prior for that member. This is a soft, learned signal — distinct from a hard exclusion.

The feedback loop **never** overrides an explicit exclusion. Exclusions are absolute. The feedback loop only adjusts confidence in the absence of an exclusion.

---

### Block 13 — `text` — Tag Hygiene Page (Consolidation & Hierarchy)

A dedicated page: `/settings/tags/hygiene`. Parents only. This is where entropy is actively reduced.

### Sections

**1. Duplicates & near-duplicates**

Clusters of tags whose embedding centroids are within a threshold (default cosine 0.85). Examples:
- `travel` / `trip` / `vacation`
- `school-fees` / `schoolfee` / `fees-school`
- `maths` / `math` / `mathematics`

Each cluster shows the tags, their usage counts, and a **suggested merge** with a target. Preview shows the list of affected notes. Merging:
- Repoints all `note_tags` from the losers to the winner.
- Sets `tags.canonical_slug` on the losers to the winner's slug (so old URLs and old agent queries still resolve).
- Writes a `tag_merges` row.
- Writes `tag_audit_log` rows.
- Notifies the household (one notification, not one per note).

**2. Hierarchy suggestions**

The AI observes that notes tagged `#japan-2027` are almost always also tagged `#travel`. It proposes a `parent_of` relationship: `travel → japan-2027`. If approved:
- The tag sidebar groups children under their parent.
- Search for `#travel` optionally includes descendants (a toggle).
- The AI's prompt includes the hierarchy, so it proposes more specific tags (`#japan-2027`) rather than the general one (`#travel`) when both fit.

**3. Unused tags**

Tags with `usage_count=0` and no `note_tags` reference. After 180 days, these are candidates for retirement (`retired_at` set, hidden from pickers but kept for history). Retired tags do not appear in the AI's candidate pool.

**4. Low-use AI tags**

AI tags applied once and never interacted with (never clicked in search, never filtered by, never edited) for 90 days. These are candidates for removal — the only auto-removal path, off by default, and even when on, it produces a proposal rather than an action.

**5. Exclusions review**

Every exclusion, its scope, its origin, when it was created. One-click revoke. A chart of how many exclusions exist at each scope (a rising household-level exclusion count is a signal that the AI is over-proposing a particular tag).

**6. Forbidden tags**

A hard list. Tags on this list are never applied, never proposed, never shown in pickers. Example: a family that hates the tag `#misc`. This is the household-scope exclusion, surfaced directly.

---

### Block 14 — `text` — Re-evaluation on Note Changes

When does the AI re-evaluate a note's tags?

| Trigger | Behavior |
|---|---|
| Note created | Full evaluation after enrichment completes |
| New block added | Re-evaluate; only AI tags with `approved_by_human=false` may change |
| Block edited | Re-evaluate the affected block's contribution to evidence; may remove AI tags whose evidence is gone |
| Note title changed | Re-evaluate (title has high weight) |
| Note type changed | Full re-evaluation; exclusions for the new type apply |
| Owner/member changed | Re-evaluate member-scoped exclusions and member preferences |
| 30 days elapsed since last eval | Lazy re-evaluation in the background (configurable) |
| Model version changed | Full re-evaluation, staggered across notes to avoid load spikes |
| Prompt version changed | Same as model version |

**Guardrails:**
- Human tags are never touched.
- AI tags with `approved_by_human=true` (accepted by a human from the queue) are **treated as human tags** and never removed automatically. They may only be removed by a human.
- The re-evaluation job is rate-limited per household (max 100 notes/minute by default).
- Every removal during re-evaluation writes a `tag_audit_log` row with `action='ai_remove_stale'` and the evidence that disappeared.

**The "why did this tag disappear?" question.** Every AI tag row has a full audit trail. Clicking the tag in the note's history view shows when it was added, by which model, with what evidence, and when/why it was removed.

---

### Block 15 — `text` — UI Surfaces

### In the note editor

- Tag chips show a small **AI badge** (`✦`) if `source='ai'` and not approved by a human.
- Hover a chip → tooltip with evidence ("matched 'school fee' in OCR").
- Click a chip → small menu: remove, exclude ("Never here"), exclude wider, edit, copy.
- A subtle **"+ 3 proposed"** chip at the end of the tag row, opening a popover with pending proposals for *this* note.

### In the tag picker (autocomplete)

- Existing tags appear first, sorted by relevance then usage.
- Excluded tags are dimmed with a "excluded on this note" note; selecting one overrides the exclusion (with a small confirm).
- Typing a new tag offers "Create `#newtag`" — with a warning if the style violates household conventions.

### In the sidebar

- Tag list groups by hierarchy when relations exist.
- A **"Review"** entry appears if there are pending proposals.
- A **"Hygiene"** entry (parents only) appears if there are duplicates or unused tags.

### On the Overview dashboard

- Small **Tag Review widget**: count of pending proposals, three highest-confidence proposals inline, a link to `/tags/review`.
- Small **Tag Hygiene widget** (parents): count of duplicate clusters, count of unused tags.

### On `/search`

- A tag facet shows a small **✦** next to AI tags, with a toggle "Include AI tags in facet counts."
- A filter "Tag source: human | ai | any" is available in advanced filters.

### On the Wall

- No tagging UI. A single read-only rotating panel: "Tag review: 12 pending." Not interactive.

### On the Kid Portal

- No tagging. AI tagging runs silently for the child's notes, but the child cannot see the AI/AI distinction — tags simply appear. The parent's review queue catches anything inappropriate.

---

### Block 16 — `text` — Agent Tools

New tools in `app/agent/tools/tagging.py`. All read-only except where noted.

| Tool | Params | Mutates | Notes |
|---|---|---|---|
| `list_tags` | `kind?`, `namespace?`, `include_proposed=false` | N | Enumerates the tag pool |
| `search_tags` | `query`, `limit=10` | N | Fuzzy match against the pool |
| `get_tag_info` | `slug` | N | Returns usage count, hierarchy, exclusions summary |
| `get_note_tags` | `note_id` | N | Returns tags with source, confidence, evidence |
| `list_tag_exclusions` | `note_id?`, `scope?` | N | Who excluded what, where |
| `list_tag_proposals` | `note_id?`, `status='pending'` | N | The queue |
| `propose_tags` | `note_id`, `suggestions[]` | **Y** | Hermes may propose but not auto-apply on behalf of a user |
| `apply_tag` | `note_id`, `slug`, `reason` | **Y** | Applied as `source='ai'`, requires confirmation |
| `remove_tag` | `note_id`, `slug`, `exclude_scope?` | **Y** | Removing an AI tag also records an exclusion |
| `explain_tag` | `note_id`, `slug` | N | Returns the evidence chain |

**The cardinal rule for agent tools:** Hermes may *propose*, but only a human may *approve* an AI tag on a note the human did not explicitly ask to tag. If a user says to Hermes *"tag this note about the Japan trip"*, that is an explicit instruction — Hermes may apply tags directly (through `apply_tag`, with confirmation). If Hermes is running on its own (a scheduled job, an enrichment task), it must use the proposal queue, never direct application.

**The refusal rule.** When Hermes is asked to apply an excluded tag, it must refuse and surface the exclusion:

> "I've noted that you don't want `#travel` on this note. Do you want to override that?"

If the user says yes, Hermes calls `remove_exclusion` (a mutating tool) and then `apply_tag`. Never the other way around — removal of an exclusion is always an explicit, separate act.

---

### Block 17 — `text` — Reference Set Integration

The tag pool is a **Reference Set** (Note B). Key: `tags`. Kind: `derived`. TTL: 5 minutes.

Consequences:
- Hermes validates a tag against the current set before using it (Note B, §9 Freshness Guide).
- When the tag pool changes (a new tag added, a tag merged, a tag retired), the capability snapshot version bumps and Hermes is notified.
- The tag set's change log is the `tag_audit_log`, filtered and projected as `reference_changes`.

**Exclusions are also a reference set** (`tag_exclusions`), scoped to the actor. When Hermes builds a search or proposes a tag, the exclusion set is part of its capability context.

**This is what makes the whole design work at the agent level.** Hermes cannot accidentally propose an excluded tag, because the exclusion is part of the capability snapshot it fetched at session start — and if the user adds a new exclusion mid-conversation, the version bump triggers a refetch, and the next tool call sees the updated set.

---

### Block 18 — `text` — Worked Examples

### Example 1 — The Receipt (Happy Path)

1. User uploads a photo of a Wellcome receipt to a new note.
2. Enrichment runs OCR → "Wellcome", "TOTAL", "HKD 342.50".
3. Tag classifier produces candidates:
   - `#receipt` (0.94) — strong keyword + OCR signal
   - `#wellcome` (0.81) — store name in OCR
   - `#groceries` (0.72) — semantic match to prior grocery notes
   - `#finance` (0.66) — semantic match, weaker
4. Auto-apply threshold is 0.85. `#receipt` is applied silently (source='ai', approved=false).
5. `#wellcome`, `#groceries`, `#finance` are queued as proposals.
6. User opens the note, sees `#receipt` with the AI badge, and a "+3 proposed" chip.
7. Clicks the chip, reviews evidence, accepts `#groceries`, rejects `#wellcome`, rejects `#finance`.
8. Rejections are recorded at note scope. The prompt hint from Block 8 appears but the user clicks away.
9. Over the next month, the user rejects `#wellcome` on three more receipts. The system proposes widening the exclusion to `note_type='receipt'`. The user accepts.
10. From now on, the AI never proposes `#wellcome` on any receipt. But it may still propose it on, say, a coupon from Wellcome — the exclusion is type-scoped, not household-scoped.

### Example 2 — The Removed Tag (The Key Requirement)

1. A note about a family holiday has `#travel`, `#japan-2027` (both human), and `#family-time` (AI, 0.72).
2. The user removes `#family-time` from this note.
3. Toast: *"Noted. Never suggest `#family-time` on this note. [Wider…]"*
4. User clicks `Wider…`, selects "Everywhere".
5. A household-scope exclusion is created. `#family-time` is now banned globally.
6. Thirty days later, a different note about a holiday triggers the classifier. `#family-time` is in the candidate list from the model — but the exclusion filter removes it before it ever reaches the auto-apply or proposal stage.
7. If a user tries to add `#family-time` manually, the picker shows it dimmed with "you excluded this — undo?" A single tap revokes the household exclusion.
8. Hermes, in a subsequent session, receives an updated capability snapshot with the new exclusion. If a user asks Hermes *"tag this holiday note"*, Hermes does not propose `#family-time` and will say so if asked why.

### Example 3 — The Duplicate Cleanup

1. Over a year, the household has accumulated `#travel` (48 uses), `#trip` (12), `#vacation` (7), `#holiday` (4).
2. The Hygiene page shows a cluster with suggested target `#travel`.
3. The parent clicks Preview, sees all 23 affected notes.
4. Confirms. The merge runs:
   - All `note_tags` rows pointing to the three losers are repointed to `#travel`.
   - The losers get `canonical_slug='travel'`, `retired_at=now()`.
   - `tag_merges` row written.
   - One notification: *"Merged `#trip`, `#vacation`, `#holiday` into `#travel` — 23 notes updated."*
5. Any old search for `#trip` still works — the search layer canonicalizes to `#travel`.
6. Hermes's next capability fetch sees the retired tags and never proposes them again.

---

### Block 19 — `text` — Phase Placement & Acceptance

**Phase 2 (initial tagging):**
- Schema migration (Block 5).
- Backfill `note_tags.source='human'` for all existing rows.
- Tag classifier service with confidence bands and evidence.
- Auto-apply and proposal queue.
- In-note UI: AI badge, evidence tooltip, "+N proposed" chip.
- `/tags/review` page with per-proposal and basic bulk actions.
- Exclusion system at note scope, with the toast and the "Wider…" menu.
- Agent tools: `list_tags`, `search_tags`, `get_note_tags`, `explain_tag`, `propose_tags`, `apply_tag`, `remove_tag`.

**Phase 3 (hygiene):**
- `/settings/tags/hygiene` page.
- Duplicate detection, merge, and redirect.
- Hierarchy suggestion and approval.
- Unused tag retirement.
- Feedback loop (style profile, member preferences).
- New-tag proposal cool-down and expiry.
- Exclusions at all four scopes, with auto-widen proposal.
- `list_tag_exclusions`, `list_tag_proposals` agent tools.
- Reference Set integration (tag pool + exclusions as reference sets).

**Phase 4:**
- Auto-accept rules per tag.
- Swap proposals when budget is full.
- Trust decay for unused AI tags (off by default).
- Cross-household tag pool sharing.
- Tag hierarchy import/export.

**Acceptance (Phase 2):**
- [ ] A new note with a photo of a receipt gets `#receipt` auto-applied within 60 s of enrichment completing.
- [ ] The `#receipt` chip shows the AI badge and an evidence tooltip that names the specific OCR text.
- [ ] Removing `#receipt` from the note produces a toast and records a note-scope exclusion.
- [ ] Re-running enrichment on the same note does not re-add `#receipt`.
- [ ] A new note about a Wellcome receipt does **not** get `#receipt` proposed if the exclusion was widened to `note_type='receipt'`.
- [ ] Human tags are never removed by any AI process. (Test: add `#travel` by hand, run re-evaluation 10 times, confirm `#travel` survives.)
- [ ] AI tags with `approved_by_human=true` are never removed by re-evaluation.
- [ ] The proposal queue shows evidence for every proposal.
- [ ] The AI tag budget (5 by default) is enforced: a note with 9 candidates receives at most 5.
- [ ] `propose_tags` and `apply_tag` return correct data via `/internal/agent/tools`, and `apply_tag` for an excluded tag returns `error_code='tag_excluded'`.
- [ ] The capability snapshot version bumps within 60 s of any tag pool change (a tag added, merged, or retired).
- [ ] Hermes, mid-conversation, correctly picks up a newly created exclusion without a session restart.

**Acceptance (Phase 3):**
- [ ] The Hygiene page detects a hand-planted duplicate cluster and proposes a merge.
- [ ] Merging preserves all note associations and makes old searches for the loser tag still work.
- [ ] The style profile after 100 human tags correctly predicts case and separator, and AI proposals that violate it are auto-rejected.
- [ ] Auto-widening proposal fires after 3 identical removals within 30 days.
- [ ] A retired tag never appears in the AI candidate pool.

---

### Block 20 — `text` — Design Notes for the Coding Agent

A few things that are easy to get wrong and expensive to fix:

1. **The exclusion check happens before the model is ever called, whenever possible.** If a note's exclusion set is fully known, pass it as a negative constraint in the prompt *and* filter the model's output. Belt and suspenders. The model should never see a tag it cannot propose.

2. **Never delete a `note_tags` row on AI removal — soft-mark it.** The audit trail is what lets users trust the system. A tag that disappears must have a visible "why."

3. **The evidence object must be concrete.** "Semantic match 0.71" alone is not evidence. Point at a specific string, a specific block, a specific OCR line. The user's ability to verify in two seconds is the entire trust mechanism.

4. **Confidence is calibrated, not raw LLM probability.** The LLM's own confidence numbers are poorly calibrated. Run a small calibration layer (Platt scaling or an isotonic regression on a labelled set of historical proposals) so that a 0.85 from the system really means ~85% likely to be accepted. This is a Phase 3 refinement but design for it now — store the raw and the calibrated score.

5. **The tag pool sent to the model must be pruned.** Top 200 by usage, plus the tags already on this note, plus their direct relations. Sending 5,000 tags wastes tokens and degrades quality.

6. **Never let the AI propose a tag that duplicates a facet.** If `owner_member_id=emma`, the model must not propose `#emma`. Add this as an explicit negative constraint in the prompt and as a post-filter. Facets and tags are different things; conflating them is how tag lists become redundant noise.

7. **The `note_type='receipt'` exclusion must be checked against the *current* type, not the type at exclusion time.** A note that changes type inherits the new type's exclusions. This is a subtle bug that will bite if not designed for.

8. **Batch jobs must be idempotent and rate-limited.** Re-evaluation runs on a schedule and must be safe to run twice, and must never exceed the household's configured notes-per-minute.

9. **Human interaction with an AI tag is a signal.** If the user clicks the tag in search, filters by it, opens a note through it, or edits the note after seeing it, that is a positive signal. Feed it back into the calibrated confidence. This is how the system learns.

10. **The style profile must be conservative.** It should not propose a hypothesis about style until it has at least ~30 observations, and it should update slowly (exponential moving average) so that a single unusual week does not change the AI's behavior.

11. **Retired and merged tags must resolve in every query path.** Search, filter, reference set, agent tool, URL. If `#trip` was merged into `#travel`, then `/search?tag=trip` must return the `#travel` results. This is a redirect table, treated like URL redirects in a web framework — miss one path and old bookmarks break.

12. **The `propose_tags` tool exists for one reason: to let Hermes surface candidates in a conversation without changing state.** It is a read-only-in-effect tool even though it writes a proposal row. It must never auto-apply. If the LLM is ever in a position where calling `propose_tags` could lead to an unwanted tag being applied, the bug is in the approval flow, not in the proposal.

---

### Block 21 — `text` — The Core Insight, Stated Once

Most tagging systems ask: *"What tags should we add?"*

This system asks: *"What tags should we add, and with what authority, and what is the evidence, and who can override it, and how does the system remember being overridden?"*

The first question leads to tag entropy. The second leads to a small, trustworthy, self-correcting vocabulary that stays useful for years.

The four rules that make it work:
1. **Human tags are sacred.**
2. **AI tags carry evidence and confidence.**
3. **Removals are permanent and scoped.**
4. **The pool grows slowly and shrinks deliberately.**

Everything in this note serves those four rules.

---

**End of Note D.**
`status='active'` · `pinned=false` · `tags=['tags','agent','governance','classification','v1.1']` · `visibility='parents'`