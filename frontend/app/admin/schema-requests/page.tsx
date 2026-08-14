"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, ShieldCheck, XCircle } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { applySchemaRequest, getFeedback, getSchemaRequests, updateSchemaRequestStatus } from "@/features/api/client";
import { useAuth } from "@/features/auth/auth-provider";
import { useToastStore } from "@/features/store/use-toast-store";
import type { SchemaRequest } from "@/features/api/types";

export default function AdminSchemaRequestsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const pushToast = useToastStore((state) => state.pushToast);
  const requests = useQuery({ queryKey: ["admin-schema-requests"], queryFn: getSchemaRequests, enabled: user?.role === "admin" });
  const feedback = useQuery({ queryKey: ["admin-feedback"], queryFn: getFeedback, enabled: user?.role === "admin" });
  const mutation = useMutation({
    mutationFn: ({ requestId, status }: { requestId: number; status: SchemaRequest["status"] }) =>
      updateSchemaRequestStatus(requestId, status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin-schema-requests"] });
      pushToast({ title: "Review status updated", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Status update failed",
      description: error instanceof Error ? error.message : "Unable to update request.",
      variant: "error"
    })
  });
  const applyMutation = useMutation({
    mutationFn: applySchemaRequest,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin-schema-requests"] }),
        queryClient.invalidateQueries({ queryKey: ["schema-requests"] }),
        queryClient.invalidateQueries({ queryKey: ["schema-catalog"] }),
        queryClient.invalidateQueries({ queryKey: ["metadata-status"] }),
        queryClient.invalidateQueries({ queryKey: ["relationships"] }),
        queryClient.invalidateQueries({ queryKey: ["metrics"] })
      ]);
      pushToast({ title: "Schema proposal applied", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Apply failed",
      description: error instanceof Error ? error.message : "Unable to apply proposal.",
      variant: "error"
    })
  });

  if (user?.role !== "admin") {
    return (
      <AppShell>
        <Card>
          <CardContent className="flex min-h-64 flex-col items-center justify-center text-center">
            <ShieldCheck className="mb-3 h-8 w-8 text-amber-200" />
            <div className="font-medium text-white">Administrator access required</div>
            <div className="mt-2 text-sm text-slate-400">This queue contains submissions from multiple users.</div>
          </CardContent>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader title="Admin Review" description="Review schema requests, uploaded samples, business requirements, and product feedback." />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Schema Request Queue</CardTitle>
            <Badge tone="amber">{requests.data?.analytics.pending_requests ?? 0} pending</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {(requests.data?.requests ?? []).map((item) => (
              <div key={item.request_id} className="rounded-md border border-white/10 bg-white/[0.04] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-medium text-white">Request #{item.request_id}</div>
                    <div className="mt-1 text-xs text-slate-500">{item.request_kind ?? "table_request"} / user {item.requested_by_user_id ?? "legacy"}</div>
                  </div>
                  <Badge tone={item.status === "pending" ? "amber" : item.status === "rejected" ? "slate" : "emerald"}>{item.status}</Badge>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-300">{item.user_notes || item.business_context}</p>
                {item.attachment_name ? <div className="mt-3 flex items-center gap-2 text-xs text-indigo-200"><FileText className="h-4 w-4" />{item.attachment_name}</div> : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button className="h-8 px-3 text-xs" onClick={() => mutation.mutate({ requestId: item.request_id, status: "approved" })}><CheckCircle2 className="h-3.5 w-3.5" />Approve</Button>
                  <Button variant="outline" className="h-8 px-3 text-xs" onClick={() => applyMutation.mutate(item.request_id)} disabled={applyMutation.isPending}>Apply proposal</Button>
                  <Button variant="outline" className="h-8 px-3 text-xs" onClick={() => mutation.mutate({ requestId: item.request_id, status: "generated" })}>Mark generated</Button>
                  <Button variant="ghost" className="h-8 px-3 text-xs text-rose-200" onClick={() => mutation.mutate({ requestId: item.request_id, status: "rejected" })}><XCircle className="h-3.5 w-3.5" />Reject</Button>
                </div>
              </div>
            ))}
            {!requests.isLoading && !requests.data?.requests.length ? <Empty label="No schema requests are waiting for review." /> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Product Feedback</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {(feedback.data?.feedback ?? []).map((item) => (
              <div key={item.id} className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                <div className="flex items-center justify-between gap-2">
                  <Badge tone="cyan">{item.category}</Badge>
                  <span className="text-[11px] text-slate-500">{item.user_name ?? item.user_email ?? "User"}</span>
                </div>
                <p className="mt-2 break-words text-sm leading-6 text-slate-300">{item.message}</p>
              </div>
            ))}
            {!feedback.isLoading && !feedback.data?.feedback.length ? <Empty label="No feedback has been submitted." /> : null}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="rounded-md border border-dashed border-white/10 p-6 text-center text-sm text-slate-500">{label}</div>;
}
