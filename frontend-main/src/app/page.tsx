"use client";

import { ArrowRight, ArrowUpRight, Inbox, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { NoteRow } from "@/components/note-row";
import { ApiError, listNotes, type Note, type NoteList } from "@/lib/api";
import { usePanelStore } from "@/lib/panel-store";

export default function HomePage() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const open = usePanelStore((state) => state.open);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const result: NoteList = await listNotes(new URLSearchParams({ limit: "6", status: "inbox" }));
      setNotes(result.items);
    } catch (reason) {
      setError(reason instanceof ApiError && reason.status === 401 ? "Sign in to load your family notes." : "Notes are temporarily unavailable.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  const now = new Date();
  const greeting = now.getHours() < 12 ? "Good morning" : now.getHours() < 18 ? "Good afternoon" : "Good evening";

  return (
    <div className="page-wrap home-page">
      <section className="home-welcome">
        <div>
          <p className="eyebrow">{new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric" }).format(now)}</p>
          <h1>{greeting}, family.</h1>
          <p className="welcome-subtitle">A clear place for the things you want to remember.</p>
        </div>
        <button className="primary-button" onClick={() => open("capture")}><Plus size={17} /> Capture</button>
      </section>

      <section className="home-grid" aria-label="Family overview">
        <div className="home-section inbox-section">
          <div className="section-heading">
            <div className="section-title-group">
              <span className="section-icon"><Inbox size={18} /></span>
              <div><p className="eyebrow">YOUR NOTES</p><h2>Inbox</h2></div>
              {!loading && <span className="count-chip">{notes.length}</span>}
            </div>
            <div className="section-actions">
              <button className="icon-button small-icon" onClick={() => void refresh()} aria-label="Refresh inbox"><RefreshCw size={16} /></button>
              <Link className="text-link" href="/notes">All notes <ArrowRight size={15} /></Link>
            </div>
          </div>

          {loading ? (
            <div className="loading-rows" aria-label="Loading notes"><i /><i /><i /></div>
          ) : error ? (
            <div className="inline-state"><p>{error}</p><button className="text-button" onClick={() => void refresh()}>Retry</button></div>
          ) : notes.length === 0 ? (
            <div className="empty-state compact-empty">
              <span className="empty-mark">N</span>
              <div><strong>Your inbox is clear.</strong><p>New notes you capture will be collected here.</p></div>
              <button className="text-link" onClick={() => open("capture")}>Capture a note <ArrowRight size={15} /></button>
            </div>
          ) : (
            <div className="note-list home-note-list">
              {notes.map((note) => <NoteRow key={note.id} note={note} />)}
            </div>
          )}
        </div>

        <section className="home-section family-brief">
          <div className="section-heading">
            <div><p className="eyebrow">FAMILY SPACE</p><h2>Today at home</h2></div>
            <span className="availability-dot" aria-label="Local workspace" />
          </div>
          <div className="brief-list">
            <div className="brief-row"><span className="brief-index">01</span><div><strong>Keep good notes close</strong><p>Capture a thought, receipt, or plan without leaving this page.</p></div></div>
            <div className="brief-row"><span className="brief-index">02</span><div><strong>Find it when it matters</strong><p>Search your notes by title, tag, status, or note type.</p></div></div>
          </div>
          <Link className="brief-footer" href="/search">Open search <ArrowUpRight size={15} /></Link>
        </section>
      </section>

      <section className="recent-section">
        <div className="section-heading">
          <div><p className="eyebrow">QUICK ACCESS</p><h2>Start somewhere</h2></div>
        </div>
        <div className="shortcut-grid">
          <button className="shortcut-row" onClick={() => open("capture")}><span className="shortcut-icon capture-shortcut"><Plus size={17} /></span><span><strong>Capture something</strong><small>Text, plans, reminders</small></span><ArrowUpRight size={16} /></button>
          <Link className="shortcut-row" href="/notes"><span className="shortcut-icon notes-shortcut"><Inbox size={17} /></span><span><strong>Browse notes</strong><small>Open your family inbox</small></span><ArrowUpRight size={16} /></Link>
          <Link className="shortcut-row" href="/search"><span className="shortcut-icon search-shortcut"><RefreshCw size={17} /></span><span><strong>Find a detail</strong><small>Search by word or tag</small></span><ArrowUpRight size={16} /></Link>
        </div>
      </section>
    </div>
  );
}