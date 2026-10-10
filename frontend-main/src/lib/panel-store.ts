import { create } from "zustand";
import type { PanelKind } from "@/lib/navigation";

type PanelItem = { kind: PanelKind; noteId?: string; blockId?: string };

type PanelState = {
  panels: PanelItem[];
  open: (kind: PanelKind, noteId?: string, blockId?: string) => void;
  close: (kind: PanelKind) => void;
  closeTop: () => void;
};

export const usePanelStore = create<PanelState>((set) => ({
  panels: [],
  open: (kind, noteId, blockId) =>
    set((state) => {
      // The whiteboard panel is keyed per drawing block, so opening a second
      // drawing must not replace the first. Other panels stay singletons.
      const panels = state.panels.filter((panel) =>
        kind === "whiteboard" ? !(panel.kind === kind && panel.blockId === blockId) : panel.kind !== kind,
      );
      return { panels: [...panels, { kind, noteId, blockId }] };
    }),
  close: (kind) => set((state) => ({ panels: state.panels.filter((panel) => panel.kind !== kind) })),
  closeTop: () => set((state) => ({ panels: state.panels.slice(0, -1) })),
}));