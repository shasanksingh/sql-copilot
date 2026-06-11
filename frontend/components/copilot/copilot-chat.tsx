"use client";

import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Clock, Copy, DatabaseZap, Send, Sparkles, UserRound } from "lucide-react";
import type React from "react";
import { useState } from "react";
import { generateSql } from "@/features/api/client";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { useToastStore } from "@/features/store/use-toast-store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ExplainabilityPanel } from "./explainability-panel";
import { Badge } from "@/components/ui/badge";
import { suggestedPrompts } from "@/features/demo/demo-data";

export function CopilotChat() {
  const [query, setQuery] = useState("");
  const history = useCopilotStore((state) => state.history);
  const activeResponse = useCopilotStore((state) => state.activeResponse);
  const addResponse = useCopilotStore((state) => state.addResponse);
  const pushToast = useToastStore((state) => state.pushToast);

  const mutation = useMutation({
    mutationFn: generateSql,
    onSuccess: (response) => {
      addResponse(response);
      pushToast({
        title: response.insights.valid ? "SQL generated" : "Clarification needed",
        description: response.insights.valid ? `Confidence ${response.insights.confidence}%` : response.message,
        variant: response.insights.valid ? "success" : "warning"
      });
    },
    onError: (error) => {
      pushToast({ title: "Backend request failed", description: error instanceof Error ? error.message : "Unable to generate SQL.", variant: "error" });
    }
  });

  const submit = (value = query) => {
    const text = value.trim();
    if (!text) return;
    setQuery("");
    mutation.mutate(text);
  };

  const copySql = async (sql: string) => {
    await navigator.clipboard.writeText(sql);
    pushToast({ title: "SQL copied", variant: "success" });
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_430px]">
      <Card className="min-h-[calc(100vh-9rem)] overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Copilot Console</CardTitle>
          <Badge tone="cyan">Streaming UI</Badge>
        </CardHeader>
        <CardContent className="flex min-h-[calc(100vh-14rem)] flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            {suggestedPrompts.map((item) => (
              <Button key={item} variant="outline" className="h-9" onClick={() => submit(item)}>
                <Sparkles className="h-4 w-4" />
                {item}
              </Button>
            ))}
          </div>
          <div className="flex-1 space-y-4 overflow-auto pr-1 scrollbar-thin">
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
                    <pre className="overflow-auto whitespace-pre-wrap rounded-md bg-slate-950/70 p-3 font-mono text-sm leading-6 text-cyan-50 scrollbar-thin">{item.sql}</pre>
                  </Message>
                </motion.div>
              ))}
            </AnimatePresence>
            {mutation.isPending ? (
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                <div className="mt-1 text-cyan-200"><Bot className="h-4 w-4" /></div>
                <div className="flex min-w-0 flex-1 items-center gap-3 rounded-lg border border-cyan-300/20 bg-cyan-300/10 p-4 text-sm text-cyan-100">
                  <Clock className="h-4 w-4 animate-spin" />
                  Reading schema, planning joins, validating SQL...
                </div>
              </motion.div>
            ) : null}
            {!history.length && (
              <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-white/10 text-sm text-slate-500">
                Ask a schema-aware question to generate validated SQL.
              </div>
            )}
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/60 p-3">
            <Textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ask for SQL in natural language" />
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
      <ExplainabilityPanel response={activeResponse} />
    </div>
  );
}

function Message({ icon, tone, children }: { icon: React.ReactNode; tone: "user" | "assistant"; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className={tone === "user" ? "mt-1 text-indigo-200" : "mt-1 text-cyan-200"}>{icon}</div>
      <div className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/[0.04] p-4 text-sm text-slate-100">{children}</div>
    </div>
  );
}
