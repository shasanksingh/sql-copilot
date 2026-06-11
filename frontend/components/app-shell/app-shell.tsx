"use client";

import type React from "react";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { CommandPalette } from "./command-palette";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { AnimatePresence, motion } from "framer-motion";

export function AppShell({ children }: { children: React.ReactNode }) {
  const mobileSidebarOpen = useCopilotStore((state) => state.mobileSidebarOpen);
  const setMobileSidebarOpen = useCopilotStore((state) => state.setMobileSidebarOpen);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <AnimatePresence>
        {mobileSidebarOpen ? (
          <motion.div className="fixed inset-0 z-40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <button className="absolute inset-0 bg-slate-950/70" onClick={() => setMobileSidebarOpen(false)} aria-label="Close navigation" />
            <motion.div initial={{ x: -320 }} animate={{ x: 0 }} exit={{ x: -320 }} transition={{ type: "spring", damping: 28, stiffness: 280 }} className="relative h-full">
              <Sidebar mobile />
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
