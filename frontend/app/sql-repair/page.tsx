"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert, ClipboardCheck, Copy, DatabaseZap, Network, Wrench } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { repairSql } from "@/features/api/client";
import type { SqlRepairIssue, SqlRepairResponse } from "@/features/api/types";
import { useToastStore } from "@/features/store/use-toast-store";
import { SQL_LANGUAGES, type SqlLanguage } from "@/lib/sql-language";
import { useState } from "react";

function issueTone(issue: SqlRepairIssue) {
  if (issue.severity === "error") return "amber" as const;
  if (issue.severity === "warning") return "indigo" as const;
  return "slate" as const;
}

function IssueList({ title, issues, empty }: { title: string; issues: SqlRepairIssue[]; empty: string }) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{title}</h2>
        {issues.length ? <Badge tone="slate">{issues.length}</Badge> : null}
      </div>
      {issues.length ? (
        <div className="space-y-2">
          {issues.map((issue, index) => (
            <article key={`${issue.kind}-${issue.title}-${index}`} className="min-w-0 rounded-xl border border-slate-200/80 bg-slate-50/80 p-3 dark:border-white/10 dark:bg-white/[0.035]">
              <div className="flex min-w-0 flex-wrap items-center gap-2"><Badge tone={issueTone(issue)}>{issue.severity}</Badge><h3 className="min-w-0 text-sm font-semibold text-slate-950 dark:text-white">{issue.title}</h3></div>
              <p className="mt-2 break-words text-sm leading-5 text-slate-600 dark:text-slate-400">{issue.detail}</p>
              {issue.fix ? <p className="mt-2 rounded-lg border border-cyan-300/15 bg-cyan-300/10 px-2.5 py-2 text-xs leading-5 text-cyan-800 dark:text-cyan-100"><span className="font-semibold">Next check:</span> {issue.fix}</p> : null}
            </article>
          ))}
        </div>
      ) : <div className="rounded-xl border border-dashed border-slate-300 p-3 text-sm text-slate-500 dark:border-white/15">{empty}</div>}
    </section>
  );
}

