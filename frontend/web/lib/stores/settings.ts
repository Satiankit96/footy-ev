import { create } from "zustand";

export interface OperatorSettings {
  theme: "dark" | "light" | "system";
  density: "comfortable" | "compact";
  default_page_size: 25 | 50 | 100;
  default_time_range_days: 7 | 14 | 30 | 90;
}

const DEFAULTS: OperatorSettings = {
  theme: "system",
  density: "comfortable",
  default_page_size: 50,
  default_time_range_days: 30,
};

interface SettingsStore {
  settings: OperatorSettings;
  loaded: boolean;
  setSettings: (s: OperatorSettings) => void;
  updateSetting: <K extends keyof OperatorSettings>(key: K, value: OperatorSettings[K]) => void;
}

export const useSettingsStore = create<SettingsStore>((set) => ({
  settings: DEFAULTS,
  loaded: false,
  setSettings: (settings) => set({ settings, loaded: true }),
  updateSetting: (key, value) =>
    set((state) => ({
      settings: { ...state.settings, [key]: value },
    })),
}));
