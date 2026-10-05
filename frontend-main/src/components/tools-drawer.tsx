"use client";

import { useEffect, useState } from "react";
import {
  CalendarDays,
  CheckSquare,
  Clock,
  Coins,
  File,
  Image,
  Link2,
  Lock,
  MapPin,
  Mic,
  PenTool,
  Search,
  Share2,
  ShieldCheck,
  Table,
  X,
} from "lucide-react";

export type ToolId =
  | "photo"
  | "file"
  | "drawing"
  | "voice"
  | "checkbox"
  | "date"
  | "time"
  | "currency"
  | "password"
  | "location"
  | "table"
  | "reminder"
  | "lock"
  | "link"
  | "share";

export type Tool = {
  id: ToolId;
  label: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  group: "media" | "fields" | "structure" | "actions";
};

export const tools: Tool[] = [
  { id: "photo", label: "Photo", icon: Image, group: "media" },
  { id: "file", label: "File", icon: File, group: "media" },
  { id: "drawing", label: "Draw", icon: PenTool, group: "media" },
  { id: "voice", label: "Voice", icon: Mic, group: "media" },
  { id: "location", label: "Location", icon: MapPin, group: "media" },
  { id: "checkbox", label: "Checkbox", icon: CheckSquare, group: "fields" },
  { id: "date", label: "Date", icon: CalendarDays, group: "fields" },
  { id: "time", label: "Time", icon: Clock, group: "fields" },
  { id: "currency", label: "Money", icon: Coins, group: "fields" },
  { id: "password", label: "Password", icon: ShieldCheck, group: "fields" },
  { id: "table", label: "Table", icon: Table, group: "structure" },
  { id: "reminder", label: "Reminder", icon: Clock, group: "actions" },
  { id: "link", label: "Link note", icon: Link2, group: "actions" },
  { id: "lock", label: "Lock", icon: Lock, group: "actions" },
  { id: "share", label: "Share", icon: Share2, group: "actions" },
];

const groupLabels: Record<Tool["group"], string> = {
  media: "MEDIA",
  fields: "FIELDS",
  structure: "STRUCTURE",
  actions: "ACTIONS",
};

const RECENT_KEY = "familyos-recent-tools";
const RECENT_LIMIT = 4;

function readRecent(): ToolId[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? (parsed.filter((id) => typeof id === "string") as ToolId[]) : [];
  } catch {
    return [];
  }
}

export function ToolsDrawer({
  open,
  onClose,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (tool: Tool) => void;
}) {
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<ToolId[]>([]);

  useEffect(() => {
    if (open) setRecent(readRecent());
  }, [open]);

  if (!open) return null;

  function choose(tool: Tool) {
    // Remember what gets used so the common tools sit at the top next time and
    // the user stops scrolling for them.
    try {
      const next = [tool.id, ...readRecent().filter((id) => id !== tool.id)].slice(0, RECENT_LIMIT);
      window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    } catch {
      // Storage unavailable: the grid still works, just without ordering.
    }
    onSelect(tool);
    onClose();
  }

  const filtered = tools.filter(
    (tool) =>
      tool.label.toLowerCase().includes(query.toLowerCase()) ||
      tool.group.toLowerCase().includes(query.toLowerCase()),
  );

  const recentTools = recent
    .map((id) => tools.find((tool) => tool.id === id))
    .filter((tool): tool is Tool => Boolean(tool));

  const groups: Tool["group"][] = ["media", "fields", "structure", "actions"];

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2>Tools</h2>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="drawer-search">
          <Search size={16} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tools…"
          />
        </div>
        <div className="drawer-body">
          {recentTools.length > 0 && !query && (
            <div className="drawer-group">
              <p className="drawer-group-label">RECENT</p>
              <div className="drawer-grid">
                {recentTools.map((tool) => {
                  const Icon = tool.icon;
                  return (
                    <button key={`recent-${tool.id}`} className="drawer-item" onClick={() => choose(tool)}>
                      <Icon size={16} />
                      <span>{tool.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {groups.map((group) => {
            const groupTools = filtered.filter((t) => t.group === group);
            if (groupTools.length === 0) return null;
            return (
              <div key={group} className="drawer-group">
                <p className="drawer-group-label">{groupLabels[group]}</p>
                <div className="drawer-grid">
                  {groupTools.map((tool) => {
                    const Icon = tool.icon;
                    return (
                      <button
                        key={tool.id}
                        className="drawer-item"
                        onClick={() => choose(tool)}
                      >
                        <Icon size={16} />
                        <span>{tool.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
