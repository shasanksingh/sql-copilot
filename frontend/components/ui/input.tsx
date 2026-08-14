import type React from "react";
import { cn } from "@/lib/utils";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "h-10 w-full rounded-md border border-slate-200/80 bg-white/[0.85] px-3 text-sm text-slate-950 outline-none ring-cyan-300/30 placeholder:text-slate-500 focus:ring-4 dark:border-white/10 dark:bg-slate-950/70 dark:text-white",
        props.className
      )}
    />
  );
}
