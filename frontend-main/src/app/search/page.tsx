"use client";

import { Search, SlidersHorizontal } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { NoteRow } from "@/components/note-row";
import { searchNotes, type Note } from "@/lib/api";

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="page-wrap list-page"><section className="page-heading-row"><div><p className="eyebrow">FIND IT AGAIN</p><h1>Search</h1><p className="page-subtitle">Preparing your note index…</p></div><SlidersHorizontal size={20} className="heading-mark" /></section><div className="loading-rows"><i /><i /><i /></div></div>}>
      <SearchPageContent />
    </Suspense>
  );
}

function SearchPageContent() {
  const params = useSearchParams();
  const initial = params.get("q") ?? "";
  const [query, setQuery] = useState(initial);
  const [noteType, setNoteType] = useState(params.get("type") ?? "");
  const [tag, setTag] = useState(params.get("tag") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setQuery(params.get("q") ?? "");
    setNoteType(params.get("type") ?? "");
    setTag(params.get("tag") ?? "");
    setStatus(params.get("status") ?? "");
  }, [params]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      const searchParams = new URLSearchParams({ limit: "50" });
      if (query.trim()) searchParams.set("q", query.trim());
      if (noteType) searchParams.set("types", noteType);
      if (tag.trim()) searchParams.set("tags", tag.trim());
      if (status) searchParams.set("statuses", status);
      setLoading(true);
      searchNotes(searchParams)
        .then((result) => active && setNotes(result.items))
        .catch(() => active && setNotes([]))
        .finally(() => active && setLoading(false));
    }, 150);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query, noteType, tag, status]);

  useEffect(() => {
    const url = new URL(window.location.href);
    for (const [key, value] of [["q", query], ["type", noteType], ["tag", tag], ["status", status]]) {
      if (value.trim()) url.searchParams.set(key, value.trim());
      else url.searchParams.delete(key);
    }
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }, [query, noteType, tag, status]);

  return (
    <div className="page-wrap list-page">
      <section className="page-heading-row"><div><p className="eyebrow">FIND IT AGAIN</p><h1>Search</h1><p className="page-subtitle">Search notes across titles, blocks, tags, and attachments.</p></div><SlidersHorizontal size={20} className="heading-mark" /></section>
      <label className="search-field search-page-field"><Search size={18} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search notes, words, or tags" aria-label="Search notes" /></label>
      <div className="search-filters" aria-label="Search filters">
        <label className="form-field"><span>Type</span><input value={noteType} onChange={(event) => setNoteType(event.target.value)} placeholder="Any type" aria-label="Filter by note type" /></label>
        <label className="form-field"><span>Tag</span><input value={tag} onChange={(event) => setTag(event.target.value)} placeholder="Any tag" aria-label="Filter by tag" /></label>
        <label className="form-field"><span>Status</span><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter by status"><option value="">Any status</option><option value="inbox">Inbox</option><option value="active">Active</option><option value="done">Done</option><option value="archived">Archived</option></select></label>
      </div>
      <section className="list-results"><div className="results-meta">{loading ? "Searching" : `${notes.length} matches`}</div>{loading ? <div className="loading-rows"><i /><i /><i /></div> : notes.length ? <div className="note-list">{notes.map((note) => <NoteRow key={note.id} note={note} />)}</div> : <div className="empty-state"><span className="empty-mark">?</span><strong>No matches</strong><p>Try a shorter phrase or another tag.</p></div>}</section>
    </div>
  );
}