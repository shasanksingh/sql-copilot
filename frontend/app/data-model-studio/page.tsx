"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DatabaseZap, FileJson, FileSpreadsheet, GitBranch, Layers3, MessageSquareText, Plus, Send, Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createFeedback, createSchemaRequest, getEnterpriseSchema, getSchemaRequests } from "@/features/api/client";
import { useToastStore } from "@/features/store/use-toast-store";

export default function DataModelStudioPage() {
  const queryClient = useQueryClient();
  const pushToast = useToastStore((state) => state.pushToast);
  const [tableName, setTableName] = useState("Vendor Performance");
  const [requestKind, setRequestKind] = useState("table_request");
  const [businessPurpose, setBusinessPurpose] = useState("Track vendor SLA, delivery quality, and procurement risk.");
  const [columns, setColumns] = useState("vendor_id, vendor_name, sla_score, delivery_rating, risk_tier");
  const [relationships, setRelationships] = useState("suppliers.supplier_id");
  const [sampleData, setSampleData] = useState("Acme Logistics, 96, 4.8, low");
  const [businessRules, setBusinessRules] = useState("SLA score must be 0-100. Risk tier is low, medium, or high.");
  const [file, setFile] = useState<File>();
  const [feedback, setFeedback] = useState("");

  const requestsQuery = useQuery({ queryKey: ["schema-requests"], queryFn: getSchemaRequests });
  const enterpriseQuery = useQuery({ queryKey: ["enterprise-schema"], queryFn: getEnterpriseSchema });
  const latestRequest = requestsQuery.data?.requests[0];
  const domains = useMemo(() => enterpriseQuery.data?.domains.slice(0, 10) ?? [], [enterpriseQuery.data]);

  const mutation = useMutation({
    mutationFn: createSchemaRequest,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["schema-requests"] });
      pushToast({ title: "Schema request submitted", description: "Generated design is ready for developer review.", variant: "success" });
    },
    onError: (error) => {
      pushToast({ title: "Schema request failed", description: error instanceof Error ? error.message : "Unable to submit request.", variant: "error" });
    }
  });

  const submit = () => {
    mutation.mutate({
      table_name: tableName,
      request_kind: requestKind,
      business_purpose: businessPurpose,
      columns: columns.split(",").map((item) => item.trim()).filter(Boolean),
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
      <PageHeader title="Data Model Studio" description="Request new enterprise tables, generate draft schemas, and review schema evolution demand." />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
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
                <option value="json_upload">JSON upload</option>
              </select>
            </label>
            <Input value={tableName} onChange={(event) => setTableName(event.target.value)} aria-label="Table name" />
            <Textarea value={businessPurpose} onChange={(event) => setBusinessPurpose(event.target.value)} aria-label="Business purpose" />
            <Input value={columns} onChange={(event) => setColumns(event.target.value)} aria-label="Columns" />
            <Input value={relationships} onChange={(event) => setRelationships(event.target.value)} aria-label="Relationships" />
            <Textarea value={sampleData} onChange={(event) => setSampleData(event.target.value)} aria-label="Sample data" />
            <Textarea value={businessRules} onChange={(event) => setBusinessRules(event.target.value)} aria-label="Business rules" />
            <label className="block rounded-md border border-dashed border-white/15 bg-white/[0.03] p-4">
              <span className="mb-2 flex items-center gap-2 text-sm text-slate-300">
                {requestKind === "json_upload" ? <FileJson className="h-4 w-4 text-indigo-200" /> : <FileSpreadsheet className="h-4 w-4 text-emerald-200" />}
                Optional CSV or JSON sample
              </span>
              <input
                className="block w-full text-xs text-slate-400 file:mr-3 file:rounded-md file:border-0 file:bg-cyan-300 file:px-3 file:py-2 file:text-slate-950"
                type="file"
                accept=".csv,.json,application/json,text/csv"
                onChange={(event) => setFile(event.target.files?.[0])}
              />
              <span className="mt-2 block text-xs text-slate-500">Maximum 1 MB. Content is stored with the review request.</span>
            </label>
            <Button onClick={submit} disabled={mutation.isPending}>
              <Send className="h-4 w-4" />
              {mutation.isPending ? "Submitting" : "Submit for Review"}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-cyan-200" />Enterprise Scale</CardTitle></CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Metric label="Virtual tables" value={enterpriseQuery.data?.summary.tables_count ?? 0} />
              <Metric label="Relationships" value={enterpriseQuery.data?.summary.relationships_count ?? 0} />
              <Metric label="Domains" value={enterpriseQuery.data?.summary.domains_count ?? 0} />
              <Metric label="Requests" value={requestsQuery.data?.analytics.total_requests ?? 0} />
              <div className="sm:col-span-2 flex flex-wrap gap-2">
                {domains.map((domain) => <Badge key={domain}>{domain}</Badge>)}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Latest Generated Design</CardTitle></CardHeader>
            <CardContent>
              <pre className="max-h-80 overflow-auto rounded-md bg-slate-950/80 p-3 text-xs leading-5 text-cyan-100 scrollbar-thin">
                {JSON.stringify(latestRequest?.generated_schema ?? { status: "Submit a request to generate a schema design." }, null, 2)}
              </pre>
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

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-white">{value}</div>
    </div>
  );
}
