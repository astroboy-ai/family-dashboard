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

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  return decodeResponse<T>(response);
}

export function getActor(): Promise<Actor> {
  return apiRequest<Actor>("/auth/me");
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