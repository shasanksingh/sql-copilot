"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Clock, Copy, Download, Mic, Search, Send, Sparkles, Square, Trash2, UserRound, X } from "lucide-react";
import type React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { generateSql, getSchemaCatalog } from "@/features/api/client";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { useToastStore } from "@/features/store/use-toast-store";
import { useSpeechRecognition } from "@/features/voice/use-speech-recognition";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ExplainabilityPanel } from "./explainability-panel";
import { Badge } from "@/components/ui/badge";
import type { CopilotResponse, SchemaCatalogColumn, SchemaCatalogTable } from "@/features/api/types";
import { SQL_LANGUAGES, type SqlLanguage } from "@/lib/sql-language";

const fallbackPrompts = [
  "Show available associates by business unit",
  "Active associate assignments by project",
  "Customers with unpaid invoices",
  "Headcount by department",
  "Open work assigned to employees",
  "Delivery hours by project this month"
];

function isSqlAnswer(response: CopilotResponse) {
  return /^(select|with|declare)\b/i.test(response.sql.trim()) && response.insights.query_type !== "Metadata";
}

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
  const [language, setLanguage] = useState<SqlLanguage>("sql");
  const [mobileReview, setMobileReview] = useState<CopilotResponse | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);
  const history = useCopilotStore((state) => state.history);
  const activeResponse = useCopilotStore((state) => state.activeResponse);
  const addResponse = useCopilotStore((state) => state.addResponse);
  const setActiveResponse = useCopilotStore((state) => state.setActiveResponse);
  const deleteResponse = useCopilotStore((state) => state.deleteResponse);
  const clearHistory = useCopilotStore((state) => state.clearHistory);
  const pushToast = useToastStore((state) => state.pushToast);
  const submitRef = useRef<(value: string) => void>(() => undefined);
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
      return uniquePrompts([...recentSuccessful, ...fallbackPrompts, ...schemaDriven]);
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
    return uniquePrompts([...contextual, ...recentSuccessful, ...fallbackPrompts, ...schemaDriven])
      .filter((item) => item.toLowerCase() !== queryText);
  }, [activeResponse, history, schemaQuery.data]);

  const mutation = useMutation({
    mutationFn: ({ value, targetLanguage }: { value: string; targetLanguage: SqlLanguage }) => generateSql(value, targetLanguage),
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

  const submit = useCallback((value = query) => {
    const text = value.trim();
    if (!text || mutation.isPending) return;
    setQuery("");
    setPendingQuery(text);
    mutation.mutate({ value: text, targetLanguage: language });
  }, [language, mutation, query]);

  useEffect(() => {
    submitRef.current = submit;
  }, [submit]);

  const voice = useSpeechRecognition({
    onTranscript: setQuery,
    onFinal: (spoken) => submitRef.current(spoken),
  });

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
    <div className={activeResponse ? "grid min-w-0 gap-3 xl:h-[calc(100dvh-10.75rem)] xl:grid-cols-[minmax(0,1fr)_360px] 2xl:grid-cols-[minmax(0,1fr)_390px]" : "grid min-w-0 gap-3 xl:h-[calc(100dvh-10.75rem)]"}>
      <Card className="flex min-h-0 min-w-0 flex-col overflow-visible xl:h-full xl:overflow-hidden">
        <CardHeader className="flex shrink-0 flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center sm:justify-between sm:px-4">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle>Conversation</CardTitle>
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
          <div className="min-h-[240px] max-h-[52dvh] flex-none space-y-3 overflow-y-auto overscroll-y-auto px-2.5 py-3 touch-pan-y sm:px-3 xl:min-h-0 xl:max-h-none xl:flex-1 xl:overscroll-contain scrollbar-thin">
            <AnimatePresence>
              {filteredHistory.map(({ item, index }) => (
                <motion.div key={`${index}-${item.query}-${item.insights.confidence}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-2">
                  <Message icon={<UserRound className="h-4 w-4" />} tone="user">{item.query}</Message>
                  <Message icon={<Bot className="h-4 w-4" />} tone="assistant">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap gap-2">
                        <Badge tone={item.insights.generic_sql ? "amber" : item.insights.valid ? "emerald" : "amber"}>
                          {item.insights.generic_sql ? "Draft SQL" : isSqlAnswer(item) ? (item.insights.valid ? "Reviewed SQL" : "Needs review") : "Schema reference"}
                        </Badge>
                        {isSqlAnswer(item) ? <Badge tone="indigo">{item.insights.generic_sql ? `${item.insights.confidence}% draft confidence` : `${item.insights.confidence}% confidence`}</Badge> : <Badge tone="slate">No SQL generated</Badge>}
                        {item.insights.target_language && item.insights.target_language !== "sql" ? <Badge tone="cyan">{SQL_LANGUAGES.find((option) => option.value === item.insights.target_language)?.label ?? item.insights.target_language}</Badge> : null}
                        {item.insights.cache_hit ? <Badge tone="cyan">Saved answer</Badge> : null}
                        {(item.insights.repair_attempts ?? 0) > 0 ? <Badge tone="amber">{item.insights.repair_attempts} refinement{item.insights.repair_attempts === 1 ? "" : "s"}</Badge> : null}
                      </div>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" className="h-8 px-2" onClick={() => setActiveResponse(item)} aria-label="Open decision trail">
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
                    <div className="mb-2 flex items-center justify-between gap-2 rounded-lg border border-cyan-300/20 bg-cyan-300/10 p-2 xl:hidden">
                      <div className="min-w-0"><div className="text-xs font-semibold text-cyan-100">Review this answer</div><div className="text-[11px] text-slate-400">Scores, checks, and workflow</div></div>
                      <Button variant="outline" className="h-8 shrink-0 px-2.5 text-xs" onClick={() => setMobileReview(item)}>
                        <Sparkles className="h-3.5 w-3.5" />
                        View review
                      </Button>
                    </div>
                    <SqlBlock sql={item.sql} />
                    {item.insights.generic_sql ? <div className="mt-2 rounded-md border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs text-amber-100">This is a generic SQL draft. Connect or register the target schema before it can be treated as reviewed SQL.</div> : null}
                    {isSqlAnswer(item) && item.insights.execution_requires_approval ? <div className="mt-2 rounded-md border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs text-amber-100">Human approval is required before this SQL can run against a connected database.</div> : null}
                    {index === history.length - 1 && suggestions.length ? <div className="mt-3 border-t border-white/10 pt-3 xl:hidden"><div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Recommended next questions</div><div className="flex max-w-full gap-2 overflow-x-auto pb-1 scrollbar-thin">{suggestions.slice(0, 4).map((suggestion) => <Button key={suggestion} variant="outline" className="h-8 shrink-0 px-2.5 text-xs" onClick={() => submit(suggestion)} disabled={mutation.isPending}>{suggestion}</Button>)}</div></div> : null}
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
                  Reviewing your request, building the query, and checking it for safety...
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
                Ask a business question to generate a reviewed SQL query.
              </div>
            )}
            <div ref={scrollAnchorRef} />
          </div>
          <div className="sticky bottom-0 shrink-0 border-t border-white/10 bg-slate-950/92 p-2.5 backdrop-blur-xl">
            <div className="mb-1.5 flex max-w-full gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
              {suggestions.map((item) => (
                <Button key={item} variant="outline" className="h-7 shrink-0 px-2.5 text-xs" onClick={() => submit(item)} disabled={mutation.isPending}>
                  <Sparkles className="h-3 w-3" />
                  {item}
                </Button>
              ))}
            </div>
            <Textarea
              className="max-h-40 min-h-[92px] resize-y break-words p-3 text-sm leading-5"
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
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs text-slate-500">{voice.isListening ? "Voice stays on until you stop it. Completed speech sends automatically." : "Speak or type a business question"}</div>
              <div className="flex items-center gap-2">
                <label className="sr-only" htmlFor="copilot-language">SQL language</label>
                <select
                  id="copilot-language"
                  value={language}
                  onChange={(event) => setLanguage(event.target.value as SqlLanguage)}
                  className="h-10 max-w-36 rounded-md border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-800 outline-none transition focus:border-cyan-400 focus:ring-2 focus:ring-cyan-300/30 dark:border-white/15 dark:bg-slate-950 dark:text-slate-100"
                  aria-label="SQL language"
                >
                  {SQL_LANGUAGES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
                <Button
                  type="button"
                  variant="outline"
                  className="h-10 px-3"
                  onClick={() => {
                    if (voice.isListening) voice.stop();
                    else if (!voice.start(query)) pushToast({ title: "Voice input is unavailable", description: "Use a current Chromium-based browser to dictate your question.", variant: "warning" });
                  }}
                  aria-label={voice.isListening ? "Stop live voice input" : "Start live voice input"}
                  title={voice.isListening ? "Stop live voice input" : "Start live voice input"}
                >
                  {voice.isListening ? <Square className="h-4 w-4 text-rose-300" /> : <Mic className="h-4 w-4" />}
                  {voice.isListening ? "Listening" : "Voice"}
                </Button>
                <Button onClick={() => submit()} disabled={mutation.isPending}>
                <Send className="h-4 w-4" />
                {mutation.isPending ? "Generating" : language === "plsql" ? "Generate PL/SQL" : "Generate SQL"}
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
      <AnimatePresence>
        {activeResponse ? (
          <motion.div className="hidden min-h-0 xl:block xl:h-full xl:overflow-hidden xl:pr-1" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 24 }}>
            <div className="h-[72dvh] min-h-0 xl:h-full">
              <ExplainabilityPanel response={activeResponse} />
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <AnimatePresence>
        {mobileReview ? (
          <motion.div className="fixed inset-0 z-50 xl:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <button className="absolute inset-0 bg-slate-950/75 backdrop-blur-sm" onClick={() => setMobileReview(null)} aria-label="Close query review" />
            <motion.section role="dialog" aria-modal="true" aria-label="Query review" className="absolute inset-x-0 bottom-0 flex h-[88dvh] flex-col overflow-hidden rounded-t-3xl border border-white/10 bg-slate-950 shadow-2xl" initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={{ type: "spring", damping: 28, stiffness: 300 }}>
              <div className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-3">
                <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-300">Answer review</div><div className="mt-0.5 text-sm font-semibold text-white">Query review</div></div>
                <Button variant="ghost" className="h-8 w-8 px-0" onClick={() => setMobileReview(null)} aria-label="Close review"><X className="h-4 w-4" /></Button>
              </div>
              <div className="min-h-0 flex-1 p-3"><ExplainabilityPanel response={mobileReview} /></div>
            </motion.section>
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
  "SUM", "COUNT", "AVG", "MIN", "MAX", "DATE_TRUNC", "OVER", "PARTITION", "DESC", "ASC",
  "DECLARE", "CURSOR", "IS", "BEGIN", "LOOP", "NULL"
]);

const SQL_TOKEN_PATTERN = /(--[^\n]*|'(?:''|[^'])*'|\b[A-Z_]+\b|\b\d+(?:\.\d+)?\b)/gi;

function SqlBlock({ sql }: { sql: string }) {
  const parts = sql.split(SQL_TOKEN_PATTERN).filter((part) => part.length > 0);
  return (
    <pre className="min-h-32 max-h-[36dvh] overflow-auto rounded-md bg-slate-950/70 p-3 font-mono text-sm leading-6 text-cyan-50 sm:min-h-40 xl:min-h-48 xl:max-h-[56dvh] scrollbar-thin">
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
