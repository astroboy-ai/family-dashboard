"use client";

import { Check, LoaderCircle, PencilLine, Sparkles, Tag, Trash2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { addTagToNote, createDrawingBlock, createNote, getNote, removeTagFromNote, updateDrawingBlock, type Note } from "@/lib/api";
import { usePanelStore } from "@/lib/panel-store";

function CapturePanel({ close }: { close: () => void }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function save() {
    if (!text.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      const note = await createNote({
        title: text.trim().split("\n")[0].slice(0, 120),
        blocks: [{ type: "text", text_content: text.trim() }],
      });
      setSaved(true);
      window.setTimeout(() => {
        close();
        router.push(`/notes/${note.id}`);
      }, 450);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save this note");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="panel-heading">
        <div><span className="panel-eyebrow">QUICK CAPTURE</span><h2>New note</h2></div>
        <button className="icon-button" onClick={close} aria-label="Close capture"><X size={18} /></button>
      </div>
      <div className="capture-panel-body">
        <label className="field-label" htmlFor="capture-title">What do you want to remember?</label>
        <textarea
          id="capture-title"
          autoFocus
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") void save(); }}
          placeholder="A thought, a plan, something to find later…"
        />
        {error && <p className="inline-error" role="alert">{error}</p>}
        <div className="capture-hint">Saved to your Notes inbox. You can add more blocks after saving.</div>
      </div>
      <div className="panel-footer">
        <span className="quiet-shortcut"><kbd>⌘</kbd><kbd>↵</kbd> to save</span>
        <button className="primary-button" onClick={() => void save()} disabled={!text.trim() || saving || saved}>
          {saving ? <LoaderCircle className="spin" size={16} /> : saved ? <Check size={16} /> : null}
          {saved ? "Saved" : saving ? "Saving" : "Save note"}
        </button>
      </div>
    </>
  );
}

type StrokePoint = { x: number; y: number };
type Stroke = { id: string; color: string; width: number; points: StrokePoint[] };
type WhiteboardTheme = "chalkboard_green" | "chalkboard_black" | "whiteboard";

type WhiteboardData = {
  theme: WhiteboardTheme;
  strokes: Stroke[];
  canvas: { width: number; height: number; unit: string };
  viewport: { x: number; y: number; zoom: number; rotation: number };
  meta: { stroke_count: number; shape_count: number; text_count: number; size_bytes: number };
};

const DEFAULT_WHITEBOARD_DATA: WhiteboardData = {
  theme: "chalkboard_green",
  strokes: [],
  canvas: { width: 900, height: 640, unit: "px" },
  viewport: { x: 0, y: 0, zoom: 1, rotation: 0 },
  meta: { stroke_count: 0, shape_count: 0, text_count: 0, size_bytes: 0 },
};

function stringifyTheme(theme: string | undefined): WhiteboardTheme {
  if (theme === "chalkboard_black" || theme === "whiteboard") return theme;
  return "chalkboard_green";
}

function deriveTagSuggestions(note: Note | null) {
  if (!note) return [];
  const haystack = [
    note.title,
    note.summary,
    note.ai_summary,
    ...note.blocks.map((block) => [block.text_content, block.caption, block.ocr_text, block.transcript].join(" ")),
  ].join(" ").toLowerCase();
  const rules: Array<[string, string[]]> = [
    ["travel", ["travel", "trip", "flight", "airport", "train", "bus", "mtr", "holiday", "vacation", "japan", "kyoto", "tokyo", "beach"]],
    ["school", ["school", "class", "lesson", "assignment", "homework", "teacher", "camp", "study", "exam", "project"]],
    ["family", ["family", "dad", "mum", "mom", "parent", "parents", "grandma", "grandpa", "emma", "household"]],
    ["garden", ["garden", "plant", "plants", "seed", "soil", "greenhouse", "flower", "vegetable", "raised bed"]],
    ["meals", ["meal", "breakfast", "lunch", "dinner", "recipe", "cook", "snack", "grocery"]],
    ["shopping", ["shopping", "market", "grocery", "receipt", "budget", "cost", "store"]],
  ];
  const existing = new Set(note.tags.map((tag) => tag.slug));
  return rules.flatMap(([tag, keywords]) => (existing.has(tag) || !keywords.some((keyword) => haystack.includes(keyword)) ? [] : [tag]));
}

function WhiteboardPanel({ noteId, close }: { noteId?: string; close: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const draftRef = useRef<Stroke | null>(null);
  const [drawing, setDrawing] = useState<WhiteboardData>(DEFAULT_WHITEBOARD_DATA);
  const [activeColor, setActiveColor] = useState("#edf3d5");
  const [brushSize, setBrushSize] = useState(4);
  const [noteBlockId, setNoteBlockId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    if (!noteId) return;
    let active = true;
    getNote(noteId)
      .then((note) => {
        if (!active) return;
        const drawingBlock = note.blocks.find((block) => block.type === "drawing");
        if (!drawingBlock) {
          setDrawing(DEFAULT_WHITEBOARD_DATA);
          setNoteBlockId(null);
          return;
        }
        const data = (drawingBlock.data ?? {}) as Partial<WhiteboardData>;
        setNoteBlockId(drawingBlock.id);
        setDrawing({
          ...DEFAULT_WHITEBOARD_DATA,
          ...data,
          theme: stringifyTheme(typeof data.theme === "string" ? data.theme : undefined),
          strokes: Array.isArray(data.strokes) ? (data.strokes as Stroke[]) : [],
          canvas: {
            ...DEFAULT_WHITEBOARD_DATA.canvas,
            ...((data.canvas as Partial<{ width: number; height: number; unit: string }> | undefined) ?? {}),
          },
          viewport: {
            ...DEFAULT_WHITEBOARD_DATA.viewport,
            ...((data.viewport as Partial<{ x: number; y: number; zoom: number; rotation: number }> | undefined) ?? {}),
          },
          meta: {
            ...DEFAULT_WHITEBOARD_DATA.meta,
            ...((data.meta as Partial<typeof DEFAULT_WHITEBOARD_DATA.meta> | undefined) ?? {}),
          },
        });
      })
      .catch(() => {
        if (active) {
          setDrawing(DEFAULT_WHITEBOARD_DATA);
          setNoteBlockId(null);
        }
      });
    return () => { active = false; };
  }, [noteId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const { width, height } = drawing.canvas;
    canvas.width = width;
    canvas.height = height;
    context.clearRect(0, 0, width, height);

    const background = drawing.theme === "whiteboard" ? "#f9f8f2" : drawing.theme === "chalkboard_black" ? "#131817" : "#183a2d";
    context.fillStyle = background;
    context.fillRect(0, 0, width, height);

    context.strokeStyle = "rgba(255,255,255,0.16)";
    context.lineWidth = 1;
    for (let x = 40; x < width; x += 40) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, height);
      context.stroke();
    }
    for (let y = 40; y < height; y += 40) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }

    drawing.strokes.forEach((stroke) => {
      if (stroke.points.length < 2) return;
      context.beginPath();
      context.lineJoin = "round";
      context.lineCap = "round";
      context.strokeStyle = stroke.color;
      context.lineWidth = stroke.width;
      context.moveTo(stroke.points[0].x, stroke.points[0].y);
      for (let index = 1; index < stroke.points.length; index += 1) {
        context.lineTo(stroke.points[index].x, stroke.points[index].y);
      }
      context.stroke();
    });

    if (draftRef.current) {
      const stroke = draftRef.current;
      if (stroke.points.length > 1) {
        context.beginPath();
        context.lineJoin = "round";
        context.lineCap = "round";
        context.strokeStyle = stroke.color;
        context.lineWidth = stroke.width;
        context.moveTo(stroke.points[0].x, stroke.points[0].y);
        for (let index = 1; index < stroke.points.length; index += 1) {
          context.lineTo(stroke.points[index].x, stroke.points[index].y);
        }
        context.stroke();
      }
    }
  }, [drawing, draftRef]);

  function getPoint(event: React.PointerEvent<HTMLCanvasElement>): StrokePoint | null {
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    return {
      x: ((event.clientX - rect.left) / rect.width) * drawing.canvas.width,
      y: ((event.clientY - rect.top) / rect.height) * drawing.canvas.height,
    };
  }

  function pointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    const point = getPoint(event);
    if (!point) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const nextStroke: Stroke = { id: `${Date.now()}`, color: activeColor, width: brushSize, points: [point] };
    draftRef.current = nextStroke;
    setDrawing((current) => ({
      ...current,
      strokes: current.strokes,
    }));
  }

  function pointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    const draft = draftRef.current;
    if (!draft) return;
    const point = getPoint(event);
    if (!point) return;
    draft.points = [...draft.points, point];
    draftRef.current = { ...draft };
    setDrawing((current) => ({ ...current, strokes: current.strokes }));
  }

  function pointerUp() {
    const draft = draftRef.current;
    if (!draft) return;
    if (draft.points.length > 0) {
      setDrawing((current) => ({
        ...current,
        strokes: [...current.strokes, draft],
        meta: { ...current.meta, stroke_count: current.strokes.length + 1 },
      }));
    }
    draftRef.current = null;
  }

  async function saveDrawing() {
    if (!noteId) return;
    setSaving(true);
    try {
      const payload = {
        ...DEFAULT_WHITEBOARD_DATA,
        ...drawing,
        theme: drawing.theme,
        strokes: drawing.strokes,
        meta: { ...drawing.meta, stroke_count: drawing.strokes.length },
      };
      if (noteBlockId) {
        const block = await updateDrawingBlock(noteBlockId, payload, "Whiteboard sketch");
        setNoteBlockId(block.id);
      } else {
        const block = await createDrawingBlock(noteId, payload, "Whiteboard sketch");
        setNoteBlockId(block.id);
      }
      const timestamp = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      setSavedAt(timestamp);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="panel-heading">
        <div><span className="panel-eyebrow">DRAWING TOOL</span><h2>Whiteboard</h2></div>
        <button className="icon-button" onClick={close} aria-label="Close whiteboard"><X size={18} /></button>
      </div>

      <div className="whiteboard-toolbar">
        <div className="swatch-row">
          {[
            { name: "Chalk", value: "#edf3d5" },
            { name: "Ink", value: "#dfeaf6" },
            { name: "Red", value: "#f0a4a4" },
            { name: "Green", value: "#bfe7c9" },
            { name: "Amber", value: "#f6d69d" },
          ].map((swatch) => (
            <button
              key={swatch.value}
              type="button"
              className={activeColor === swatch.value ? "swatch-button active" : "swatch-button"}
              style={{ background: swatch.value }}
              onClick={() => setActiveColor(swatch.value)}
              aria-label={`Select ${swatch.name}`}
            />
          ))}
        </div>
        <div className="toolbar-controls">
          <label className="range-wrap">
            <span>Brush</span>
            <input type="range" min="2" max="20" value={brushSize} onChange={(event) => setBrushSize(Number(event.target.value))} />
          </label>
          <select value={drawing.theme} onChange={(event) => setDrawing((current) => ({ ...current, theme: event.target.value as WhiteboardTheme }))}>
            <option value="chalkboard_green">Chalkboard</option>
            <option value="chalkboard_black">Blackboard</option>
            <option value="whiteboard">Whiteboard</option>
          </select>
        </div>
      </div>

      <div className="whiteboard-canvas-wrap">
        <canvas
          ref={canvasRef}
          className="whiteboard-canvas"
          onPointerDown={pointerDown}
          onPointerMove={pointerMove}
          onPointerUp={pointerUp}
          onPointerLeave={pointerUp}
        />
      </div>

      <div className="panel-footer whiteboard-footer">
        <div className="whiteboard-status">
          <strong>{drawing.strokes.length} strokes</strong>
          {savedAt ? <span>Saved {savedAt}</span> : <span>Not saved yet</span>}
        </div>
        <div className="whiteboard-actions">
          <button type="button" className="secondary-button" onClick={() => setDrawing((current) => ({ ...current, strokes: [] }))}>Clear</button>
          <button type="button" className="primary-button" onClick={() => void saveDrawing()} disabled={saving}>
            {saving ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}
            {saving ? "Saving" : "Save"}
          </button>
        </div>
      </div>
    </>
  );
}

