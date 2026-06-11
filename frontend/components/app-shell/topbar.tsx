"use client";

import { Command, Menu, Moon, Search, SidebarIcon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { Badge } from "@/components/ui/badge";

export function Topbar() {
  const collapsed = useCopilotStore((state) => state.sidebarCollapsed);
  const setCollapsed = useCopilotStore((state) => state.setSidebarCollapsed);
  const setMobileSidebarOpen = useCopilotStore((state) => state.setMobileSidebarOpen);
  const setCommandPaletteOpen = useCopilotStore((state) => state.setCommandPaletteOpen);
  const theme = useCopilotStore((state) => state.theme);
  const setTheme = useCopilotStore((state) => state.setTheme);

  return (
    <header className="flex h-16 items-center gap-3 border-b border-white/10 bg-slate-950/55 px-4 backdrop-blur-xl">
      <Button variant="ghost" className="h-9 w-9 px-0 lg:hidden" onClick={() => setMobileSidebarOpen(true)} aria-label="Open menu">
        <Menu className="h-4 w-4" />
      </Button>
      <Button variant="ghost" className="hidden h-9 w-9 px-0 lg:inline-flex" onClick={() => setCollapsed(!collapsed)} aria-label="Toggle sidebar">
        <SidebarIcon className="h-4 w-4" />
      </Button>
      <div className="relative max-w-xl flex-1">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
        <Input className="pl-9" placeholder="Search tables, queries, plans, commands" onFocus={() => setCommandPaletteOpen(true)} readOnly />
      </div>
      <Badge tone="emerald" className="hidden sm:inline-flex">API ready</Badge>
      <Button variant="outline" className="hidden h-9 gap-2 px-3 md:inline-flex" onClick={() => setCommandPaletteOpen(true)}>
        <Command className="h-4 w-4" />
        Command
      </Button>
      <Button variant="outline" className="h-9 w-9 px-0" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">
        {theme === "dark" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
      </Button>
    </header>
  );
}
