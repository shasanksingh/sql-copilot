"use client";

import { Download, FileSpreadsheet, Play, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { sampleRows } from "@/features/demo/demo-data";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { useToastStore } from "@/features/store/use-toast-store";
import { Badge } from "@/components/ui/badge";

export default function ExecutionPage() {
  const activeSql = useCopilotStore((state) => state.activeResponse?.sql);
  const [sql, setSql] = useState(activeSql || "SELECT\n  p.project_name,\n  p.status\nFROM projects p\nWHERE LOWER(p.status) = 'active';");
  const [hasRun, setHasRun] = useState(false);
  const [approved, setApproved] = useState(false);
  const pushToast = useToastStore((state) => state.pushToast);
  const columns = useMemo(() => Object.keys(sampleRows[0]), []);

  const exportRows = (format: "csv" | "excel") => {
    const csv = [columns.join(","), ...sampleRows.map((row) => columns.map((column) => row[column as keyof typeof row]).join(","))].join("\n");
    const blob = new Blob([csv], { type: format === "csv" ? "text/csv" : "application/vnd.ms-excel" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `sql-copilot-results.${format === "csv" ? "csv" : "xls"}`;
    link.click();
    URL.revokeObjectURL(url);
    pushToast({ title: `${format === "csv" ? "CSV" : "Excel"} export ready`, variant: "success" });
  };

  return (
    <AppShell>
      <PageHeader title="Query Execution" description="Review SQL and explicitly approve a read-only preview before inspecting result grids or exporting files." />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>SQL Editor</CardTitle>
            <Badge tone="cyan"><ShieldCheck className="h-3.5 w-3.5" />Read-only safe mode</Badge>
          </CardHeader>
          <CardContent>
            <Textarea className="min-h-72" value={sql} onChange={(event) => setSql(event.target.value)} />
            <label className="mt-4 flex cursor-pointer items-start gap-2 rounded-lg border border-amber-300/20 bg-amber-300/10 p-3 text-sm text-amber-100">
              <input type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} className="mt-0.5 h-4 w-4 accent-cyan-400" />
              <span><span className="font-semibold">Human approval required.</span> I have reviewed this read-only SQL. The current screen shows a safe preview only; no connected database is run automatically.</span>
            </label>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button disabled={!approved} onClick={() => { setHasRun(true); pushToast({ title: "Approved preview ready", description: "No connected database was executed.", variant: "success" }); }}>
                <Play className="h-4 w-4" />Approve preview
              </Button>
              <Button variant="outline" onClick={() => exportRows("csv")}><Download className="h-4 w-4" />Export CSV</Button>
              <Button variant="outline" onClick={() => exportRows("excel")}><FileSpreadsheet className="h-4 w-4" />Export Excel</Button>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>Results Grid</CardTitle>
            <Badge tone={hasRun ? "emerald" : "slate"}>{hasRun ? "3 rows" : "Preview"}</Badge>
          </CardHeader>
          <CardContent>
            <div className="overflow-auto rounded-md border border-white/10 scrollbar-thin">
              <table className="w-full min-w-[520px] text-left text-sm">
                <thead className="bg-white/[0.04] text-xs uppercase text-slate-500">
                  <tr>{columns.map((column) => <th key={column} className="px-3 py-2 font-medium">{column}</th>)}</tr>
                </thead>
                <tbody>
                  {sampleRows.map((row) => (
                    <tr key={row.project_name} className="border-t border-white/10 text-slate-300">
                      {columns.map((column) => <td key={column} className="px-3 py-2">{row[column as keyof typeof row]}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
