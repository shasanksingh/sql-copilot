import type React from "react";
import { cn } from "@/lib/utils";

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  tone?: "cyan" | "indigo" | "emerald" | "amber" | "slate";
};

const tones: Record<NonNullable<BadgeProps["tone"]>, string> = {
  cyan: "border-cyan-300/25 bg-cyan-300/10 text-cyan-100",
  indigo: "border-indigo-300/25 bg-indigo-300/10 text-indigo-100",
  emerald: "border-emerald-300/25 bg-emerald-300/10 text-emerald-100",
  amber: "border-amber-300/25 bg-amber-300/10 text-amber-100",
  slate: "border-white/10 bg-white/[0.04] text-slate-300"
};

export function Badge({ className, tone = "slate", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center rounded-md border px-2.5 text-xs font-medium",
        tones[tone],
        className
      )}
      {...props}
    />
  );
}
