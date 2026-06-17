"use client";

import { useMemo } from "react";
import ReactFlow, { Background, Controls, MarkerType, MiniMap, type Edge, type Node } from "reactflow";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { Badge } from "@/components/ui/badge";

const steps = [
  { id: "intent", label: "Intent", key: "intent" },
  { id: "entities", label: "Entities", key: "entity" },
  { id: "tables", label: "Tables", key: "column" },
  { id: "joins", label: "Joins", key: "join" },
  { id: "aggregations", label: "Aggregations", key: "aggregation" },
  { id: "sql", label: "SQL", key: "validation" }
] as const;

export default function PlannerPage() {
  const response = useCopilotStore((state) => state.activeResponse);
  const nodes = useMemo<Node[]>(() => steps.map((step, index) => {
    const score = response?.insights.confidence_breakdown?.[step.key] ?? 0;
    const detail = step.id === "intent"
      ? response?.insights.query_type ?? "Waiting"
      : step.id === "tables"
        ? (response?.insights.selected_tables ?? []).join(", ") || "No tables"
        : step.id === "joins"
          ? `${response?.insights.join_path?.length ?? 0} edges`
          : step.id === "sql"
            ? response?.insights.valid ? "Validated" : "Not validated"
            : `${Math.round(score)}% coverage`;
    return {
      id: step.id,
      position: { x: index * 230, y: index % 2 === 0 ? 70 : 220 },
      data: {
        label: (
          <div className="min-w-36">
            <div className="text-xs uppercase tracking-wide text-slate-500">{index + 1}. Stage</div>
            <div className="mt-1 font-semibold text-white">{step.label}</div>
            <div className="mt-2 max-w-40 truncate text-xs text-slate-400">{detail}</div>
            <Badge tone={score >= 70 ? "emerald" : score > 0 ? "amber" : "slate"} className="mt-2">{Math.round(score)}%</Badge>
          </div>
        )
      },
      style: {
        border: "1px solid rgba(255,255,255,.12)",
        borderRadius: 10,
        background: "rgba(15,23,42,.94)",
        padding: 14,
        color: "white"
      }
    };
  }), [response]);
  const edges = useMemo<Edge[]>(() => steps.slice(0, -1).map((step, index) => ({
    id: `${step.id}-${steps[index + 1].id}`,
    source: step.id,
    target: steps[index + 1].id,
    animated: Boolean(response),
    markerEnd: { type: MarkerType.ArrowClosed, color: "#22d3ee" },
    style: { stroke: "#22d3ee" }
  })), [response]);

  return (
    <AppShell>
      <PageHeader title="Query Planner" description="Visual representation of table selection, joins, filters, aggregations, and final plan confidence." />
      <Card className="overflow-hidden">
        <CardContent className="h-[500px] p-0">
          <ReactFlow nodes={nodes} edges={edges} fitView minZoom={0.35} maxZoom={1.4} nodesDraggable>
            <Background color="rgba(148,163,184,.18)" gap={22} />
            <MiniMap pannable zoomable />
            <Controls />
          </ReactFlow>
        </CardContent>
      </Card>
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
