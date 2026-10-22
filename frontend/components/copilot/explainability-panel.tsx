"use client";

import { CheckCircle2, CircleAlert, Clock3, Database, Gauge, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { CopilotResponse } from "@/features/api/types";

function score(value: unknown, fallback: number) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.max(0, Math.min(100, Math.round(numeric))) : fallback;
}

function businessName(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function ExplainabilityPanel({ response }: { response?: CopilotResponse }) {
  const insights = response?.insights;
  const confidence = score(insights?.confidence, 0);
  const plannerScore = score(insights?.planner_confidence ?? insights?.confidence_breakdown?.planner, confidence);
  const validationScore = score(insights?.validator_confidence ?? insights?.confidence_breakdown?.validator, insights?.valid ? 100 : 0);
  const coverageScore = score(insights?.coverage_confidence ?? insights?.confidence_breakdown?.coverage, confidence);
  const tables = insights?.selected_tables?.length ? insights.selected_tables : insights?.tables ?? [];
  const retries = Number(insights?.repair_attempts ?? insights?.attempts ?? 0);

  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="border-b border-white/10 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-100"><Sparkles className="h-5 w-5" /></div><div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-300">Query review</div><CardTitle className="mt-1">Explainable AI</CardTitle><p className="mt-1 text-sm leading-5 text-slate-500">A concise view of the checks behind this SQL result.</p></div></div>
          <Badge tone={insights?.valid ? "emerald" : "amber"}>{insights?.valid ? "Reviewed" : "Needs review"}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 overflow-y-auto p-4 scrollbar-thin">
        <section className="rounded-2xl border border-cyan-300/20 bg-gradient-to-br from-cyan-300/14 to-indigo-400/12 p-4">
          <div className="flex items-end justify-between gap-4"><div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Confidence</div><div className="mt-1 text-4xl font-semibold tracking-tight text-slate-950 dark:text-white">{confidence}<span className="text-xl text-cyan-500">%</span></div></div><Gauge className="h-5 w-5 text-cyan-500" /></div>
          <Progress className="mt-3 h-2" value={confidence} />
        </section>

        <section>
          <SectionLabel>Agent scorecard</SectionLabel>
          <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
            <ScoreCard icon={<Sparkles className="h-4 w-4" />} label="Planning" value={plannerScore} />
            <ScoreCard icon={<ShieldCheck className="h-4 w-4" />} label="Validation" value={validationScore} />
            <ScoreCard icon={<Database className="h-4 w-4" />} label="Data fit" value={coverageScore} />
          </div>
        </section>

        <section>
          <SectionLabel>Request details</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            <Detail label="Request" value={insights?.query_type ?? "Query"} />
            <Detail label="Safety" value={insights?.valid ? "Ready" : "Review required"} />
            <Detail label="Refinements" value={retries ? String(retries) : "None"} icon={<RefreshCw className="h-3.5 w-3.5" />} />
            <Detail label="Response" value={insights?.cache_hit ? "Saved answer" : "New answer"} icon={insights?.cache_hit ? <Clock3 className="h-3.5 w-3.5" /> : undefined} />
          </div>
        </section>

        <section>
          <SectionLabel>Data used</SectionLabel>
          {tables.length ? <div className="flex flex-wrap gap-2">{tables.slice(0, 8).map((table) => <Badge key={table} tone="slate">{businessName(table)}</Badge>)}</div> : <div className="rounded-xl border border-dashed border-white/10 p-3 text-sm text-slate-500">The result did not require a registered data source.</div>}
        </section>

        {insights?.validation ? <div className={`flex gap-2 rounded-xl border p-3 text-sm leading-5 ${insights.valid ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-100" : "border-amber-300/20 bg-amber-300/10 text-amber-100"}`}>{insights.valid ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />}<span>{insights.validation}</span></div> : null}
      </CardContent>
    </Card>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{children}</div>;
}

function ScoreCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return <div className="rounded-xl border border-white/10 bg-white/[0.035] p-3"><div className="flex items-center justify-between gap-2 text-slate-500"><span className="flex items-center gap-1.5 text-xs">{icon}{label}</span><span className="font-semibold text-slate-700 dark:text-slate-200">{value}%</span></div><Progress className="mt-2 h-1.5" value={value} /></div>;
}

function Detail({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return <div className="min-w-0 rounded-xl border border-white/10 bg-white/[0.035] p-3"><div className="text-[10px] font-medium uppercase tracking-[0.1em] text-slate-500">{label}</div><div className="mt-1 flex items-center gap-1.5 truncate text-sm font-medium text-slate-950 dark:text-white">{icon}{value}</div></div>;
}
