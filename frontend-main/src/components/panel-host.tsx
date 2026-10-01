"use client";

import { Check, LoaderCircle, Sparkles, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createNote } from "@/lib/api";
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

function StagedPanel({ kind, close }: { kind: "whiteboard" | "hermes"; close: () => void }) {
  const isWhiteboard = kind === "whiteboard";
  return (
    <>
      <div className="panel-heading">
        <div><span className="panel-eyebrow">{isWhiteboard ? "DRAWING TOOL" : "FAMILY ASSISTANT"}</span><h2>{isWhiteboard ? "Whiteboard" : "Hermes"}</h2></div>
        <button className="icon-button" onClick={close} aria-label={`Close ${kind}`}><X size={18} /></button>
      </div>
      <div className="staged-panel-state">
        <span className="staged-icon">{isWhiteboard ? "04" : <Sparkles size={22} />}</span>
        <strong>{isWhiteboard ? "Canvas stage follows" : "Agent runtime follows"}</strong>
        <p>{isWhiteboard ? "The panel host is ready. The drawing canvas and note persistence are in the next Add-on 04 stage." : "The panel host is ready. Chat connects when the Hermes API and confirmation flow land."}</p>
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
        <section className="slide-panel" key={panel.kind} aria-label={`${panel.kind} panel`}>
          {panel.kind === "capture" ? (
            <CapturePanel close={() => close(panel.kind)} />
          ) : (
            <StagedPanel kind={panel.kind} close={() => close(panel.kind)} />
          )}
        </section>
      ))}
    </aside>
  );
}