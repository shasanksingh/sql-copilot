"use client";

import { AlertTriangle, Gauge, KeyRound, Zap } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { Badge } from "@/components/ui/badge";

export default function OptimizerPage() {
  const active = useCopilotStore((state) => state.activeResponse);
  const suggestions = active?.insights.optimizations ?? [];
  const tables = active?.insights.selected_tables ?? active?.insights.tables ?? ["projects", "clients"];
  const indexCandidates = tables.map((table) => `${table}.id / join key coverage`);

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
                  <div className="text-sm text-white">{active?.insights.valid ? "Low execution risk" : "Needs validation"}</div>
                  <div className="mt-1 text-xs text-slate-500">Based on confidence, validation result, and optimizer warnings.</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
