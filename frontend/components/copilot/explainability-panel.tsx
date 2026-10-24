"use client";

import { CheckCircle2, CircleAlert, Clock3, Database, Gauge, RefreshCw, ShieldCheck, Sparkles, Workflow } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { WorkflowSequence, type WorkflowStage } from "@/components/copilot/workflow-sequence";
import type { CopilotResponse } from "@/features/api/types";

function score(value: unknown, fallback: number) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.max(0, Math.min(100, Math.round(numeric))) : fallback;
}

function businessName(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function traceEvent(insights: CopilotResponse["insights"] | undefined, names: string[]) {
  const trace = insights?.execution_trace;
  const events = trace && Array.isArray(trace.events) ? trace.events as Array<Record<string, unknown>> : [];
  return events.find((event) => names.includes(String(event.stage || "")));
}

function eventDetail(event: Record<string, unknown> | undefined, fallback: string) {
  if (!event) return fallback;
  const explicit = event.summary || event.reason || event.validation;
  if (typeof explicit === "string" && explicit.trim()) return explicit;
  const operation = event.operation;
  if (typeof operation === "string" && operation) return `Detected ${businessName(operation)} request.`;
  const tables = event.tables;
  if (Array.isArray(tables) && tables.length) return `Matched ${tables.slice(0, 3).map(String).map(businessName).join(", ")}.`;
  return fallback;
}

export function ExplainabilityPanel({ response }: { response?: CopilotResponse }) {
  const insights = response?.insights;
  const isMetadata = insights?.query_type === "Metadata" || Boolean(insights?.confidence_not_applicable);
  const isSql = Boolean(response && /^(select|with)\b/i.test(response.sql.trim()) && !isMetadata);
  const confidence = score(insights?.confidence, 0);
  const plannerScore = score(insights?.planner_confidence ?? insights?.confidence_breakdown?.planner, confidence);
  const validationScore = score(insights?.validator_confidence ?? insights?.confidence_breakdown?.validator, insights?.valid ? 100 : 0);
  const coverageScore = score(insights?.coverage_confidence ?? insights?.confidence_breakdown?.coverage, confidence);
  const tables = insights?.selected_tables?.length ? insights.selected_tables : insights?.tables ?? [];
  const retries = Number(insights?.repair_attempts ?? insights?.attempts ?? 0);
  const intentEvent = traceEvent(insights, ["intent_detection", "business_logic_lookup", "enterprise_schema_gate"]);
  const entityEvent = traceEvent(insights, ["entity_extraction", "semantic_resolution"]);
  const linkingEvent = traceEvent(insights, ["schema_linking", "schema_retrieval_calls", "spider_retrieval"]);
  const planningEvent = traceEvent(insights, ["planning", "plan_validation"]);
  const generationEvent = traceEvent(insights, ["sql_generation", "generic_generation", "business_logic_lookup"]);
  const validationEvent = traceEvent(insights, ["sql_validation", "read_only_guard", "validation"]);
  const workflow: WorkflowStage[] = [
    { stage: "01", title: "Intent Analysis Agent", detail: eventDetail(intentEvent, isMetadata ? "Recognised a schema catalog request." : `Classified this as ${businessName(insights?.query_type ?? "business")}.`), icon: <Sparkles className="h-3.5 w-3.5" /> },
    { stage: "02", title: "Entity Resolution Agent", detail: eventDetail(entityEvent, tables.length ? `Resolved business terms for ${tables.slice(0, 2).map(businessName).join(" and ")}.` : "Resolved the request terms before planning."), icon: <Workflow className="h-3.5 w-3.5" /> },
    { stage: "03", title: "Schema Linking Agent", detail: eventDetail(linkingEvent, tables.length ? `Matched ${tables.slice(0, 3).map(businessName).join(", ")}.` : isMetadata ? "Retrieved the registered schema catalog." : "No registered schema match was required for this response."), icon: <Database className="h-3.5 w-3.5" /> },
    { stage: "04", title: "Query Planning Agent", detail: eventDetail(planningEvent, isSql ? "Prepared a read-only plan with the matched business data." : "Prepared a non-executable information response."), icon: <Gauge className="h-3.5 w-3.5" /> },
    { stage: "05", title: "SQL Generation Agent", detail: eventDetail(generationEvent, isSql ? (insights?.cache_hit ? "Reused a matching reviewed SQL result." : "Generated a read-only SQL statement.") : "Returned the requested schema information without SQL."), icon: <Sparkles className="h-3.5 w-3.5" /> },
    { stage: "06", title: "SQL Validation & Refinement Agent", detail: !isSql ? "No SQL validation was needed for this information response." : retries ? `${retries} repair ${retries === 1 ? "pass was" : "passes were"} completed before review.` : eventDetail(validationEvent, insights?.valid ? "Validated the first SQL draft; no repair pass was required." : "Validation found items that require review."), icon: <RefreshCw className="h-3.5 w-3.5" /> },
    { stage: "07", title: "Response Delivery Agent", detail: insights?.cache_hit ? "Delivered the matching saved response." : isSql && insights?.execution_requires_approval ? "Prepared the reviewed SQL for human approval before execution." : "Prepared the response for review." , icon: <CheckCircle2 className="h-3.5 w-3.5" /> },
  ];

  return (
    <Card className="flex h-full min-h-0 flex-col overflow-hidden">
      <CardHeader className="shrink-0 border-b border-white/10 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-100"><Sparkles className="h-5 w-5" /></div><div className="min-w-0"><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-300">Query review</div><CardTitle className="mt-1">Explainable AI</CardTitle><p className="mt-1 max-w-[18rem] text-sm leading-5 text-slate-500">{isMetadata ? "A clear view of the schema information returned." : "A concise view of the checks behind this response."}</p></div></div>
          <Badge tone={insights?.valid ? "emerald" : "amber"}>{isMetadata ? "Reference" : insights?.valid ? "Reviewed" : "Needs review"}</Badge>
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-y-auto p-4 touch-pan-y scrollbar-thin">
        {isMetadata ? <section className="rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-4"><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Response type</div><div className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">Schema catalog</div><p className="mt-1 text-sm leading-5 text-slate-500">This response lists registered data sources. It is not SQL, so no confidence score applies.</p></section> : <section className="rounded-2xl border border-cyan-300/20 bg-gradient-to-br from-cyan-300/14 to-indigo-400/12 p-4"><div className="flex items-end justify-between gap-4"><div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Confidence</div><div className="mt-1 text-4xl font-semibold tracking-tight text-slate-950 dark:text-white">{confidence}<span className="text-xl text-cyan-500">%</span></div></div><Gauge className="h-5 w-5 text-cyan-500" /></div><Progress className="mt-3 h-2" value={confidence} /></section>}

        <section>
          <SectionLabel>Agent scorecard</SectionLabel>
          <div className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-3">
            <ScoreCard icon={<Sparkles className="h-4 w-4" />} label="Planning" value={plannerScore} />
            <ScoreCard icon={<ShieldCheck className="h-4 w-4" />} label="Validation" value={validationScore} />
            <ScoreCard icon={<Database className="h-4 w-4" />} label="Data fit" value={coverageScore} />
          </div>
        </section>

        <section><SectionLabel>7-stage agent workflow</SectionLabel><WorkflowSequence stages={workflow} /></section>

        <section>
          <SectionLabel>Request details</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            <Detail label="Request" value={insights?.query_type ?? "Query"} />
            <Detail label="Safety" value={isSql ? (insights?.valid ? "Reviewed" : "Review required") : "Not applicable"} />
            <Detail label="Refinements" value={retries ? String(retries) : isSql ? "First pass" : "Not applicable"} icon={<RefreshCw className="h-3.5 w-3.5" />} />
            <Detail label="Response" value={insights?.cache_hit ? "Saved answer" : "New answer"} icon={insights?.cache_hit ? <Clock3 className="h-3.5 w-3.5" /> : undefined} />
          </div>
        </section>

        <section><SectionLabel>Data used</SectionLabel>{tables.length ? <div className="flex flex-wrap gap-2">{tables.slice(0, 8).map((table) => <Badge key={table} tone="slate">{businessName(table)}</Badge>)}</div> : <div className="rounded-xl border border-dashed border-white/10 p-3 text-sm text-slate-500">No registered data source was needed for this response.</div>}</section>

        {insights?.validation ? <div className={`flex gap-2 rounded-xl border p-3 text-sm leading-5 ${insights.valid ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-100" : "border-amber-300/20 bg-amber-300/10 text-amber-100"}`}>{insights.valid ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />}<span>{insights.validation}</span></div> : null}
      </CardContent>
    </Card>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) { return <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{children}</div>; }
function ScoreCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) { return <div className="min-w-0 rounded-xl border border-white/10 bg-white/[0.035] p-2.5"><div className="flex min-w-0 items-start justify-between gap-1.5 text-slate-500"><span className="flex min-w-0 items-center gap-1 text-[11px] leading-4"><span className="shrink-0">{icon}</span><span className="min-w-0 break-words">{label}</span></span><span className="shrink-0 text-xs font-semibold text-slate-700 dark:text-slate-200">{value}%</span></div><Progress className="mt-2 h-1.5" value={value} /></div>; }
function Detail({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) { return <div className="min-w-0 rounded-xl border border-white/10 bg-white/[0.035] p-3"><div className="text-[10px] font-medium uppercase tracking-[0.1em] text-slate-500">{label}</div><div className="mt-1 flex items-center gap-1.5 truncate text-sm font-medium text-slate-950 dark:text-white">{icon}{value}</div></div>; }