function TagReviewPanel({ noteId, close }: { noteId?: string; close: () => void }) {
  const [note, setNote] = useState<Note | null>(null);
  const [saving, setSaving] = useState(false);
  const [tagInput, setTagInput] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!noteId) return;
    let active = true;
    getNote(noteId)
      .then((value) => active && setNote(value))
      .catch(() => active && setNote(null));
    return () => { active = false; };
  }, [noteId]);

  const suggestions = useMemo(() => deriveTagSuggestions(note), [note]);

  async function addTag(name: string) {
    if (!noteId || !name.trim()) return;
    setSaving(true);
    setError("");
    try {
      const tags = await addTagToNote(noteId, name.trim());
      setNote((current) => (current ? { ...current, tags } : current));
      setTagInput("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to add the tag.");
    } finally {
      setSaving(false);
    }
  }

  async function removeTag(slug: string) {
    if (!noteId) return;
    setSaving(true);
    try {
      const tags = await removeTagFromNote(noteId, slug);
      setNote((current) => (current ? { ...current, tags } : current));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to remove the tag.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="panel-heading">
        <div><span className="panel-eyebrow">FAMILY ASSISTANT</span><h2>Tag review</h2></div>
        <button className="icon-button" onClick={close} aria-label="Close tag review"><X size={18} /></button>
      </div>

      <div className="tag-review-body">
        <div className="tag-review-header">
          <span className="staged-icon"><Tag size={18} /></span>
          <strong>AI tag suggestions</strong>
        </div>

        {note ? (
          <>
            <div className="tag-row">
              {note.tags.map((tag) => (
                <span className="tag-chip" key={tag.id}>
                  #{tag.slug}
                  <button type="button" aria-label={`Remove ${tag.slug}`} onClick={() => void removeTag(tag.slug)}>
                    <Trash2 size={12} />
                  </button>
                </span>
              ))}
            </div>

            <div className="tag-entry">
              <input value={tagInput} onChange={(event) => setTagInput(event.target.value)} placeholder="Add a tag" />
              <button type="button" className="primary-button" onClick={() => void addTag(tagInput)} disabled={saving || !tagInput.trim()}>
                Add
              </button>
            </div>

            <div className="suggestion-list">
              {suggestions.length === 0 ? (
                <p className="inline-helper">No high-confidence proposals right now.</p>
              ) : (
                suggestions.map((tag) => (
                  <button key={tag} type="button" className="suggestion-item" onClick={() => void addTag(tag)}>
                    <Sparkles size={14} />
                    <span>#{tag}</span>
                    <small>Proposed</small>
                  </button>
                ))
              )}
            </div>
          </>
        ) : (
          <div className="staged-panel-state compact-state">
            <span className="staged-icon"><PencilLine size={18} /></span>
            <strong>Open a note to review tags</strong>
            <p>Suggestions appear here when a note is active.</p>
          </div>
        )}

        {error && <p className="inline-error" role="alert">{error}</p>}
      </div>
    </>
  );
}

export function PanelHost() {
  const panels = usePanelStore((state) => state.panels);
  const close = usePanelStore((state) => state.close);
  if (panels.length === 0) return null;

  return (
    <aside className="panel-rail" aria-label="Open panels">
      {panels.map((panel) => (
        <section className="slide-panel" key={`${panel.kind}-${panel.noteId ?? "root"}`} aria-label={`${panel.kind} panel`}>
          {panel.kind === "capture" ? (
            <CapturePanel close={() => close(panel.kind)} />
          ) : panel.kind === "whiteboard" ? (
            <WhiteboardPanel noteId={panel.noteId} close={() => close(panel.kind)} />
          ) : (
            <TagReviewPanel noteId={panel.noteId} close={() => close(panel.kind)} />
          )}
        </section>
      ))}
    </aside>
  );
}