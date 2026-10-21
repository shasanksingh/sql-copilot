import type React from "react";
import { cn } from "@/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "outline";
};

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition duration-200 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cyan-300/30 disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-gradient-to-r from-cyan-300 via-sky-300 to-indigo-400 text-slate-950 shadow-[0_10px_24px_rgba(34,211,238,0.18)] hover:-translate-y-0.5 hover:brightness-110 active:translate-y-0",
        variant === "ghost" && "text-slate-600 hover:bg-slate-900/[0.06] hover:text-slate-950 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white",
        variant === "outline" && "border border-slate-200/80 bg-white/70 text-slate-700 hover:border-cyan-300/35 hover:bg-cyan-50/70 hover:text-slate-950 dark:border-white/12 dark:bg-white/[0.03] dark:text-slate-200 dark:hover:border-cyan-300/25 dark:hover:bg-cyan-300/10 dark:hover:text-white",
        className
      )}
      {...props}
    />
  );
}