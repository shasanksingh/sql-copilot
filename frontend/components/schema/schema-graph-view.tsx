"use client";

import { useQuery } from "@tanstack/react-query";
import ReactFlow, { Background, Controls, MiniMap, type Edge, type Node } from "reactflow";
import { getRelationships } from "@/features/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fallbackRelationships, schemaTables } from "@/features/demo/demo-data";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function SchemaGraphView() {
  const { data } = useQuery({ queryKey: ["relationships"], queryFn: getRelationships });
  const tables = data?.tables?.length ? data.tables : schemaTables.map((table) => table.name);
  const relationships = data?.relationships ?? fallbackRelationships;
  const nodes: Node[] = tables.map((table, index) => ({
    id: table,
    position: { x: (index % 4) * 280, y: Math.floor(index / 4) * 170 },
    data: { label: `${table}\n${schemaTables.find((item) => item.name === table)?.columns.length ?? 0} columns` },
    className: "rounded-md border border-cyan-300/30 bg-slate-950/95 px-4 py-3 text-center text-sm text-white shadow-glow"
  }));
  const edges: Edge[] = Object.values(relationships)
    .flat()
    .map((rel, index) => ({
      id: `${rel.from_table}-${rel.to_table}-${index}`,
      source: rel.from_table,
      target: rel.to_table,
      animated: true,
      label: `${rel.from_column} -> ${rel.to_column}`,
      style: { stroke: index < 3 ? "#22d3ee" : "#64748b" }
    }));

  return (
    <Card className="h-[calc(100vh-11rem)] overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>Interactive Relationship Graph</CardTitle>
        <div className="flex flex-wrap gap-2">
          <Badge tone="cyan">{tables.length} tables</Badge>
          <Button variant="outline" className="h-8 px-3">Auto layout</Button>
          <Button variant="outline" className="h-8 px-3">Highlight join paths</Button>
        </div>
      </CardHeader>
      <CardContent className="h-full p-0">
        <ReactFlow nodes={nodes} edges={edges} fitView className="bg-slate-950/30">
          <Background color="rgba(148,163,184,.16)" />
          <MiniMap nodeColor="#22d3ee" maskColor="rgba(2,6,23,.76)" />
          <Controls className="overflow-hidden rounded-md border border-white/10 bg-slate-950/90 text-white" />
        </ReactFlow>
      </CardContent>
    </Card>
  );
}
