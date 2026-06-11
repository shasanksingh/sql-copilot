import type React from "react";
import { cn } from "@/lib/utils";

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "min-h-28 w-full resize-none rounded-md border border-white/10 bg-slate-950/70 p-3 font-mono text-sm text-white outline-none ring-cyan-300/30 placeholder:text-slate-500 focus:ring-4",
        props.className
      )}
    />
  );
}
