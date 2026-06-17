"use client";

import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Clock, Copy, DatabaseZap, Send, Sparkles, UserRound } from "lucide-react";
import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { generateSql } from "@/features/api/client";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { useToastStore } from "@/features/store/use-toast-store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ExplainabilityPanel } from "./explainability-panel";
import { Badge } from "@/components/ui/badge";

const categorizedPrompts = [
  { category: "HR", prompts: ["Top performers by department", "Count employees by department"] },
  { category: "Finance", prompts: ["Revenue by quarter", "List invoices grouped by status"] },
  { category: "Projects", prompts: ["Active projects by client tier", "Projects ending this month", "Sprints ending this month by project"] },
  { category: "Operations", prompts: ["Find tasks due this week by assignee", "Deployments this week by environment"] },
  { category: "Analytics", prompts: ["Running revenue by month", "Top 10 clients by invoice amount"] }
];

const tablePrompts: Record<string, string[]> = {
  employees: [
    "Top performers by department",
    "Count active employees by department",
    "Employee hours by department"
  ],
  time_logs: [
    "Running hours by employee each month",
    "Top performers by department",
    "Hours logged by project"
  ],
  payments: [
    "Revenue by quarter",
    "Running revenue by month",
    "Revenue by payment method"
  ],
  invoices: [
    "Top 10 clients by invoice amount",
    "List invoices grouped by status",
    "Invoices due this month by client"
  ],
  tasks: [
    "Find tasks due this week by assignee",
    "Overdue tasks by assignee",
    "Task count by priority"
  ],
  projects: [
    "Active projects by client tier",
    "Show project budget by client tier",
    "Projects ending this month"
  ],
  clients: [
    "Active projects by client tier",
    "Top 10 clients by invoice amount",
    "Clients by industry"
  ],
  bugs: [
    "Open bugs by severity",
    "Critical bugs by assignee",
    "Resolved bugs by project"
  ],
  sprints: [
    "Sprints ending this month by project",
    "Count sprints by status",
    "Active sprints by project"
  ],
  deployments: [
    "Deployments this week by environment",
    "Count deployments by environment",
    "Deployments by releaser"
  ]
};

