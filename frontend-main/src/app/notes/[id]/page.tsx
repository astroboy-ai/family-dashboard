"use client";

import { ArrowLeft, Check, Copy, Eye, EyeOff, Expand, GripVertical, LoaderCircle, Lock, LockOpen, Maximize, Minimize, Minus, Plus, Save, SquarePen, Trash2, Type, Unlock, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { addTagToNote, ApiError, createBlock, createDrawingBlock, createTextBlock, deleteBlock, enqueueMediaEnrich, getNote, patchBlock, patchNote, patchTextBlock, removeTagFromNote, reorderBlocks, uploadFile, type Note, type NoteBlock } from "@/lib/api";
import { usePanelStore } from "@/lib/panel-store";
import { BlockMenu } from "@/components/block-menu";
import { confirmDialog } from "@/components/confirm-dialog";
import { DrawingThumb, type ThumbStroke } from "@/components/drawing-thumb";
import { ToolsDrawer, type Tool } from "@/components/tools-drawer";

export default function NoteDetailPage() {
  const params = useParams<{ id: string }>();
  const [note, setNote] = useState<Note | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  // Row height is a reading preference, shared by every text block in the app,
  // so it lives here and is remembered per browser. It is never sent to the API:
  // it is how you like to read, not part of the note.
  const [textRows, setTextRows] = useState<number>(3);
  // Which text block is open full screen. Held at page level so the overlay
  // renders outside every block's <fieldset> and stays interactive when the
  // block it belongs to is locked.
  const [textOverlay, setTextOverlay] = useState<NoteBlock | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);
  // Per-block edit lock — a UI guard only, never persisted.
  //
  // Every block renders read-only when the note opens, so a stray click cannot
  // change anything, and unlocking is a deliberate per-block action. It is a
  // safety habit for the human, not a property of the data: keeping it out of
  // the API means no migration, no scope and no effect on any agent.
  //
  // Holds the ids that are currently UNLOCKED; a new block is added on creation
  // so a block you just made is immediately editable.
  const [unlockedBlocks, setUnlockedBlocks] = useState<Set<string>>(new Set());
  const [galleryIndex, setGalleryIndex] = useState<number | null>(null);
  const openPanel = usePanelStore((state) => state.open);

  /** Open the image gallery at a specific block index. */
  const openGallery = (blockIndex: number) => setGalleryIndex(blockIndex);
  // Blocks render in list order, so a drag only needs to splice the array and
  // persist the resulting ids; order_index is recomputed server-side.
  const blockIdsRef = useRef<string[]>([]);

  useEffect(() => {
    let active = true;
    getNote(params.id)
      .then((value) => active && setNote(value))
      .catch((reason: unknown) => active && setError(reason instanceof ApiError && reason.status === 404 ? "This note isn’t available to your account." : "Unable to load this note."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [params.id]);

  // A fresh load starts fully locked: nothing is unlocked until the user says so.
  // Keyed on params.id so navigating to another note re-locks everything.
  useEffect(() => {
    setUnlockedBlocks(new Set());
  }, [params.id]);

  // Restore the remembered row height once on mount, after hydration.
  useEffect(() => {
    try {
      const parsed = Number(window.localStorage.getItem("familyos.textRows"));
      if ([3, 10, 20].includes(parsed)) setTextRows(parsed);
    } catch { /* storage unavailable — keep the default */ }
  }, []);

  function chooseTextRows(next: number) {
    setTextRows(next);
    try {
      window.localStorage.setItem("familyos.textRows", String(next));
    } catch { /* storage unavailable — the choice just won't persist */ }
  }

  function isUnlocked(blockId: string) {
    return unlockedBlocks.has(blockId);
  }

  /** Mark a block unlocked, or drop it back to locked. */
  function toggleBlockLock(blockId: string) {
    setUnlockedBlocks((current) => {
      const next = new Set(current);
      if (next.has(blockId)) next.delete(blockId);
      else next.add(blockId);
      return next;
    });
  }

  /** Add a newly created block to the unlocked set so it is editable at once. */
  function adoptNewBlock(block: NoteBlock) {
    setNote((current) => current ? { ...current, blocks: [...current.blocks, block] } : current);
    setUnlockedBlocks((current) => new Set(current).add(block.id));
  }

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
      adoptNewBlock(block);
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
      adoptNewBlock(block);
      // Hand the panel this block's own id so it edits the new board rather
      // than re-loading the note's first drawing.
      openPanel("whiteboard", note.id, block.id);
      setMessage("Drawing block ready");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn’t add a drawing block.");
    }
  }

  /** Move the dragged block to the hovered slot, then persist the new order. */
  async function moveBlock(fromId: string, toIndex: number) {
    if (!note) return;
    const current = note.blocks.map((block) => block.id);
    const fromIndex = current.indexOf(fromId);
    if (fromIndex === -1) return;
    // Removing first then inserting keeps the target index meaningful whether
    // the block moved up or down.
    const next = [...current];
    next.splice(fromIndex, 1);
    const insertAt = fromIndex < toIndex ? toIndex - 1 : toIndex;
    next.splice(Math.max(0, Math.min(insertAt, next.length)), 0, fromId);
    if (next.join(",") === current.join(",")) return;

    const byId = new Map(note.blocks.map((block) => [block.id, block]));
    const optimistic = next.map((id) => byId.get(id)!).filter(Boolean);
    setNote((current) => current ? { ...current, blocks: optimistic } : current);
    try {
      const updated = await reorderBlocks(note.id, next);
      setNote((current) => current ? { ...current, blocks: updated } : current);
      setMessage("Order saved");
    } catch (reason) {
      // Roll back so the UI never lies about what is stored.
      setNote((current) => current ? { ...current, blocks: note.blocks } : current);
      setError(reason instanceof Error ? reason.message : "Couldn’t reorder blocks.");
    }
  }

  async function removeBlock(blockId: string) {
    if (!note) return;
    const ok = await confirmDialog({
      title: "Delete this block?",
      message: "This block will be permanently removed from the note.",
      confirmLabel: "Delete",
    });
    if (!ok) return;
    try {
      await deleteBlock(blockId);
      setNote((current) => current ? { ...current, blocks: current.blocks.filter((b) => b.id !== blockId) } : current);
      setMessage("Block removed");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn't remove block.");
    }
  }

  /** Queue (or re-queue) vision analysis for an image block. */
  async function analyseImage(block: NoteBlock) {
    const assetId = String(block.data?.media_asset_id ?? "");
    if (!assetId) return;
    try {
      setMessage("Queuing AI analysis…");
      await enqueueMediaEnrich(assetId);
      setNote((current) =>
        current
          ? {
              ...current,
              blocks: current.blocks.map((b) =>
                b.id === block.id ? { ...b, data: { ...b.data, ai_pending: true } } : b,
              ),
            }
          : current,
      );
      setMessage("AI analysis queued — reload in a moment to see the description");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn't queue AI analysis.");
    }
  }

  /** Patch one block and splice the server's copy back into the note. */
  async function updateBlockData(blockId: string, data: Record<string, unknown>) {
    try {
      const updated = await patchBlock(blockId, { data });
      setNote((current) => current ? { ...current, blocks: current.blocks.map((b) => b.id === blockId ? updated : b) } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn't update the block.");
    }
  }

  async function handleToolSelect(tool: Tool) {
    if (!note) return;
    try {
      switch (tool.id) {
        case "checkbox": {
          const block = await createBlock(note.id, {
            type: "checkbox",
            text_content: "",
            data: { checked: false },
          });
          adoptNewBlock(block);
          setMessage("Checkbox added");
          break;
        }
        case "date": {
          const block = await createBlock(note.id, {
            type: "date",
            text_content: "",
            data: { value: new Date().toISOString().slice(0, 10) },
          });
          adoptNewBlock(block);
          setMessage("Date field added");
          break;
        }
        case "currency": {
          const block = await createBlock(note.id, {
            type: "currency",
            text_content: "",
            data: { value: "", currency: "HKD" },
          });
          adoptNewBlock(block);
          setMessage("Currency field added");
          break;
        }
        case "password": {
          const block = await createBlock(note.id, {
            type: "password",
            text_content: "",
            data: { value: "", masked: true },
          });
          adoptNewBlock(block);
          setMessage("Password field added");
          break;
        }
        case "photo": {
          // No up-front prompt: photos are attached straight away and the AI
          // analysis is chosen per image from the block's ⋮ menu, so adding
          // several pictures never turns into a chain of dialogs.
          const input = document.createElement("input");
          input.type = "file";
          input.accept = "image/*";
          input.multiple = true;
          input.onchange = async () => {
            const files = Array.from(input.files ?? []);
            if (files.length === 0) return;
            setMessage(`Uploading ${files.length} photo(s)…`);
            for (const file of files) {
              try {
                const assetId = await uploadFile(file);
                const block = await createBlock(note.id, {
                  type: "image",
                  text_content: file.name,
                  data: { media_asset_id: assetId },
                });
                adoptNewBlock(block);
              } catch (reason) {
                setError(reason instanceof Error ? reason.message : "Couldn't upload photo.");
              }
            }
            setMessage(`${files.length} photo(s) added`);
          };
          input.click();
          break;
        }
        case "file": {
          const input = document.createElement("input");
          input.type = "file";
          input.multiple = true;
          input.onchange = async () => {
            const files = Array.from(input.files ?? []);
            if (files.length === 0) return;
            setMessage(`Uploading ${files.length} file(s)…`);
            for (const file of files) {
              try {
                const assetId = await uploadFile(file);
                const block = await createBlock(note.id, {
                  type: "file",
                  text_content: file.name,
                  data: { media_asset_id: assetId },
                });
                adoptNewBlock(block);
              } catch (reason) {
                setError(reason instanceof Error ? reason.message : "Couldn't upload file.");
              }
            }
            setMessage(`${files.length} file(s) added`);
          };
          input.click();
          break;
        }
        case "table": {
          const block = await createBlock(note.id, {
            type: "table",
            text_content: "",
            data: { rows: [["", ""], ["", ""]], columns: 2 },
          });
          adoptNewBlock(block);
          setMessage("Table added");
          break;
        }
        case "time": {
          const block = await createBlock(note.id, {
            type: "time",
            text_content: "",
            data: { value: "", duration_min: 0 },
          });
          adoptNewBlock(block);
          setMessage("Time field added");
          break;
        }
        case "drawing": {
          // Must create a block, not just re-open the panel — otherwise the
          // toolbox appears to do nothing on a note that already has a drawing.
          await addDrawingBlock();
          break;
        }
        case "reminder": {
          const when = window.prompt("Reminder time (YYYY-MM-DDTHH:MM):", new Date(Date.now() + 3600000).toISOString().slice(0, 16));
          if (!when) break;
          const block = await createBlock(note.id, {
            type: "reminder",
            text_content: "",
            data: { remind_at: when, done: false },
          });
          adoptNewBlock(block);
          setMessage("Reminder added");
          break;
        }
        case "lock": {
          const block = await createBlock(note.id, {
            type: "lock",
            text_content: "",
            data: { locked: true },
          });
          adoptNewBlock(block);
          setMessage("Note locked");
          break;
        }
        case "link": {
          const target = window.prompt("Note ID or URL to link:");
          if (!target) break;
          const block = await createBlock(note.id, {
            type: "link",
            text_content: target,
            data: { target },
          });
          adoptNewBlock(block);
          setMessage("Link added");
          break;
        }
        case "share": {
          const text = note.blocks.map((b) => b.text_content ?? "").filter(Boolean).join("\n\n");
          const blob = new Blob([`# ${note.title}\n\n${text}`], { type: "text/markdown" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `${note.title || "note"}.md`;
          a.click();
          URL.revokeObjectURL(url);
          setMessage("Exported as Markdown");
          break;
        }
        case "location": {
          try {
            const position = await new Promise<GeolocationPosition>((resolve, reject) => {
              navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 });
            });
            const { latitude, longitude } = position.coords;
            const block = await createBlock(note.id, {
              type: "location",
              text_content: `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`,
              data: { latitude, longitude },
            });
            adoptNewBlock(block);
            setMessage("Location added");
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : "Couldn't get location.");
          }
          break;
        }
        case "voice": {
          try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const recorder = new MediaRecorder(stream);
            const chunks: Blob[] = [];
            recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
            recorder.onstop = async () => {
              stream.getTracks().forEach((t) => t.stop());
              const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
              const file = new File([blob], `voice-${Date.now()}.webm`, { type: blob.type });
              try {
                const assetId = await uploadFile(file);
                const block = await createBlock(note.id, {
                  type: "audio",
                  text_content: "Voice note",
                  data: { media_asset_id: assetId },
                });
                adoptNewBlock(block);
                setMessage("Voice note added");
              } catch (reason) {
                setError(reason instanceof Error ? reason.message : "Couldn't upload voice note.");
              }
            };
            recorder.start();
            setMessage("Recording… tap again to stop");
            const stopHandler = () => {
              if (recorder.state !== "inactive") recorder.stop();
              document.removeEventListener("click", stopHandler);
            };
            setTimeout(() => document.addEventListener("click", stopHandler), 100);
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : "Microphone access denied.");
          }
          break;
        }
        default:
          setMessage(`${tool.label} tool selected — coming soon`);
          break;
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Couldn't add tool.");
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
    <div className={`page-wrap note-detail-page ${fullscreen ? "fullscreen" : ""}`}>
      <div className="detail-back-row"><Link href="/notes"><ArrowLeft size={16} /> Notes</Link><span>{message && <span className="save-state"><Check size={14} /> {message}</span>}</span></div>
      <section className="note-detail-heading">
        <div className="note-title-row">
          <input className="note-title-input" value={note.title ?? ""} onChange={(event) => setNote({ ...note, title: event.target.value })} onBlur={() => void saveTitle()} aria-label="Note title" placeholder="Untitled note" />
          <button className="icon-button" onClick={() => void saveTitle()} disabled={saving} aria-label="Save title" title="Save title">{saving ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}</button>
        </div>
        <p className="eyebrow">{note.type.replaceAll("_", " ")} · {note.status}</p>
        <p className="page-subtitle">Updated {new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(note.updated_at))}</p>
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
        <div className="section-heading"><div><p className="eyebrow">NOTE CONTENT</p><h2>Blocks</h2></div></div>
        {note.blocks.length === 0 ? <div className="empty-state compact-empty"><strong>This note has no content blocks.</strong><p>Add a text block or a drawing to start writing.</p></div> : note.blocks.map((block, index) => (
          <div
            className={`editable-block${dragId === block.id ? " dragging" : ""}${dropIndex === index && dragId && dragId !== block.id ? " drop-target" : ""}`}
            key={block.id}
            onDragOver={(event) => {
              if (!dragId || dragId === block.id) return;
              event.preventDefault();
              setDropIndex(index);
            }}
            onDrop={(event) => {
              event.preventDefault();
              if (dragId && dragId !== block.id) void moveBlock(dragId, index);
              setDragId(null);
              setDropIndex(null);
            }}
          >
            <div className="block-meta">
              <span className="block-grip" draggable={isUnlocked(block.id)} onDragStart={() => isUnlocked(block.id) && setDragId(block.id)} onDragEnd={() => { setDragId(null); setDropIndex(null); }} role="button" tabIndex={0} aria-label={isUnlocked(block.id) ? "Drag to reorder" : "Unlock to reorder"} title={isUnlocked(block.id) ? "Drag to reorder" : "Unlock to reorder"} aria-disabled={!isUnlocked(block.id)}><GripVertical size={13} /></span>
              <span>{block.type}</span>
              <span className="block-order">{block.order_index.toString().padStart(4, "0")}</span>
              <button
                type="button"
                className={`icon-button small-icon block-lock-toggle${isUnlocked(block.id) ? " unlocked" : ""}`}
                onClick={() => toggleBlockLock(block.id)}
                aria-pressed={!isUnlocked(block.id)}
                aria-label={isUnlocked(block.id) ? `Lock this ${block.type} block` : `Unlock this ${block.type} block`}
                title={isUnlocked(block.id) ? "Lock — make read-only again" : "Unlock — allow editing"}
              >
                {isUnlocked(block.id) ? <LockOpen size={14} /> : <Lock size={14} />}
              </button>
              <button className="icon-button small-icon" onClick={() => void removeBlock(block.id)} disabled={!isUnlocked(block.id)} aria-label={isUnlocked(block.id) ? "Remove block" : "Unlock to remove this block"} title={isUnlocked(block.id) ? "Remove block" : "Unlock to remove this block"}><Trash2 size={14} /></button>
            </div>
            {/*
              A locked block is wrapped in a disabled <fieldset>, which is the one
              thing that reliably makes every control inside it inert — inputs,
              textareas, selects, buttons and anything a future block type adds.
              Styling alone would not stop a click, and per-type handling would
              have to be repeated for every new block type.
            */}
            <fieldset className="block-fieldset" disabled={!isUnlocked(block.id)}>
            {block.type === "text" ? (
              <TextBlockView block={block} rows={textRows} onSave={saveBlock} />
            ) : block.type === "drawing" ? (
              <button className="drawing-preview" type="button" onClick={() => openPanel("whiteboard", note.id, block.id)}>
                <span className="drawing-preview-header">
                  <strong>{String((block.data?.theme ?? "chalkboard_green") as string).replaceAll("_", " ")}</strong>
                  <em>{Array.isArray(block.data?.strokes) ? `${block.data.strokes.length} strokes` : "New drawing"}</em>
                </span>
                {Array.isArray(block.data?.strokes) && block.data.strokes.length > 0 ? (
                  <DrawingThumb
                    strokes={block.data.strokes as ThumbStroke[]}
                    theme={String(block.data?.theme ?? "chalkboard_green")}
                    canvas={(block.data?.canvas as { width: number; height: number } | undefined) ?? { width: 900, height: 640 }}
                  />
                ) : (
                  <span className="drawing-preview-body">{block.text_content ?? "Sketch board"}</span>
                )}
              </button>
            ) : block.type === "checkbox" ? (
              <div className="block-checkbox">
                <input
                  type="checkbox"
                  checked={Boolean(block.data?.checked)}
                  onChange={(e) => void updateBlockData(block.id, { ...block.data, checked: e.target.checked })}
                  aria-label={block.text_content || "Checkbox item"}
                />
                <input
                  className="block-checkbox-label"
                  type="text"
                  defaultValue={block.text_content ?? ""}
                  placeholder="What needs doing?"
                  onBlur={(e) => {
                    if (e.currentTarget.value === (block.text_content ?? "")) return;
                    void patchBlock(block.id, { text_content: e.currentTarget.value })
                      .then((updated) => setNote((current) => current ? { ...current, blocks: current.blocks.map((b) => b.id === block.id ? updated : b) } : current))
                      .catch(() => setError("Couldn't update the checkbox label."));
                  }}
                />
                <input
                  className="block-checkbox-due"
                  type="date"
                  defaultValue={String(block.data?.due ?? "")}
                  onChange={(e) => void updateBlockData(block.id, { ...block.data, due: e.target.value })}
                  aria-label="Due date"
                />
              </div>
            ) : block.type === "date" ? (
              <div className="block-field">
                <input
                  type="date"
                  value={String(block.data?.value ?? "")}
                  onChange={async (e) => {
                    try {
                      await updateBlockData(block.id, { ...block.data, value: e.target.value });
                    } catch { /* ignore */ }
                  }}
                />
              </div>
            ) : block.type === "currency" ? (
              <div className="block-field block-currency">
                <select
                  value={String(block.data?.currency ?? "HKD")}
                  onChange={async (e) => {
                    try {
                      await updateBlockData(block.id, { ...block.data, currency: e.target.value });
                    } catch { /* ignore */ }
                  }}
                >
                  <option value="HKD">HKD</option>
                  <option value="USD">USD</option>
                  <option value="CNY">CNY</option>
                  <option value="TWD">TWD</option>
                  <option value="JPY">JPY</option>
                  <option value="GBP">GBP</option>
                  <option value="EUR">EUR</option>
                </select>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0.00"
                  value={String(block.data?.value ?? "")}
                  onChange={async (e) => {
                    try {
                      await updateBlockData(block.id, { ...block.data, value: e.target.value });
                    } catch { /* ignore */ }
                  }}
                />
              </div>
            ) : block.type === "password" ? (
              <PasswordBlockView block={block} onUpdate={updateBlockData} />
            ) : block.type === "image" ? (
              <ImageBlockView block={block} onAnalyse={() => void analyseImage(block)} onRemove={() => void removeBlock(block.id)} onOpenGallery={() => openGallery(index)} onUpdateData={(data) => void updateBlockData(block.id, data)} />
            ) : block.type === "file" ? (
              <div className="block-media block-file">
                <a
                  href={`/api/media/${encodeURIComponent(String(block.data?.media_asset_id ?? ""))}/download`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block-file-link"
                >
                  📎 {block.text_content ?? "Download file"}
                </a>
              </div>
            ) : block.type === "audio" ? (
              <div className="block-media block-audio">
                <audio
                  controls
                  src={`/api/media/${encodeURIComponent(String(block.data?.media_asset_id ?? ""))}/download`}
                  className="block-audio-player"
                >
                  Your browser does not support the audio element.
                </audio>
                {block.text_content && <p className="block-caption">{block.text_content}</p>}
              </div>
            ) : block.type === "location" ? (
              <div className="block-location">
                <a
                  href={`https://www.google.com/maps?q=${Number(block.data?.latitude ?? 0)},${Number(block.data?.longitude ?? 0)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block-location-link"
                >
                  📍 {block.text_content || "View on map"}
                </a>
              </div>
            ) : block.type === "table" ? (
              <div className="block-table-wrap">
                <table className="block-table">
                  <tbody>
                    {(Array.isArray(block.data?.rows) ? (block.data.rows as string[][]) : []).map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {row.map((cell, cellIndex) => (
                          <td key={cellIndex}>
                            <input
                              type="text"
                              defaultValue={cell}
                              onBlur={async (e) => {
                                const rows = (Array.isArray(block.data?.rows) ? (block.data.rows as string[][]) : []).map((r) => [...r]);
                                rows[rowIndex][cellIndex] = e.currentTarget.value;
                                try {
                                  await updateBlockData(block.id, { ...block.data, rows });
                                } catch { /* ignore */ }
                              }}
                            />
                          </td>
                        ))}
                        <td className="table-row-controls">
                          <button
                            type="button"
                            className="table-control-btn"
                            aria-label="Add row below"
                            onClick={async () => {
                              const rows = (Array.isArray(block.data?.rows) ? (block.data.rows as string[][]) : []).map((r) => [...r]);
                              const colCount = rows[0]?.length ?? 2;
                              rows.splice(rowIndex + 1, 0, Array(colCount).fill(""));
                              try { await updateBlockData(block.id, { ...block.data, rows }); } catch { /* ignore */ }
                            }}
                          >
                            <Plus size={13} />
                          </button>
                          <button
                            type="button"
                            className="table-control-btn"
                            aria-label="Delete row"
                            onClick={async () => {
                              const rows = (Array.isArray(block.data?.rows) ? (block.data.rows as string[][]) : []);
                              if (rows.length <= 1) return;
                              const ok = await confirmDialog({
                                title: "Delete this row?",
                                message: "This row and its contents will be removed.",
                                confirmLabel: "Delete",
                              });
                              if (!ok) return;
                              const next = rows.filter((_, i) => i !== rowIndex);
                              try { await updateBlockData(block.id, { ...block.data, rows: next }); } catch { /* ignore */ }
                            }}
                          >
                            <Minus size={13} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      {(Array.isArray(block.data?.rows) ? (block.data.rows as string[][]) : [])[0]?.map((_, colIndex) => (
                        <td key={colIndex} className="table-col-controls">
                          <button
                            type="button"
                            className="table-control-btn"
                            aria-label="Add column"
                            onClick={async () => {
                              const rows = (Array.isArray(block.data?.rows) ? (block.data.rows as string[][]) : []).map((r) => [...r, ""]);
                              try { await updateBlockData(block.id, { ...block.data, rows }); } catch { /* ignore */ }
                            }}
                          >
                            <Plus size={13} />
                          </button>
                          <button
                            type="button"
                            className="table-control-btn"
                            aria-label="Delete column"
                            onClick={async () => {
                              const rows = (Array.isArray(block.data?.rows) ? (block.data.rows as string[][]) : []);
                              const colCount = rows[0]?.length ?? 0;
                              if (colCount <= 1) return;
                              const ok = await confirmDialog({
                                title: "Delete this column?",
                                message: "This column and its contents will be removed.",
                                confirmLabel: "Delete",
                              });
                              if (!ok) return;
                              const next = rows.map((r) => r.filter((_, i) => i !== colIndex));
                              try { await updateBlockData(block.id, { ...block.data, rows: next }); } catch { /* ignore */ }
                            }}
                          >
                            <Minus size={13} />
                          </button>
                        </td>
                      ))}
                    </tr>
                  </tfoot>
                </table>
              </div>
            ) : block.type === "reminder" ? (
              <div className="block-reminder">
                <span className="block-reminder-icon">🔔</span>
                <input
                  type="datetime-local"
                  defaultValue={String(block.data?.remind_at ?? "").slice(0, 16)}
                  onBlur={async (e) => {
                    try {
                      await updateBlockData(block.id, { ...block.data, remind_at: e.currentTarget.value });
                    } catch { /* ignore */ }
                  }}
                />
                <label className="block-reminder-done">
                  <input
                    type="checkbox"
                    defaultChecked={Boolean(block.data?.done)}
                    onChange={async (e) => {
                      try {
                        await updateBlockData(block.id, { ...block.data, done: e.target.checked });
                      } catch { /* ignore */ }
                    }}
                  />
                  Done
                </label>
              </div>
            ) : block.type === "lock" ? (
              <div className="block-lock">
                <span>🔒 Locked section</span>
                <label className="block-lock-toggle">
                  <input
                    type="checkbox"
                    defaultChecked={Boolean(block.data?.locked)}
                    onChange={async (e) => {
                      try {
                        await updateBlockData(block.id, { ...block.data, locked: e.target.checked });
                      } catch { /* ignore */ }
                    }}
                  />
                  Enabled
                </label>
              </div>
            ) : block.type === "link" ? (
              <div className="block-link">
                <a
                  href={String(block.data?.target ?? "#").startsWith("http") ? String(block.data?.target) : `/notes/${encodeURIComponent(String(block.data?.target ?? ""))}`}
                  className="block-link-anchor"
                >
                  🔗 {block.text_content || String(block.data?.target ?? "")}
                </a>
              </div>
            ) : block.type === "time" ? (
              <div className="block-field block-time">
                <input
                  type="time"
                  value={String(block.data?.value ?? "")}
                  onChange={async (e) => {
                    try {
                      await updateBlockData(block.id, { ...block.data, value: e.target.value });
                    } catch { /* ignore */ }
                  }}
                />
                <input
                  type="number"
                  min="0"
                  placeholder="duration (min)"
                  defaultValue={Number(block.data?.duration_min ?? 0) || ""}
                  onBlur={async (e) => {
                    try {
                      await updateBlockData(block.id, { ...block.data, duration_min: Number(e.currentTarget.value) || 0 });
                    } catch { /* ignore */ }
                  }}
                />
              </div>
            ) : <pre>{JSON.stringify(block.data, null, 2)}</pre>}
            {block.caption && <p className="block-caption">{block.caption}</p>}
            </fieldset>
            {/*
              Reading controls live OUTSIDE the <fieldset> on purpose: row height
              and full screen must keep working on a locked block. The lock gates
              editing, not looking at your own note.
            */}
            {block.type === "text" && (
              <div className="text-block-toolbar">
                <button
                  type="button"
                  className="icon-button small-icon"
                  onClick={() => setTextOverlay(block)}
                  aria-label="View full text"
                  title="View full text"
                >
                  <Expand size={14} />
                </button>
                <div className="text-rows-toggle">
                  {[3, 10, 20].map((n) => (
                    <button
                      key={n}
                      type="button"
                      className={textRows === n ? "active" : ""}
                      onClick={() => chooseTextRows(n)}
                      aria-label={`${n} rows`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </section>
      {error && <p className="inline-error" role="alert">{error}</p>}
      {/*
        One action bar at the bottom of the note: the lock switch and the two
        quick block types sit beside the tool drawer opener, all on one line.
        Kept out of the content flow so it never scrolls away.
      */}
      <div className="tool-dock" role="toolbar" aria-label="Note actions">
        <button type="button" className="tool-dock-item" onClick={() => void addTextBlock()} title="Add a text block"><Type size={15} /> text</button>
        <button type="button" className="tool-dock-item" onClick={() => void addDrawingBlock()} title="Add a drawing block"><SquarePen size={15} /> drawing</button>
        <button type="button" className="tool-dock-item tool-dock-primary" onClick={() => setDrawerOpen(true)} aria-label="Open the tool drawer"><Plus size={15} /> Tools</button>
        {note.blocks.length > 0 && (unlockedBlocks.size < note.blocks.length ? (
          <button type="button" className="tool-dock-icon" onClick={() => setUnlockedBlocks(new Set(note.blocks.map((b) => b.id)))} title="Unlock every block" aria-label="Unlock every block"><Unlock size={15} /></button>
        ) : (
          <button type="button" className="tool-dock-icon" onClick={() => setUnlockedBlocks(new Set())} title="Lock every block" aria-label="Lock every block"><Lock size={15} /></button>
        ))}
        <button type="button" className="tool-dock-icon" onClick={() => setFullscreen(!fullscreen)} aria-label={fullscreen ? "Exit full screen" : "Full screen"} title={fullscreen ? "Exit full screen" : "Full screen"}>{fullscreen ? <Minimize size={15} /> : <Maximize size={15} />}</button>
      </div>

      {textOverlay && (
        <TextOverlayView
          block={textOverlay}
          onClose={() => setTextOverlay(null)}
          onSave={saveBlock}
        />
      )}

      {galleryIndex !== null && note && (() => {
        const images = note.blocks.map((b, i) => ({ block: b, index: i })).filter(({ block }) => block.type === "image");
        const start = images.findIndex(({ index }) => index === galleryIndex);
        return (
          <ImageGallery
            images={images.map(({ block }) => block)}
            initialIndex={start === -1 ? 0 : start}
            onClose={() => setGalleryIndex(null)}
          />
        );
      })()}

      <ToolsDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} onSelect={handleToolSelect} />
    </div>
  );
}

/**
 * Password block with reveal toggle, copy, and label.
 *
 * The backend stores `data.value` as AES-GCM ciphertext and only returns the
 * plaintext when the caller holds `notes.read.secrets`. Without that scope the
 * value arrives as "••••••••" with `data.masked: true` — the UI must not try to
 * edit a masked value, or it would overwrite the real secret with the dots.
 *
 * A legacy plaintext row (written before encryption existed) comes back with
 * `data.encrypted: false`; the UI offers to re-save it, which encrypts it.
 */
function PasswordBlockView({
  block,
  onUpdate,
}: {
  block: NoteBlock;
  onUpdate: (blockId: string, data: Record<string, unknown>) => Promise<void>;
}) {
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [label, setLabel] = useState(String(block.data?.label ?? ""));
  const masked = Boolean(block.data?.masked);
  const decryptError = Boolean(block.data?.decrypt_error);
  const encrypted = block.data?.encrypted !== false;
  const value = String(block.data?.value ?? "");

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="block-field block-password">
      {label && <label className="block-password-label">{label}</label>}
      <div className="block-password-row">
        <input
          type={revealed && !masked ? "text" : "password"}
          placeholder="Enter secret…"
          value={masked ? "" : value}
          readOnly={masked}
          onChange={async (e) => {
            try {
              await onUpdate(block.id, { ...block.data, value: e.target.value });
            } catch { /* ignore */ }
          }}
        />
        <button
          type="button"
          className="icon-button small-icon"
          onClick={() => setRevealed((v) => !v)}
          aria-label={revealed ? "Hide secret" : "Reveal secret"}
          title={revealed ? "Hide" : "Reveal"}
        >
          {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
        <button
          type="button"
          className="icon-button small-icon"
          onClick={() => void copy()}
          aria-label="Copy secret"
          title="Copy"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
      {decryptError && <p className="block-password-error">Could not decrypt — wrong key or corrupted data.</p>}
      {!encrypted && !masked && (
        <p className="block-password-hint">
          <Lock size={12} /> Stored in plaintext. Re-enter and save to encrypt.
        </p>
      )}
      <div className="block-password-label-row">
        <input
          type="text"
          placeholder="Label (optional)"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() => {
            if (label !== String(block.data?.label ?? "")) {
              void onUpdate(block.id, { ...block.data, label });
            }
          }}
          aria-label="Password label"
        />
      </div>
    </div>
  );
}

/**
 * Text block with row-count toggle (3/10/20) and expand-to-overlay.
 *
 * The row count is stored in `data.rows` so it survives a reload. The overlay
 * opens the same text in a larger editable area — the inline textarea is for
 * quick edits, the overlay for serious writing.
 */
function TextBlockView({
  block,
  rows,
  onSave,
}: {
  block: NoteBlock;
  rows: number;
  onSave: (blockId: string, text: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? block.text_content ?? "";

  return (
    <div className="text-block-wrap">
      <textarea
        rows={rows}
        value={value}
        key={`${block.id}:${block.updated_at}`}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          if (value !== (block.text_content ?? "")) {
            void onSave(block.id, value);
          }
          setDraft(null);
        }}
        aria-label="Text block"
        placeholder="Write a note…"
      />
    </div>
  );
}

/**
 * Full-screen text editor overlay.
 *
 * Opens a text block in a larger editable area. Saves on blur and on close.
 * Copy button puts the text on the clipboard.
 */
function TextOverlayView({
  block,
  onClose,
  onSave,
}: {
  block: NoteBlock;
  onClose: () => void;
  onSave: (blockId: string, text: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState(block.text_content ?? "");
  const [copied, setCopied] = useState(false);
  // Opens locked: the full screen view is for reading a long block, and an
  // accidental keystroke there would edit the note. Unlocking is deliberate.
  const [unlocked, setUnlocked] = useState(false);

  // Esc closes the full screen view, the usual expectation for a full-bleed panel.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Freeze the page behind the overlay. Without this the page keeps its
  // scrollbar, so the "full screen" panel is 15px short of the viewport width
  // and the note scrolls underneath while you are reading.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="text-overlay" role="dialog" aria-modal="true" aria-label="Full text">
      <div className="text-overlay-card">
        <div className="text-overlay-head">
          <strong>Text block</strong>
          <div className="inline-actions">
            <button
              type="button"
              className={`icon-button${unlocked ? " unlocked" : ""}`}
              onClick={() => setUnlocked(!unlocked)}
              aria-pressed={!unlocked}
              aria-label={unlocked ? "Lock this text" : "Unlock to edit"}
              title={unlocked ? "Lock — make read-only again" : "Unlock — allow editing"}
            >
              {unlocked ? <LockOpen size={18} /> : <Lock size={18} />}
            </button>
            <button type="button" className="secondary-button" onClick={() => void copy()}>
              {copied ? "Copied" : "Copy"}
            </button>
            <button className="icon-button" onClick={onClose} aria-label="Close"><X size={18} /></button>
          </div>
        </div>
        <textarea
          className="text-overlay-editor"
          value={draft}
          readOnly={!unlocked}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => {
            if (unlocked && draft !== (block.text_content ?? "")) {
              void onSave(block.id, draft);
            }
          }}
          autoFocus
          aria-label="Text editor"
        />
      </div>
    </div>
  );
}

/**
 * Image block with thumbnail, click-to-enlarge, and EXIF overlay.
 *
 * The thumbnail is served by the backend worker (Pillow). Clicking opens a
 * lightbox that shows the full image. EXIF is fetched on demand and shown as a
 * read-only overlay — it is never written back to the block or note.
 */
function ImageBlockView({
  block,
  onAnalyse,
  onRemove,
  onOpenGallery,
  onUpdateData,
}: {
  block: NoteBlock;
  onAnalyse: () => void;
  onRemove: () => void;
  onOpenGallery?: () => void;
  onUpdateData?: (data: Record<string, unknown>) => void;
}) {
  const assetId = String(block.data?.media_asset_id ?? "");
  const [lightbox, setLightbox] = useState(false);
  const [exif, setExif] = useState<Record<string, unknown> | null>(null);
  const [showExif, setShowExif] = useState(false);
  const [editingAnalysis, setEditingAnalysis] = useState(false);
  const [editingNote, setEditingNote] = useState(false);
  const [analysisDraft, setAnalysisDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");

  async function toggleExif() {
    if (showExif) {
      setShowExif(false);
      return;
    }
    if (!exif) {
      try {
        const res = await fetch(`/api/media/${encodeURIComponent(assetId)}/exif`);
        if (res.ok) {
          const data = (await res.json()) as { exif: Record<string, unknown> };
          setExif(data.exif);
        }
      } catch { /* ignore */ }
    }
    setShowExif(true);
  }

  function saveAnalysis() {
    if (onUpdateData) {
      onUpdateData({ ...block.data, analysis_text: analysisDraft });
    }
    setEditingAnalysis(false);
  }

  function saveNote() {
    if (onUpdateData) {
      onUpdateData({ ...block.data, note_text: noteDraft });
    }
    setEditingNote(false);
  }

  const analysisText = String(block.data?.analysis_text ?? "");
  const noteText = String(block.data?.note_text ?? "");

  return (
    <>
      <div className="block-media">
        <div className="block-media-head">
          <span className="block-media-name">{block.text_content || "Image"}</span>
          <BlockMenu
            items={[
              ...(block.ai_description
                ? [{ label: "Re-analyse with AI", action: onAnalyse }]
                : [{ label: "Analyse with AI", action: onAnalyse }]),
              { label: "View EXIF", action: () => void toggleExif() },
              { label: "Remove block", action: onRemove, danger: true },
            ]}
          />
        </div>
        <img
          src={`/api/media/${encodeURIComponent(assetId)}/thumbnail`}
          alt={block.text_content ?? "Image"}
          className="block-image block-image-clickable"
          onClick={() => setLightbox(true)}
        />
        {block.ai_description ? (
          <p className="block-ai-description">{block.ai_description}</p>
        ) : block.data?.ai_pending ? (
          <p className="block-ai-pending">AI analysis queued…</p>
        ) : null}
      </div>

      {/* Two text properties: analysis + personal note */}
      <div className="block-text-props">
        <div className="block-text-prop">
          <div className="block-text-prop-header">
            <span className="block-text-prop-label">Analysis</span>
            {onUpdateData && !editingAnalysis && (
              <button
                type="button"
                className="block-text-prop-edit"
                onClick={() => { setAnalysisDraft(analysisText); setEditingAnalysis(true); }}
              >
                {analysisText ? "Edit" : "Add"}
              </button>
            )}
          </div>
          {editingAnalysis ? (
            <div className="block-text-prop-edit-row">
              <textarea
                className="block-text-prop-input"
                value={analysisDraft}
                onChange={(e) => setAnalysisDraft(e.target.value)}
                placeholder="AI analysis results…"
                rows={2}
              />
              <div className="block-text-prop-actions">
                <button type="button" className="primary-button small-button" onClick={saveAnalysis}>Save</button>
                <button type="button" className="secondary-button small-button" onClick={() => setEditingAnalysis(false)}>Cancel</button>
              </div>
            </div>
          ) : analysisText ? (
            <p className="block-text-prop-value">{analysisText}</p>
          ) : null}
        </div>

        <div className="block-text-prop">
          <div className="block-text-prop-header">
            <span className="block-text-prop-label">Note</span>
            {onUpdateData && !editingNote && (
              <button
                type="button"
                className="block-text-prop-edit"
                onClick={() => { setNoteDraft(noteText); setEditingNote(true); }}
              >
                {noteText ? "Edit" : "Add"}
              </button>
            )}
          </div>
          {editingNote ? (
            <div className="block-text-prop-edit-row">
              <textarea
                className="block-text-prop-input"
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
                placeholder="Personal note…"
                rows={2}
              />
              <div className="block-text-prop-actions">
                <button type="button" className="primary-button small-button" onClick={saveNote}>Save</button>
                <button type="button" className="secondary-button small-button" onClick={() => setEditingNote(false)}>Cancel</button>
              </div>
            </div>
          ) : noteText ? (
            <p className="block-text-prop-value">{noteText}</p>
          ) : null}
        </div>
      </div>

      {/* Reading control — outside the fieldset so it works when locked */}
      {onOpenGallery && (
        <button
          type="button"
          className="block-gallery-button"
          onClick={onOpenGallery}
          title="View all images in this note"
        >
          View gallery
        </button>
      )}
      {lightbox && (
        <ImageLightbox
          block={block}
          onClose={() => setLightbox(false)}
          exif={exif}
          showExif={showExif}
          onToggleExif={() => void toggleExif()}
        />
      )}
    </>
  );
}

/**
 * Lightbox for viewing an image at full size.
 *
 * Shows the full-resolution image with optional EXIF overlay. The overlay is
 * read-only — EXIF data is never written back to the block or note.
 */
function ImageLightbox({
  block,
  onClose,
  exif,
  showExif,
  onToggleExif,
}: {
  block: NoteBlock;
  onClose: () => void;
  exif: Record<string, unknown> | null;
  showExif: boolean;
  onToggleExif: () => void;
}) {
  const assetId = String(block.data?.media_asset_id ?? "");

  return (
    <div className="image-lightbox" role="dialog" aria-modal="true" aria-label="Image viewer" onClick={onClose}>
      <div className="image-lightbox-content" onClick={(event) => event.stopPropagation()}>
        <div className="image-lightbox-head">
          <strong>{block.text_content || "Image"}</strong>
          <div className="inline-actions">
            <button type="button" className="secondary-button" onClick={onToggleExif}>
              {showExif ? "Hide EXIF" : "EXIF"}
            </button>
            <button className="icon-button" onClick={onClose} aria-label="Close"><X size={18} /></button>
          </div>
        </div>
        <div className="image-lightbox-body">
          <img
            src={`/api/media/${encodeURIComponent(assetId)}/download`}
            alt={block.text_content ?? "Image"}
            className="image-lightbox-img"
          />
          {showExif && exif && (
            <div className="image-exif-overlay">
              {Object.entries(exif).map(([key, value]) => (
                <div key={key} className="image-exif-row">
                  <span className="image-exif-key">{key}</span>
                  <span className="image-exif-value">{String(value)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Full-screen gallery that navigates all image blocks in the same note.
 * Clicking any image block opens this; arrows or swipe move between images.
 */
function ImageGallery({
  images,
  initialIndex,
  onClose,
}: {
  images: NoteBlock[];
  initialIndex: number;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(initialIndex);
  const current = images[index];
  const assetId = String(current?.data?.media_asset_id ?? "");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") setIndex((i) => (i > 0 ? i - 1 : images.length - 1));
      if (e.key === "ArrowRight") setIndex((i) => (i < images.length - 1 ? i + 1 : 0));
    }
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [images.length, onClose]);

  if (!current) return null;

  return (
    <div className="image-gallery" role="dialog" aria-modal="true" aria-label="Image gallery" onClick={onClose}>
      <div className="image-gallery-content" onClick={(e) => e.stopPropagation()}>
        <div className="image-gallery-head">
          <span className="image-gallery-counter">{index + 1} / {images.length}</span>
          <button className="icon-button" onClick={onClose} aria-label="Close gallery"><X size={18} /></button>
        </div>
        <div className="image-gallery-body">
          {images.length > 1 && (
            <button
              className="image-gallery-nav image-gallery-prev"
              onClick={() => setIndex((i) => (i > 0 ? i - 1 : images.length - 1))}
              aria-label="Previous image"
            >
              ‹
            </button>
          )}
          <img
            src={`/api/media/${encodeURIComponent(assetId)}/download`}
            alt={current.text_content ?? "Image"}
            className="image-gallery-img"
          />
          {images.length > 1 && (
            <button
              className="image-gallery-nav image-gallery-next"
              onClick={() => setIndex((i) => (i < images.length - 1 ? i + 1 : 0))}
              aria-label="Next image"
            >
              ›
            </button>
          )}
        </div>
        {current.text_content && (
          <p className="image-gallery-caption">{current.text_content}</p>
        )}
      </div>
    </div>
  );
}