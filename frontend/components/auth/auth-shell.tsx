import { Database, ShieldCheck, Sparkles } from "lucide-react";
import type React from "react";

export function AuthShell({
  title,
  description,
  children
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <main className="grid min-h-dvh bg-slate-950 lg:grid-cols-[minmax(0,1.1fr)_minmax(420px,.9fr)]">
      <section className="relative hidden overflow-hidden border-r border-white/10 p-12 lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,rgba(34,211,238,.2),transparent_30%),radial-gradient(circle_at_80%_75%,rgba(99,102,241,.22),transparent_35%)]" />
        <div className="relative flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-300 to-indigo-400 text-slate-950 shadow-glow">
            <Sparkles className="h-6 w-6" />
          </div>
          <div>
            <div className="font-semibold text-white">SQL Copilot</div>
            <div className="text-sm text-slate-400">Enterprise data intelligence</div>
          </div>
        </div>
        <div className="relative max-w-xl">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1.5 text-xs text-cyan-100">
            <ShieldCheck className="h-4 w-4" />
            Authenticated, explainable, read-only SQL
          </div>
          <h1 className="text-5xl font-semibold leading-tight text-white">
            Explore enterprise data without losing control of the query.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-slate-400">
            Schema-aware planning, validation, confidence scoring, and audit-ready sessions in one workspace.
          </p>
        </div>
        <div className="relative flex items-center gap-3 text-sm text-slate-500">
          <Database className="h-4 w-4 text-cyan-200" />
          Local-first processing with protected APIs
        </div>
      </section>
      <section className="flex min-h-dvh items-center justify-center p-5 sm:p-8">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-300 text-slate-950">
              <Sparkles className="h-5 w-5" />
            </div>
            <div className="font-semibold text-white">SQL Copilot</div>
          </div>
          <h2 className="text-3xl font-semibold text-white">{title}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
          <div className="mt-8">{children}</div>
        </div>
      </section>
    </main>
  );
}
