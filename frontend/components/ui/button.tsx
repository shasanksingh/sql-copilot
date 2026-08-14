import type React from "react";
import { cn } from "@/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "outline";
};

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-cyan-400 text-slate-950 hover:bg-cyan-300",
        variant === "ghost" && "text-slate-600 hover:bg-slate-900/[0.06] hover:text-slate-950 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white",
        variant === "outline" && "border border-slate-200/80 bg-white/70 text-slate-700 hover:bg-slate-100/80 hover:text-slate-950 dark:border-white/12 dark:bg-white/[0.03] dark:text-slate-200 dark:hover:bg-white/10 dark:hover:text-white",
        className
      )}
      {...props}
    />
  );
}
