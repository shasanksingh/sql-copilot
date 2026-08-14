"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  DatabaseZap,
  FileCode2,
  FileJson,
  FileSpreadsheet,
  GitBranch,
  Layers3,
  MessageSquareText,
  Plus,
  RefreshCw,
  Send,
  Table2,
  Trash2
} from "lucide-react";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  applySchemaRequest,
  createFeedback,
  createSchemaRequest,
  createSchemaStudioTable,
  deleteSchemaStudioTable,
  getEnterpriseSchema,
  getMetadataStatus,
  getSchemaCatalog,
  getSchemaRequests,
  refreshMetadata
} from "@/features/api/client";
import { useAuth } from "@/features/auth/auth-provider";
import { useToastStore } from "@/features/store/use-toast-store";
import type { SchemaCatalogTable, SchemaStudioTablePayload } from "@/features/api/types";

export default function DataModelStudioPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canAdmin = user?.role === "admin";
  const pushToast = useToastStore((state) => state.pushToast);
  const [tableName, setTableName] = useState("Vendor Performance");
  const [requestKind, setRequestKind] = useState("table_request");
  const [businessPurpose, setBusinessPurpose] = useState("Track vendor SLA, delivery quality, and procurement risk.");
  const [columns, setColumns] = useState("vendor_id:INTEGER:Primary key\nvendor_name:TEXT:Vendor display name\nsla_score:DECIMAL(18,2):SLA score\nrisk_tier:TEXT:Risk tier");
  const [relationships, setRelationships] = useState("supplier_id -> suppliers.supplier_id");
  const [sampleData, setSampleData] = useState("Acme Logistics, 96, low");
  const [businessRules, setBusinessRules] = useState("SLA score must be 0-100. Risk tier is low, medium, or high.");
  const [file, setFile] = useState<File>();
  const [feedback, setFeedback] = useState("");

  const requestsQuery = useQuery({ queryKey: ["schema-requests"], queryFn: getSchemaRequests });
  const enterpriseQuery = useQuery({ queryKey: ["enterprise-schema"], queryFn: getEnterpriseSchema });
  const catalogQuery = useQuery({ queryKey: ["schema-catalog"], queryFn: getSchemaCatalog });
  const metadataQuery = useQuery({
    queryKey: ["metadata-status"],
    queryFn: getMetadataStatus,
    refetchInterval: 15_000
  });
  const latestRequest = requestsQuery.data?.requests[0];
  const domains = useMemo(() => enterpriseQuery.data?.domains.slice(0, 10) ?? [], [enterpriseQuery.data]);
  const dynamicTables = metadataQuery.data?.dynamic_tables ?? [];

  const invalidateSchema = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["schema-requests"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-schema-requests"] }),
      queryClient.invalidateQueries({ queryKey: ["enterprise-schema"] }),
      queryClient.invalidateQueries({ queryKey: ["schema-catalog"] }),
      queryClient.invalidateQueries({ queryKey: ["metadata-status"] }),
      queryClient.invalidateQueries({ queryKey: ["relationships"] }),
      queryClient.invalidateQueries({ queryKey: ["metrics"] })
    ]);
  };

  const schemaPayload = (): SchemaStudioTablePayload => ({
    name: tableName,
    domain: "Dynamic Enterprise Schema",
    purpose: businessPurpose,
    owner: user?.email ?? "data-platform",
    tags: ["dynamic", requestKind.replace("_", "-")],
    aliases: [tableName],
    columns: parseColumnInput(columns),
    relationships: parseRelationshipInput(relationships),
    indexes: parseColumnInput(columns)
      .filter((column) => column.is_pk || column.is_fk || ["status", "created_at"].includes(column.name))
      .map((column) => column.name)
  });

  const mutation = useMutation({
    mutationFn: createSchemaRequest,
    onSuccess: async () => {
      await invalidateSchema();
      pushToast({ title: "Schema request submitted", description: "Generated design is ready for developer review.", variant: "success" });
    },
    onError: (error) => {
      pushToast({ title: "Schema request failed", description: error instanceof Error ? error.message : "Unable to submit request.", variant: "error" });
    }
  });

  const liveMutation = useMutation({
    mutationFn: () => createSchemaStudioTable(schemaPayload()),
    onSuccess: async () => {
      await invalidateSchema();
      pushToast({ title: "Live schema updated", description: "Metadata, retrieval, and planner state were refreshed.", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Live schema update failed",
      description: error instanceof Error ? error.message : "Administrator access is required.",
      variant: "error"
    })
  });

  const refreshMutation = useMutation({
    mutationFn: refreshMetadata,
    onSuccess: async () => {
      await invalidateSchema();
      pushToast({ title: "Metadata refreshed", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Refresh failed",
      description: error instanceof Error ? error.message : "Unable to refresh metadata.",
      variant: "error"
    })
  });

  const applyMutation = useMutation({
    mutationFn: applySchemaRequest,
    onSuccess: async () => {
      await invalidateSchema();
      pushToast({ title: "Proposal applied", description: "Dynamic schema is live without backend restart.", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Apply failed",
      description: error instanceof Error ? error.message : "Unable to apply proposal.",
      variant: "error"
    })
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSchemaStudioTable,
    onSuccess: async () => {
      await invalidateSchema();
      pushToast({ title: "Dynamic table deleted", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Delete failed",
      description: error instanceof Error ? error.message : "Unable to delete table.",
      variant: "error"
    })
  });

  const submit = () => {
    mutation.mutate({
      table_name: tableName,
      request_kind: requestKind,
      business_purpose: businessPurpose,
      columns: parseColumnInput(columns).map((column) => column.name),
      relationships,
      sample_data: sampleData,
      business_rules: businessRules,
      file
    });
  };

  const feedbackMutation = useMutation({
    mutationFn: () => createFeedback("data_model", feedback),
    onSuccess: () => {
      setFeedback("");
      pushToast({ title: "Feedback submitted", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Feedback failed",
      description: error instanceof Error ? error.message : "Unable to submit feedback.",
      variant: "error"
    })
  });

  return (
    <AppShell>
      <PageHeader title="Data Model Studio" description="Request new tables, infer schemas from files, and manage live enterprise metadata." />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_430px]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle className="flex items-center gap-2"><DatabaseZap className="h-4 w-4 text-cyan-200" />New Table Request</CardTitle>
            <Badge tone="cyan">SchemaDesignAgent</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase text-slate-500">Request type</span>
              <select className="h-10 w-full rounded-md border border-white/10 bg-slate-950/70 px-3 text-sm text-white outline-none focus:ring-4 focus:ring-cyan-300/30" value={requestKind} onChange={(event) => setRequestKind(event.target.value)}>
                <option value="table_request">New table request</option>
                <option value="schema_request">New schema request</option>
                <option value="business_requirement">Business requirement</option>
                <option value="csv_upload">CSV upload</option>
                <option value="excel_upload">Excel upload</option>
                <option value="json_upload">JSON upload</option>
                <option value="sql_upload">SQL DDL upload</option>
                <option value="parquet_upload">Parquet upload</option>
              </select>
            </label>
            <Input value={tableName} onChange={(event) => setTableName(event.target.value)} aria-label="Table name" />
            <Textarea value={businessPurpose} onChange={(event) => setBusinessPurpose(event.target.value)} aria-label="Business purpose" />
            <Textarea className="min-h-36" value={columns} onChange={(event) => setColumns(event.target.value)} aria-label="Columns" />
            <Input value={relationships} onChange={(event) => setRelationships(event.target.value)} aria-label="Relationships" />
            <Textarea value={sampleData} onChange={(event) => setSampleData(event.target.value)} aria-label="Sample data" />
            <Textarea value={businessRules} onChange={(event) => setBusinessRules(event.target.value)} aria-label="Business rules" />
            <label className="block rounded-md border border-dashed border-white/15 bg-white/[0.03] p-4">
              <span className="mb-2 flex items-center gap-2 text-sm text-slate-300">
                {requestKind === "json_upload" ? <FileJson className="h-4 w-4 text-indigo-200" /> : requestKind === "sql_upload" ? <FileCode2 className="h-4 w-4 text-cyan-200" /> : <FileSpreadsheet className="h-4 w-4 text-emerald-200" />}
                Optional data or DDL sample
              </span>
              <input
                className="block w-full text-xs text-slate-400 file:mr-3 file:rounded-md file:border-0 file:bg-cyan-300 file:px-3 file:py-2 file:text-slate-950"
                type="file"
                accept=".csv,.json,.xlsx,.xls,.sql,.parquet,application/json,text/csv"
                onChange={(event) => setFile(event.target.files?.[0])}
              />
              <span className="mt-2 block text-xs text-slate-500">Maximum 5 MB. The backend infers columns, types, metadata, and draft relationships.</span>
            </label>
            <div className="flex flex-wrap gap-2">
              <Button onClick={submit} disabled={mutation.isPending}>
                <Send className="h-4 w-4" />
                {mutation.isPending ? "Submitting" : "Submit for Review"}
              </Button>
              <Button variant="outline" onClick={() => liveMutation.mutate()} disabled={!canAdmin || liveMutation.isPending}>
                <CheckCircle2 className="h-4 w-4" />
                {liveMutation.isPending ? "Applying" : "Apply Live"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-cyan-200" />Enterprise Scale</CardTitle></CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Metric label="Catalog tables" value={catalogQuery.data?.summary.tables_count ?? 0} />
              <Metric label="Relationships" value={catalogQuery.data?.summary.relationships_count ?? 0} />
              <Metric label="Dynamic tables" value={metadataQuery.data?.dynamic_tables.length ?? 0} />
              <Metric label="Requests" value={requestsQuery.data?.analytics.total_requests ?? 0} />
              <div className="sm:col-span-2 flex flex-wrap gap-2">
                {domains.map((domain) => <Badge key={domain}>{domain}</Badge>)}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle>Latest Generated Design</CardTitle>
              <Button variant="outline" className="h-8 px-3 text-xs" onClick={() => latestRequest && applyMutation.mutate(latestRequest.request_id)} disabled={!canAdmin || !latestRequest || applyMutation.isPending}>
                <CheckCircle2 className="h-3.5 w-3.5" />
                Apply
              </Button>
            </CardHeader>
            <CardContent>
              <pre className="max-h-80 overflow-auto rounded-md bg-slate-950/80 p-3 text-xs leading-5 text-cyan-100 scrollbar-thin">
                {JSON.stringify(latestRequest?.generated_schema ?? { status: "Submit a request to generate a schema design." }, null, 2)}
              </pre>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2"><RefreshCw className="h-4 w-4 text-cyan-200" />Live Metadata Engine</CardTitle>
              <Button variant="outline" className="h-8 px-3 text-xs" onClick={() => refreshMutation.mutate()} disabled={!canAdmin || refreshMutation.isPending}>
                <RefreshCw className={`h-3.5 w-3.5 ${refreshMutation.isPending ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-3">
                <Metric label="Version" value={metadataQuery.data?.status.version ?? 0} />
                <Metric label="BM25" value={metadataQuery.data?.status.bm25_enabled ? "on" : "off"} />
                <Metric label="FAISS" value={metadataQuery.data?.status.faiss_enabled ? "on" : "off"} />
              </div>
              <div className="max-h-72 space-y-2 overflow-auto pr-1 scrollbar-thin">
                {dynamicTables.map((table) => (
                  <LiveTableCard key={table.name} table={table} onDelete={() => deleteMutation.mutate(table.name)} disabled={!canAdmin || deleteMutation.isPending} />
                ))}
                {!metadataQuery.isLoading && !dynamicTables.length ? (
                  <div className="rounded-md border border-dashed border-white/10 p-4 text-center text-sm text-slate-500">
                    No dynamic tables are live.
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <Card className="mt-4">
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2"><Table2 className="h-4 w-4 text-cyan-200" />Developer Review Queue</CardTitle>
          <Badge tone="amber">{requestsQuery.data?.analytics.pending_requests ?? 0} pending</Badge>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(requestsQuery.data?.requests ?? []).map((item) => (
            <div key={item.request_id} className="rounded-md border border-white/10 bg-white/[0.04] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium text-white">Request #{item.request_id}</div>
                <Badge tone={item.status === "pending" ? "amber" : item.status === "rejected" ? "slate" : "emerald"}>{item.status}</Badge>
              </div>
              <div className="mt-2 line-clamp-2 text-sm text-slate-400">{item.user_notes || item.business_context}</div>
              <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                <GitBranch className="h-3.5 w-3.5" />
                {String((item.generated_schema?.domain as string) ?? "General")}
              </div>
              <Button variant="outline" className="mt-3 h-8 px-3 text-xs" onClick={() => applyMutation.mutate(item.request_id)} disabled={!canAdmin || applyMutation.isPending}>
                <CheckCircle2 className="h-3.5 w-3.5" />
                Apply proposal
              </Button>
            </div>
          ))}
          {!requestsQuery.data?.requests.length ? (
            <div className="rounded-md border border-dashed border-white/10 p-6 text-center text-sm text-slate-500">
              <Plus className="mx-auto mb-2 h-5 w-5" />
              No schema requests yet.
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><MessageSquareText className="h-4 w-4 text-cyan-200" />Feedback Portal</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea className="min-h-28" value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Describe a missing workflow, schema concern, or product improvement." />
          <Button className="mt-3" onClick={() => feedbackMutation.mutate()} disabled={feedbackMutation.isPending || feedback.trim().length < 5}>
            <Send className="h-4 w-4" />
            {feedbackMutation.isPending ? "Submitting" : "Submit feedback"}
          </Button>
        </CardContent>
      </Card>
    </AppShell>
  );
}

function parseColumnInput(value: string): SchemaStudioTablePayload["columns"] {
  const rows = value.includes("\n") ? value.split("\n") : value.split(",");
  return rows
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item, index) => {
      const [name, dataType, ...description] = item.split(":");
      const cleanName = name.trim();
      return {
        name: cleanName,
        data_type: (dataType || inferType(cleanName, index)).trim().toUpperCase(),
        description: description.join(":").trim() || `Business field ${cleanName.replaceAll("_", " ")}.`,
        is_pk: index === 0 && cleanName.endsWith("_id"),
        is_fk: cleanName.endsWith("_id") && index > 0
      };
    });
}

function parseRelationshipInput(value: string): NonNullable<SchemaStudioTablePayload["relationships"]> {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [left, right] = item.includes("->") ? item.split("->").map((part) => part.trim()) : ["", item];
      const [toTable, toColumn] = right.split(".").map((part) => part.trim());
      return {
        from_column: left || toColumn || "id",
        to_table: toTable || "",
        to_column: toColumn || "id"
      };
    })
    .filter((item) => item.to_table.length > 0 && item.to_column.length > 0);
}

function inferType(name: string, index: number) {
  if (name.endsWith("_id") || index === 0) return "INTEGER";
  if (name.includes("date") || name.endsWith("_at")) return "TIMESTAMP";
  if (name.includes("score") || name.includes("amount") || name.includes("rate")) return "DECIMAL(18,2)";
  return "TEXT";
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-white">{value}</div>
    </div>
  );
}

function LiveTableCard({ table, onDelete, disabled }: { table: SchemaCatalogTable; onDelete: () => void; disabled: boolean }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-medium text-white">{table.name}</div>
          <div className="mt-1 line-clamp-2 text-xs text-slate-500">{table.purpose}</div>
        </div>
        <Button variant="ghost" className="h-8 w-8 shrink-0 px-0 text-rose-200" onClick={onDelete} disabled={disabled} aria-label={`Delete ${table.name}`}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone="indigo">{table.columns.length} columns</Badge>
        <Badge tone="cyan">{table.relationships.length} relationships</Badge>
        <Badge tone="slate">{table.source ?? "dynamic"}</Badge>
      </div>
    </div>
  );
}
