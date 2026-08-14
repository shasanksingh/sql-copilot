"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Clock, Copy, DatabaseZap, Download, Search, Send, Sparkles, Trash2, UserRound } from "lucide-react";
import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { generateSql, getSchemaCatalog } from "@/features/api/client";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { useToastStore } from "@/features/store/use-toast-store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ExplainabilityPanel } from "./explainability-panel";
import { Badge } from "@/components/ui/badge";
import type { CopilotInsights, SchemaCatalogColumn, SchemaCatalogTable } from "@/features/api/types";

const fallbackPrompts = [
  "Show active records by status",
  "Count records by department",
  "Total revenue by quarter",
  "Find open work due this week",
  "Top clients by amount"
];

function humanize(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function findColumn(table: SchemaCatalogTable, matcher: (column: SchemaCatalogColumn) => boolean) {
  return table.columns.find(matcher);
}

function isNumericColumn(column: SchemaCatalogColumn) {
  const type = column.data_type.toLowerCase();
  const name = column.name.toLowerCase();
  return /(int|decimal|numeric|number|float|double|money|currency)/.test(type)
    || /(amount|revenue|budget|cost|price|salary|hours|score|total)/.test(name);
}

function isDateColumn(column: SchemaCatalogColumn) {
  const type = column.data_type.toLowerCase();
  const name = column.name.toLowerCase();
  return /(date|time|timestamp)/.test(type) || /(date|time|created|updated|due|closed|paid|start|end)/.test(name);
}

function promptsForTable(table: SchemaCatalogTable) {
  const subject = humanize(table.name);
  const status = findColumn(table, (column) => /(^status$|_status$|state|priority|severity|environment|tier|department|industry)/i.test(column.name));
  const date = findColumn(table, isDateColumn);
  const measure = findColumn(table, isNumericColumn);
  const display = findColumn(table, (column) => /(name|title|label|email|description)/i.test(column.name));
  const prompts = new Set<string>();

  prompts.add(`List ${subject}`);
  if (display) prompts.add(`Show ${subject} with ${humanize(display.name)}`);
  if (status) prompts.add(`Count ${subject} by ${humanize(status.name)}`);
  if (date) prompts.add(`Show ${subject} from this month`);
  if (measure && status) prompts.add(`Total ${humanize(measure.name)} by ${humanize(status.name)} for ${subject}`);
  if (measure && date) prompts.add(`Trend ${humanize(measure.name)} by month for ${subject}`);

  return [...prompts];
}

function uniquePrompts(items: string[], limit = 14) {
  return [...new Set(items.map((item) => item.trim()).filter(Boolean))].slice(0, limit);
}

export function CopilotChat() {
  const [query, setQuery] = useState("");
  const [pendingQuery, setPendingQuery] = useState("");
  const [historyFilter, setHistoryFilter] = useState("");
  const scrollAnchorRef = useRef<HTMLDivElement>(null);
  const history = useCopilotStore((state) => state.history);
  const activeResponse = useCopilotStore((state) => state.activeResponse);
  const addResponse = useCopilotStore((state) => state.addResponse);
  const setActiveResponse = useCopilotStore((state) => state.setActiveResponse);
  const deleteResponse = useCopilotStore((state) => state.deleteResponse);
  const clearHistory = useCopilotStore((state) => state.clearHistory);
  const pushToast = useToastStore((state) => state.pushToast);
  const schemaQuery = useQuery({
    queryKey: ["schema-catalog", "copilot-prompts"],
    queryFn: getSchemaCatalog,
    staleTime: 60_000
  });
  const filteredHistory = useMemo(() => {
    const term = historyFilter.trim().toLowerCase();
    return history
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => {
        if (!term) return true;
        return `${item.query} ${item.sql} ${item.insights.summary ?? ""}`
          .toLowerCase()
          .includes(term);
      });
  }, [history, historyFilter]);
  const suggestions = useMemo(() => {
    const schemaTables = schemaQuery.data?.tables ?? [];
    const tableMap = new Map(schemaTables.map((table) => [table.name, table]));
    const schemaDriven = schemaTables.flatMap(promptsForTable);
    const recentSuccessful = history
      .slice(-5)
      .reverse()
      .filter((item) => item.insights.valid)
      .map((item) => item.query);
    if (!activeResponse) {
      return uniquePrompts([...schemaDriven, ...recentSuccessful, ...fallbackPrompts]);
    }
    const tables = activeResponse.insights.selected_tables?.length
      ? activeResponse.insights.selected_tables
      : activeResponse.insights.tables;
    const related = tables.flatMap((table) => {
      const schemaTable = tableMap.get(table);
      return schemaTable ? promptsForTable(schemaTable) : [];
    });
    const queryText = activeResponse.query.toLowerCase();
    const contextual = uniquePrompts(related, 6)
      .filter((item) => item.toLowerCase() !== queryText)
      .slice(0, 4);
    return uniquePrompts([...contextual, ...schemaDriven, ...recentSuccessful, ...fallbackPrompts])
      .filter((item) => item.toLowerCase() !== queryText);
  }, [activeResponse, history, schemaQuery.data]);
  const providerBadge = (insights: CopilotInsights) => {
    if (insights?.generic_sql) return "Spider Generic SQL";
    const provider = String(insights?.llm_provider ?? insights?.provider_status?.provider ?? "local");
    const model = String(insights?.llm_model ?? insights?.provider_status?.model ?? "");
    const reason = String(insights?.fallback_reason ?? insights?.llm_trace?.fallback_reason ?? "");
    const skipReason = String(insights?.llm_trace?.skip_reason ?? "");
    if (reason === "network_blocked") return "NVIDIA network blocked";
    if (skipReason === "deterministic_plan_validated") return "Validated deterministic plan";
    if (insights?.fallback_used) return "Validated fallback";
    if (provider === "local") return "Local Planner";
    if (provider === "nvidia") return "NVIDIA GPT-OSS-20B";
    return model || provider;
  };

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

  const exportHistory = () => {
    const blob = new Blob([
      JSON.stringify({
        exported_at: new Date().toISOString(),
        conversations: history
      }, null, 2)
    ], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `sql-copilot-chats-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    pushToast({ title: "Chats exported", variant: "success" });
  };

  return (
    <div className={activeResponse ? "grid min-h-0 gap-3 xl:h-[calc(100dvh-6.25rem)] xl:grid-cols-[minmax(0,1fr)_360px] 2xl:grid-cols-[minmax(0,1fr)_390px]" : "grid min-h-0 gap-3 xl:h-[calc(100dvh-6.25rem)]"}>
      <Card className="flex h-[calc(100dvh-5rem)] min-w-0 flex-col overflow-hidden md:h-[calc(100dvh-6.25rem)] xl:h-full">
        <CardHeader className="flex shrink-0 flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center sm:justify-between sm:px-4">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle>Copilot Console</CardTitle>
            <Badge tone="cyan">Streaming UI</Badge>
          </div>
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:max-w-md">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-2 h-4 w-4 text-slate-500" />
              <Input
                className="h-8 pl-9"
                value={historyFilter}
                onChange={(event) => setHistoryFilter(event.target.value)}
                placeholder="Search chats"
                aria-label="Search chats"
              />
            </div>
            <Button title="Export chats" aria-label="Export chats" variant="outline" className="h-8 w-8 px-0" onClick={exportHistory} disabled={!history.length}>
              <Download className="h-4 w-4" />
            </Button>
            <Button title="Clear chat history" aria-label="Clear chat history" variant="outline" className="h-8 w-8 px-0" onClick={clearHistory} disabled={!history.length}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col p-0">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-2.5 py-3 sm:px-3 scrollbar-thin">
            <AnimatePresence>
              {filteredHistory.map(({ item, index }) => (
                <motion.div key={`${index}-${item.query}-${item.insights.confidence}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-2">
                  <Message icon={<UserRound className="h-4 w-4" />} tone="user">{item.query}</Message>
                  <Message icon={<Bot className="h-4 w-4" />} tone="assistant">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap gap-2">
                        <Badge tone={item.insights.generic_sql ? "indigo" : item.insights.valid ? "emerald" : "amber"}>
                          {item.insights.generic_sql ? "Generic SQL" : item.insights.valid ? "Valid SQL" : "Needs review"}
                        </Badge>
                        <Badge tone="indigo">{item.insights.confidence}% confidence</Badge>
                        <Badge tone={item.insights.fallback_used ? "amber" : item.insights.llm_provider === "nvidia" ? "cyan" : "slate"}>
                          {providerBadge(item.insights)}
                        </Badge>
                        <Badge tone="slate">{item.insights.query_complexity ?? "SIMPLE"}</Badge>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" className="h-8 px-2" onClick={() => setActiveResponse(item)} aria-label="Open explainability">
                          <Sparkles className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" className="h-8 px-2" onClick={() => copySql(item.sql)} aria-label="Copy SQL">
                          <Copy className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" className="h-8 px-2" onClick={() => deleteResponse(index)} aria-label="Delete chat">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    {item.insights.generic_warning ? (
                      <div className="mb-2 rounded-md border border-indigo-300/20 bg-indigo-300/10 p-2 text-xs leading-5 text-indigo-100">
                        {item.insights.generic_warning}
                      </div>
                    ) : null}
                    <SqlBlock sql={item.sql} />
                  </Message>
                </motion.div>
              ))}
            </AnimatePresence>
            {pendingQuery ? <Message icon={<UserRound className="h-4 w-4" />} tone="user">{pendingQuery}</Message> : null}
            {mutation.isPending ? (
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                <div className="mt-1 text-cyan-200"><Bot className="h-4 w-4" /></div>
                <div className="flex min-w-0 flex-1 items-center gap-3 rounded-lg border border-cyan-300/20 bg-cyan-300/10 p-3 text-sm text-cyan-100">
                  <Clock className="h-4 w-4 animate-spin" />
                  Reading schema, planning joins, validating SQL...
                </div>
              </motion.div>
            ) : null}
            {history.length > 0 && !filteredHistory.length && (
              <div className="flex min-h-32 items-center justify-center rounded-lg border border-dashed border-white/10 px-4 text-center text-sm text-slate-500">
                No chats match the current search.
              </div>
            )}
            {!history.length && !pendingQuery && (
              <div className="flex min-h-48 items-center justify-center rounded-lg border border-dashed border-white/10 px-4 text-center text-sm text-slate-500">
                Ask a schema-aware question to generate validated SQL.
              </div>
            )}
            <div ref={scrollAnchorRef} />
          </div>
          <div className="sticky bottom-0 z-10 shrink-0 border-t border-white/10 bg-slate-950/92 p-2 backdrop-blur-xl">
            <div className="mb-1.5 flex max-w-full gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
              {suggestions.map((item) => (
                <Button key={item} variant="outline" className="h-7 shrink-0 px-2.5 text-xs" onClick={() => submit(item)} disabled={mutation.isPending}>
                  <Sparkles className="h-3 w-3" />
                  {item}
                </Button>
              ))}
            </div>
            <Textarea
              className="max-h-20 min-h-11 resize-none break-words p-2 text-sm leading-5"
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
            <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <DatabaseZap className="h-4 w-4 text-cyan-200" />
                {schemaQuery.data
                  ? `${schemaQuery.data.summary.tables_count} live tables, schema graph, validator, confidence scoring`
                  : "Loading live schema catalog, validator, confidence scoring"}
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
    <div className="flex gap-2">
      <div className={tone === "user" ? "mt-1 text-indigo-200" : "mt-1 text-cyan-200"}>{icon}</div>
      <div className="min-w-0 flex-1 overflow-hidden break-words rounded-lg border border-white/10 bg-white/[0.04] p-3 text-sm text-slate-100">{children}</div>
    </div>
  );
}