export function CopilotChat() {
  const [query, setQuery] = useState("");
  const [pendingQuery, setPendingQuery] = useState("");
  const scrollAnchorRef = useRef<HTMLDivElement>(null);
  const history = useCopilotStore((state) => state.history);
  const activeResponse = useCopilotStore((state) => state.activeResponse);
  const addResponse = useCopilotStore((state) => state.addResponse);
  const pushToast = useToastStore((state) => state.pushToast);
  const suggestions = useMemo(() => {
    const general = categorizedPrompts.flatMap((group) => group.prompts);
    if (!activeResponse) {
      return general;
    }
    const tables = activeResponse.insights.selected_tables?.length
      ? activeResponse.insights.selected_tables
      : activeResponse.insights.tables;
    const related = tables.flatMap((table) => tablePrompts[table] ?? []);
    const queryText = activeResponse.query.toLowerCase();
    if (queryText.includes("revenue")) related.unshift(...tablePrompts.payments);
    if (queryText.includes("task")) related.unshift(...tablePrompts.tasks);
    if (queryText.includes("performer")) related.unshift(...tablePrompts.employees);
    const contextual = [...new Set(related)]
      .filter((item) => item.toLowerCase() !== queryText)
      .slice(0, 2);
    return [...new Set([...contextual, ...general])]
      .filter((item) => item.toLowerCase() !== queryText);
  }, [activeResponse]);

  const mutation = useMutation({
    mutationFn: generateSql,
    onSuccess: (response) => {
      addResponse(response);
      setPendingQuery("");
      pushToast({
        title: response.insights.valid ? "SQL generated" : "Clarification needed",
        description: response.insights.valid ? `Confidence ${response.insights.confidence}%` : response.message,
        variant: response.insights.valid ? "success" : "warning"
      });
    },
    onError: (error) => {
      setPendingQuery("");
      pushToast({ title: "Backend request failed", description: error instanceof Error ? error.message : "Unable to generate SQL.", variant: "error" });
    }
  });

  const submit = (value = query) => {
    const text = value.trim();
    if (!text) return;
    setQuery("");
    setPendingQuery(text);
    mutation.mutate(text);
  };

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history, mutation.isPending]);

  const copySql = async (sql: string) => {
    await navigator.clipboard.writeText(sql);
    pushToast({ title: "SQL copied", variant: "success" });
  };

  return (
    <div className={activeResponse ? "grid min-h-0 gap-4 xl:h-[calc(100dvh-12rem)] xl:grid-cols-[minmax(0,1fr)_430px]" : "grid min-h-0 gap-4 xl:h-[calc(100dvh-12rem)]"}>
      <Card className="flex h-[calc(100dvh-10.5rem)] min-w-0 flex-col overflow-hidden md:h-[calc(100dvh-12rem)] xl:h-full">
        <CardHeader className="flex shrink-0 flex-row items-center justify-between gap-3">
          <CardTitle>Copilot Console</CardTitle>
          <Badge tone="cyan">Streaming UI</Badge>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col p-0">
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4 sm:px-5 scrollbar-thin">
            <AnimatePresence>
              {history.map((item) => (
                <motion.div key={`${item.query}-${item.insights.confidence}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                  <Message icon={<UserRound className="h-4 w-4" />} tone="user">{item.query}</Message>
                  <Message icon={<Bot className="h-4 w-4" />} tone="assistant">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap gap-2">
                        <Badge tone={item.insights.valid ? "emerald" : "amber"}>{item.insights.valid ? "Valid SQL" : "Needs review"}</Badge>
                        <Badge tone="indigo">{item.insights.confidence}% confidence</Badge>
                      </div>
                      <Button variant="ghost" className="h-8 px-2" onClick={() => copySql(item.sql)} aria-label="Copy SQL">
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                    <pre className="overflow-auto whitespace-pre-wrap break-all rounded-md bg-slate-950/70 p-3 font-mono text-sm leading-6 text-cyan-50 scrollbar-thin">{item.sql}</pre>
                  </Message>
                </motion.div>
              ))}
            </AnimatePresence>
            {pendingQuery ? <Message icon={<UserRound className="h-4 w-4" />} tone="user">{pendingQuery}</Message> : null}
            {mutation.isPending ? (
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                <div className="mt-1 text-cyan-200"><Bot className="h-4 w-4" /></div>
                <div className="flex min-w-0 flex-1 items-center gap-3 rounded-lg border border-cyan-300/20 bg-cyan-300/10 p-4 text-sm text-cyan-100">
                  <Clock className="h-4 w-4 animate-spin" />
                  Reading schema, planning joins, validating SQL...
                </div>
              </motion.div>
            ) : null}
            {!history.length && !pendingQuery && (
              <div className="flex min-h-48 items-center justify-center rounded-lg border border-dashed border-white/10 px-4 text-center text-sm text-slate-500">
                Ask a schema-aware question to generate validated SQL.
              </div>
            )}
            <div ref={scrollAnchorRef} />
          </div>
          <div className="shrink-0 border-t border-white/10 bg-slate-950/92 p-3 backdrop-blur-xl sm:p-4">
            <div className="mb-3 flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
              {suggestions.map((item) => (
                <Button key={item} variant="outline" className="h-8 shrink-0 px-3 text-xs" onClick={() => submit(item)} disabled={mutation.isPending}>
                  <Sparkles className="h-3.5 w-3.5" />
                  {item}
                </Button>
              ))}
            </div>
            <Textarea
              className="max-h-40 min-h-20 resize-none break-words"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              placeholder="Ask for SQL in natural language"
            />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <DatabaseZap className="h-4 w-4 text-cyan-200" />
                Uses schema graph, validator, confidence scoring
              </div>
              <Button onClick={() => submit()} disabled={mutation.isPending}>
                <Send className="h-4 w-4" />
                {mutation.isPending ? "Generating" : "Generate SQL"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      <AnimatePresence>
        {activeResponse ? (
          <motion.div className="min-h-0 xl:overflow-y-auto xl:pr-1 scrollbar-thin" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 24 }}>
            <ExplainabilityPanel response={activeResponse} />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function Message({ icon, tone, children }: { icon: React.ReactNode; tone: "user" | "assistant"; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className={tone === "user" ? "mt-1 text-indigo-200" : "mt-1 text-cyan-200"}>{icon}</div>
      <div className="min-w-0 flex-1 overflow-hidden break-words rounded-lg border border-white/10 bg-white/[0.04] p-4 text-sm text-slate-100">{children}</div>
    </div>
  );
}
