"use client";

import { useQuery } from "@tanstack/react-query";
import { Columns3, GitBranch, Search } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getRelationships } from "@/features/api/client";
import { useState } from "react";
import { schemaTables, fallbackRelationships } from "@/features/demo/demo-data";
import { Badge } from "@/components/ui/badge";

export default function SchemaExplorerPage() {
  const [search, setSearch] = useState("");
  const { data } = useQuery({ queryKey: ["relationships"], queryFn: getRelationships });
  const tableNames = data?.tables?.length ? data.tables : schemaTables.map((table) => table.name);
  const relationships = data?.relationships ?? fallbackRelationships;
  const tables = tableNames.filter((table) => table.toLowerCase().includes(search.toLowerCase()));

  return (
    <AppShell>
      <PageHeader title="Schema Explorer" description="Explore tables, columns, and relationships surfaced by the backend schema graph." />
      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-500" />
        <Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search tables" />
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {tables.map((table) => (
          <Card key={table}>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>{table}</CardTitle>
                <Badge tone="cyan">{schemaTables.find((item) => item.name === table)?.rowCount ?? "live"}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-slate-300">
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase text-slate-500">
                  <Columns3 className="h-3.5 w-3.5" />
                  Columns
                </div>
                <div className="flex flex-wrap gap-2">
                  {(schemaTables.find((item) => item.name === table)?.columns ?? ["id", "name", "status", "created_at"]).map((column) => (
                    <Badge key={column}>{column}</Badge>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase text-slate-500">
                  <GitBranch className="h-3.5 w-3.5" />
                  Relationships
                </div>
              {(relationships[table] ?? []).slice(0, 6).map((rel) => (
                <div key={`${rel.from_table}-${rel.from_column}-${rel.to_table}`} className="rounded-md bg-white/[0.04] p-2">
                  {rel.from_table}.{rel.from_column} {"->"} {rel.to_table}.{rel.to_column}
                </div>
              ))}
              {!relationships[table]?.length && <div className="text-slate-500">No direct relationships detected.</div>}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
