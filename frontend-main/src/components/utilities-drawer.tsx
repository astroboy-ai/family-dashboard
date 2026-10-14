"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import { UtilityBody, utilities, useIsNarrow, type Utility } from "@/components/utilities-tools";

/**
 * Global utilities picker.
 *
 * Reached from the top nav Tools button on every page, so no tool needs a
 * route of its own. The list is grouped by the registry's `group`; groups
 * collapse so a long list stays usable, and search filters across
 * label + description.
 *
 * Once a tool is open the panel belongs to it — the tool keeps its own
 * header, and that header's close button is what closes the drawer.
 */
export function UtilitiesDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const narrow = useIsNarrow();

  // Land on the picker every time it opens.
  useEffect(() => {
    if (open) {
      setActiveId(null);
      setQuery("");
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const visible = utilities.filter(
      (u) =>
        !q ||
        u.label.toLowerCase().includes(q) ||
        u.description.toLowerCase().includes(q),
    );
    const out: { group: string; items: Utility[] }[] = [];
    for (const u of visible) {
      const last = out[out.length - 1];
      if (last && last.group === u.group) last.items.push(u);
      else out.push({ group: u.group, items: [u] });
    }
    return out;
  }, [query]);

  if (!open) return null;

  const active = utilities.find((u) => u.id === activeId) ?? null;

  function pick(u: Utility) {
    if (u.desktopOnly && narrow) return;
    setActiveId(u.id);
  }

  return (
    <>
      <button
        type="button"
        className="utilities-drawer-scrim"
        aria-label="Close utilities"
        onClick={onClose}
      />
      <aside className="utilities-drawer" role="dialog" aria-modal="true" aria-label="Utilities">
        {!active ? (
          <>
            <div className="utilities-drawer-head">
              <strong>Utilities</strong>
              <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            <label className="search-field utilities-drawer-search">
              <Search size={15} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search tools…"
                aria-label="Search utilities"
              />
            </label>
            <nav className="utilities-drawer-groups">
              {groups.length === 0 && <p className="inline-helper">No tools match “{query}”.</p>}
              {groups.map(({ group, items }) => {
                const isCollapsed = collapsed[group] ?? false;
                return (
                  <section className="utilities-drawer-group" key={group}>
                    <button
                      type="button"
                      className="utilities-drawer-group-head"
                      onClick={() =>
                        setCollapsed((current) => ({ ...current, [group]: !current[group] }))
                      }
                      aria-expanded={!isCollapsed}
                    >
                      <span>{group}</span>
                      <span className="utilities-drawer-group-count">{items.length}</span>
                      <ChevronDown size={14} className={isCollapsed ? "utilities-chevron-closed" : ""} />
                    </button>
                    {!isCollapsed && (
                      <div className="utilities-drawer-items">
                        {items.map((utility) => {
                          const Icon = utility.icon;
                          const blocked = Boolean(utility.desktopOnly && narrow);
                          return (
                            <button
                              key={utility.id}
                              type="button"
                              className={`utilities-drawer-item${blocked ? " blocked" : ""}`}
                              onClick={() => pick(utility)}
                              disabled={blocked}
                              title={blocked ? "Desktop only" : undefined}
                            >
                              <span className="utilities-drawer-icon">
                                <Icon size={17} />
                              </span>
                              <span className="utilities-drawer-text">
                                <span className="utilities-drawer-label">
                                  {utility.label}
                                  {blocked && <em className="utilities-drawer-badge">desktop</em>}
                                </span>
                                <span className="utilities-drawer-desc">{utility.description}</span>
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </section>
                );
              })}
            </nav>
          </>
        ) : (
          <UtilityBody id={active.id} onClose={onClose} />
        )}
      </aside>
    </>
  );
}
