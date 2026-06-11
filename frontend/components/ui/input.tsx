import type React from "react";
import { cn } from "@/lib/utils";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "h-10 w-full rounded-md border border-white/10 bg-slate-950/70 px-3 text-sm text-white outline-none ring-cyan-300/30 placeholder:text-slate-500 focus:ring-4",
        props.className
      )}
    />
  );
}
