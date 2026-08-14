"use client";

import {
  Bot,
  Braces,
  Database,
  GitBranch,
  LayoutDashboard,
  Network,
  PlayCircle,
  Settings,
  ShieldCheck,
  Zap,
  type LucideIcon
} from "lucide-react";
import type { ReactNode } from "react";
import { Icon3D, type Icon3DTone } from "@/components/ui/icon-3d";
import { cn } from "@/lib/utils";

const pageIconMap: Record<string, { icon: LucideIcon; tone: Icon3DTone }> = {
  Dashboard: { icon: LayoutDashboard, tone: "cyan" },
  "SQL Copilot": { icon: Bot, tone: "cyan" },
  "Schema Explorer": { icon: Database, tone: "indigo" },
  "Schema Graph": { icon: GitBranch, tone: "cyan" },
  "Data Model Studio": { icon: Network, tone: "indigo" },
  "Query Execution": { icon: PlayCircle, tone: "amber" },
  "Query Planner": { icon: Braces, tone: "indigo" },
  "SQL Optimizer": { icon: Zap, tone: "emerald" },
  Settings: { icon: Settings, tone: "slate" },
  "Admin Review": { icon: ShieldCheck, tone: "emerald" }
};

export function PageHeader({
  title,
  description,
  compact = false,
  icon,
  tone,
  actions,
  meta
}: {
  title: string;
  description: string;
  compact?: boolean;
  icon?: LucideIcon;
  tone?: Icon3DTone;
  actions?: ReactNode;
  meta?: ReactNode;
}) {
  const iconConfig = pageIconMap[title] ?? pageIconMap.Dashboard;
  const HeaderIcon = icon ?? iconConfig.icon;

  return (
    <section className={cn(
      "mb-5 overflow-hidden rounded-lg border border-white/10 bg-white/[0.06] shadow-glow backdrop-blur-xl dark:bg-slate-950/45",
      compact && "mb-3"
    )}>
      <div className={cn(
        "flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between",
        compact ? "p-3" : "p-4 md:p-5"
      )}>
        <div className="flex min-w-0 gap-4">
          <Icon3D icon={HeaderIcon} tone={tone ?? iconConfig.tone} size={compact ? "md" : "lg"} />
          <div className="min-w-0">
            <h1 className={cn("font-semibold tracking-normal text-white", compact ? "text-xl md:text-2xl" : "text-2xl md:text-3xl")}>
              {title}
            </h1>
            <p className={cn("max-w-3xl text-slate-400", compact ? "mt-1 text-xs leading-5" : "mt-2 text-sm leading-6")}>
              {description}
            </p>
            {meta ? <div className="mt-3 flex flex-wrap gap-2">{meta}</div> : null}
          </div>
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </section>
  );
}
