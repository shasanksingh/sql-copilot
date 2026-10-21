import { AlertTriangle, CheckCircle2, ChevronDown, CircleSlash2, Gauge, ShieldCheck, Sparkles } from "lucide-react";
import type React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import type { ConfidenceEvidenceItem, CopilotResponse } from "@/features/api/types";

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-52 overflow-auto rounded-xl border border-white/5 bg-slate-950/75 p-3 text-xs leading-5 text-cyan-100 scrollbar-thin">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}

const evidenceLabels: Record<string, string> = {
  intent: "Request clarity",
  entity: "Data mapping",
  column: "Field coverage",
  join: "Relationship path",
  aggregation: "Measure logic",
  semantic: "Business alignment",
  validation: "SQL safety",
  planner_confidence: "Plan quality",
  validator_confidence: "Validation quality",
  coverage_confidence: "Coverage",
  model_confidence: "Model assist",
  system_confidence: "Overall confidence"
};

const displayBreakdownKeys = [
  "intent", "entity", "column", "join", "aggregation", "semantic", "validation",
  "planner_confidence", "coverage_confidence", "model_confidence", "system_confidence"
];

function fallbackEvidence(response?: CopilotResponse): ConfidenceEvidenceItem[] {
  const breakdown = response?.insights.confidence_breakdown;
  if (!breakdown) return [];
  return displayBreakdownKeys
    .filter((key) => typeof breakdown[key] === "number")
    .map((key) => {
      const score = breakdown[key];
      const modelInactive = key === "model_confidence" && score === 0 && response?.insights.llm_provider !== "nvidia";
      return {
        key,
        label: evidenceLabels[key] ?? key.replaceAll("_", " "),
        score: modelInactive ? null : score,
        applicable: !modelInactive,
        status: modelInactive ? "not_applicable" : score >= 90 ? "passed" : score >= 70 ? "warning" : "failed",
        note: modelInactive ? "Model assist was not needed for this request." : undefined
      };
    });
}

function providerLabelFor(response?: CopilotResponse) {
  const insights = response?.insights;
  if (insights?.generic_sql) return "General SQL guidance";
  const provider = String(insights?.llm_provider ?? insights?.provider_status?.provider ?? "local");
  const model = String(insights?.llm_model ?? insights?.provider_status?.model ?? "");
  const reason = String(insights?.fallback_reason ?? insights?.llm_trace?.fallback_reason ?? "");
  const skipReason = String(insights?.llm_trace?.skip_reason ?? "");
  if (reason === "network_blocked") return "NVIDIA connection unavailable";
  if (skipReason === "deterministic_plan_validated") return "Verified query plan";
  if (insights?.fallback_used) return "Verified fallback";
  if (provider === "nvidia") return "NVIDIA GPT-OSS-20B";
  if (provider === "local") return "Local planner";
  return model || provider || "Deterministic workflow";
}

function fallbackReasonLabel(reason?: string) {
  if (reason === "network_blocked") return "NVIDIA could not be reached, so a verified local result was used.";
  if (reason === "provider_error") return "NVIDIA did not respond; a verified local result was used.";
  if (reason === "timeout") return "NVIDIA took too long to respond; a verified local result was used.";
  if (reason === "rate_limit") return "NVIDIA was busy; a verified local result was used.";
  if (reason === "configuration") return "NVIDIA needs a valid provider configuration before it can assist.";
  if (reason === "candidate_failed_validation") return "The generated suggestion did not meet safety checks, so it was not used.";
  if (reason === "provider_unavailable") return "NVIDIA is unavailable; a verified local result was used.";
  return reason || "A verified fallback was used for this query.";
}

