"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Database,
  FileKey2,
  Fingerprint,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  UserCog,
  Users
} from "lucide-react";

import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  getAdminAuditLogs,
  getAdminUsers,
  getPrivateSchema,
  importPrivateSchema,
  reindexPrivateSchema,
  searchPrivateSchema,
  updateAdminUser
} from "@/features/api/client";
import type { AuthUser } from "@/features/api/types";
import { useAuth } from "@/features/auth/auth-provider";
import { useToastStore } from "@/features/store/use-toast-store";

export default function AdminPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const pushToast = useToastStore((state) => state.pushToast);
  const [catalogFile, setCatalogFile] = useState<File>();
  const [searchText, setSearchText] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ kind: string; table: string; column?: string | null; score: number }>>([]);
  const isAdmin = user?.role === "admin";

  const privateSchema = useQuery({
    queryKey: ["admin-private-schema"],
    queryFn: getPrivateSchema,
    enabled: isAdmin
  });
  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: getAdminUsers,
    enabled: isAdmin
  });
  const auditLogs = useQuery({
    queryKey: ["admin-audit-logs"],
    queryFn: () => getAdminAuditLogs(60),
    enabled: isAdmin
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => importPrivateSchema(file),
    onSuccess: async () => {
      setCatalogFile(undefined);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin-private-schema"] }),
        queryClient.invalidateQueries({ queryKey: ["schema-catalog"] }),
        queryClient.invalidateQueries({ queryKey: ["relationships"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-audit-logs"] })
      ]);
      pushToast({ title: "Confidential catalog imported", description: "The administrator retrieval index is ready.", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Catalog import failed",
      description: error instanceof Error ? error.message : "The confidential catalog could not be imported.",
      variant: "error"
    })
  });

  const reindexMutation = useMutation({
    mutationFn: reindexPrivateSchema,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin-private-schema"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-audit-logs"] })
      ]);
      pushToast({ title: "Private index rebuilt", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Index rebuild failed",
      description: error instanceof Error ? error.message : "Unable to rebuild the private index.",
      variant: "error"
    })
  });

  const userMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: number; payload: { role?: AuthUser["role"]; is_active?: boolean } }) =>
      updateAdminUser(userId, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-audit-logs"] })
      ]);
      pushToast({ title: "Account access updated", variant: "success" });
    },
    onError: (error) => pushToast({
      title: "Access update failed",
      description: error instanceof Error ? error.message : "Unable to update this account.",
      variant: "error"
    })
  });

  const summary = useMemo(() => ({
    tables: privateSchema.data?.tables.length ?? 0,
    relationships: privateSchema.data?.relationships.length ?? 0,
    documents: privateSchema.data?.embedding.documents ?? 0,
    activeUsers: (users.data?.users ?? []).filter((item) => item.is_active).length
  }), [privateSchema.data, users.data]);

  if (!isAdmin) {
    return (
      <AppShell>
        <Card>
          <CardContent className="flex min-h-72 flex-col items-center justify-center text-center">
            <ShieldCheck className="mb-3 h-10 w-10 text-amber-300" />
            <div className="text-lg font-semibold text-white">Administrator access required</div>
            <p className="mt-2 max-w-md text-sm leading-6 text-slate-400">
              Confidential schema controls, account access, and audit records are restricted to administrators.
            </p>
          </CardContent>
        </Card>
      </AppShell>
    );
  }

  const runSearch = async () => {
    const query = searchText.trim();
    if (!query) return;
    try {
      const response = await searchPrivateSchema(query);
      setSearchResults(response.matches);
    } catch (error) {
      pushToast({
        title: "Private search failed",
        description: error instanceof Error ? error.message : "Unable to search the private catalog.",
        variant: "error"
      });
    }
  };

  return (
    <AppShell>
      <PageHeader
        title="Administrator Console"
        description="Manage confidential schema retrieval, account access, review queues, and system audit activity."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard icon={Database} label="Private tables" value={summary.tables} />
        <SummaryCard icon={Activity} label="Relationships" value={summary.relationships} />
        <SummaryCard icon={Fingerprint} label="Indexed documents" value={summary.documents} />
        <SummaryCard icon={Users} label="Active accounts" value={summary.activeUsers} />
      </div>

      <div className="mt-4 grid gap-4 2xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,.65fr)]">
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>Confidential schema vault</CardTitle>
                <p className="mt-1 text-sm text-slate-400">Stored and indexed on the backend runtime volume; never exposed to ordinary user sessions.</p>
              </div>
              <Badge tone={privateSchema.data?.enabled ? "emerald" : "amber"}>
                {privateSchema.data?.enabled ? "Admin scope ready" : "Catalog not imported"}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 rounded-md border border-cyan-300/15 bg-cyan-300/[0.04] p-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                <label className="min-w-0 text-sm text-slate-300">
                  <span className="mb-2 block font-medium text-white">Import private JSON catalog</span>
                  <input
                    type="file"
                    accept="application/json,.json"
                    className="block w-full rounded-md border border-white/10 bg-slate-950/80 px-3 py-2 text-xs text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-cyan-300/15 file:px-3 file:py-1.5 file:text-cyan-100"
                    onChange={(event) => setCatalogFile(event.target.files?.[0])}
                  />
                </label>
                <div className="flex gap-2">
                  <Button
                    disabled={!catalogFile || importMutation.isPending}
                    onClick={() => catalogFile && importMutation.mutate(catalogFile)}
                  >
                    <Upload className="h-4 w-4" />Import
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!privateSchema.data?.enabled || reindexMutation.isPending}
                    onClick={() => reindexMutation.mutate()}
                  >
                    <RefreshCw className="h-4 w-4" />Reindex
                  </Button>
                </div>
              </div>

              <div className="grid gap-3 rounded-md border border-white/10 bg-white/[0.03] p-4 md:grid-cols-[minmax(0,1fr)_auto]">
                <Input
                  value={searchText}
                  onChange={(event) => setSearchText(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && void runSearch()}
                  placeholder="Test private schema retrieval"
                />
                <Button variant="outline" onClick={() => void runSearch()} disabled={!privateSchema.data?.enabled}>
                  <Search className="h-4 w-4" />Search index
                </Button>
                {searchResults.length ? (
                  <div className="grid gap-2 md:col-span-2 sm:grid-cols-2 xl:grid-cols-3">
                    {searchResults.map((match, index) => (
                      <div key={`${match.table}-${match.column ?? "table"}-${index}`} className="rounded border border-white/10 bg-slate-950/50 p-3 text-xs">
                        <div className="font-medium text-white">{match.table}{match.column ? `.${match.column}` : ""}</div>
                        <div className="mt-1 text-slate-500">{match.kind} · {match.score}% match</div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {(privateSchema.data?.tables ?? []).map((table) => (
                  <div key={table.name} className="rounded-md border border-white/10 bg-white/[0.03] p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 font-medium text-white">{table.name}</div>
                      <Badge tone="indigo">{table.columns.length}</Badge>
                    </div>
                    <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-400">{table.purpose}</p>
                  </div>
                ))}
              </div>

              {privateSchema.data?.embedding ? (
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                  <FileKey2 className="h-4 w-4 text-cyan-300" />
                  <span>{privateSchema.data.embedding.algorithm}</span>
                  <span>· {privateSchema.data.embedding.dimensions} dimensions</span>
                  <span>· local embeddings</span>
                  <span>· remote model {privateSchema.data.remote_llm_enabled ? "approved" : "blocked"}</span>
                  <span>· {privateSchema.data.embedding.catalog_fingerprint}</span>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <CardTitle>Account access</CardTitle>
              <Badge tone="cyan">{users.data?.users.length ?? 0} accounts</Badge>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-left text-sm">
                <thead className="text-xs uppercase tracking-[0.12em] text-slate-500">
                  <tr><th className="pb-3">Account</th><th className="pb-3">Role</th><th className="pb-3">Status</th><th className="pb-3 text-right">Access</th></tr>
                </thead>
                <tbody className="divide-y divide-white/10">
                  {(users.data?.users ?? []).map((item) => (
                    <tr key={item.id}>
                      <td className="py-3 pr-4"><div className="font-medium text-white">{item.name}</div><div className="text-xs text-slate-500">{item.email}</div></td>
                      <td className="py-3 pr-4">
                        <select
                          value={item.role}
                          disabled={userMutation.isPending || item.id === user?.id}
                          onChange={(event) => userMutation.mutate({ userId: item.id, payload: { role: event.target.value as AuthUser["role"] } })}
                          className="rounded border border-white/10 bg-slate-950 px-2 py-1.5 text-xs text-slate-200"
                        >
                          <option value="user">User</option><option value="admin">Admin</option>
                        </select>
                      </td>
                      <td className="py-3 pr-4"><Badge tone={item.is_active ? "emerald" : "slate"}>{item.is_active ? "Active" : "Disabled"}</Badge></td>
                      <td className="py-3 text-right">
                        <Button
                          variant="outline"
                          className="h-8 px-3 text-xs"
                          disabled={userMutation.isPending || item.id === user?.id}
                          onClick={() => userMutation.mutate({ userId: item.id, payload: { is_active: !item.is_active } })}
                        >
                          <UserCog className="h-3.5 w-3.5" />{item.is_active ? "Disable" : "Enable"}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Administration</CardTitle></CardHeader>
            <CardContent className="grid gap-2">
              <AdminLink href="/admin/schema-requests" label="Review schema requests and feedback" />
              <AdminLink href="/settings" label="Configure provider and email delivery" />
              <AdminLink href="/data-model-studio" label="Manage public dynamic schema" />
              <AdminLink href="/schema-graph" label="Inspect administrator relationship graph" />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between"><CardTitle>Audit activity</CardTitle><Badge tone="slate">latest 60</Badge></CardHeader>
            <CardContent className="max-h-[720px] space-y-2 overflow-y-auto scrollbar-thin">
              {(auditLogs.data?.logs ?? []).map((item) => (
                <div key={item.id} className="rounded-md border border-white/10 bg-white/[0.03] p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="break-words text-sm font-medium text-white">{item.event.replaceAll("_", " ")}</div>
                    <Badge tone={item.level === "error" ? "amber" : "slate"}>{item.level}</Badge>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">{item.user_name ?? item.user_email ?? "System"} · {new Date(item.created_at).toLocaleString()}</div>
                </div>
              ))}
              {!auditLogs.isLoading && !auditLogs.data?.logs.length ? <div className="py-8 text-center text-sm text-slate-500">No audit activity yet.</div> : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}

function SummaryCard({ icon: Icon, label, value }: { icon: typeof Database; label: string; value: number }) {
  return <Card><CardContent className="flex items-center justify-between gap-3"><div><div className="text-xs uppercase tracking-[0.14em] text-slate-500">{label}</div><div className="mt-1 text-2xl font-semibold text-white">{value}</div></div><Icon className="h-6 w-6 text-cyan-300" /></CardContent></Card>;
}

function AdminLink({ href, label }: { href: Route; label: string }) {
  return <Link href={href} className="rounded-md border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-slate-300 transition hover:border-cyan-300/30 hover:bg-cyan-300/10 hover:text-white">{label}</Link>;
}
