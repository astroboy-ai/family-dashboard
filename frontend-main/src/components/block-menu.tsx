"use client";

import { MoreVertical } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export type BlockMenuItem = {
  label: string;
  action: () => void;
  danger?: boolean;
};

/**
 * Small ⋮ menu for a block.
 *
 * Used for per-block actions that should not clutter the block itself — notably
 * "Analyse with AI" on an image, which replaced the old modal that asked about
 * every single upload.
 */
export function BlockMenu({ items, label = "Block actions" }: { items: BlockMenuItem[]; label?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="block-menu" ref={ref}>
      <button
        type="button"
        className="icon-button small-icon"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <MoreVertical size={15} />
      </button>
      {open && (
        <div className="block-menu-list" role="menu">
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className={item.danger ? "block-menu-item danger" : "block-menu-item"}
              onClick={() => {
                setOpen(false);
                item.action();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
