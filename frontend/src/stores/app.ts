import { create } from "zustand";

interface AppState {
  aoiId: string | null;
  setAoiId: (id: string | null) => void;
  focus: { bbox: [number, number, number, number]; key: number } | null;
  focusOn: (bbox: [number, number, number, number]) => void;
}

const initialAoi = (() => {
  try {
    return localStorage.getItem("sylva.aoi");
  } catch {
    return null;
  }
})();

export const useApp = create<AppState>((set) => ({
  aoiId: initialAoi,
  setAoiId: (id) => {
    try {
      if (id) localStorage.setItem("sylva.aoi", id);
    } catch {
      /* storage unavailable */
    }
    set({ aoiId: id });
  },
  focus: null,
  focusOn: (bbox) => set({ focus: { bbox, key: Date.now() } }),
}));
