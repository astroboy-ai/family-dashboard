"use client";

import { ArrowRight, CornerDownLeft, Plus, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { navigation } from "@/lib/navigation";
import { usePanelStore } from "@/lib/panel-store";

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const openPanel = usePanelStore((state) => state.open);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (open) setQuery("");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose, open]);

  const items = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return navigation.filter((item) => !normalized || item.label.toLowerCase().includes(normalized));
  }, [query]);

  if (!open) return null;

  function go(href: string) {
    router.push(href);
    onClose();
  }

  function runQuery() {
    if (!query.trim()) return;
    go(`/search?q=${encodeURIComponent(query.trim())}`);
  }

  return (
    <div className="palette-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="palette-input-row">
          <Search size={19} />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && runQuery()}
            placeholder="Search notes or jump to…"
            aria-label="Search notes or navigate"
          />
          <kbd>ESC</kbd>
        </div>
        <div className="palette-results">
          {query.trim() && (
            <button className="palette-result palette-action" onClick={runQuery}>
              <Search size={17} />
              <span>Search everything for <strong>“{query.trim()}”</strong></span>
              <CornerDownLeft size={15} />
            </button>
          )}
          <div className="palette-section-label">Navigate</div>
          {items.slice(0, 8).map(({ href, label, icon: Icon }) => (
            <button className="palette-result" key={href} onClick={() => go(href)}>
              <Icon size={17} /> <span>{label}</span> <ArrowRight size={15} />
            </button>
          ))}
          <div className="palette-section-label">Quick actions</div>
          <button className="palette-result" onClick={() => { openPanel("capture"); onClose(); }}>
            <Plus size={17} /> <span>Create a note</span> <kbd>C</kbd>
          </button>
          <div className="palette-footer">Navigate with the keyboard · search state is shareable in the URL</div>
        </div>
      </section>
    </div>
  );
}