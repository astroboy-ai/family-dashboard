export type Actor = {
  member_id: string;
  household_id: string;
  display_name: string;
  role: "parent" | "child" | "guest" | "device";
  timezone: string;
  locale: string;
  scopes: string[];
};

export type LoginMember = {
  id: string;
  display_name: string;
  avatar: string | null;
  has_pin: boolean;
};

export type Tag = {
  id: string;
  name: string;
  slug: string;
  color: string | null;
  kind: string;
};

export type TagProposal = {
  id: string;
  note_id: string;
  tag_id: string | null;
  proposed_slug: string;
  proposed_kind: string;
  proposed_namespace: string | null;
  confidence: number;
  evidence: Record<string, unknown>;
  model: string;
  status: string;
  created_at: string;
};

export type GraphNode = {
  id: string;
  type: string;
  label: string;
  note_type: string | null;
  pinned: boolean;
  tags: string[];
  extra: Record<string, unknown>;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  relation_type: string | null;
};

export type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  meta: { node_count: number; edge_count: number; truncated: boolean; generated_at: string };
};

export type GraphView = {
  id: string;
  name: string;
  description: string;
  kind: string;
  config: {
    scope?: string;
    node_types?: string[];
    edge_types?: string[];
    filters?: Record<string, unknown>;
    layout?: string;
    colors?: Record<string, string>;
    cluster_by?: string | null;
  };
  is_shared: boolean;
  order_index: number;
  created_at: string;
  updated_at: string;
};

export type GraphViewList = {
  items: GraphView[];
  total: number;
};

/**
 * An imported Archify artifact — a self-contained HTML/PNG/SVG/JSON produced
 * outside FamilyOS and displayed in a sandboxed iframe. Distinct from a
 * GraphView: a view is a config FamilyOS renders itself, an artifact is opaque
 * content it only shows.
 */
export type GraphArtifact = {
  id: string;
  name: string;
  description: string;
  kind: string;
  media_asset_id: string | null;
  source: string;
  size_bytes: number;
  meta: Record<string, unknown>;
  order_index: number;
  created_at: string;
  updated_at: string;
};

export type GraphArtifactList = {
  items: GraphArtifact[];
  total: number;
};

export type NoteBlock = {
  id: string;
  note_id: string;
  order_index: number;
  type: string;
  text_content: string | null;
  media_asset_id: string | null;
  thumb_media_id: string | null;
  data: Record<string, unknown>;
  caption: string | null;
  ai_description: string | null;
  ocr_text: string | null;
  transcript: string | null;
  expires_at: string | null;
  importance: number;
  created_at: string;
  updated_at: string;
};

export type Note = {
  id: string;
  household_id: string;
  title: string | null;
  type: string;
  status: string;
  summary: string | null;
  ai_summary: string | null;
  created_by: string | null;
  owner_member_id: string | null;
  visibility: string;
  pinned: boolean;
  occurred_at: string | null;
  expires_at: string | null;
  location: Record<string, unknown> | null;
  parent_note_id: string | null;
  extra: Record<string, unknown>;
  embedding_status: string;
  created_at: string;
  updated_at: string;
  blocks: NoteBlock[];
  tags: Tag[];
};

