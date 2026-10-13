"use client";

import { Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export type StatusDropdownProps = {
  statuses: string[];
  onChange: (statuses: string[]) => void;
  allStatuses: readonly string[];
  label?: string;
};

/**
 * Multi-select dropdown for filtering notes by status.
 *
 * Shows a compact button ("Status" or "All statuses"); clicking opens a
 * menu with a checkbox row per status. Toggle on/off; an "All" row
 * selects everything and a "None" row clears.
 *
 * Reuses the same outside-click / Escape handling as BlockMenu so the
 * two feel identical to the user.
 */
export function StatusDropdown({
  statuses,
  onChange,
  allStatuses,
  label = "Status filter",
}: StatusDropdownProps) {
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

  const allSelected = statuses.length === allStatuses.length;
  const noneSelected = statuses.length === 0;

  function toggle(value: string) {
    onChange(
      statuses.includes(value)
        ? statuses.filter((item) => item !== value)
        : [...statuses, value],
    );
  }

  function selectAll() {
    onChange([...allStatuses]);
  }

  function selectNone() {
    onChange([]);
  }

  const summary =
    allSelected
      ? "All statuses"
      : noneSelected
        ? "No statuses"
        : `${statuses.length} selected`;

  return (
    <div className="status-dropdown" ref={ref}>
      <button
        type="button"
        className={`status-dropdown-button${open ? " status-dropdown-button-open" : ""}`}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="status-dropdown-summary">{summary}</span>
        <ChevronDown
          size={14}
          className={`status-dropdown-chevron${open ? " status-dropdown-chevron-open" : ""}`}
        />
      </button>
      {open && (
        <div className="status-dropdown-menu" role="menu" aria-label="Filter by status">
          <div className="status-dropdown-actions">
            <button
              type="button"
              role="menuitem"
              className="status-dropdown-action"
              onClick={selectAll}
            >
              All
            </button>
            <button
              type="button"
              role="menuitem"
              className="status-dropdown-action"
              onClick={selectNone}
            >
              None
            </button>
          </div>
          <div className="status-dropdown-divider" />
          {allStatuses.map((value) => {
            const on = statuses.includes(value);
            return (
              <button
                key={value}
                type="button"
                role="menuitemcheckbox"
                aria-checked={on}
                className="status-dropdown-item"
                onClick={() => toggle(value)}
              >
                <span className={`status-dropdown-checkbox${on ? " status-dropdown-checkbox-on" : ""}`}>
                  {on && <Check size={12} strokeWidth={3} />}
                </span>
                <span className="status-dropdown-item-label">{value}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