export function ExplainabilityPanel({ response }: { response?: CopilotResponse }) {
  const insights = response?.insights;
  const selectedTables = insights?.selected_tables ?? insights?.tables ?? [];
  const hasPlan = Boolean(insights?.plan);
  const entities = insights?.entities;
  const coverageReport = insights?.coverage_report;
  const evidence = insights?.confidence_evidence?.length ? insights.confidence_evidence : fallbackEvidence(response);
  const providerLabel = providerLabelFor(response);
  const stages = [
    ["Understand the request", insights?.intent],
    ["Map the relevant data", entities],
    ["Apply business rules", { measures: entities?.["measures"], filters: entities?.["filters"], registered_rules: coverageReport?.["business_logic"] }],
    ["Build the query plan", insights?.plan],
    ["Resolve relationships", { selected_tables: selectedTables, join_path: insights?.join_path, join_graph: coverageReport?.["join_graph"] }],
    ["Use model assist when helpful", insights?.llm_trace],
    ["Produce the SQL", { sql: response?.sql }],
    ["Run safety checks", { valid: insights?.valid, message: insights?.validation }],
    ["Score the result", { breakdown: insights?.confidence_breakdown, evidence }],
    ["Confirm coverage", insights?.coverage_report]
  ] as const;

  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="border-b border-cyan-300/10 bg-gradient-to-br from-cyan-300/10 via-transparent to-indigo-400/10">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-100"><Sparkles className="h-5 w-5" /></div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-200">Query assurance</div>
            <CardTitle className="mt-1 text-base">Explainable AI</CardTitle>
            <p className="mt-1 text-xs leading-5 text-slate-400">A clear, reviewable trail from question to trusted SQL.</p>
          </div>
          <Badge tone={insights?.valid ? "emerald" : response ? "amber" : "slate"} className="shrink-0">{insights?.valid ? "Verified" : response ? "Review" : "Waiting"}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 p-4 sm:p-5">
        <section className="rounded-2xl border border-cyan-300/15 bg-gradient-to-br from-cyan-300/10 via-slate-950/35 to-indigo-400/10 p-4">
          <div className="flex items-end justify-between gap-3">
            <div><div className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">Confidence</div><div className="mt-1 text-3xl font-semibold tracking-tight text-white">{insights?.confidence ?? 0}<span className="text-base text-cyan-200">%</span></div></div>
            <div className="flex items-center gap-1.5 text-xs text-slate-300"><ShieldCheck className="h-4 w-4 text-cyan-200" />{insights?.confidence_band ?? "Awaiting query"}</div>
          </div>
          <Progress className="mt-4" value={insights?.confidence ?? 0} />
        </section>

        {evidence.length ? <section><SectionLabel>Quality signals</SectionLabel><div className="grid gap-2 sm:grid-cols-2">{evidence.map((item) => <EvidenceRow key={item.key} item={item} />)}</div></section> : null}

        <section className="grid grid-cols-2 gap-2">
          <Metric label="Request" value={insights?.query_type ?? "Waiting"} />
          <Metric label="Safety" value={!response ? "Waiting" : insights?.valid ? "Ready" : "Blocked"} />
          <Metric label="Assistant" value={providerLabel} />
          <Metric label="Complexity" value={insights?.query_complexity ?? "Simple"} />
          <Metric label="Tables" value={selectedTables.join(", ") || "—"} />
          <Metric label="Repair passes" value={String(insights?.repair_attempts ?? 0)} />
        </section>

        {insights?.fallback_used ? <div className="rounded-xl border border-amber-300/20 bg-amber-300/10 p-3 text-xs leading-5 text-amber-100">{fallbackReasonLabel(insights.fallback_reason)}</div> : null}
        {insights?.generic_warning ? <div className="rounded-xl border border-indigo-300/20 bg-indigo-300/10 p-3 text-xs leading-5 text-indigo-100">{insights.generic_warning}</div> : null}

        <section>
          <SectionLabel>Relationship path</SectionLabel>
          <div className="flex flex-wrap gap-2">
            {(insights?.join_path ?? []).length ? insights?.join_path?.map((item) => <Badge key={item} tone="cyan">{item}</Badge>) : hasPlan && selectedTables.length <= 1 ? <Badge tone="emerald">Single table, no join needed</Badge> : hasPlan ? <Badge tone="cyan">Plan complete</Badge> : response ? <Badge tone="amber">More detail needed</Badge> : <Badge>Run a query to view the path</Badge>}
          </div>
        </section>

        {insights?.clarification_options?.length ? <div className="rounded-xl border border-amber-300/20 bg-amber-300/10 p-3 text-sm text-amber-100">{insights.clarification_options.join(", ")}</div> : null}

        <section>
          <SectionLabel>Decision trail</SectionLabel>
          <div className="space-y-2">
            {stages.map(([label, value], index) => (
              <details key={label} className="group overflow-hidden rounded-xl border border-white/10 bg-white/[0.035]" open={index === 0}>
                <summary className="flex cursor-pointer list-none items-center gap-3 p-3 text-sm text-slate-200 transition hover:bg-white/[0.04]">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-cyan-300/15 bg-cyan-300/10 text-xs font-semibold text-cyan-100">{index + 1}</span>
                  <span className="min-w-0 flex-1">{label}</span>
                  <ChevronDown className="h-4 w-4 text-slate-500 transition group-open:rotate-180" />
                </summary>
                <div className="border-t border-white/10 p-3"><JsonBlock value={value} /></div>
              </details>
            ))}
          </div>
        </section>
      </CardContent>
    </Card>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{children}</div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded-xl border border-white/10 bg-white/[0.035] p-3"><div className="text-[10px] font-medium uppercase tracking-[0.1em] text-slate-500">{label}</div><div className="mt-1 truncate text-sm font-medium text-white" title={value}>{value}</div></div>;
}

function EvidenceRow({ item }: { item: ConfidenceEvidenceItem }) {
  const score = typeof item.score === "number" ? Math.max(0, Math.min(100, item.score)) : null;
  const isSkipped = !item.applicable || score === null;
  const Icon = isSkipped ? CircleSlash2 : item.status === "passed" ? CheckCircle2 : item.status === "warning" ? Gauge : AlertTriangle;
  const iconClass = isSkipped ? "text-slate-500" : item.status === "passed" ? "text-emerald-200" : "text-amber-200";
  const missing = item.missing?.filter(Boolean) ?? [];

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.035] p-3">
      <div className="flex items-center gap-2"><Icon className={`h-4 w-4 shrink-0 ${iconClass}`} /><span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-200">{item.label}</span><span className="text-xs font-semibold text-slate-300">{isSkipped ? "—" : `${Math.round(score)}%`}</span></div>
      {isSkipped ? <div className="mt-2 h-1.5 rounded-full border border-dashed border-white/10" /> : <Progress className="mt-2 h-1.5" value={score} />}
      {item.note ? <div className="mt-2 line-clamp-2 text-[11px] leading-4 text-slate-500">{item.note}</div> : null}
      {missing.length ? <div className="mt-2 line-clamp-2 text-[11px] leading-4 text-amber-100">Missing: {missing.slice(0, 4).join(", ")}</div> : null}
    </div>
  );
}