"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Columns3, GitBranch, KeyRound, Network, Search } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getSchemaCatalog } from "@/features/api/client";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";

export default function SchemaExplorerPage() {
  const [search, setSearch] = useState("");
  const [domain, setDomain] = useState("all");
  const [selectedTable, setSelectedTable] = useState("");
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["schema-catalog"], queryFn: getSchemaCatalog });
  const needle = search.toLowerCase();
  const tables = (data?.tables ?? []).filter((table) =>
    (domain === "all" || table.domain === domain) &&
    (table.name.toLowerCase().includes(needle) ||
      table.columns.some((column) => column.name.toLowerCase().includes(needle)))
  );
  const domains = useMemo(() => [...new Set((data?.tables ?? []).map((table) => table.domain))], [data?.tables]);
  const selected = (data?.tables ?? []).find((table) => table.name === selectedTable) ?? tables[0];
  const recommendations = selected?.relationships.map((rel) => `${selected.name} -> ${rel.to_table}`) ?? [];

  return (
    <AppShell>
      <PageHeader title="Schema Explorer" description="Explore tables, columns, and relationships surfaced by the backend schema graph." />
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-500" />
          <Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search tables or columns" />
        </div>
        <select className="h-10 min-w-48 rounded-md border border-white/10 bg-slate-950/70 px-3 text-sm text-white" value={domain} onChange={(event) => setDomain(event.target.value)}>
          <option value="all">All domains</option>
          {domains.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <Link href="/schema-graph" className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-white/12 bg-white/[0.03] px-4 text-sm font-medium text-slate-200 transition hover:bg-white/10">
          <Network className="h-4 w-4" />Graph view
        </Link>
      </div>
      {isError ? <div className="mb-4 rounded-md border border-rose-300/20 bg-rose-300/10 p-4 text-sm text-rose-100">Schema catalog failed to load. <button className="ml-2 underline" onClick={() => void refetch()}>Retry</button></div> : null}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="grid content-start gap-4 md:grid-cols-2">
        {tables.map((table) => (
          <Card key={table.name} className={selected?.name === table.name ? "ring-1 ring-cyan-300/40" : ""} onClick={() => setSelectedTable(table.name)}>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>{table.name}</CardTitle>
                <Badge tone="cyan">{table.row_count}</Badge>
              </div>
              <div className="text-xs text-slate-500">{table.purpose}</div>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-slate-300">
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase text-slate-500">
                  <Columns3 className="h-3.5 w-3.5" />
                  Columns
                </div>
                <div className="flex flex-wrap gap-2">
                  {table.columns.slice(0, 12).map((column) => (
                    <Badge key={column.name} tone={column.is_pk ? "emerald" : column.is_fk ? "indigo" : "slate"}>
                      {column.name} {column.is_pk ? "PK" : column.is_fk ? "FK" : ""}
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase text-slate-500">
                  <KeyRound className="h-3.5 w-3.5" />
                  Indexes
                </div>
                <div className="flex flex-wrap gap-2">
                  {table.indexes.slice(0, 6).map((index) => <Badge key={index}>{index}</Badge>)}
                  {!table.indexes.length ? <div className="text-slate-500">No index hints detected.</div> : null}
                </div>
              </div>
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase text-slate-500">
                  <GitBranch className="h-3.5 w-3.5" />
                  Relationships
                </div>
              {table.relationships.slice(0, 6).map((rel) => (
                <div key={`${rel.from_table}-${rel.from_column}-${rel.to_table}`} className="rounded-md bg-white/[0.04] p-2">
                  {rel.from_table}.{rel.from_column} {"->"} {rel.to_table}.{rel.to_column}
                </div>
              ))}
              {!table.relationships.length && <div className="text-slate-500">No direct relationships detected.</div>}
              </div>
            </CardContent>
          </Card>
        ))}
        {!isLoading && !tables.length ? <div className="rounded-md border border-dashed border-white/10 p-8 text-center text-sm text-slate-500 md:col-span-2">No tables match the current filters.</div> : null}
        </div>
        <Card className="h-fit xl:sticky xl:top-0">
          <CardHeader>
            <CardTitle>{selected ? `${selected.name} explorer` : "Column explorer"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {selected ? (
              <>
                <div>
                  <div className="mb-2 text-xs font-medium uppercase text-slate-500">Columns</div>
                  <div className="max-h-56 space-y-2 overflow-y-auto pr-1 scrollbar-thin">
                    {selected.columns.map((column) => (
                      <div key={column.name} className="flex items-center justify-between gap-3 rounded-md bg-white/[0.04] p-2 text-sm">
                        <span className="truncate text-slate-200">{column.name}</span>
                        <span className="shrink-0 text-xs text-slate-500">{column.data_type}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-xs font-medium uppercase text-slate-500">Join recommendations</div>
                  <div className="space-y-2">
                    {recommendations.map((item) => <div key={item} className="rounded-md border border-cyan-300/10 bg-cyan-300/5 p-2 text-xs text-cyan-100">{item}</div>)}
                    {!recommendations.length ? <div className="text-sm text-slate-500">No direct join recommendation is available.</div> : null}
                  </div>
                </div>
                <Link className="inline-flex items-center gap-2 text-sm text-cyan-200 hover:text-cyan-100" href="/schema-graph"><GitBranch className="h-4 w-4" />Inspect in relationship graph</Link>
              </>
            ) : <div className="text-sm text-slate-500">Select a table to inspect columns and relationships.</div>}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
