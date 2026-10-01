export type Actor = {
  member_id: string;
  household_id: string;
  display_name: string;
  role: "parent" | "child" | "guest" | "device";
  timezone: string;
  locale: string;
  scopes: string[];
};

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