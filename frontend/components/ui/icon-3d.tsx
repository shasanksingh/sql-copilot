import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type Icon3DTone = "cyan" | "emerald" | "amber" | "indigo" | "rose" | "slate";

const toneClasses: Record<Icon3DTone, { base: string; side: string; icon: string; glow: string }> = {
  cyan: {
    base: "from-cyan-200 via-cyan-400 to-indigo-500",
    side: "from-cyan-700 to-indigo-900",
    icon: "text-slate-950",
    glow: "shadow-cyan-500/25"
  },
  emerald: {
    base: "from-emerald-200 via-emerald-400 to-teal-600",
    side: "from-emerald-700 to-teal-900",
    icon: "text-slate-950",
    glow: "shadow-emerald-500/25"
  },
  amber: {
    base: "from-amber-100 via-amber-400 to-rose-500",
    side: "from-amber-700 to-rose-900",
    icon: "text-slate-950",
    glow: "shadow-amber-500/25"
  },
  indigo: {
    base: "from-indigo-200 via-indigo-400 to-violet-700",
    side: "from-indigo-800 to-violet-950",
    icon: "text-white",
    glow: "shadow-indigo-500/25"
  },
  rose: {
    base: "from-rose-200 via-rose-400 to-red-700",
    side: "from-rose-800 to-red-950",
    icon: "text-white",
    glow: "shadow-rose-500/25"
  },
  slate: {
    base: "from-slate-200 via-slate-400 to-slate-700",
    side: "from-slate-700 to-slate-950",
    icon: "text-white",
    glow: "shadow-slate-500/20"
  }
};

const sizes = {
  xs: { box: "h-7 w-7", icon: "h-3.5 w-3.5", depth: "translate-y-1" },
  sm: { box: "h-8 w-8", icon: "h-4 w-4", depth: "translate-y-1" },
  md: { box: "h-10 w-10", icon: "h-5 w-5", depth: "translate-y-1.5" },
  lg: { box: "h-12 w-12", icon: "h-6 w-6", depth: "translate-y-1.5" },
  xl: { box: "h-16 w-16", icon: "h-8 w-8", depth: "translate-y-2" }
};

export function Icon3D({
  icon: Icon,
  tone = "cyan",
  size = "md",
  className
}: {
  icon: LucideIcon;
  tone?: Icon3DTone;
  size?: keyof typeof sizes;
  className?: string;
}) {
  const palette = toneClasses[tone];
  const dimensions = sizes[size];

  return (
    <span
      aria-hidden="true"
      className={cn("relative inline-grid shrink-0 place-items-center", dimensions.box, className)}
    >
      <span
        className={cn(
          "absolute inset-x-1 bottom-0 top-2 rounded-[7px] bg-gradient-to-br opacity-90 blur-[0.2px]",
          dimensions.depth,
          palette.side
        )}
      />
      <span
        className={cn(
          "relative grid h-full w-full place-items-center rounded-[7px] border border-white/45 bg-gradient-to-br shadow-lg transition-transform duration-200",
          "before:absolute before:inset-x-1.5 before:top-1.5 before:h-2 before:rounded-full before:bg-white/45 before:content-['']",
          "group-hover:-translate-y-0.5",
          palette.base,
          palette.glow
        )}
        style={{ transform: "perspective(90px) rotateX(8deg) rotateY(-9deg)" }}
      >
        <Icon className={cn(dimensions.icon, palette.icon, "relative drop-shadow-sm")} strokeWidth={2.45} />
      </span>
    </span>
  );
}
