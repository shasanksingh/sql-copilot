import type React from "react";
import { cn } from "@/lib/utils";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "h-11 w-full rounded-xl border border-slate-200/80 bg-white/[0.9] px-3.5 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-500 focus:border-cyan-300/70 focus:ring-4 focus:ring-cyan-300/15 dark:border-white/10 dark:bg-slate-950/60 dark:text-white",
        props.className
      )}
    />
  );
}