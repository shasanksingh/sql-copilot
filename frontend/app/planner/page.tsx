"use client";

import { useMemo } from "react";
import ReactFlow, { Background, Controls, MarkerType, MiniMap, type Edge, type Node } from "reactflow";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { Badge } from "@/components/ui/badge";

export default function PlannerPage() {
  const response = useCopilotStore((state) => state.activeResponse);
  const plannerSteps = useMemo(() => {
    const insights = response?.insights;
    const selectedTables = insights?.selected_tables ?? [];
    const joinPath = insights?.join_path ?? [];
    const joinSteps = joinPath.length > 4
      ? joinPath.map((join, index) => ({
          id: `join-${index}`,
          label: `Join ${index + 1}`,
          key: "join",
          detail: join
        }))
      : [{
          id: "joins",
          label: "Join Graph",
          key: "join",
          detail: `${joinPath.length} edge${joinPath.length === 1 ? "" : "s"}`
        }];
    return [
      { id: "intent", label: "Intent", key: "intent", detail: insights?.query_type ?? "Waiting" },
      { id: "entities", label: "Entities", key: "entity", detail: `${(insights?.entities?.["canonical_terms"] as string[] | undefined)?.length ?? 0} terms` },
      { id: "business", label: "Business Rules", key: "semantic", detail: `${(insights?.entities?.["measures"] as string[] | undefined)?.length ?? 0} measures` },
      { id: "tables", label: "Tables", key: "column", detail: selectedTables.join(", ") || "No tables" },
      ...joinSteps,
      { id: "aggregations", label: "Aggregations", key: "aggregation", detail: `${(insights?.plan?.["aggregations"] as unknown[] | undefined)?.length ?? 0} planned` },
      { id: "filters", label: "Filters", key: "semantic", detail: `${(insights?.plan?.["filters"] as unknown[] | undefined)?.length ?? 0} planned` },
      { id: "plan", label: "Query Plan", key: "planner_confidence", detail: insights?.query_complexity ?? "SIMPLE" },
      { id: "sql", label: "SQL", key: "validation", detail: insights?.valid ? "Validated" : "Not validated" },
      { id: "confidence", label: "Confidence", key: "system_confidence", detail: insights?.confidence_band ?? "LOW" }
    ];
  }, [response]);
  const nodes = useMemo<Node[]>(() => plannerSteps.map((step, index) => {
    const evidence = response?.insights.confidence_evidence?.find((item) => item.key === step.key);
    const score = typeof evidence?.score === "number"
      ? evidence.score
      : response?.insights.confidence_breakdown?.[step.key] ?? 0;
    const applicable = evidence?.applicable ?? Boolean(response);
    const columns = Math.min(5, Math.max(1, Math.ceil(Math.sqrt(plannerSteps.length))));
    const column = index % columns;
    const row = Math.floor(index / columns);
    return {
      id: step.id,
      position: { x: column * 250, y: row * 160 + 60 },
      data: {
        label: (
          <div className="min-w-36">
            <div className="text-xs uppercase tracking-wide text-slate-500">{index + 1}. Stage</div>
            <div className="mt-1 font-semibold text-white">{step.label}</div>
            <div className="mt-2 max-w-44 truncate text-xs text-slate-400">{step.detail}</div>
            <Badge tone={!applicable ? "slate" : score >= 70 ? "emerald" : score > 0 ? "amber" : "slate"} className="mt-2">
              {!applicable ? "N/A" : `${Math.round(score)}%`}
            </Badge>
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
  }), [plannerSteps, response]);
  const edges = useMemo<Edge[]>(() => plannerSteps.slice(0, -1).map((step, index) => ({
    id: `${step.id}-${plannerSteps[index + 1].id}`,
    source: step.id,
    target: plannerSteps[index + 1].id,
    animated: Boolean(response),
    markerEnd: { type: MarkerType.ArrowClosed, color: "#22d3ee" },
    style: { stroke: "#22d3ee" }
  })), [plannerSteps, response]);

  return (
    <AppShell>
      <PageHeader title="Query Planner" description="Visual representation of table selection, joins, filters, aggregations, and final plan confidence." />
      <Card className="overflow-hidden">
        <CardContent className="h-[620px] p-0">
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
