"use client";

import { AlertTriangle, Code2, Gauge, KeyRound, Zap } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { Badge } from "@/components/ui/badge";

export default function OptimizerPage() {
  const active = useCopilotStore((state) => state.activeResponse);
  const suggestions = active?.insights.optimizations ?? [];
  const tables = active?.insights.selected_tables ?? active?.insights.tables ?? ["projects", "clients"];
  const indexCandidates = active?.insights.index_suggestions?.length
    ? active.insights.index_suggestions
    : tables.map((table) => `${table}.id / join key coverage`);
  const risk = active?.insights.valid && (active.insights.confidence_breakdown?.overall ?? 0) >= 70 ? "Low execution risk" : "Needs validation";

  return (
    <AppShell>
      <PageHeader title="SQL Optimizer" description="Review performance suggestions, missing indexes, wildcard warnings, and execution risks." />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>Performance Suggestions</CardTitle>
            <Badge tone={suggestions.length ? "cyan" : "amber"}>{suggestions.length || 1} checks</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {(suggestions.length ? suggestions : ["Run a query to receive optimizer suggestions."]).map((item) => (
              <div key={item} className="flex gap-3 rounded-md border border-white/10 bg-white/[0.04] p-3 text-sm text-slate-300">
                {suggestions.length ? <Zap className="h-4 w-4 text-cyan-200" /> : <AlertTriangle className="h-4 w-4 text-amber-200" />}
                {item}
              </div>
            ))}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Missing Index Candidates</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {indexCandidates.map((item) => (
                <div key={item} className="flex items-center gap-3 rounded-md bg-white/[0.04] p-3 text-sm text-slate-300">
                  <KeyRound className="h-4 w-4 text-indigo-200" />
                  {item}
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Risk Meter</CardTitle></CardHeader>
            <CardContent>
              <div className="flex items-center gap-3">
                <Gauge className="h-5 w-5 text-cyan-200" />
                <div>
                  <div className="text-sm text-white">{risk}</div>
              <div className="mt-1 text-xs text-slate-500">Confidence {active?.insights.confidence ?? 0}% / semantic {Math.round(active?.insights.confidence_breakdown?.semantic ?? 0)}%</div>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Estimated Cost</CardTitle></CardHeader>
            <CardContent className="text-sm text-slate-300">
              Estimated reduction: {active?.insights.cost_reduction_percent ?? 0}%. {tables.length > 2 ? "Multi-hop join path." : tables.length > 1 ? "Direct join path." : "Single table scan."}
            </CardContent>
          </Card>
        </div>
      </div>
      <Card className="mt-4">
        <CardHeader><CardTitle className="flex items-center gap-2"><Code2 className="h-4 w-4 text-cyan-200" />Before vs After SQL</CardTitle></CardHeader>
        <CardContent className="grid gap-4 xl:grid-cols-2">
          <pre className="overflow-auto whitespace-pre-wrap break-all rounded-md bg-slate-950/80 p-4 text-sm text-cyan-100 scrollbar-thin">{active?.sql ?? "-- Generate a query to inspect optimizer output."}</pre>
          <pre className="overflow-auto whitespace-pre-wrap break-all rounded-md bg-slate-950/80 p-4 text-sm text-emerald-100 scrollbar-thin">{active?.insights.optimized_sql ?? "-- Optimized SQL will appear here."}</pre>
        </CardContent>
      </Card>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Optimization Explanation</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {(active?.insights.optimization_explanation ?? ["Run a query to inspect optimizer reasoning."]).map((item) => <div key={item} className="rounded-md bg-white/[0.04] p-3 text-sm text-slate-300">{item}</div>)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Execution Plan</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {(active?.insights.execution_plan ?? ["No execution plan available."]).map((item, index) => <div key={`${item}-${index}`} className="flex gap-3 rounded-md bg-white/[0.04] p-3 text-sm text-slate-300"><span className="text-cyan-200">{index + 1}</span>{item}</div>)}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
