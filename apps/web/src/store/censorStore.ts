// apps/web/src/store/censorStore.ts
import { create } from "zustand";

type CensorState = {
  enabled: boolean;
  toggle: () => void;
  set: (v: boolean) => void;
};

export const useCensorStore = create<CensorState>((set) => ({
  enabled: false,
  toggle: () => set((s) => ({ enabled: !s.enabled })),
  set: (v) => set({ enabled: v }),
}));
