"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import Link from "next/link";
import { Bell, ChevronDown, Command, Compass, LayoutDashboard, LogOut, Menu, Moon, Search, Sun, UserCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { useAuth } from "@/features/auth/auth-provider";
import { usePathname, useRouter } from "next/navigation";
import { Icon3D } from "@/components/ui/icon-3d";
import { navItems } from "./sidebar";

export function Topbar() {
  const router = useRouter();
  const pathname = usePathname();
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
  const currentPage = navItems.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));
  const availableNavItems = navItems.filter((item) => !item.admin || user?.role === "admin");

  return (
    <header className="flex h-16 shrink-0 items-center gap-2 border-b border-white/10 bg-white/[0.06] px-3 backdrop-blur-xl dark:bg-slate-950/70 sm:gap-3 sm:px-4 md:px-5">
      <Button variant="ghost" className="h-9 w-9 px-0 lg:hidden" onClick={() => setMobileSidebarOpen(true)} aria-label="Open menu">
        <Menu className="h-4 w-4" />
      </Button>
      <div className="hidden min-w-0 items-center gap-2 lg:flex">
        <Icon3D icon={currentPage?.icon ?? LayoutDashboard} tone={currentPage?.tone ?? "cyan"} size="sm" />
        <div className="min-w-0">
          <div className="max-w-40 truncate text-sm font-semibold text-white">{currentPage?.label ?? "SQL Copilot"}</div>
          <div className="text-[10px] uppercase text-slate-500">Workspace</div>
        </div>
      </div>
      <div className="relative min-w-0 max-w-xl flex-1">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
        <Input className="pl-9" placeholder="Search tables, queries, plans, commands" onFocus={() => setCommandPaletteOpen(true)} readOnly />
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <Button variant="outline" className="hidden h-9 gap-2 px-2.5 md:inline-flex" aria-label="Jump to workspace page">
              <Icon3D icon={Compass} tone="cyan" size="xs" />
              <span className="hidden xl:inline">Jump</span>
              <ChevronDown className="h-3.5 w-3.5" />
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={8}
              className="z-50 w-64 rounded-lg border border-slate-200/80 bg-white/95 p-2 shadow-2xl backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/95"
            >
              <div className="px-2 pb-2 pt-1 text-[10px] font-semibold uppercase tracking-normal text-slate-500">
                Workspace
              </div>
              {availableNavItems.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);

                return (
                  <DropdownMenu.Item key={item.href} asChild>
                    <Link
                      href={item.href}
                      className={[
                        "group flex h-10 items-center gap-3 rounded-md px-2 text-sm outline-none transition",
                        active
                          ? "bg-cyan-300/15 text-cyan-700 ring-1 ring-cyan-300/20 dark:text-cyan-100"
                          : "text-slate-600 hover:bg-slate-900/[0.06] hover:text-slate-950 focus:bg-slate-900/[0.06] dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white dark:focus:bg-white/10"
                      ].join(" ")}
                      aria-current={active ? "page" : undefined}
                    >
                      <Icon3D icon={item.icon} tone={active ? item.tone : "slate"} size="xs" />
                      <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    </Link>
                  </DropdownMenu.Item>
                );
              })}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        <Button variant="outline" className="hidden h-9 gap-2 px-3 lg:inline-flex" onClick={() => setCommandPaletteOpen(true)}>
          <Command className="h-4 w-4" />
          <span className="hidden xl:inline">Command</span>
        </Button>
      <Button variant="outline" className="h-9 w-9 px-0" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">
        {theme === "dark" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
      </Button>
      <Button variant="outline" className="hidden h-9 w-9 px-0 xl:inline-flex" aria-label="Notifications">
        <Bell className="h-4 w-4" />
      </Button>
      <div className="hidden min-w-0 items-center gap-2 rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-1.5 2xl:flex">
        <UserCircle className="h-4 w-4" />
        <div className="min-w-0">
          <div className="max-w-28 truncate text-xs font-medium text-white">{user?.name}</div>
          <div className="text-[10px] uppercase text-slate-500">{user?.role}</div>
        </div>
      </div>
      <Button variant="outline" className="h-9 w-9 px-0" onClick={signOut} aria-label="Sign out" title="Sign out">
        <LogOut className="h-4 w-4" />
      </Button>
      </div>
    </header>
  );
}
