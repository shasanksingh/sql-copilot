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
  X,
  Zap,
  type LucideIcon
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import { Icon3D, type Icon3DTone } from "@/components/ui/icon-3d";

type NavItem = {
  href: Route;
  label: string;
  icon: LucideIcon;
  tone: Icon3DTone;
  admin?: boolean;
};

export const navItems: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    tone: "cyan"
  },
  {
    href: "/copilot",
    label: "SQL Copilot",
    icon: Bot,
    tone: "cyan"
  },
  {
    href: "/schema-explorer",
    label: "Schema Explorer",
    icon: Database,
    tone: "indigo"
  },
  {
    href: "/schema-graph",
    label: "Schema Graph",
    icon: GitBranch,
    tone: "cyan"
  },
  {
    href: "/data-model-studio",
    label: "Data Model Studio",
    icon: Network,
    tone: "indigo"
  },
  {
    href: "/execution",
    label: "Query Execution",
    icon: PlayCircle,
    tone: "amber"
  },
  {
    href: "/planner",
    label: "Query Planner",
    icon: Braces,
    tone: "indigo"
  },
  {
    href: "/optimizer",
    label: "SQL Optimizer",
    icon: Zap,
    tone: "emerald"
  },
  {
    href: "/settings",
    label: "Settings",
    icon: Settings,
    tone: "slate"
  },
  {
    href: "/admin/schema-requests",
    label: "Admin Review",
    icon: ShieldCheck,
    tone: "emerald",
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
        "flex h-full flex-col overflow-hidden border-r border-white/10 bg-white/[0.88] backdrop-blur-xl transition-[width] duration-300 ease-out dark:bg-slate-950/78",
        mobile ? "w-80 max-w-[86vw]" : "hidden lg:flex",
        compact ? "w-20" : "w-72"
      )}
    >
      <div
        className={cn(
          "flex h-16 items-center border-b border-white/10",
          compact ? "justify-center px-0" : "gap-3 px-5"
        )}
      >
        {!compact && (
          <Icon3D icon={Bot} tone="cyan" size="lg" />
        )}

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
            className={cn("hidden h-9 w-9 px-0 lg:inline-flex", compact && "rounded-md border border-white/10 bg-white/[0.04]")}
            onClick={() => setCollapsed(!collapsed)}
            aria-label={compact ? "Expand sidebar" : "Collapse sidebar"}
            title={compact ? "Expand sidebar" : "Collapse sidebar"}
          >
            {compact ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </Button>
        )}
      </div>

      <nav className={cn("min-h-0 flex-1 space-y-1 overflow-y-auto scrollbar-thin", compact ? "p-2" : "p-3")}>
        {navItems.filter((item) => !item.admin || user?.role === "admin").map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() =>
                mobile && setMobileSidebarOpen(false)
              }
              className={cn(
                "group flex h-10 items-center rounded-md text-sm text-slate-600 transition dark:text-slate-400",
                "hover:bg-slate-900/[0.06] hover:text-slate-950 dark:hover:bg-white/10 dark:hover:text-white",
                compact ? "justify-center px-0" : "gap-3 px-3",
                active &&
                  "bg-cyan-300/15 text-cyan-700 ring-1 ring-cyan-300/20 dark:text-cyan-100"
              )}
              aria-label={item.label}
              title={compact ? item.label : undefined}
            >
              <Icon3D icon={item.icon} tone={active ? item.tone : "slate"} size={compact ? "sm" : "xs"} />

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
          <Icon3D icon={BarChart3} tone="cyan" size="lg" className="mb-3" />

          <div className="text-sm font-medium text-white">
            Grounded SQL pipeline
          </div>

          <p className="mt-1 text-xs leading-5 text-slate-400">
            Schema graph, validation, confidence gating, and NVIDIA assist share the same checked workflow.
          </p>
        </div>
      )}
    </aside>
  );
}
