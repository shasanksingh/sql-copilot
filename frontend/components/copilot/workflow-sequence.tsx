"use client";

import type React from "react";

export type WorkflowStage = {
  stage: string;
  title: string;
  detail: string;
  icon: React.ReactNode;
};

/** A code-native workflow diagram: labels remain legible and the order cannot drift on mobile. */
export function WorkflowSequence({ stages }: { stages: WorkflowStage[] }) {
  return (
    <ol className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.035] px-3 py-1">
      {stages.map((item, index) => (
        <li key={item.stage} className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-2 py-3">
          {index < stages.length - 1 ? <span className="absolute bottom-0 left-[0.875rem] top-9 w-px bg-gradient-to-b from-cyan-300/45 to-indigo-300/20" /> : null}
          <span className="relative z-10 flex h-7 w-7 items-center justify-center rounded-full border border-cyan-300/20 bg-cyan-300/10 text-cyan-200" title={`Stage ${item.stage}`}>{item.icon}</span>
          <span className="min-w-0"><span className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-cyan-400">Stage {item.stage}</span><span className="mt-0.5 block text-xs font-semibold text-slate-800 dark:text-slate-100">{item.title}</span><span className="mt-0.5 block text-xs leading-4 text-slate-500">{item.detail}</span></span>
        </li>
      ))}
    </ol>
  );
}
