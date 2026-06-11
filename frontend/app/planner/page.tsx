"use client";

import { Filter, GitMerge, Sigma, Table2 } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { plannerStages } from "@/features/demo/demo-data";
import { Badge } from "@/components/ui/badge";

const steps = [
  { label: "Table selection", icon: Table2 },
  { label: "Join chain", icon: GitMerge },
  { label: "Filters", icon: Filter },
  { label: "Aggregations", icon: Sigma }
];

export default function PlannerPage() {
  const response = useCopilotStore((state) => state.activeResponse);

  return (
    <AppShell>
      <PageHeader title="Query Planner" description="Visual representation of table selection, joins, filters, aggregations, and final plan confidence." />
      <div className="grid gap-4 md:grid-cols-4">
        {steps.map((step, index) => {
          const Icon = step.icon;
          const stage = plannerStages[index];
          return (
            <Card key={step.label}>
              <CardContent>
                <Icon className="mb-3 h-5 w-5 text-cyan-200" />
                <div className="text-sm font-medium text-white">{step.label}</div>
                <div className="mt-2 text-xs leading-5 text-slate-400">{stage.detail}</div>
                <Badge tone="cyan" className="mt-3">{stage.metric}</Badge>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Planner Payload</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="overflow-auto rounded-md bg-slate-950/80 p-4 text-sm text-cyan-100 scrollbar-thin">
            {JSON.stringify(response?.insights.plan ?? { status: "Run a copilot query to inspect the plan." }, null, 2)}
          </pre>
        </CardContent>
      </Card>
    </AppShell>
  );
}
