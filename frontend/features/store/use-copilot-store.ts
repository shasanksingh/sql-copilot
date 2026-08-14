"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
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
  deleteResponse: (index: number) => void;
  clearHistory: () => void;
};

export const useCopilotStore = create<CopilotState>()(
  persist(
    (set) => ({
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
          history: [...state.history, response].slice(-50),
          activeResponse: response
        })),
      setActiveResponse: (response) => set({ activeResponse: response }),
      deleteResponse: (index) =>
        set((state) => {
          const nextHistory = state.history.filter((_, itemIndex) => itemIndex !== index);
          return {
            history: nextHistory,
            activeResponse: nextHistory.includes(state.activeResponse as CopilotResponse)
              ? state.activeResponse
              : nextHistory.at(-1)
          };
        }),
      clearHistory: () => set({ history: [], activeResponse: undefined })
    }),
    {
      name: "sql-copilot-ui",
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        theme: state.theme,
        history: state.history,
        activeResponse: state.activeResponse
      })
    }
  )
);
