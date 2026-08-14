import type React from "react";
import { cn } from "@/lib/utils";

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  tone?: "cyan" | "indigo" | "emerald" | "amber" | "slate";
};

const tones: Record<NonNullable<BadgeProps["tone"]>, string> = {
  cyan: "border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-300/25 dark:bg-cyan-300/10 dark:text-cyan-100",
  indigo: "border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
  amber: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100",
  slate: "border-slate-200 bg-white/70 text-slate-600 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-300"
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