export type NoteList = {
  items: Note[];
  limit: number;
  offset: number;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Raised when the session cannot be recovered. The UI shows a non-blocking
 * prompt (copy work / go to login) instead of redirecting, so unsaved input is
 * never thrown away. */
export class SessionExpiredError extends ApiError {
  constructor() {
    super("Session expired", 401, "session_expired");
    this.name = "SessionExpiredError";
  }
}

type SessionExpiredListener = () => void;
const sessionExpiredListeners = new Set<SessionExpiredListener>();

/** Subscribe to "session could not be refreshed" events. Returns an unsubscribe. */
export function onSessionExpired(listener: SessionExpiredListener): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

function notifySessionExpired(): void {
  sessionExpiredListeners.forEach((listener) => listener());
}

/**
 * Endpoints that must never trigger a silent refresh.
 *
 * These are the ones that *establish* or *destroy* a session: retrying them
 * after a 401 would either loop (refresh calling itself) or mask a genuine bad
 * credential behind a pointless round-trip. Everything else — including
 * `/auth/me`, which is what the app shell calls on every page load — must be
 * retried, otherwise an access token that simply aged out (15 min) looks like a
 * dead session and the user gets bounced to the login screen mid-task.
 */
const NO_REFRESH_PATHS = [
  "/auth/refresh",
  "/auth/logout",
  "/auth/pin-login",
  "/auth/login",
  "/auth/setup",
  "/auth/setup-status",
];

function shouldAttemptRefresh(path: string): boolean {
  return !NO_REFRESH_PATHS.some((prefix) => path.startsWith(prefix));
}

/** One refresh in flight at a time: a burst of 401s must not fire N rotations,
 * which would look like token replay and revoke the chain.
 *
 * The promise is also kept for a short grace period after it settles, because a
 * cross-tab broadcast arrives asynchronously: without the grace window a second
 * tab can fire its own rotation microseconds after the first and have the whole
 * chain revoked as a replay. */
let refreshInFlight: Promise<boolean> | null = null;
let refreshSettledAt = 0;
const REFRESH_GRACE_MS = 2000;

const REFRESH_BROADCAST_KEY = "familyos-refresh";

function broadcastRefresh(success: boolean): void {
  try {
    window.localStorage.setItem(
      REFRESH_BROADCAST_KEY,
      JSON.stringify({ at: Date.now(), success }),
    );
  } catch {
    // Private-mode / storage-disabled: single-tab behaviour still works.
  }
}

/** Did another tab refresh the session moments ago? Then reuse that result. */
function recentlyRefreshedElsewhere(): boolean | null {
  try {
    const raw = window.localStorage.getItem(REFRESH_BROADCAST_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { at?: number; success?: boolean };
    if (typeof parsed.at !== "number") return null;
    if (Date.now() - parsed.at > REFRESH_GRACE_MS) return null;
    return parsed.success === true;
  } catch {
    return null;
  }
}

async function refreshSession(): Promise<boolean> {
  const fromOtherTab = recentlyRefreshedElsewhere();
  if (fromOtherTab !== null) return fromOtherTab;

  if (!refreshInFlight) {
    refreshInFlight = fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    })
      .then((response) => {
        broadcastRefresh(response.ok);
        return response.ok;
      })
      .catch(() => false)
      .finally(() => {
        refreshSettledAt = Date.now();
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

/** True while a refresh is happening, or finished within the grace window. */
function refreshJustHappened(): boolean {
  return refreshInFlight !== null || Date.now() - refreshSettledAt < REFRESH_GRACE_MS;
}

async function decodeResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { error?: { code?: string; message?: string }; detail?: string }
      | null;
    throw new ApiError(
      body?.error?.message ?? body?.detail ?? `Request failed (${response.status})`,
      response.status,
      body?.error?.code,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * Fetch wrapper for the app's own API.
 *
 * On a 401 it attempts exactly one silent refresh and replays the request; if
 * that also fails the session is gone and a SessionExpiredError is thrown after
 * notifying listeners, so the UI can offer to copy unsaved work before the user
 * navigates to login.
 *
 * A 401 whose body says the session was *reused* is never retried: the backend
 * has already revoked the whole chain, so a retry is guaranteed to fail and
 * would only add noise. We surface it as a dead session immediately.
 */
export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  // Only default to JSON for a plain body. A FormData body must keep the
  // browser-generated multipart Content-Type (it carries the boundary), so
  // setting application/json here would make the server fail to parse it.
  if (init.body && !headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const send = () =>
    fetch(`/api${path}`, {
      ...init,
      headers,
      credentials: "include",
    });

  let response = await send();

  if (response.status === 401 && shouldAttemptRefresh(path)) {
    const refreshed = await refreshSession();
    if (refreshed) {
      response = await send();
    }
    if (!response.ok && response.status === 401) {
      const dead = await isSessionDead(response);
      // A second 401 right after a *successful* refresh is not a dead session:
      // the refreshed cookies may not have landed yet (proxy/CDN buffering) or
      // the request raced the rotation. Give it one more beat before giving up.
      if (!dead && refreshed && refreshJustHappened()) {
        response = await send();
      }
      if (!response.ok && response.status === 401) {
        notifySessionExpired();
        throw new SessionExpiredError();
      }
    }
  }

  return decodeResponse<T>(response);
}

/** Does this 401 body indicate the refresh chain is gone for good? */
async function isSessionDead(response: Response): Promise<boolean> {
  const body = (await response.clone().json().catch(() => null)) as
    | { error?: { code?: string } }
    | null;
  const code = body?.error?.code;
  return code === "session_reused" || code === "session_revoked" || code === "invalid_session";
}

export function getActor(): Promise<Actor> {
  return apiRequest<Actor>("/auth/me");
}

export type MemberPreferences = {
  calendar_theme: string | null;
  calendar_stickers: string[];
  extra: Record<string, unknown>;
};

export function getMyPreferences(): Promise<MemberPreferences> {
  return apiRequest<MemberPreferences>("/auth/me/preferences");
}

export function updateMyPreferences(
  input: Partial<Pick<MemberPreferences, "calendar_theme" | "calendar_stickers" | "extra">>,
): Promise<MemberPreferences> {
  return apiRequest<MemberPreferences>("/auth/me/preferences", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function listLoginMembers(): Promise<LoginMember[]> {
  const response = await apiRequest<{ items: LoginMember[] }>("/auth/members");
  return response.items;
}

export function signInWithPin(memberId: string, pin: string): Promise<{ member_id: string; role: string }> {
  return apiRequest<{ member_id: string; role: string }>("/auth/pin-login", {
    method: "POST",
    body: JSON.stringify({ member_id: memberId, pin }),
  });
}

export function getSetupStatus(): Promise<{ available: boolean }> {
  return apiRequest<{ available: boolean }>("/auth/setup-status");
}

export function completeSetup(input: {
  household_name: string;
  timezone: string;
  locale: string;
  week_starts_on: string;
  display_name: string;
  email: string;
  password: string;
  pin: string;
  ai_provider: "none" | "ollama" | "openai";
}): Promise<{ member_id: string; role: string }> {
  return apiRequest<{ member_id: string; role: string }>("/auth/setup", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listNotes(params: URLSearchParams = new URLSearchParams()): Promise<NoteList> {
  const query = params.toString();
  return apiRequest<NoteList>(`/notes${query ? `?${query}` : ""}`);
}

export function searchNotes(params: URLSearchParams = new URLSearchParams()): Promise<NoteList> {
  const query = params.toString();
  return apiRequest<NoteList>(`/search${query ? `?${query}` : ""}`);
}

export function getNote(noteId: string): Promise<Note> {
  return apiRequest<Note>(`/notes/${encodeURIComponent(noteId)}`);
}

export function createNote(input: {
  title?: string;
  type?: string;
  summary?: string;
  visibility?: string;
  blocks?: Array<{ type: string; text_content?: string }>;
  tags?: string[];
}): Promise<Note> {
  return apiRequest<Note>("/notes", { method: "POST", body: JSON.stringify(input) });
}

export function createTextBlock(noteId: string, text: string): Promise<NoteBlock> {
  return apiRequest<NoteBlock>(`/notes/${encodeURIComponent(noteId)}/blocks`, {
    method: "POST",
    body: JSON.stringify({ type: "text", text_content: text }),
  });
}

export function createBlock(
  noteId: string,
  input: { type: string; text_content?: string; data?: Record<string, unknown> },
): Promise<NoteBlock> {
  return apiRequest<NoteBlock>(`/notes/${encodeURIComponent(noteId)}/blocks`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function createDrawingBlock(
  noteId: string,
  data: Record<string, unknown> = {
    theme: "chalkboard_green",
    canvas: { width: 4000, height: 3000, unit: "px" },
    viewport: { x: 0, y: 0, zoom: 1, rotation: 0 },
    grid: { mode: "dot", spacing: 40, visible: false, snap: false },
    layers: [
      { id: "bg", name: "Background", visible: true, locked: true },
      { id: "main", name: "Main", visible: true, locked: false },
      { id: "anno", name: "Annotations", visible: true, locked: false },
    ],
    active_layer: "main",
    strokes: [],
    shapes: [],
    texts: [],
    bookmarks: [],
    meta: { stroke_count: 0, shape_count: 0, text_count: 0, size_bytes: 0 },
  },
  textContent: string = "New whiteboard",
): Promise<NoteBlock> {
  return apiRequest<NoteBlock>(`/notes/${encodeURIComponent(noteId)}/blocks`, {
    method: "POST",
    body: JSON.stringify({
      type: "drawing",
      text_content: textContent,
      data,
    }),
  });
}

export function updateDrawingBlock(
  blockId: string,
  data: Record<string, unknown>,
  textContent?: string,
): Promise<NoteBlock> {
  return apiRequest<NoteBlock>(`/blocks/${encodeURIComponent(blockId)}`, {
    method: "PATCH",
    body: JSON.stringify({
      data,
      text_content: textContent,
    }),
  });
}

/** Persist a new block order. ``blockIds`` must list every block exactly once. */
export function reorderBlocks(noteId: string, blockIds: string[]): Promise<NoteBlock[]> {
  return apiRequest<NoteBlock[]>(`/notes/${encodeURIComponent(noteId)}/reorder`, {
    method: "POST",
    body: JSON.stringify({ block_ids: blockIds }),
  });
}

export function addTagToNote(noteId: string, name: string): Promise<Tag[]> {
  return apiRequest<Tag[]>(`/notes/${encodeURIComponent(noteId)}/tags`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function removeTagFromNote(noteId: string, slug: string): Promise<Tag[]> {
  return apiRequest<Tag[]>(`/notes/${encodeURIComponent(noteId)}/tags/${encodeURIComponent(slug)}`, {
    method: "DELETE",
  });
}

export function signIn(email: string, password: string): Promise<{ member_id: string; role: string }> {
  return apiRequest<{ member_id: string; role: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function signOut(): Promise<void> {
  await apiRequest<void>("/auth/logout", { method: "POST" });
}

export function patchNote(noteId: string, input: Partial<Pick<Note, "title" | "summary" | "status" | "visibility" | "pinned">>): Promise<Note> {
  return apiRequest<Note>(`/notes/${encodeURIComponent(noteId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function patchTextBlock(blockId: string, text: string): Promise<NoteBlock> {
  return apiRequest<NoteBlock>(`/blocks/${encodeURIComponent(blockId)}`, {
    method: "PATCH",
    body: JSON.stringify({ text_content: text }),
  });
}

export function listTagProposals(
  options: { noteId?: string; status?: "pending" | "accepted" | "rejected" | "all" } = {},
): Promise<TagProposal[]> {
  const params = new URLSearchParams();
  if (options.noteId) params.set("note_id", options.noteId);
  if (options.status) params.set("status", options.status);
  const query = params.toString();
  return apiRequest<TagProposal[]>(`/tags/proposals${query ? `?${query}` : ""}`);
}

export function decideTagProposal(proposalId: string, accepted: boolean): Promise<TagProposal> {
  return apiRequest<TagProposal>(`/tags/proposals/${encodeURIComponent(proposalId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ accepted }),
  });
}

export function getGraph(scope = "all", limit = 2000): Promise<GraphData> {
  const params = new URLSearchParams({ scope, limit: String(limit) });
  return apiRequest<GraphData>(`/graph?${params.toString()}`);
}

export function listGraphViews(): Promise<GraphViewList> {
  return apiRequest<GraphViewList>("/graph/views");
}

export function createGraphView(input: {
  name: string;
  description?: string;
  kind?: string;
  config?: GraphView["config"];
  is_shared?: boolean;
}): Promise<GraphView> {
  return apiRequest<GraphView>("/graph/views", { method: "POST", body: JSON.stringify(input) });
}

export function updateGraphView(
  id: string,
  input: Partial<Pick<GraphView, "name" | "description" | "kind" | "config" | "is_shared" | "order_index">>,
): Promise<GraphView> {
  return apiRequest<GraphView>(`/graph/views/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}

export function deleteGraphView(id: string): Promise<void> {
  return apiRequest<void>(`/graph/views/${id}`, { method: "DELETE" });
}

// ── Archify artifacts (imported files) ────────────────────────────────────────

export function listGraphArtifacts(): Promise<GraphArtifactList> {
  return apiRequest<GraphArtifactList>("/graph/artifacts");
}

/**
 * Import an Archify file.
 *
 * Multipart, not JSON: an interactive Archify HTML can run to several MB and
 * base64 in a JSON body would inflate it by a third. The endpoint streams the
 * file straight to storage.
 */
export function uploadGraphArtifact(input: {
  file: File;
  name?: string;
  description?: string;
  kind?: string;
  source?: string;
}): Promise<GraphArtifact> {
  const form = new FormData();
  form.set("file", input.file);
  if (input.name) form.set("name", input.name);
  if (input.description) form.set("description", input.description);
  if (input.kind) form.set("kind", input.kind);
  if (input.source) form.set("source", input.source);
  // No Content-Type header: the browser must set the multipart boundary itself.
  return apiRequest<GraphArtifact>("/graph/artifacts", { method: "POST", body: form });
}

export function updateGraphArtifact(
  id: string,
  input: { name?: string; description?: string; order_index?: number },
): Promise<GraphArtifact> {
  return apiRequest<GraphArtifact>(`/graph/artifacts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteGraphArtifact(id: string): Promise<void> {
  return apiRequest<void>(`/graph/artifacts/${id}`, { method: "DELETE" });
}

/** The URL the sandboxed viewer loads an artifact's bytes from. */
export function graphArtifactFileUrl(artifact: GraphArtifact): string {
  return `/api/media/${encodeURIComponent(String(artifact.media_asset_id ?? ""))}/download`;
}

export type AdminSettings = {
  enabled: boolean;
  base_url: string;
  api_key_set: boolean;
  embedding_model: string;
  embedding_dim: number;
  embedding_batch_size: number;
  llm_model: string;
  vision_model: string;
  tagging_model: string;
  effective_tagging_model: string;
  azure_endpoint: string;
  azure_api_key_set: boolean;
  azure_api_version: string;
  azure_model: string;
};

export type GatewayModel = {
  id: string;
  mode: string;
  max_input_tokens: number | null;
  max_output_tokens: number | null;
};

export type GatewayModelsResponse = {
  ok: boolean;
  error?: string;
  base_url: string;
  groups: Record<string, GatewayModel[]>;
  count: number;
};

/** Live model catalog from the gateway, grouped by capability (chat/embedding/…). */
export function listGatewayModels(): Promise<GatewayModelsResponse> {
  return apiRequest<GatewayModelsResponse>("/admin/models");
}

export type StorageSettings = {
  public_endpoint: string;
  bucket: string;
  region: string;
  browser_reachable: boolean;
};

export type AdminSettingsResponse = {
  ai: AdminSettings;
  storage?: StorageSettings;
  household?: {
    name: string;
    timezone: string;
    locale: string;
    week_starts_on: string;
  };
  changed?: string[];
  reembed_required?: boolean;
  reembed_hint?: string;
};

export function getAdminSettings(): Promise<AdminSettingsResponse> {
  return apiRequest<AdminSettingsResponse>("/admin/settings");
}

export type AdminSettingsPatch = Partial<Omit<AdminSettings, "api_key_set" | "azure_api_key_set"> & { api_key?: string; azure_api_key?: string }> & {
  storage?: Partial<Omit<StorageSettings, "browser_reachable">>;
};

export function patchAdminSettings(input: AdminSettingsPatch): Promise<AdminSettingsResponse> {
  return apiRequest<AdminSettingsResponse>("/admin/settings", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export type StorageTestResult = {
  ok: boolean;
  public_endpoint: string;
  bucket: string;
  browser_reachable: boolean;
  upload_url: string | null;
  probe_key: string | null;
  internal_ok?: boolean;
  warnings: string[];
};

/** Ask the backend to sign a probe URL against the configured upload origin. */
export function testStorageSettings(): Promise<StorageTestResult> {
  return apiRequest<StorageTestResult>("/admin/storage/test", { method: "POST" });
}

export function reembedAll(): Promise<{ queued: number }> {
  return apiRequest<{ queued: number }>("/admin/reembed", { method: "POST" });
}

export type MediaUploadResponse = {
  asset_id: string;
  upload_url: string | null;
  fields: Record<string, string>;
  deduplicated: boolean;
};

export function presignMediaUpload(input: {
  filename: string;
  mime: string;
  size: number;
  sha256: string;
}): Promise<MediaUploadResponse> {
  return apiRequest<MediaUploadResponse>("/media/presign", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function completeMediaUpload(assetId: string): Promise<{ status: string; queued: boolean }> {
  return apiRequest<{ status: string; queued: boolean }>(`/media/${encodeURIComponent(assetId)}/complete`, {
    method: "POST",
  });
}

export function enqueueMediaEnrich(assetId: string): Promise<{ queued: boolean }> {
  return apiRequest<{ queued: boolean }>(`/media/${encodeURIComponent(assetId)}/enrich`, {
    method: "POST",
  });
}

/** Update a block's structured payload (checkbox, date, table rows, …). */
export function patchBlock(
  blockId: string,
  input: { text_content?: string; data?: Record<string, unknown>; caption?: string },
): Promise<NoteBlock> {
  return apiRequest<NoteBlock>(`/blocks/${encodeURIComponent(blockId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteBlock(blockId: string): Promise<void> {
  return apiRequest<void>(`/blocks/${encodeURIComponent(blockId)}`, { method: "DELETE" });
}

async function sha256Hex(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Upload a file and return the media asset id.
 *
 * Prefers the presigned direct-to-S3 PUT (no extra hop). Falls back to relaying
 * the bytes through the API when the browser cannot reach the S3 endpoint —
 * which is the normal case until a public tunnel hostname is configured for
 * storage, and the cause of the earlier "failed to fetch" on upload.
 */
export async function uploadFile(file: File): Promise<string> {
  const sha256 = await sha256Hex(file);
  const presigned = await presignMediaUpload({
    filename: file.name,
    mime: file.type || "application/octet-stream",
    size: file.size,
    sha256,
  });

  if (presigned.upload_url) {
    try {
      const put = await fetch(presigned.upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      if (put.ok) {
        await completeMediaUpload(presigned.asset_id);
        return presigned.asset_id;
      }
    } catch {
      // Unreachable S3 origin (offline, mixed content, DNS) — fall through to
      // the relay endpoint rather than failing the upload.
    }
  }

  await apiRequest<{ status: string }>(`/media/${encodeURIComponent(presigned.asset_id)}/content`, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  return presigned.asset_id;
}

// ── Calendar ──────────────────────────────────────────────────────────────────

export type CalendarAccount = {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
};

export type Calendar = {
  id: string;
  account_id: string;
  google_calendar_id: string;
  name: string;
  description: string | null;
  color: string | null;
  theme: string | null;
  is_primary: boolean;
  is_visible: boolean;
  /** True once a member renamed or recoloured it; the sync stops overwriting. */
  is_customized: boolean;
  last_synced_at: string | null;
};

export type CalendarEvent = {
  id: string;
  calendar_id: string;
  google_event_id: string;
  title: string;
  description: string | null;
  start_time: string;
  end_time: string;
  all_day: boolean;
  location: string | null;
  /** RRULE strings (RFC 5545), e.g. ["FREQ=WEEKLY;INTERVAL=1"]. */
  recurrence: string[] | null;
  status: string;
  html_link: string | null;
};

export type CalendarPermission = {
  id: string;
  calendar_id: string;
  member_id: string;
  level: "view" | "edit" | "manage" | "admin";
  /** Denormalised by the API so the UI never shows a raw UUID. */
  member_name: string | null;
  calendar_name: string | null;
};

export type CalendarView = {
  id: string;
  name: string;
  calendar_ids: string[];
  layout: "month" | "week" | "day" | "agenda";
  is_default: boolean;
};

export function listCalendarAccounts(): Promise<CalendarAccount[]> {
  return apiRequest<CalendarAccount[]>("/calendar/accounts");
}

export function listCalendars(includeHidden = false): Promise<Calendar[]> {
  const query = includeHidden ? "?include_hidden=true" : "";
  return apiRequest<Calendar[]>(`/calendar/calendars${query}`);
}

export function updateCalendar(
  calendarId: string,
  input: Partial<{
    name: string;
    color: string;
    theme: string;
    is_visible: boolean;
  }>,
): Promise<Calendar> {
  return apiRequest<Calendar>(`/calendar/calendars/${encodeURIComponent(calendarId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function listCalendarEvents(params?: {
  calendar_id?: string;
  start?: string;
  end?: string;
  limit?: number;
}): Promise<CalendarEvent[]> {
  const query = new URLSearchParams();
  if (params?.calendar_id) query.set("calendar_id", params.calendar_id);
  if (params?.start) query.set("start", params.start);
  if (params?.end) query.set("end", params.end);
  if (params?.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return apiRequest<CalendarEvent[]>(`/calendar/events${qs ? `?${qs}` : ""}`);
}

export function createCalendarEvent(input: {
  calendar_id: string;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  all_day?: boolean;
  location?: string;
  recurrence?: string[];
}): Promise<CalendarEvent> {
  return apiRequest<CalendarEvent>("/calendar/events", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateCalendarEvent(
  eventId: string,
  input: Partial<{
    title: string;
    description: string;
    start_time: string;
    end_time: string;
    all_day: boolean;
    location: string;
    recurrence: string[];
  }>,
): Promise<CalendarEvent> {
  return apiRequest<CalendarEvent>(`/calendar/events/${encodeURIComponent(eventId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteCalendarEvent(eventId: string): Promise<void> {
  return apiRequest<void>(`/calendar/events/${encodeURIComponent(eventId)}`, { method: "DELETE" });
}

export function syncCalendars(accountId?: string): Promise<{ calendars: number; events: number }> {
  const query = accountId ? `?account_id=${encodeURIComponent(accountId)}` : "";
  return apiRequest<{ calendars: number; events: number }>(`/calendar/sync${query}`, { method: "POST" });
}

export function getCalendarOAuthUrl(): Promise<{ authorize_url: string }> {
  return apiRequest<{ authorize_url: string }>("/calendar/oauth/url");
}

export function calendarOAuthCallback(code: string, state: string): Promise<CalendarAccount> {
  const params = new URLSearchParams({ code, state });
  return apiRequest<CalendarAccount>(`/calendar/oauth/callback?${params.toString()}`);
}

export function listCalendarPermissions(calendarId?: string): Promise<CalendarPermission[]> {
  const query = calendarId ? `?calendar_id=${encodeURIComponent(calendarId)}` : "";
  return apiRequest<CalendarPermission[]>(`/calendar/permissions${query}`);
}

export function createCalendarPermission(
  calendarId: string,
  memberId: string,
  level: "view" | "edit" | "manage" | "admin",
): Promise<CalendarPermission> {
  return apiRequest<CalendarPermission>(
    `/calendar/permissions?calendar_id=${encodeURIComponent(calendarId)}`,
    { method: "POST", body: JSON.stringify({ member_id: memberId, level }) },
  );
}

export function createCalendarPermissionsBulk(input: {
  member_ids: string[];
  calendar_ids: string[];
  level: "view" | "edit" | "manage" | "admin";
}): Promise<CalendarPermission[]> {
  return apiRequest<CalendarPermission[]>("/calendar/permissions/bulk", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteCalendarPermission(permissionId: string): Promise<void> {
  return apiRequest<void>(`/calendar/permissions/${encodeURIComponent(permissionId)}`, { method: "DELETE" });
}

export function listCalendarViews(): Promise<CalendarView[]> {
  return apiRequest<CalendarView[]>("/calendar/views");
}

export function createCalendarView(input: {
  name: string;
  calendar_ids: string[];
  layout: "month" | "week" | "day" | "agenda";
  is_default?: boolean;
}): Promise<CalendarView> {
  return apiRequest<CalendarView>("/calendar/views", { method: "POST", body: JSON.stringify(input) });
}

export function updateCalendarView(
  viewId: string,
  input: Partial<{ name: string; calendar_ids: string[]; layout: string; is_default: boolean }>,
): Promise<CalendarView> {
  return apiRequest<CalendarView>(`/calendar/views/${encodeURIComponent(viewId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteCalendarView(viewId: string): Promise<void> {
  return apiRequest<void>(`/calendar/views/${encodeURIComponent(viewId)}`, { method: "DELETE" });
}
// ---------------------------------------------------------------------------
// Agent tokens (admin)
// ---------------------------------------------------------------------------

export type AgentToken = {
  id: string;
  label: string;
  scopes: string[];
  member_id: string | null;
  created_at: string;
  expires_at: string | null;
  last_seen_at: string | null;
  revoked_at: string | null;
  is_active: boolean;
  is_expired: boolean;
};

/** The mint response. `token` is present here and never returned again. */
export type AgentTokenCreated = AgentToken & {
  token: string;
  warning: string;
};

export type AgentTokenCreateInput = {
  label: string;
  scopes: string[];
  expires_in_days: number | null;
  member_id?: string | null;
};

export function getAgentTokenScopes(): Promise<Record<string, string>> {
  return apiRequest<Record<string, string>>("/admin/agent-tokens/scopes");
}

export function listAgentTokens(): Promise<AgentToken[]> {
  return apiRequest<AgentToken[]>("/admin/agent-tokens");
}

export function createAgentToken(input: AgentTokenCreateInput): Promise<AgentTokenCreated> {
  return apiRequest<AgentTokenCreated>("/admin/agent-tokens", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function revokeAgentToken(tokenId: string): Promise<{ id: string; revoked: boolean }> {
  return apiRequest<{ id: string; revoked: boolean }>(
    `/admin/agent-tokens/${encodeURIComponent(tokenId)}`,
    { method: "DELETE" },
  );
}

// ── Notifications ────────────────────────────────────────────────────────────

export type Notification = {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  ref_type: string | null;
  ref_id: string | null;
  priority: number;
  scheduled_for: string | null;
  sent_at: string | null;
  read_at: string | null;
  channel: string;
  created_at: string;
};

export function listNotifications(unreadOnly = false, limit = 50): Promise<Notification[]> {
  const params = new URLSearchParams();
  if (unreadOnly) params.set("unread_only", "true");
  params.set("limit", String(limit));
  return apiRequest<Notification[]>(`/notifications?${params.toString()}`);
}

export function getUnreadCount(): Promise<{ count: number }> {
  return apiRequest<{ count: number }>("/notifications/unread-count");
}

export function markNotificationRead(notificationId: string): Promise<Notification> {
  return apiRequest<Notification>(`/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: "PATCH",
  });
}

export function markAllNotificationsRead(): Promise<{ marked: number }> {
  return apiRequest<{ marked: number }>("/notifications/mark-all-read", {
    method: "POST",
  });
}

// ── Dashboards ───────────────────────────────────────────────────────────────

export type Dashboard = {
  id: string;
  name: string;
  description: string | null;
  layout: string;
  is_default: boolean;
  widgets: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
};

export function listDashboards(): Promise<Dashboard[]> {
  return apiRequest<Dashboard[]>("/dashboards");
}

export function createDashboard(input: {
  name: string;
  description?: string;
  layout?: string;
  is_default?: boolean;
  widgets?: Record<string, unknown>[];
}): Promise<Dashboard> {
  return apiRequest<Dashboard>("/dashboards", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getDashboard(id: string): Promise<Dashboard> {
  return apiRequest<Dashboard>(`/dashboards/${encodeURIComponent(id)}`);
}

export function updateDashboard(
  id: string,
  input: Partial<{
    name: string;
    description: string;
    layout: string;
    is_default: boolean;
    widgets: Record<string, unknown>[];
  }>,
): Promise<Dashboard> {
  return apiRequest<Dashboard>(`/dashboards/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteDashboard(id: string): Promise<void> {
  return apiRequest<void>(`/dashboards/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
