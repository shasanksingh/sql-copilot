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
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <Metric label="Intent" value={insights?.query_type ?? "Waiting"} />
          <Metric label="Validation" value={insights?.valid ? "Valid" : "Blocked"} />
          <Metric label="Tables" value={(insights?.selected_tables ?? insights?.tables ?? []).join(", ") || "-"} />
          <Metric label="Columns" value={(insights?.columns ?? []).join(", ") || "-"} />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-slate-500">Join Path</div>
          <div className="flex flex-wrap gap-2">
            {(insights?.join_path ?? []).length ? (
              insights?.join_path?.map((item) => <Badge key={item} tone="cyan">{item}</Badge>)
            ) : (
              <Badge>Waiting for planner</Badge>
            )}
          </div>
        </div>
        {insights?.clarification_options?.length ? (
          <div className="rounded-md border border-amber-300/20 bg-amber-300/10 p-3 text-sm text-amber-100">
            {insights.clarification_options.join(", ")}
          </div>
        ) : null}
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-slate-500">Entities</div>
          <JsonBlock value={insights?.entities} />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-slate-500">Intent JSON</div>
          <JsonBlock value={insights?.intent} />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-slate-500">Query Plan</div>
          <JsonBlock value={insights?.plan} />
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