const SQL_KEYWORDS = new Set([
  "SELECT", "FROM", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON", "WHERE", "GROUP", "BY",
  "ORDER", "HAVING", "LIMIT", "AS", "AND", "OR", "CASE", "WHEN", "THEN", "ELSE", "END",
  "SUM", "COUNT", "AVG", "MIN", "MAX", "DATE_TRUNC", "OVER", "PARTITION", "DESC", "ASC"
]);

const SQL_TOKEN_PATTERN = /(--[^\n]*|'(?:''|[^'])*'|\b[A-Z_]+\b|\b\d+(?:\.\d+)?\b)/gi;

function SqlBlock({ sql }: { sql: string }) {
  const parts = sql.split(SQL_TOKEN_PATTERN).filter((part) => part.length > 0);
  return (
    <pre className="max-h-[56dvh] min-h-48 overflow-auto rounded-md bg-slate-950/70 p-3 font-mono text-sm leading-6 text-cyan-50 scrollbar-thin">
      <code className="whitespace-pre-wrap break-words">
        {parts.map((part, index) => {
          const upper = part.toUpperCase();
          const className = SQL_KEYWORDS.has(upper)
            ? "text-indigo-200"
            : part.startsWith("--")
              ? "text-slate-500"
              : part.startsWith("'")
                ? "text-emerald-200"
                : /^\d/.test(part)
                  ? "text-amber-200"
                  : undefined;
          return className ? <span key={`${part}-${index}`} className={className}>{part}</span> : part;
        })}
      </code>
    </pre>
  );
}
