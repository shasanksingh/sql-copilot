import { CheckCircle2, LockKeyhole, Sparkles } from "lucide-react";
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
    <main className="relative grid min-h-dvh overflow-hidden bg-[#050816] lg:grid-cols-[minmax(0,1.15fr)_minmax(440px,.85fr)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(34,211,238,.15),transparent_27%),radial-gradient(circle_at_72%_0%,rgba(129,140,248,.17),transparent_28%),linear-gradient(rgba(148,163,184,.035)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,.035)_1px,transparent_1px)] bg-[size:auto,auto,44px_44px,44px_44px]" />
      <section className="relative hidden border-r border-white/10 px-10 py-9 lg:flex lg:flex-col xl:px-14 xl:py-12">
        <header className="flex items-center">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-300 via-sky-300 to-indigo-400 text-slate-950 shadow-[0_12px_30px_rgba(34,211,238,.23)]">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="font-semibold tracking-tight text-white">SQL Copilot</div>
              <div className="text-xs text-slate-400">Decision-ready analytics</div>
            </div>
          </div>
        </header>

        <div className="my-auto max-w-2xl py-12">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3.5 py-2 text-xs font-medium text-cyan-50">
            <LockKeyhole className="h-3.5 w-3.5" />
            Governed, read-only analytics
          </div>
          <h1 className="max-w-xl text-5xl font-semibold leading-[1.08] tracking-[-0.045em] xl:text-6xl">
            <span className="text-white">Ask with clarity.</span><br />
            <span className="text-gradient">Move with confidence.</span>
          </h1>
          <p className="mt-7 max-w-xl text-base leading-8 text-slate-300 xl:text-lg">
            A focused workspace for exploring your business data, reviewing trusted SQL, and understanding the path behind every answer.
          </p>

        </div>
      </section>

      <section className="relative flex min-h-dvh items-center justify-center px-5 py-8 sm:px-8 lg:px-10">
        <div className="w-full max-w-md">
          <div className="mb-7 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-300 via-sky-300 to-indigo-400 text-slate-950"><Sparkles className="h-5 w-5" /></div>
            <div><div className="font-semibold text-white">SQL Copilot</div><div className="text-xs text-slate-400">Decision-ready analytics</div></div>
          </div>
          <div className="auth-form-surface rounded-3xl p-6 sm:p-8">
            <div className="mb-8 flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-100"><CheckCircle2 className="h-5 w-5" /></div>
              <div>
                <h2 className="text-3xl font-semibold tracking-tight text-white">{title}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
              </div>
            </div>
            {children}
          </div>
        </div>
      </section>
    </main>
  );
}
