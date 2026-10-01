import { create } from "zustand";
import type { PanelKind } from "@/lib/navigation";

type PanelItem = { kind: PanelKind; noteId?: string };

type PanelState = {
  panels: PanelItem[];
  open: (kind: PanelKind, noteId?: string) => void;
  close: (kind: PanelKind) => void;
  closeTop: () => void;
};

export const usePanelStore = create<PanelState>((set) => ({
  panels: [],
  open: (kind, noteId) =>
    set((state) => {
      const panels = state.panels.filter((panel) => panel.kind !== kind);
      return { panels: [...panels, { kind, noteId }] };
    }),
  close: (kind) => set((state) => ({ panels: state.panels.filter((panel) => panel.kind !== kind) })),
  closeTop: () => set((state) => ({ panels: state.panels.slice(0, -1) })),
}));