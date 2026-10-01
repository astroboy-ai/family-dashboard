export type Actor = {
  member_id: string;
  household_id: string;
  display_name: string;
  role: "parent" | "child" | "guest" | "device";
  timezone: string;
  locale: string;
  scopes: string[];
};

export type DemoMember = {
  id: string;
  display_name: string;
  role: "parent" | "child" | "guest";
  pin: string;
  avatar: string;
  timezone: string;
  locale: string;
};

export const demoMembers: DemoMember[] = [
  { id: "dad", display_name: "Dad", role: "parent", pin: "1234", avatar: "👨", timezone: "Asia/Hong_Kong", locale: "en" },
  { id: "mum", display_name: "Mum", role: "parent", pin: "4321", avatar: "👩", timezone: "Asia/Hong_Kong", locale: "en" },
  { id: "emma", display_name: "Emma", role: "child", pin: "2468", avatar: "🧒", timezone: "Asia/Hong_Kong", locale: "en" },
  { id: "guest", display_name: "Guest", role: "guest", pin: "0000", avatar: "👶", timezone: "Asia/Hong_Kong", locale: "en" },
];

const DEMO_SESSION_KEY = "familyos-demo-session";

function readDemoSession(): Actor | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(DEMO_SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Actor;
  } catch {
    return null;
  }
}

function writeDemoSession(actor: Actor | null) {
  if (typeof window === "undefined") return;
  if (!actor) {
    window.localStorage.removeItem(DEMO_SESSION_KEY);
    return;
  }
  window.localStorage.setItem(DEMO_SESSION_KEY, JSON.stringify(actor));
}

export type Tag = {
  id: string;
  name: string;
  slug: string;
  color: string | null;
  kind: string;
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
  const demoActor = readDemoSession();
  if (demoActor) return Promise.resolve(demoActor);
  return apiRequest<Actor>("/auth/me");
}

export function demoSignIn(memberId: string, pin: string): Promise<Actor> {
  const member = demoMembers.find((person) => person.id === memberId);
  if (!member) throw new ApiError("Unknown family member", 401, "unknown_member");
  if (member.pin !== pin) throw new ApiError("Incorrect PIN", 401, "invalid_pin");

  const actor: Actor = {
    member_id: member.id,
    household_id: "demo-household",
    display_name: member.display_name,
    role: member.role,
    timezone: member.timezone,
    locale: member.locale,
    scopes: ["notes:read", "notes:write", "search:read", "family:read"],
  };

  writeDemoSession(actor);
  return Promise.resolve(actor);
}

export function listNotes(params: URLSearchParams = new URLSearchParams()): Promise<NoteList> {
  const query = params.toString();
  return apiRequest<NoteList>(`/notes${query ? `?${query}` : ""}`);
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
  if (readDemoSession()) {
    writeDemoSession(null);
    return;
  }
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