"use client";

import { ArrowLeft, Check, LoaderCircle, Plus, Save, SquarePen } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { addTagToNote, ApiError, createDrawingBlock, createTextBlock, getNote, patchNote, patchTextBlock, removeTagFromNote, type Note } from "@/lib/api";
import { usePanelStore } from "@/lib/panel-store";

export default function NoteDetailPage() {
  const params = useParams<{ id: string }>();
  const [note, setNote] = useState<Note | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [tagInput, setTagInput] = useState("");
  const openPanel = usePanelStore((state) => state.open);

  useEffect(() => {
    let active = true;
    getNote(params.id)
      .then((value) => active && setNote(value))
      .catch((reason: unknown) => active && setError(reason instanceof ApiError && reason.status === 404 ? "This note isn’t available to your account." : "Unable to load this note."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [params.id]);

  async function saveTitle() {
    if (!note) return;
    setSaving(true);
    setMessage("");
    try {
      const updated = await patchNote(note.id, { title: note.title ?? "" });
      setNote((current) => current ? { ...current, ...updated } : updated);
      setMessage("Saved");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn’t save changes.");
    } finally {
      setSaving(false);
    }
  }

  async function saveBlock(blockId: string, text: string) {
    if (!note) return;
    try {
      const updated = await patchTextBlock(blockId, text);
      setNote((current) => current ? { ...current, blocks: current.blocks.map((block) => block.id === blockId ? updated : block) } : current);
      setMessage("Block saved");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn’t save this block.");
    }
  }

  async function addTextBlock() {
    if (!note) return;
    try {
      const block = await createTextBlock(note.id, "");
      setNote((current) => current ? { ...current, blocks: [...current.blocks, block] } : current);
      setMessage("Text block added");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn’t add a block.");
    }
  }

  async function addDrawingBlock() {
    if (!note) return;
    try {
      const block = await createDrawingBlock(note.id, {
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
      }, `Whiteboard ${new Date().toLocaleDateString()}`);
      setNote((current) => current ? { ...current, blocks: [...current.blocks, block] } : current);
      openPanel("whiteboard", note.id);
      setMessage("Drawing block ready");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn’t add a drawing block.");
    }
  }

  async function addTag() {
    if (!note || !tagInput.trim()) return;
    try {
      const tags = await addTagToNote(note.id, tagInput.trim());
      setNote((current) => current ? { ...current, tags } : current);
      setTagInput("");
      setMessage("Tag added");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn’t add the tag.");
    }
  }

  async function removeTag(tagSlug: string) {
    if (!note) return;
    try {
      const tags = await removeTagFromNote(note.id, tagSlug);
      setNote((current) => current ? { ...current, tags } : current);
      setMessage("Tag removed");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn’t remove the tag.");
    }
  }

  if (loading) return <div className="page-wrap"><div className="loading-rows"><i /><i /><i /></div></div>;
  if (error && !note) return <div className="page-wrap"><div className="inline-state" role="alert">{error}<Link href="/notes">Back to notes</Link></div></div>;
  if (!note) return null;

  return (
    <div className="page-wrap note-detail-page">
      <div className="detail-back-row"><Link href="/notes"><ArrowLeft size={16} /> Notes</Link><span>{message && <span className="save-state"><Check size={14} /> {message}</span>}</span></div>
      <section className="note-detail-heading">
        <div><p className="eyebrow">{note.type.replaceAll("_", " ")} · {note.status}</p><input className="note-title-input" value={note.title ?? ""} onChange={(event) => setNote({ ...note, title: event.target.value })} onBlur={() => void saveTitle()} aria-label="Note title" placeholder="Untitled note" /><p className="page-subtitle">Updated {new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(note.updated_at))}</p></div>
        <button className="secondary-button" onClick={() => void saveTitle()} disabled={saving}>{saving ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />} Save title</button>
      </section>
      <div className="note-tag-row">
        {note.tags.map((tag) => <button type="button" className="tag-chip tag-chip-button" key={tag.id} onClick={() => void removeTag(tag.slug)}>#{tag.slug}</button>)}
        <div className="tag-entry compact-tag-entry">
          <input value={tagInput} onChange={(event) => setTagInput(event.target.value)} placeholder="Add tag" aria-label="Add a tag" />
          <button type="button" className="primary-button" onClick={() => void addTag()} disabled={!tagInput.trim()}>Add</button>
          <button type="button" className="secondary-button" onClick={() => openPanel("hermes", note.id)}>AI review</button>
        </div>
      </div>
      {note.summary && <p className="note-summary">{note.summary}</p>}
      <section className="block-stack">
        <div className="section-heading"><div><p className="eyebrow">NOTE CONTENT</p><h2>Blocks</h2></div><div className="inline-actions"><button className="text-link" onClick={() => void addTextBlock()}><Plus size={16} /> Add text</button><button className="text-link" onClick={() => void addDrawingBlock()}><SquarePen size={16} /> Add drawing</button></div></div>
        {note.blocks.length === 0 ? <div className="empty-state compact-empty"><strong>This note has no content blocks.</strong><p>Add a text block or a drawing to start writing.</p></div> : note.blocks.map((block) => (
          <div className="editable-block" key={block.id}>
            <div className="block-meta"><span>{block.type}</span><span>{block.order_index.toString().padStart(4, "0")}</span></div>
            {block.type === "text" ? <textarea defaultValue={block.text_content ?? ""} key={`${block.id}:${block.updated_at}`} onBlur={(event) => event.currentTarget.value !== (block.text_content ?? "") && void saveBlock(block.id, event.currentTarget.value)} aria-label="Text block" placeholder="Write a note…" /> : block.type === "drawing" ? (
              <button className="drawing-preview" type="button" onClick={() => openPanel("whiteboard", note.id)}>
                <span className="drawing-preview-header">
                  <strong>{String((block.data?.theme ?? "chalkboard_green") as string).replaceAll("_", " ")}</strong>
                  <em>{Array.isArray(block.data?.strokes) ? `${block.data.strokes.length} strokes` : "New drawing"}</em>
                </span>
                <span className="drawing-preview-body">{block.text_content ?? "Sketch board"}</span>
              </button>
            ) : <pre>{JSON.stringify(block.data, null, 2)}</pre>}
            {block.caption && <p className="block-caption">{block.caption}</p>}
          </div>
        ))}
      </section>
      {error && <p className="inline-error" role="alert">{error}</p>}
    </div>
  );
}