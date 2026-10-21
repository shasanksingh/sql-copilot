import type React from "react";
import { cn } from "@/lib/utils";

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "min-h-28 w-full resize-none rounded-xl border border-white/10 bg-slate-950/70 p-3.5 font-mono text-sm text-white shadow-inner outline-none transition placeholder:text-slate-500 focus:border-cyan-300/45 focus:ring-4 focus:ring-cyan-300/15",
        props.className
      )}
    />
  );
}