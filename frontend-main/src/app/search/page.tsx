"use client";

import { Search, SlidersHorizontal } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { NoteRow } from "@/components/note-row";
import { listNotes, type Note } from "@/lib/api";

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
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setQuery(params.get("q") ?? "");
  }, [params]);

  useEffect(() => {
    let active = true;
    listNotes(new URLSearchParams({ limit: "100" }))
      .then((result) => active && setNotes(result.items))
      .catch(() => active && setNotes([]))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (query.trim()) url.searchParams.set("q", query.trim());
    else url.searchParams.delete("q");
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }, [query]);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return notes.slice(0, 8);
    return notes.filter((note) => [note.title, note.summary, note.ai_summary, ...note.tags.map((tag) => tag.name), ...note.blocks.map((block) => `${block.text_content ?? ""} ${block.ocr_text ?? ""} ${block.transcript ?? ""}`)]
      .some((value) => value?.toLowerCase().includes(needle)));
  }, [notes, query]);

  return (
    <div className="page-wrap list-page">
      <section className="page-heading-row"><div><p className="eyebrow">FIND IT AGAIN</p><h1>Search</h1><p className="page-subtitle">Search loaded notes by title, text, OCR, transcript, summary, and tag.</p></div><SlidersHorizontal size={20} className="heading-mark" /></section>
      <label className="search-field search-page-field"><Search size={18} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search notes, words, or tags" aria-label="Search notes" /></label>
      <section className="list-results"><div className="results-meta">{loading ? "Searching" : `${results.length} matches`}</div>{loading ? <div className="loading-rows"><i /><i /><i /></div> : results.length ? <div className="note-list">{results.map((note) => <NoteRow key={note.id} note={note} />)}</div> : <div className="empty-state"><span className="empty-mark">?</span><strong>No matches</strong><p>Try a shorter phrase or another tag.</p></div>}</section>
    </div>
  );
}