function RepairWorkspace() {
  const [statement, setStatement] = useState("SELECT client_name, industry FROM clients WHERE industry == 'retail'");
  const [errorMessage, setErrorMessage] = useState("");
  const [language, setLanguage] = useState<SqlLanguage>("sql");
  const [result, setResult] = useState<SqlRepairResponse | null>(null);
  const pushToast = useToastStore((state) => state.pushToast);
  const mutation = useMutation({
    mutationFn: repairSql,
    onSuccess: (response) => {
      setResult(response);
      pushToast({ title: response.valid ? "SQL checked" : "Review the reported issues", description: response.validation, variant: response.valid ? "success" : "warning" });
    },
    onError: (error) => pushToast({ title: "SQL check could not run", description: error instanceof Error ? error.message : "Please try again.", variant: "error" })
  });

  const copyCorrectedSql = async () => {
    if (!result?.corrected_sql) return;
    await navigator.clipboard.writeText(result.corrected_sql);
    pushToast({ title: "Corrected statement copied", variant: "success" });
  };

  return (
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)]">
      <Card className="min-w-0">
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0"><CardTitle>Check a SQL statement</CardTitle><p className="mt-1 text-sm leading-5 text-slate-600 dark:text-slate-400">Paste a statement and, if available, the database error that was returned.</p></div>
          <label className="shrink-0 text-xs font-medium text-slate-600 dark:text-slate-300"><span className="sr-only">SQL language</span><select value={language} onChange={(event) => setLanguage(event.target.value as SqlLanguage)} className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-800 outline-none transition focus:border-cyan-400 focus:ring-2 focus:ring-cyan-300/30 dark:border-white/15 dark:bg-slate-950 dark:text-slate-100">{SQL_LANGUAGES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="block"><span className="mb-2 block text-sm font-medium text-slate-800 dark:text-slate-200">SQL statement</span><Textarea value={statement} onChange={(event) => setStatement(event.target.value)} className="min-h-64 resize-y font-mono text-sm leading-6" placeholder="Paste a SQL statement" /></label>
          <label className="block"><span className="mb-2 block text-sm font-medium text-slate-800 dark:text-slate-200">Database error (optional)</span><Textarea value={errorMessage} onChange={(event) => setErrorMessage(event.target.value)} className="min-h-28 resize-y text-sm leading-6" placeholder="For example: ORA-12541: TNS:no listener, connection refused, timeout, or authentication error" /></label>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs leading-5 text-slate-500">The checker does not open a database connection or execute SQL.</p><Button onClick={() => mutation.mutate({ statement, errorMessage, language })} disabled={mutation.isPending || !statement.trim()}>{mutation.isPending ? <ClipboardCheck className="h-4 w-4 animate-pulse" /> : <Wrench className="h-4 w-4" />}{mutation.isPending ? "Checking" : "Check and correct"}</Button></div>
        </CardContent>
      </Card>
      <Card className="min-w-0 xl:max-h-[calc(100dvh-13rem)] xl:overflow-y-auto scrollbar-thin">
        <CardHeader><div className="flex items-start justify-between gap-3"><div><CardTitle>Repair result</CardTitle><p className="mt-1 text-sm text-slate-600 dark:text-slate-400">Syntax, safety, and reported connection findings.</p></div>{result ? <Badge tone={result.valid ? "emerald" : "amber"}>{result.valid ? "Ready to review" : "Needs review"}</Badge> : null}</div></CardHeader>
        <CardContent className="space-y-5">
          {result ? <>
            <section className="rounded-xl border border-cyan-300/20 bg-cyan-300/10 p-3"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Validation</div><p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{result.validation}</p></div>{result.safe_to_run ? <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-500" /> : <CircleAlert className="h-5 w-5 shrink-0 text-amber-500" />}</div></section>
            <section><div className="mb-2 flex items-center justify-between gap-2"><h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Corrected statement</h2><Button variant="outline" className="h-8 px-2.5 text-xs" onClick={copyCorrectedSql}><Copy className="h-3.5 w-3.5" />Copy</Button></div><pre className="max-h-64 overflow-auto rounded-xl bg-slate-950 p-3 font-mono text-xs leading-5 text-cyan-50 scrollbar-thin"><code className="whitespace-pre-wrap break-words">{result.corrected_sql || "No corrected statement is available."}</code></pre></section>
            <IssueList title="Statement findings" issues={result.issues} empty="No changes were required." />
            <IssueList title="Connection diagnostics" issues={result.connection_diagnostics} empty="Add the database error message above to diagnose listener, port, DNS, timeout, or sign-in problems." />
          </> : <div className="flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 px-6 text-center dark:border-white/15"><DatabaseZap className="h-9 w-9 text-cyan-500" /><p className="mt-3 text-sm font-medium text-slate-800 dark:text-slate-200">Your corrected statement will appear here.</p><p className="mt-1 text-sm leading-5 text-slate-500">Choose a language, paste the SQL, and include an error message when a connection failed.</p></div>}
        </CardContent>
      </Card>
      <Card className="min-w-0 xl:col-span-2"><CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start"><Network className="h-5 w-5 shrink-0 text-cyan-500" /><div><h2 className="text-sm font-semibold text-slate-950 dark:text-white">Connection guidance stays safe</h2><p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-400">Listener, port, DNS, timeout, and credential checks are inferred only from the error you paste. No network scans, connection attempts, or database changes are made from this page.</p></div></CardContent></Card>
    </div>
  );
}

export default function SqlRepairPage() {
  return <AppShell><PageHeader title="SQL Repair" description="Correct read-only SQL, identify syntax problems, and understand reported database connection errors." icon={Wrench} tone="amber" /><RepairWorkspace /></AppShell>;
}
