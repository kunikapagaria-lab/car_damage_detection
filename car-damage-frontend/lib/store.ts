import { create } from 'zustand';
import type { WSInspectionFrame } from '@/types';

// ── Live feed slice ───────────────────────────────────────────────────────────

interface LiveSlice {
  frames: Record<string, WSInspectionFrame>; // keyed by camera_id
  wsStatus: 'connecting' | 'connected' | 'disconnected';
  alertQueue: WSInspectionFrame[];
  scansTodayCount: number;
  newDamageCount: number;
  setFrame: (frame: WSInspectionFrame) => void;
  setWsStatus: (s: 'connecting' | 'connected' | 'disconnected') => void;
  addAlert: (frame: WSInspectionFrame) => void;
  resetDailyCounters: () => void;
}

// ── Comparison slice ──────────────────────────────────────────────────────────

interface CompareSlice {
  comparisonScanIds: [string | null, string | null];
  setComparisonScanId: (idx: 0 | 1, id: string | null) => void;
  clearComparison: () => void;
}

type Store = LiveSlice & CompareSlice;

export const useStore = create<Store>((set) => ({
  // Live feed
  frames: {},
  wsStatus: 'disconnected',
  alertQueue: [],
  scansTodayCount: 0,
  newDamageCount: 0,

  setFrame: (frame) =>
    set((s) => ({
      frames: { ...s.frames, [frame.camera_id]: frame },
      scansTodayCount: s.scansTodayCount + 1,
    })),

  setWsStatus: (wsStatus) => set({ wsStatus }),

  addAlert: (frame) =>
    set((s) => ({
      alertQueue: [frame, ...s.alertQueue].slice(0, 100),
      newDamageCount: s.newDamageCount + frame.n_damages,
    })),

  resetDailyCounters: () =>
    set({ scansTodayCount: 0, newDamageCount: 0 }),

  // Comparison
  comparisonScanIds: [null, null],

  setComparisonScanId: (idx, id) =>
    set((s) => {
      const pair: [string | null, string | null] = [
        s.comparisonScanIds[0],
        s.comparisonScanIds[1],
      ];
      pair[idx] = id;
      return { comparisonScanIds: pair };
    }),

  clearComparison: () => set({ comparisonScanIds: [null, null] }),
}));
