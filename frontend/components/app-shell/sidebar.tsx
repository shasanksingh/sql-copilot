"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Bot,
  Braces,
  Database,
  GitBranch,
  LayoutDashboard,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  PlayCircle,
  Settings,
  ShieldCheck,
  Sparkles,
  X,
  Zap
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";

type NavItem = {
  href: Route;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  admin?: boolean;
};

export const navItems: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: LayoutDashboard
  },
  {
    href: "/copilot",
    label: "SQL Copilot",
    icon: Bot
  },
  {
    href: "/schema-explorer",
    label: "Schema Explorer",
    icon: Database
  },
  {
    href: "/schema-graph",
    label: "Schema Graph",
    icon: GitBranch
  },
  {
    href: "/data-model-studio",
    label: "Data Model Studio",
    icon: Network
  },
  {
    href: "/execution",
    label: "Query Execution",
    icon: PlayCircle
  },
  {
    href: "/planner",
    label: "Query Planner",
    icon: Braces
  },
  {
    href: "/optimizer",
    label: "SQL Optimizer",
    icon: Zap
  },
  {
    href: "/settings",
    label: "Settings",
    icon: Settings
  },
  {
    href: "/admin/schema-requests",
    label: "Admin Review",
    icon: ShieldCheck,
    admin: true
  }
];

export function Sidebar({ mobile = false }: { mobile?: boolean }) {
  const { user } = useAuth();
  const pathname = usePathname();

  const collapsed = useCopilotStore(
    (state) => state.sidebarCollapsed
  );

  const setMobileSidebarOpen = useCopilotStore(
    (state) => state.setMobileSidebarOpen
  );
  const setCollapsed = useCopilotStore(
    (state) => state.setSidebarCollapsed
  );

  const compact = collapsed && !mobile;

  return (
    <aside
      className={cn(
        "flex h-full flex-col overflow-hidden border-r border-white/10 bg-slate-950/78 backdrop-blur-xl transition-[width] duration-300 ease-out",
        mobile ? "w-80 max-w-[86vw]" : "hidden lg:flex",
        compact ? "w-20" : "w-72"
      )}
    >
      <div className="flex h-16 items-center gap-3 border-b border-white/10 px-5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-cyan-300 to-indigo-400 text-slate-950 shadow-glow">
          <Sparkles className="h-5 w-5" />
        </div>

        {!compact && (
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-white">
              SQL Copilot
            </div>

            <div className="text-xs text-slate-500">
              Enterprise AI workspace
            </div>
          </div>
        )}

        {mobile ? (
          <Button
            variant="ghost"
            className="h-8 w-8 px-0"
            onClick={() => setMobileSidebarOpen(false)}
            aria-label="Close menu"
          >
            <X className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            variant="ghost"
            className="hidden h-8 w-8 px-0 lg:inline-flex"
            onClick={() => setCollapsed(!collapsed)}
            aria-label="Collapse sidebar"
            title={compact ? "Expand sidebar" : "Collapse sidebar"}
          >
            {compact ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </Button>
        )}
      </div>

      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto p-3 scrollbar-thin">
        {navItems.filter((item) => !item.admin || user?.role === "admin").map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() =>
                mobile && setMobileSidebarOpen(false)
              }
              className={cn(
                "flex h-10 items-center gap-3 rounded-md px-3 text-sm text-slate-400 transition hover:bg-white/10 hover:text-white",
                active &&
                  "bg-cyan-300/15 text-cyan-100 ring-1 ring-cyan-300/15"
              )}
              title={compact ? item.label : undefined}
            >
              <Icon className="h-4 w-4 shrink-0" />

              {!compact && (
                <span className="truncate">
                  {item.label}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {!compact && (
        <div className="m-4 rounded-lg border border-cyan-300/20 bg-gradient-to-br from-cyan-300/10 to-indigo-400/10 p-4">
          <BarChart3 className="mb-3 h-5 w-5 text-cyan-200" />

          <div className="text-sm font-medium text-white">
            LLM-free mode
          </div>

          <p className="mt-1 text-xs leading-5 text-slate-400">
            Schema graph, validation, confidence gating,
            and explainability are handled locally.
          </p>
        </div>
      )}
    </aside>
  );
}
