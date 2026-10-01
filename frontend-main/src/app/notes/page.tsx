"use client";

import { Filter, Search, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { NoteRow } from "@/components/note-row";
import { ApiError, listNotes, type Note } from "@/lib/api";
import { usePanelStore } from "@/lib/panel-store";

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("inbox");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const open = usePanelStore((state) => state.open);

  useEffect(() => {
    let active = true;
    setLoading(true);
    listNotes(new URLSearchParams({ limit: "100", ...(status ? { status } : {}) }))
      .then((result) => active && setNotes(result.items))
      .catch((reason: unknown) => active && setError(reason instanceof ApiError && reason.status === 401 ? "Sign in to view notes." : "Unable to load notes."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [status]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return notes;
    return notes.filter((note) => [note.title, note.summary, ...note.tags.map((tag) => tag.name), ...note.blocks.map((block) => block.text_content ?? "")]
      .some((value) => value?.toLowerCase().includes(needle)));
  }, [notes, query]);

  return (
    <div className="page-wrap list-page">
      <section className="page-heading-row">
        <div><p className="eyebrow">KNOWLEDGE BASE</p><h1>Notes</h1><p className="page-subtitle">Your family’s shared record, kept searchable.</p></div>
        <button className="primary-button" onClick={() => open("capture")}>＋ <span>Capture</span></button>
      </section>
      <section className="list-toolbar" aria-label="Note filters">
        <label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter notes on this page" aria-label="Filter notes" /></label>
        <label className="select-field"><Filter size={16} /><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter by status"><option value="inbox">Inbox</option><option value="active">Active</option><option value="done">Done</option><option value="archived">Archived</option><option value="">All statuses</option></select></label>
        <Link className="toolbar-link" href={`/search?q=${encodeURIComponent(query)}`}><SlidersHorizontal size={16} /> Full search</Link>
      </section>
      <section className="list-results" aria-live="polite">
        <div className="results-meta">{loading ? "Loading notes" : `${filtered.length} ${filtered.length === 1 ? "note" : "notes"}`}</div>
        {loading ? <div className="loading-rows"><i /><i /><i /></div> : error ? <div className="inline-state" role="alert">{error}</div> : filtered.length ? <div className="note-list">{filtered.map((note) => <NoteRow note={note} key={note.id} />)}</div> : <div className="empty-state"><span className="empty-mark">N</span><strong>No matching notes</strong><p>Try another filter or capture a new note.</p></div>}
      </section>
    </div>
  );
}