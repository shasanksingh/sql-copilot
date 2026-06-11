"use client";

import { create } from "zustand";
import type { CopilotResponse } from "@/features/api/types";

type ThemeMode = "dark" | "light";

type CopilotState = {
  sidebarCollapsed: boolean;
  mobileSidebarOpen: boolean;
  commandPaletteOpen: boolean;
  theme: ThemeMode;
  history: CopilotResponse[];
  activeResponse?: CopilotResponse;
  setSidebarCollapsed: (value: boolean) => void;
  setMobileSidebarOpen: (value: boolean) => void;
  setCommandPaletteOpen: (value: boolean) => void;
  setTheme: (theme: ThemeMode) => void;
  addResponse: (response: CopilotResponse) => void;
  setActiveResponse: (response?: CopilotResponse) => void;
};

export const useCopilotStore = create<CopilotState>((set) => ({
  sidebarCollapsed: false,
  mobileSidebarOpen: false,
  commandPaletteOpen: false,
  theme: "dark",
  history: [],
  setSidebarCollapsed: (value) => set({ sidebarCollapsed: value }),
  setMobileSidebarOpen: (value) => set({ mobileSidebarOpen: value }),
  setCommandPaletteOpen: (value) => set({ commandPaletteOpen: value }),
  setTheme: (theme) => set({ theme }),
  addResponse: (response) =>
    set((state) => ({
      history: [response, ...state.history].slice(0, 20),
      activeResponse: response
    })),
  setActiveResponse: (response) => set({ activeResponse: response })
}));
