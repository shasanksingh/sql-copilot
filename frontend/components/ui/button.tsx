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
        variant === "ghost" && "text-slate-300 hover:bg-white/10 hover:text-white",
        variant === "outline" && "border border-white/12 bg-white/[0.03] text-slate-200 hover:bg-white/10",
        className
      )}
      {...props}
    />
  );
}
