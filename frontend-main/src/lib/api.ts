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

/** One refresh in flight at a time: a burst of 401s must not fire N rotations,
 * which would look like token replay and revoke the chain. */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
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
 */
export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const send = () =>
    fetch(`/api${path}`, {
      ...init,
      headers,
      credentials: "include",
    });

  let response = await send();

  if (response.status === 401 && !path.startsWith("/auth/")) {
    const refreshed = await refreshSession();
    if (refreshed) {
      response = await send();
    }
    if (!response.ok && response.status === 401) {
      notifySessionExpired();
      throw new SessionExpiredError();
    }
  }

  return decodeResponse<T>(response);
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

export function listTagProposals(noteId?: string): Promise<TagProposal[]> {
  const params = new URLSearchParams();
  if (noteId) params.set("note_id", noteId);
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

export type AdminSettings = {
  enabled: boolean;
  base_url: string;
  api_key_set: boolean;
  embedding_model: string;
  embedding_dim: number;
  embedding_batch_size: number;
  llm_model: string;
  vision_model: string;
};

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

export type AdminSettingsPatch = Partial<Omit<AdminSettings, "api_key_set"> & { api_key?: string }> & {
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