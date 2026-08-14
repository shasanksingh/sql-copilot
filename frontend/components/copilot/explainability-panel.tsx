"use client";

import { AlertTriangle, CheckCircle2, CircleSlash2, Gauge } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import type { ConfidenceEvidenceItem, CopilotResponse } from "@/features/api/types";

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-48 overflow-auto rounded-md bg-slate-950/80 p-3 text-xs leading-5 text-cyan-100 scrollbar-thin">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}

const evidenceLabels: Record<string, string> = {
  intent: "Intent",
  entity: "Entity Resolution",
  column: "Column Coverage",
  join: "Join Path",
  aggregation: "Aggregation",
  semantic: "Semantic Alignment",
  validation: "SQL Validator",
  planner_confidence: "Planner",
  validator_confidence: "Validator",
  coverage_confidence: "Applicable Coverage",
  model_confidence: "LLM Model",
  system_confidence: "System Confidence"
};

const displayBreakdownKeys = [
  "intent",
  "entity",
  "column",
  "join",
  "aggregation",
  "semantic",
  "validation",
  "planner_confidence",
  "coverage_confidence",
  "model_confidence",
  "system_confidence"
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
        note: modelInactive ? "LLM assist was not active for this request." : undefined
      };
    });
}

function providerLabelFor(response?: CopilotResponse) {
  const insights = response?.insights;
  if (insights?.generic_sql) return "Spider Generic SQL";
  const provider = String(insights?.llm_provider ?? insights?.provider_status?.provider ?? "local");
  const model = String(insights?.llm_model ?? insights?.provider_status?.model ?? "");
  const reason = String(insights?.fallback_reason ?? insights?.llm_trace?.fallback_reason ?? "");
  const skipReason = String(insights?.llm_trace?.skip_reason ?? "");
  if (reason === "network_blocked") return "NVIDIA network blocked";
  if (skipReason === "deterministic_plan_validated") return "Validated deterministic plan";
  if (insights?.fallback_used) return "Validated fallback";
  if (provider === "nvidia") return "NVIDIA GPT-OSS-20B";
  if (provider === "local") return "Local Planner";
  return model || provider || "Deterministic";
}

function fallbackReasonLabel(reason?: string) {
  if (reason === "network_blocked") {
    return "Backend network access to NVIDIA is blocked; deterministic SQL was used.";
  }
  if (reason === "provider_error") return "NVIDIA assist could not connect; deterministic SQL was used.";
  if (reason === "timeout") return "NVIDIA assist timed out; deterministic SQL was used.";
  if (reason === "rate_limit") return "NVIDIA assist was rate limited; deterministic SQL was used.";
  if (reason === "configuration") return "NVIDIA assist needs a valid provider configuration; deterministic SQL was used.";
  if (reason === "candidate_failed_validation") return "NVIDIA candidate failed deterministic validation; deterministic SQL was used.";
  if (reason === "provider_unavailable") return "NVIDIA assist is unavailable; deterministic SQL was used.";
  return reason || "Provider fallback was used for this query.";
}

