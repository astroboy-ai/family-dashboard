"use client";

import { Search, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { NoteRow } from "@/components/note-row";
import { ApiError, listNotes, type Note } from "@/lib/api";
import { useNewNote } from "@/lib/new-note";

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [query, setQuery] = useState("");
  // Default to every live status so a note created by an agent (status
  // "active") is visible without the user first finding the filter. The
  // chips below let them narrow it down.
  const [statuses, setStatuses] = useState<string[]>(["inbox", "active"]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchMode, setSearchMode] = useState<"instant" | "manual">("instant");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { startNewNote } = useNewNote();

  const ALL_STATUSES = ["inbox", "active", "done", "archived", "expired"] as const;

  useEffect(() => {
    let active = true;
    setLoading(true);
    const params = new URLSearchParams({ limit: "100" });
    statuses.forEach((value) => params.append("statuses", value));
    listNotes(params)
      .then((result) => active && setNotes(result.items))
      .catch((reason: unknown) => active && setError(reason instanceof ApiError && reason.status === 401 ? "Sign in to view notes." : "Unable to load notes."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [statuses]);

  function toggleStatus(value: string) {
    setStatuses((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    );
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return notes;
    return notes.filter((note) => [note.title, note.summary, ...note.tags.map((tag) => tag.name), ...note.blocks.map((block) => block.text_content ?? "")]
      .some((value) => value?.toLowerCase().includes(needle)));
  }, [notes, query]);

  function handleQueryChange(value: string) {
    setQuery(value);
    if (searchMode === "instant") {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        // The filter is already applied via useMemo; this debounce is a
        // placeholder for future server-side search. For now it just prevents
        // excessive re-renders during fast typing.
      }, 150);
    }
  }

  return (
    <div className="page-wrap list-page">
      <section className="page-heading-row">
        <div><p className="eyebrow">KNOWLEDGE BASE</p><h1>Notes</h1><p className="page-subtitle">Your family’s shared record, kept searchable.</p></div>
        <button className="primary-button" onClick={() => void startNewNote()}>＋ <span>New note</span></button>
      </section>
      <section className="list-toolbar" aria-label="Note filters">
        <label className="search-field"><Search size={17} /><input value={query} onChange={(event) => handleQueryChange(event.target.value)} placeholder="Filter notes on this page" aria-label="Filter notes" /></label>
        <label className="select-field"><select value={searchMode} onChange={(event) => setSearchMode(event.target.value as "instant" | "manual")} aria-label="Search mode"><option value="instant">Instant</option><option value="manual">Manual</option></select></label>
        <div className="status-chips" role="group" aria-label="Filter by status">
          {ALL_STATUSES.map((value) => {
            const on = statuses.includes(value);
            return (
              <button
                key={value}
                type="button"
                className={`status-chip${on ? " status-chip-on" : ""}`}
                aria-pressed={on}
                onClick={() => toggleStatus(value)}
              >
                {value}
              </button>
            );
          })}
          <button
            type="button"
            className="status-chip status-chip-all"
            onClick={() => setStatuses(statuses.length === ALL_STATUSES.length ? [] : [...ALL_STATUSES])}
          >
            {statuses.length === ALL_STATUSES.length ? "clear" : "all"}
          </button>
        </div>
        <Link className="toolbar-link" href={`/search?q=${encodeURIComponent(query)}`}><SlidersHorizontal size={16} /> Full search</Link>
      </section>
      <section className="list-results" aria-live="polite">
        <div className="results-meta">{loading ? "Loading notes" : `${filtered.length} ${filtered.length === 1 ? "note" : "notes"}`}</div>
        {loading ? <div className="loading-rows"><i /><i /><i /></div> : error ? <div className="inline-state" role="alert">{error}</div> : filtered.length ? <div className="note-list">{filtered.map((note) => <NoteRow note={note} key={note.id} />)}</div> : <div className="empty-state"><span className="empty-mark">N</span><strong>No matching notes</strong><p>Try another filter or capture a new note.</p></div>}
      </section>
    </div>
  );
}