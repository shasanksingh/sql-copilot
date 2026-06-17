"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import type { CopilotResponse } from "@/features/api/types";

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-48 overflow-auto rounded-md bg-slate-950/80 p-3 text-xs leading-5 text-cyan-100 scrollbar-thin">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}

export function ExplainabilityPanel({ response }: { response?: CopilotResponse }) {
  const insights = response?.insights;
  const selectedTables = insights?.selected_tables ?? insights?.tables ?? [];
  const hasPlan = Boolean(insights?.plan);
  const stages = [
    ["Intent Detection", insights?.intent],
    ["Entity Extraction", insights?.entities],
    ["Planner", insights?.plan],
    ["SQL Generation", { sql: response?.sql }],
    ["Validation", { valid: insights?.valid, message: insights?.validation }],
    ["Confidence Scoring", insights?.confidence_breakdown],
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
        {insights?.confidence_breakdown ? (
          <div className="grid gap-2">
            {Object.entries(insights.confidence_breakdown).map(([key, value]) => (
              <div key={key} className="rounded-md border border-white/10 bg-white/[0.04] p-2">
                <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
                  <span>{key.replaceAll("_", " ")}</span>
                  <span>{Math.round(value)}%</span>
                </div>
                <Progress value={value} />
              </div>
            ))}
          </div>
        ) : null}
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <Metric label="Intent" value={insights?.query_type ?? "Waiting"} />
          <Metric label="Validation" value={!response ? "Waiting" : insights?.valid ? "Valid" : "Blocked"} />
          <Metric label="Tables" value={selectedTables.join(", ") || "-"} />
          <Metric label="Columns" value={(insights?.columns ?? []).join(", ") || "-"} />
        </div>
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
