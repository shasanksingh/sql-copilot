"use client";

import { Bell, Command, LogOut, Menu, Moon, Search, Sun, UserCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/features/auth/auth-provider";
import { useRouter } from "next/navigation";

export function Topbar() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const setMobileSidebarOpen = useCopilotStore((state) => state.setMobileSidebarOpen);
  const setCommandPaletteOpen = useCopilotStore((state) => state.setCommandPaletteOpen);
  const theme = useCopilotStore((state) => state.theme);
  const setTheme = useCopilotStore((state) => state.setTheme);
  const signOut = async () => {
    await logout();
    router.replace("/login");
    router.refresh();
  };

  return (
    <header className="flex h-16 shrink-0 items-center gap-2 border-b border-white/10 bg-slate-950/70 px-3 backdrop-blur-xl sm:gap-3 sm:px-4">
      <Button variant="ghost" className="h-9 w-9 px-0 lg:hidden" onClick={() => setMobileSidebarOpen(true)} aria-label="Open menu">
        <Menu className="h-4 w-4" />
      </Button>
      <div className="relative min-w-0 max-w-xl flex-1">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
        <Input className="pl-9" placeholder="Search tables, queries, plans, commands" onFocus={() => setCommandPaletteOpen(true)} readOnly />
      </div>
      <div className="hidden min-w-0 flex-1 justify-center xl:flex">
        <div className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-slate-300">
          Enterprise Data Intelligence Workspace
        </div>
      </div>
      <Badge tone="emerald" className="hidden md:inline-flex">Protected</Badge>
      <Button variant="outline" className="hidden h-9 gap-2 px-3 md:inline-flex" onClick={() => setCommandPaletteOpen(true)}>
        <Command className="h-4 w-4" />
        Command
      </Button>
      <Button variant="outline" className="h-9 w-9 px-0" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">
        {theme === "dark" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
      </Button>
      <Button variant="outline" className="hidden h-9 w-9 px-0 sm:inline-flex" aria-label="Notifications">
        <Bell className="h-4 w-4" />
      </Button>
      <div className="hidden min-w-0 items-center gap-2 rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-1.5 xl:flex">
        <UserCircle className="h-4 w-4" />
        <div className="min-w-0">
          <div className="max-w-28 truncate text-xs font-medium text-white">{user?.name}</div>
          <div className="text-[10px] uppercase text-slate-500">{user?.role}</div>
        </div>
      </div>
      <Button variant="outline" className="h-9 w-9 px-0" onClick={signOut} aria-label="Sign out" title="Sign out">
        <LogOut className="h-4 w-4" />
      </Button>
    </header>
  );
}