export function ExplainabilityPanel({ response }: { response?: CopilotResponse }) {
  const insights = response?.insights;
  const selectedTables = insights?.selected_tables ?? insights?.tables ?? [];
  const hasPlan = Boolean(insights?.plan);
  const entities = insights?.entities;
  const coverageReport = insights?.coverage_report;
  const evidence = insights?.confidence_evidence?.length
    ? insights.confidence_evidence
    : fallbackEvidence(response);
  const providerLabel = providerLabelFor(response);
  const stages = [
    ["Intent Detection", insights?.intent],
    ["Entity Extraction", entities],
    ["Business Rules", {
      measures: entities?.["measures"],
      filters: entities?.["filters"],
      registered_rules: coverageReport?.["business_logic"]
    }],
    ["Planner", insights?.plan],
    ["Join Discovery", { selected_tables: selectedTables, join_path: insights?.join_path, join_graph: coverageReport?.["join_graph"] }],
    ["LLM Assist", insights?.llm_trace],
    ["SQL Generation", { sql: response?.sql }],
    ["Validation", { valid: insights?.valid, message: insights?.validation }],
    ["Confidence Scoring", { breakdown: insights?.confidence_breakdown, evidence }],
    ["Coverage Analysis", insights?.coverage_report]
  ] as const;

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Explainable AI</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div>
          <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
            <span>Confidence</span>
            <span>{insights?.confidence ?? 0}%</span>
          </div>
          <Progress value={insights?.confidence ?? 0} />
        </div>
        {evidence.length ? (
          <div className="grid gap-2">
            {evidence.map((item) => <EvidenceRow key={item.key} item={item} />)}
          </div>
        ) : null}
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <Metric label="Intent" value={insights?.query_type ?? "Waiting"} />
          <Metric label="Validation" value={!response ? "Waiting" : insights?.valid ? "Valid" : "Blocked"} />
          <Metric label="Provider" value={providerLabel} />
          <Metric label="Complexity" value={insights?.query_complexity ?? "SIMPLE"} />
          <Metric label="Confidence Band" value={insights?.confidence_band ?? "LOW"} />
          <Metric label="Repair Attempts" value={String(insights?.repair_attempts ?? 0)} />
          <Metric label="Tables" value={selectedTables.join(", ") || "-"} />
          <Metric label="Columns" value={(insights?.columns ?? []).join(", ") || "-"} />
        </div>
        {insights?.fallback_used ? (
          <div className="rounded-md border border-amber-300/20 bg-amber-300/10 p-3 text-sm text-amber-100">
            {fallbackReasonLabel(insights.fallback_reason)}
          </div>
        ) : null}
        {insights?.generic_warning ? (
          <div className="rounded-md border border-indigo-300/20 bg-indigo-300/10 p-3 text-sm text-indigo-100">
            {insights.generic_warning}
          </div>
        ) : null}
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-slate-500">Join Path</div>
          <div className="flex flex-wrap gap-2">
            {(insights?.join_path ?? []).length ? (
              insights?.join_path?.map((item) => <Badge key={item} tone="cyan">{item}</Badge>)
            ) : hasPlan && selectedTables.length <= 1 ? (
              <Badge tone="emerald">Single-table plan, no join required</Badge>
            ) : hasPlan ? (
              <Badge tone="cyan">Planner completed, no explicit join path</Badge>
            ) : response ? (
              <Badge tone="amber">Planner stopped for clarification</Badge>
            ) : (
              <Badge>Run a query to inspect its join plan</Badge>
            )}
          </div>
        </div>
        {insights?.clarification_options?.length ? (
          <div className="rounded-md border border-amber-300/20 bg-amber-300/10 p-3 text-sm text-amber-100">
            {insights.clarification_options.join(", ")}
          </div>
        ) : null}
        <div className="space-y-2">
          <div className="mb-2 text-xs font-medium uppercase text-slate-500">Reasoning Timeline</div>
          {stages.map(([label, value], index) => (
            <details key={label} className="group rounded-md border border-white/10 bg-white/[0.04]">
              <summary className="flex cursor-pointer list-none items-center gap-3 p-3 text-sm text-slate-200">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-cyan-300/10 text-xs text-cyan-200">{index + 1}</span>
                <span className="flex-1">{label}</span>
                <span className="text-xs text-slate-500 group-open:hidden">Expand</span>
              </summary>
              <div className="border-t border-white/10 p-3"><JsonBlock value={value} /></div>
            </details>
          ))}
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-slate-500">Runtime Trace</div>
          <JsonBlock value={insights?.execution_trace ?? insights?.agent_telemetry} />
        </div>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm text-white">{value}</div>
    </div>
  );
}

function EvidenceRow({ item }: { item: ConfidenceEvidenceItem }) {
  const score = typeof item.score === "number" ? Math.max(0, Math.min(100, item.score)) : null;
  const isSkipped = !item.applicable || score === null;
  const Icon = isSkipped
    ? CircleSlash2
    : item.status === "passed"
      ? CheckCircle2
      : item.status === "warning"
        ? Gauge
        : AlertTriangle;
  const tone = isSkipped
    ? "slate"
    : item.status === "passed"
      ? "emerald"
      : item.status === "warning"
        ? "amber"
        : "amber";
  const missing = item.missing?.filter(Boolean) ?? [];

  return (
    <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className={isSkipped ? "h-4 w-4 text-slate-500" : item.status === "passed" ? "h-4 w-4 text-emerald-200" : "h-4 w-4 text-amber-200"} />
          <span className="truncate text-xs font-medium text-slate-200">{item.label}</span>
        </div>
        <Badge tone={tone} className="h-6 shrink-0">
          {isSkipped ? "N/A" : `${Math.round(score)}%`}
        </Badge>
      </div>
      {isSkipped ? (
        <div className="h-2 rounded-full border border-dashed border-white/10 bg-white/[0.03]" />
      ) : (
        <Progress value={score} />
      )}
      {item.note ? <div className="mt-2 line-clamp-2 text-xs text-slate-500">{item.note}</div> : null}
      {missing.length ? (
        <div className="mt-2 line-clamp-2 text-xs text-amber-100">
          Missing: {missing.slice(0, 4).join(", ")}
        </div>
      ) : null}
    </div>
  );
}
