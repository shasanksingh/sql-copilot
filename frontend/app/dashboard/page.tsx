"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Bot,
  Braces,
  CalendarDays,
  CheckCircle2,
  Database,
  FileCode2,
  Gauge,
  GitBranch,
  Inbox,
  LayoutDashboard,
  Network,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  Timer,
  Wrench,
  Zap,
  type LucideIcon,
  X
} from "lucide-react";
import Link from "next/link";
import type { Route } from "next";
import { useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  type Edge,
  type Node
} from "reactflow";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { AnalyticsChart } from "@/components/dashboard/analytics";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getMetrics, getRelationships } from "@/features/api/client";
import type { FeedbackTrendPoint, RelationshipResponse, SchemaRelationship } from "@/features/api/types";
import { cn } from "@/lib/utils";
import { Icon3D, type Icon3DTone } from "@/components/ui/icon-3d";

const ranges = [
  { key: "day", label: "Day", days: 1, helper: "Last 24 hours" },
  { key: "week", label: "Week", days: 7, helper: "Last 7 days" },
  { key: "month", label: "Month", days: 30, helper: "Last 30 days" },
  { key: "quarter", label: "Quarter", days: 90, helper: "Last 90 days" },
  { key: "year", label: "Year", days: 365, helper: "Last 365 days" },
  { key: "all", label: "All", days: null, helper: "Complete history" }
] as const;

type RangeKey = typeof ranges[number]["key"];
type RangeOption = typeof ranges[number];
type DashboardMetric = {
  key: string;
  label: string;
  value: string;
  helper: string;
  detail: string;
  icon: LucideIcon;
  tone: Icon3DTone;
  actionHref?: Route;
  actionLabel?: string;
};

const DASHBOARD_RANGE_STORAGE_KEY = "sql-copilot.dashboard.range";

function normalizeRangeKey(value?: string | null): RangeKey | null {
  return ranges.some((item) => item.key === value) ? (value as RangeKey) : null;
}

function trendTimestamp(timestamp?: string | null) {
  const parsed = Date.parse(timestamp ?? "");
  return Number.isFinite(parsed) ? parsed : null;
}

function average(values: number[]) {
  const finite = values.filter(Number.isFinite);
  return finite.length ? finite.reduce((sum, value) => sum + value, 0) / finite.length : 0;
}

function percent(value: number) {
  return `${Math.round(value * 100) / 100}%`;
}

function relationshipKey(relationship: SchemaRelationship) {
  return [
    relationship.from_table,
    relationship.from_column,
    relationship.to_table,
    relationship.to_column
  ].join("|");
}

function flattenRelationships(relationships?: RelationshipResponse["relationships"]) {
  const seen = new Set<string>();
  const list: SchemaRelationship[] = [];
  Object.values(relationships ?? {}).flat().forEach((relationship) => {
    const key = relationshipKey(relationship);
    if (seen.has(key)) return;
    seen.add(key);
    list.push(relationship);
  });
  return list;
}

function readPersistedRange() {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  return normalizeRangeKey(params.get("range")) ?? normalizeRangeKey(window.localStorage.getItem(DASHBOARD_RANGE_STORAGE_KEY));
}

export default function DashboardPage() {
  const [range, setRange] = useState<RangeKey>("week");
  const [rangeHydrated, setRangeHydrated] = useState(false);
  const [activeMetricKey, setActiveMetricKey] = useState<string | null>(null);
  const [relationshipsOpen, setRelationshipsOpen] = useState(false);

  useEffect(() => {
    const persistedRange = readPersistedRange();
    if (persistedRange) setRange(persistedRange);
    setRangeHydrated(true);
  }, []);

  useEffect(() => {
    if (!rangeHydrated || typeof window === "undefined") return;
    window.localStorage.setItem(DASHBOARD_RANGE_STORAGE_KEY, range);
    const url = new URL(window.location.href);
    if (url.searchParams.get("range") !== range) {
      url.searchParams.set("range", range);
      window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    }
  }, [range, rangeHydrated]);

  const metricsQuery = useQuery({
    queryKey: ["metrics", range],
    queryFn: () => getMetrics(range),
    enabled: rangeHydrated,
    placeholderData: keepPreviousData,
    refetchInterval: rangeHydrated ? 10_000 : false,
    refetchOnWindowFocus: true,
    staleTime: 5_000
  });
  const schemaQuery = useQuery({ queryKey: ["relationships"], queryFn: getRelationships });
  const metrics = metricsQuery.data;
  const providerStatus = metrics?.llm_provider;
  const llmMetrics = metrics?.llm_metrics;
  const providerIsLocal = providerStatus?.provider === "local";
  const providerReady = providerIsLocal || Boolean(providerStatus?.available);
  const providerConfigured = providerIsLocal || Boolean(providerStatus?.configured);
  const providerName = providerStatus?.provider === "nvidia"
    ? "NVIDIA GPT-OSS-20B"
    : providerStatus?.provider === "local"
      ? "Local Planner"
      : providerStatus?.provider === "openai"
        ? "Custom OpenAI-Compatible"
        : providerStatus?.provider ?? "Local Planner";
  const providerMessage = providerReady
    ? providerIsLocal
      ? "Deterministic SQL planner is active"
      : `${providerStatus?.model ?? "model"} ready`
    : providerConfigured
      ? providerStatus?.reason ?? "Provider configured, currently falling back"
      : providerStatus?.reason ?? "NVIDIA_API_KEY is not configured";
  const selectedRange = ranges.find((item) => item.key === range) ?? ranges[1];
  const isDashboardLoading = !rangeHydrated || metricsQuery.isLoading || schemaQuery.isLoading;
  const isRangeFetching = rangeHydrated && metricsQuery.isFetching;
  const relationshipList = useMemo(() => flattenRelationships(schemaQuery.data?.relationships), [schemaQuery.data?.relationships]);
  const relationshipCount = metrics?.enterprise_schema?.relationships_count ?? relationshipList.length;
  const filteredTrend = useMemo(() => (
    [...(metrics?.trend ?? [])].sort((left, right) => {
      const leftTime = trendTimestamp(left.timestamp) ?? 0;
      const rightTime = trendTimestamp(right.timestamp) ?? 0;
      return leftTime - rightTime;
    })
  ), [metrics?.trend]);
  const rangeMetrics = useMemo(() => {
    const count = filteredTrend.length;
    const validCount = filteredTrend.filter((point) => point.valid).length;
    const successfulCount = filteredTrend.filter((point) => point.valid && point.reward > 0).length;
    const fallbackCount = filteredTrend.filter((point) => point.fallback_used).length;
    return {
      plannerAccuracy: count ? average(filteredTrend.map((point) => point.planner_score)) : metrics?.planner_accuracy ?? 0,
      sqlAccuracy: count ? (validCount / count) * 100 : metrics?.sql_accuracy ?? 0,
      validatorPrecision: count ? average(filteredTrend.map((point) => point.validator_score)) : metrics?.validator_precision ?? 0,
      confidenceReliability: count
        ? average(filteredTrend.map((point) => point.valid ? point.confidence : 100 - point.confidence))
        : metrics?.confidence_reliability ?? 0,
      successRate: count ? (successfulCount / count) * 100 : metrics?.query_success_rate ?? 0,
      averageLatency: count ? average(filteredTrend.map((point) => point.execution_time)) : metrics?.average_latency ?? 0,
      fallbackRate: count ? (fallbackCount / count) * 100 : metrics?.research_metrics?.fallback_rate ?? llmMetrics?.fallback_rate ?? 0,
      fallbackCount,
      validCount,
      count
    };
  }, [filteredTrend, llmMetrics?.fallback_rate, metrics]);

  const stats: DashboardMetric[] = [
    {
      key: "planner_accuracy",
      label: "Planner Accuracy",
      value: percent(rangeMetrics.plannerAccuracy),
      helper: `${rangeMetrics.count} evaluated plans`,
      detail: "Average confidence from table selection, joins, filters, aggregations, and plan assembly for the selected range.",
      icon: Braces,
      tone: "cyan",
      actionHref: "/planner",
      actionLabel: "Open Planner"
    },
    {
      key: "sql_accuracy",
      label: "SQL Accuracy",
      value: percent(rangeMetrics.sqlAccuracy),
      helper: `${rangeMetrics.validCount}/${rangeMetrics.count || 0} validated`,
      detail: "Share of generated SQL runs that passed validation and read-only policy checks in this dashboard range.",
      icon: FileCode2,
      tone: "emerald",
      actionHref: "/copilot",
      actionLabel: "Open Copilot"
    },
    {
      key: "validator_precision",
      label: "Validator Precision",
      value: percent(rangeMetrics.validatorPrecision),
      helper: "Read-only policy and schema checks",
      detail: "Average validator score from schema compatibility, SQL safety, and execution readiness checks.",
      icon: ShieldCheck,
      tone: "indigo",
      actionHref: "/optimizer",
      actionLabel: "Open Optimizer"
    },
    {
      key: "confidence_reliability",
      label: "Confidence Reliability",
      value: percent(rangeMetrics.confidenceReliability),
      helper: "Outcome-aligned confidence",
      detail: "How closely system confidence follows the actual validation outcome for recent query activity.",
      icon: Gauge,
      tone: "amber",
      actionHref: "/copilot",
      actionLabel: "Review Queries"
    }
  ];

  const runtimeStats: DashboardMetric[] = [
    {
      key: "llm_runtime",
      label: "LLM Runtime",
      value: providerName,
      helper: providerMessage,
      detail: "Current provider selected for assisted SQL generation, including whether the backend can reach it now.",
      icon: ServerCog,
      tone: providerReady ? "emerald" : "amber",
      actionHref: "/settings",
      actionLabel: "Provider Settings"
    },
    {
      key: "provider_success",
      label: "Provider Success",
      value: percent(llmMetrics?.success_rate ?? 0),
      helper: `${llmMetrics?.success_count ?? 0}/${llmMetrics?.request_count ?? 0} LLM calls`,
      detail: "Remote provider success rate from the backend LLM client metrics.",
      icon: ServerCog,
      tone: providerReady ? "emerald" : "indigo",
      actionHref: "/settings",
      actionLabel: "Provider Settings"
    },
    {
      key: "fallback_rate",
      label: "Fallback Rate",
      value: percent(rangeMetrics.fallbackRate),
      helper: `${rangeMetrics.fallbackCount} fallbacks in range`,
      detail: "Percent of query attempts that used deterministic fallback instead of a remote model response.",
      icon: RefreshCw,
      tone: rangeMetrics.fallbackCount ? "amber" : "cyan",
      actionHref: "/copilot",
      actionLabel: "Run Query"
    },
    {
      key: "p95_llm_latency",
      label: "P95 LLM Latency",
      value: `${Math.round(llmMetrics?.p95_latency_ms ?? 0)}ms`,
      helper: `${Math.round(llmMetrics?.average_latency_ms ?? 0)}ms average`,
      detail: "Ninety-fifth percentile provider latency from recent backend LLM calls.",
      icon: Timer,
      tone: "indigo",
      actionHref: "/settings",
      actionLabel: "Provider Settings"
    }
  ];

  const schemaStats: DashboardMetric[] = [
    {
      key: "validated_queries",
      label: "Validated queries",
      value: String(rangeMetrics.validCount),
      helper: `${rangeMetrics.count} events in ${selectedRange.label.toLowerCase()} range`,
      detail: "Validated SQL generations in the selected dashboard range.",
      icon: CheckCircle2,
      tone: "emerald",
      actionHref: "/copilot",
      actionLabel: "Open Copilot"
    },
    {
      key: "average_latency",
      label: "Average latency",
      value: `${rangeMetrics.averageLatency.toFixed(3)}s`,
      helper: "Mean response time",
      detail: "Average SQL generation and validation latency for the selected range.",
      icon: Timer,
      tone: "amber",
      actionHref: "/execution",
      actionLabel: "Execution View"
    },
    {
      key: "schema_tables",
      label: "Schema tables",
      value: String(metrics?.enterprise_schema?.tables_count ?? schemaQuery.data?.tables.length ?? 0),
      helper: `${metrics?.enterprise_schema?.domains_count ?? 0} domains indexed`,
      detail: "Tables available to the schema retriever and SQL planner.",
      icon: Database,
      tone: "indigo",
      actionHref: "/schema-explorer",
      actionLabel: "Explore Schema"
    }
  ];

  const telemetryStats: DashboardMetric[] = [
    {
      key: "intent_accuracy",
      label: "Intent accuracy",
      value: percent(filteredTrend.length ? average(filteredTrend.map((point) => point.intent_score)) : metrics?.agent_telemetry?.intent_accuracy ?? 0),
      helper: "Intent classifier signal",
      detail: "Average intent confidence from the agent telemetry rows in the current range.",
      icon: Bot,
      tone: "cyan",
      actionHref: "/planner",
      actionLabel: "Open Planner"
    },
    {
      key: "telemetry_planner_accuracy",
      label: "Planner accuracy",
      value: percent(rangeMetrics.plannerAccuracy),
      helper: "Planner confidence signal",
      detail: "Planner-specific telemetry for table, join, filter, and aggregation decisions.",
      icon: Braces,
      tone: "indigo",
      actionHref: "/planner",
      actionLabel: "Open Planner"
    },
    {
      key: "validation_accuracy",
      label: "Validation accuracy",
      value: percent(rangeMetrics.validatorPrecision),
      helper: "Validator telemetry signal",
      detail: "Validator score for policy safety, schema usage, and SQL structure.",
      icon: ShieldCheck,
      tone: "emerald",
      actionHref: "/optimizer",
      actionLabel: "Open Optimizer"
    },
    {
      key: "optimization_accuracy",
      label: "Optimization accuracy",
      value: percent(rangeMetrics.successRate),
      helper: "Successful optimized outputs",
      detail: "Optimization pass rate based on validated, rewarded query outcomes.",
      icon: Zap,
      tone: "amber",
      actionHref: "/optimizer",
      actionLabel: "Open Optimizer"
    },
    {
      key: "five_table_success",
      label: "5+ table success",
      value: percent(metrics?.research_metrics?.five_plus_table_success_rate ?? 0),
      helper: "Enterprise query success",
      detail: "Success rate for larger enterprise-style plans that span at least five tables.",
      icon: Network,
      tone: "cyan",
      actionHref: "/planner",
      actionLabel: "Open Planner"
    },
    {
      key: "repair_attempts",
      label: "Repair attempts",
      value: String(llmMetrics?.repair_attempts ?? 0),
      helper: "SQL repair loop usage",
      detail: "Number of repair passes requested by the backend LLM provider workflow.",
      icon: Wrench,
      tone: "slate",
      actionHref: "/settings",
      actionLabel: "Provider Settings"
    }
  ];

  const growthStats: DashboardMetric[] = [
    {
      key: "schema_requests",
      label: "Pending requests",
      value: String(metrics?.schema_growth?.pending_requests ?? 0),
      helper: `${metrics?.schema_growth?.total_requests ?? 0} total schema requests`,
      detail: "Schema requests waiting for review or application into the live metadata catalog.",
      icon: Inbox,
      tone: "amber",
      actionHref: "/admin/schema-requests",
      actionLabel: "Review Requests"
    }
  ];

  const activeMetric = [...stats, ...runtimeStats, ...schemaStats, ...telemetryStats, ...growthStats].find((item) => item.key === activeMetricKey) ?? null;

  return (
    <AppShell>
      <PageHeader
        title="Dashboard"
        description="Operational view of SQL generation quality, provider health, confidence, schema coverage, and recent activity."
        meta={(
          <>
            <Badge tone="cyan">{filteredTrend.length} events</Badge>
            <Badge tone="emerald">{percent(rangeMetrics.successRate)} success</Badge>
            <Badge tone={providerReady ? "emerald" : "amber"}>{providerName}</Badge>
          </>
        )}
        actions={(
          <>
            <Button variant="outline" className="h-10 px-3" onClick={() => setRelationshipsOpen(true)}>
              <Icon3D icon={GitBranch} tone="cyan" size="xs" />
              Relationships
            </Button>
            <Link
              href="/copilot"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-slate-200/80 bg-white/70 px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100/80 hover:text-slate-950 dark:border-white/12 dark:bg-white/[0.03] dark:text-slate-200 dark:hover:bg-white/10 dark:hover:text-white"
            >
              <Icon3D icon={FileCode2} tone="emerald" size="xs" />
              Copilot
            </Link>
            <Button
              variant="outline"
              className="h-10 px-3"
              onClick={() => { void metricsQuery.refetch(); void schemaQuery.refetch(); }}
              disabled={!rangeHydrated || metricsQuery.isFetching || schemaQuery.isFetching}
            >
              <RefreshCw className={`h-4 w-4 ${isRangeFetching ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </>
        )}
      />
      {metricsQuery.isError || schemaQuery.isError ? (
        <Card className="mb-4 border-rose-300/20">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-medium text-rose-100">Dashboard data is unavailable</div>
              <div className="mt-1 text-sm text-slate-400">Check the authenticated API session and backend health.</div>
            </div>
            <Button variant="outline" onClick={() => { void metricsQuery.refetch(); void schemaQuery.refetch(); }}>
              <RefreshCw className="h-4 w-4" />
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {stats.map((item) => (
          <MetricButtonCard
            key={item.key}
            metric={item}
            isLoading={isDashboardLoading}
            onOpen={() => setActiveMetricKey(item.key)}
          />
        ))}
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {runtimeStats.map((item) => (
          <MetricButtonCard
            key={item.key}
            metric={item}
            isLoading={!rangeHydrated || metricsQuery.isLoading}
            onOpen={() => setActiveMetricKey(item.key)}
          />
        ))}
      </div>
      <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-3">
          <RangeFilterBar
            selectedRange={selectedRange}
            range={range}
            eventCount={filteredTrend.length}
            isRangeFetching={isRangeFetching}
            onRangeChange={setRange}
          />
          <AnalyticsChart trend={filteredTrend} />
        </div>
        <Card>
          <CardContent>
            <div className="mb-4 flex items-center justify-between">
              <div className="text-sm font-semibold text-white">Recent Activity</div>
              <Badge tone="cyan">{percent(rangeMetrics.successRate)} success</Badge>
            </div>
            {filteredTrend.slice(-6).reverse().map((item, index) => (
              <button
                key={`${item.query}-${item.timestamp}-${index}`}
                type="button"
                className="block w-full border-b border-white/10 py-3 text-left transition last:border-0 hover:bg-white/[0.03] focus:outline-none focus:ring-2 focus:ring-cyan-300/30"
                onClick={() => setActiveMetricKey("sql_accuracy")}
              >
                <div className="line-clamp-1 px-1 text-sm text-slate-200">{item.query}</div>
                <div className="mt-2 flex flex-wrap items-center gap-2 px-1 text-xs text-slate-500">
                  <Icon3D icon={item.valid ? CheckCircle2 : FileCode2} tone={item.valid ? "emerald" : "amber"} size="xs" />
                  <Badge tone={item.valid ? "emerald" : "amber"} className="h-6">{item.valid ? "Valid" : "Review"}</Badge>
                  <Badge tone={item.fallback_used ? "amber" : item.provider === "nvidia" ? "cyan" : "slate"} className="h-6">
                    {item.fallback_used ? "Fallback" : item.provider === "nvidia" ? "NVIDIA" : "Local"}
                  </Badge>
                  <span>{Math.round(item.confidence)}% confidence</span>
                  <span>{Math.round(item.latency_ms ?? item.execution_time * 1000)}ms</span>
                </div>
              </button>
            ))}
            {!filteredTrend.length ? (
              <div className="rounded-md border border-dashed border-white/10 p-6 text-center text-sm text-slate-500">
                No query activity exists in the selected range.
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {schemaStats.map((item) => (
          <CompactMetricButton
            key={item.key}
            metric={item}
            isLoading={isDashboardLoading}
            onOpen={() => setActiveMetricKey(item.key)}
          />
        ))}
        <RelationshipSummaryButton
          value={relationshipCount}
          helper={`${schemaQuery.data?.tables.length ?? metrics?.enterprise_schema?.tables_count ?? 0} connected tables`}
          isLoading={isDashboardLoading}
          onOpen={() => setRelationshipsOpen(true)}
        />
      </div>
      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <Card>
          <CardContent>
            <div className="mb-4 text-sm font-semibold text-white">Agent Telemetry</div>
            <div className="grid gap-3 sm:grid-cols-2">
              {telemetryStats.map((item) => (
                <TelemetryButton key={item.key} metric={item} onOpen={() => setActiveMetricKey(item.key)} />
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-white">Schema Growth</div>
              <Badge tone="indigo">{metrics?.enterprise_schema?.domains_count ?? 0} domains</Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <button
                type="button"
                className="rounded-md border border-white/10 bg-white/[0.04] p-3 text-left transition hover:border-indigo-300/25 hover:bg-indigo-300/10 focus:outline-none focus:ring-2 focus:ring-indigo-300/30"
                onClick={() => setActiveMetricKey("schema_tables")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-xs text-slate-500">Virtual tables</div>
                    <div className="mt-1 text-xl font-semibold text-white">{metrics?.enterprise_schema?.tables_count ?? 0}</div>
                  </div>
                  <Icon3D icon={Database} tone="indigo" size="sm" />
                </div>
              </button>
              <button
                type="button"
                className="rounded-md border border-white/10 bg-white/[0.04] p-3 text-left transition hover:border-cyan-300/25 hover:bg-cyan-300/10 focus:outline-none focus:ring-2 focus:ring-cyan-300/30"
                onClick={() => setRelationshipsOpen(true)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-xs text-slate-500">Relationships</div>
                    <div className="mt-1 text-xl font-semibold text-white">{relationshipCount}</div>
                  </div>
                  <Icon3D icon={GitBranch} tone="cyan" size="sm" />
                </div>
              </button>
              <button
                type="button"
                className="rounded-md border border-white/10 bg-white/[0.04] p-3 text-left transition hover:border-amber-300/25 hover:bg-amber-300/10 focus:outline-none focus:ring-2 focus:ring-amber-300/30"
                onClick={() => setActiveMetricKey("schema_requests")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-xs text-slate-500">Pending requests</div>
                    <div className="mt-1 text-xl font-semibold text-white">{metrics?.schema_growth?.pending_requests ?? 0}</div>
                  </div>
                  <Icon3D icon={Inbox} tone="amber" size="sm" />
                </div>
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
      <MetricDetailModal
        metric={activeMetric}
        rangeLabel={selectedRange.label}
        trend={filteredTrend}
        open={Boolean(activeMetric)}
        onOpenChange={(open) => {
          if (!open) setActiveMetricKey(null);
        }}
      />
      <RelationshipGraphModal
        open={relationshipsOpen}
        onOpenChange={setRelationshipsOpen}
        data={schemaQuery.data}
        isLoading={schemaQuery.isLoading}
      />
    </AppShell>
  );
}

function RangeFilterBar({
  selectedRange,
  range,
  eventCount,
  isRangeFetching,
  onRangeChange
}: {
  selectedRange: RangeOption;
  range: RangeKey;
  eventCount: number;
  isRangeFetching: boolean;
  onRangeChange: (range: RangeKey) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/[0.06] p-3 shadow-glow backdrop-blur-xl dark:bg-slate-950/45">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className="flex h-9 items-center gap-2 rounded-md border border-cyan-300/20 bg-cyan-300/10 px-3 text-xs font-medium text-cyan-100">
          <CalendarDays className="h-3.5 w-3.5" />
          {selectedRange.helper}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {ranges.map((item) => (
            <Button
              key={item.key}
              variant={range === item.key ? "primary" : "outline"}
              className="h-8 px-3 text-xs"
              onClick={() => onRangeChange(item.key)}
              aria-pressed={range === item.key}
              title={item.helper}
            >
              {item.label}
            </Button>
          ))}
        </div>
      </div>
      <Badge tone={isRangeFetching ? "amber" : "cyan"}>
        {isRangeFetching ? "Updating" : `${eventCount} events`}
      </Badge>
    </div>
  );
}

function MetricButtonCard({ metric, isLoading, onOpen }: { metric: DashboardMetric; isLoading: boolean; onOpen: () => void }) {
  return (
    <button
      type="button"
      className={cn(
        "group relative overflow-hidden rounded-lg border border-slate-200/80 bg-white/80 text-left shadow-glow backdrop-blur-xl transition dark:border-white/10 dark:bg-white/[0.06]",
        "hover:-translate-y-0.5 hover:border-cyan-300/25 hover:bg-slate-50/90 focus:outline-none focus:ring-2 focus:ring-cyan-300/30 dark:hover:bg-white/[0.08]"
      )}
      onClick={onOpen}
      aria-label={`Open ${metric.label} details`}
    >
      <div className={cn(
        "absolute inset-x-0 top-0 h-px",
        metric.tone === "emerald" && "bg-emerald-300/70",
        metric.tone === "amber" && "bg-amber-300/70",
        metric.tone === "cyan" && "bg-gradient-to-r from-cyan-300/70 via-indigo-300/60 to-emerald-300/50",
        metric.tone === "indigo" && "bg-indigo-300/70",
        metric.tone === "slate" && "bg-slate-300/40"
      )} />
      <div className="flex min-h-28 items-center justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="text-xs font-medium text-slate-500 dark:text-slate-400">{metric.label}</div>
          {isLoading ? (
            <Skeleton className="mt-2 h-7 w-20" />
          ) : (
            <div className="mt-1 truncate text-2xl font-semibold text-slate-950 dark:text-white">{metric.value}</div>
          )}
          <div className="mt-1 line-clamp-2 text-xs text-slate-500">{metric.helper}</div>
        </div>
        <Icon3D icon={metric.icon} tone={metric.tone} size="md" className="transition group-hover:scale-105" />
      </div>
      <div className="flex items-center justify-between border-t border-slate-200/80 px-4 py-1.5 text-xs text-slate-500 dark:border-white/10">
        <span>Details</span>
        <ArrowUpRight className="h-3.5 w-3.5 transition group-hover:text-cyan-100" />
      </div>
    </button>
  );
}

function CompactMetricButton({ metric, isLoading, onOpen }: { metric: DashboardMetric; isLoading: boolean; onOpen: () => void }) {
  return (
    <button
      type="button"
      className="group rounded-lg border border-slate-200/80 bg-white/80 text-left shadow-glow backdrop-blur-xl transition hover:border-indigo-300/25 hover:bg-slate-50/90 focus:outline-none focus:ring-2 focus:ring-indigo-300/30 dark:border-white/10 dark:bg-white/[0.06] dark:hover:bg-white/[0.08]"
      onClick={onOpen}
    >
      <div className="flex items-center justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="text-xs text-slate-500">{metric.label}</div>
          {isLoading ? <Skeleton className="mt-2 h-6 w-16" /> : <div className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">{metric.value}</div>}
          <div className="mt-1 line-clamp-1 text-xs text-slate-500">{metric.helper}</div>
        </div>
        <Icon3D icon={metric.icon} tone={metric.tone} size="sm" className="transition group-hover:scale-105" />
      </div>
    </button>
  );
}

function RelationshipSummaryButton({
  value,
  helper,
  isLoading,
  onOpen
}: {
  value: number;
  helper: string;
  isLoading: boolean;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      className="group relative overflow-hidden rounded-lg border border-slate-200/80 bg-white/80 text-left shadow-glow backdrop-blur-xl transition hover:-translate-y-0.5 hover:border-cyan-300/30 hover:bg-slate-50/90 focus:outline-none focus:ring-2 focus:ring-cyan-300/30 dark:border-white/10 dark:bg-white/[0.06] dark:hover:bg-white/[0.08]"
      onClick={onOpen}
      aria-label="Open relationship graph"
    >
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-cyan-300/80 via-indigo-300/70 to-emerald-300/70" />
      <div className="flex items-center justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="text-xs text-slate-500">Relationships</div>
          {isLoading ? <Skeleton className="mt-2 h-6 w-16" /> : <div className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">{value}</div>}
          <div className="mt-1 line-clamp-1 text-xs text-slate-500">{helper}</div>
        </div>
        <Icon3D icon={GitBranch} tone="cyan" size="sm" className="transition group-hover:scale-105" />
      </div>
    </button>
  );
}

function TelemetryButton({ metric, onOpen }: { metric: DashboardMetric; onOpen: () => void }) {
  return (
    <button
      type="button"
      className="rounded-md border border-slate-200/80 bg-white/70 p-3 text-left transition hover:border-cyan-300/25 hover:bg-cyan-50 focus:outline-none focus:ring-2 focus:ring-cyan-300/30 dark:border-white/10 dark:bg-white/[0.04] dark:hover:bg-cyan-300/10"
      onClick={onOpen}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs text-slate-500">{metric.label}</div>
          <div className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">{metric.value}</div>
        </div>
        <Icon3D icon={metric.icon} tone={metric.tone} size="xs" />
      </div>
    </button>
  );
}

function MetricDetailModal({
  metric,
  open,
  onOpenChange,
  rangeLabel,
  trend
}: {
  metric: DashboardMetric | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rangeLabel: string;
  trend: FeedbackTrendPoint[];
}) {
  const recent = trend.slice(-5).reverse();
  const MetricIcon = metric?.icon ?? LayoutDashboard;
  const tone = metric?.tone ?? "cyan";
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-sm dark:bg-slate-950/78" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[min(92vw,720px)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg border border-white/10 bg-white/95 text-slate-950 shadow-glow focus:outline-none dark:bg-slate-950/96 dark:text-white">
          <div className="flex items-start justify-between gap-4 border-b border-white/10 p-5">
            <div className="flex min-w-0 items-start gap-3">
              <Icon3D icon={MetricIcon} tone={tone} size="lg" />
              <div className="min-w-0">
                <Dialog.Title className="text-base font-semibold text-white">{metric?.label ?? "Metric Details"}</Dialog.Title>
                <Dialog.Description className="mt-1 text-sm text-slate-400">
                  {metric?.detail ?? "Metric context for the selected dashboard range."}
                </Dialog.Description>
              </div>
            </div>
            <Dialog.Close asChild>
              <button type="button" className="rounded-md p-2 text-slate-500 transition hover:bg-slate-900/[0.06] hover:text-slate-950 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-white" aria-label="Close metric details">
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>
          <div className="max-h-[calc(88vh-86px)] overflow-auto p-5 scrollbar-thin">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                <div className="text-xs text-slate-500">Current value</div>
                <div className="mt-1 text-2xl font-semibold text-white">{metric?.value ?? "N/A"}</div>
              </div>
              <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                <div className="text-xs text-slate-500">Range</div>
                <div className="mt-1 text-2xl font-semibold text-white">{rangeLabel}</div>
              </div>
              <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                <div className="text-xs text-slate-500">Events</div>
                <div className="mt-1 text-2xl font-semibold text-white">{trend.length}</div>
              </div>
            </div>
            <div className="mt-4 rounded-md border border-white/10 bg-white/[0.03] p-4">
              <div className="text-sm font-semibold text-white">{metric?.helper ?? "No helper text"}</div>
              <div className="mt-2 text-sm leading-6 text-slate-400">
                The value is calculated from the same data powering the dashboard chart, so changing Day, Month, Quarter, or All updates this view without losing the previous selection.
              </div>
              {metric?.actionHref ? (
                <Link
                  href={metric.actionHref}
                  className="mt-4 inline-flex h-9 items-center justify-center gap-2 rounded-md border border-slate-200/80 bg-white/70 px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100/80 hover:text-slate-950 dark:border-white/12 dark:bg-white/[0.04] dark:text-slate-200 dark:hover:bg-white/10 dark:hover:text-white"
                >
                  {metric.actionLabel ?? "Open"}
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              ) : null}
            </div>
            <div className="mt-4">
              <div className="mb-2 text-sm font-semibold text-white">Recent signals</div>
              {recent.length ? (
                <div className="divide-y divide-white/10 rounded-md border border-white/10">
                  {recent.map((item, index) => (
                    <div key={`${item.timestamp}-${index}`} className="p-3">
                      <div className="line-clamp-1 text-sm text-slate-200">{item.query}</div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                        <Badge tone={item.valid ? "emerald" : "amber"} className="h-6">{item.valid ? "Valid" : "Review"}</Badge>
                        <span>{Math.round(item.confidence)}% confidence</span>
                        <span>{Math.round(item.planner_score)}% planner</span>
                        <span>{Math.round(item.validator_score)}% validator</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-md border border-dashed border-white/10 p-6 text-center text-sm text-slate-500">
                  No query signals exist in this range yet.
                </div>
              )}
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function RelationshipGraphModal({
  open,
  onOpenChange,
  data,
  isLoading
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data?: RelationshipResponse;
  isLoading: boolean;
}) {
  const relationships = useMemo(() => flattenRelationships(data?.relationships), [data?.relationships]);
  const graph = useMemo(() => {
    const degree = new Map<string, number>();
    relationships.forEach((relationship) => {
      degree.set(relationship.from_table, (degree.get(relationship.from_table) ?? 0) + 1);
      degree.set(relationship.to_table, (degree.get(relationship.to_table) ?? 0) + 1);
    });
    const tableCandidates = (data?.tables?.length ? data.tables : [...degree.keys()])
      .filter(Boolean)
      .sort((left, right) => (degree.get(right) ?? 0) - (degree.get(left) ?? 0) || left.localeCompare(right));
    const selectedTables = tableCandidates.slice(0, 18);
    const selected = new Set(selectedTables);
    const visibleRelationships = relationships
      .filter((relationship) => selected.has(relationship.from_table) && selected.has(relationship.to_table))
      .slice(0, 54);
    const columns = Math.min(5, Math.max(2, Math.ceil(Math.sqrt(Math.max(selectedTables.length, 1)))));
    const nodes: Node[] = selectedTables.map((table, index) => {
      const column = index % columns;
      const row = Math.floor(index / columns);
      return {
        id: table,
        position: { x: column * 230, y: row * 145 },
        data: {
          label: (
            <div className="min-w-32">
              <div className="truncate text-sm font-semibold text-[#f8fafc]">{table}</div>
              <div className="mt-1 text-xs text-[#cbd5e1]">{degree.get(table) ?? 0} links</div>
            </div>
          )
        },
        style: {
          border: "1px solid rgba(103,232,249,.28)",
          borderRadius: 8,
          background: "linear-gradient(145deg, rgba(15,23,42,.98), rgba(30,41,59,.92))",
          boxShadow: "0 16px 40px rgba(8,145,178,.14)",
          color: "white",
          padding: 12
        }
      };
    });
    const edges: Edge[] = visibleRelationships.map((relationship, index) => ({
      id: `${relationshipKey(relationship)}-${index}`,
      source: relationship.from_table,
      target: relationship.to_table,
      animated: index < 18,
      label: `${relationship.from_column} -> ${relationship.to_column}`,
      markerEnd: { type: MarkerType.ArrowClosed, color: index < 18 ? "#22d3ee" : "#64748b" },
      style: { stroke: index < 18 ? "#22d3ee" : "#64748b", strokeWidth: index < 18 ? 2.2 : 1.5 }
    }));
    return { nodes, edges, selectedTables, visibleRelationships };
  }, [data?.tables, relationships]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-sm dark:bg-slate-950/78" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[92vh] w-[min(94vw,1100px)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg border border-white/10 bg-white/95 text-slate-950 shadow-glow focus:outline-none dark:bg-slate-950/96 dark:text-white">
          <div className="flex items-start justify-between gap-4 border-b border-white/10 p-5">
            <div className="flex min-w-0 items-start gap-3">
              <Icon3D icon={GitBranch} tone="cyan" size="lg" />
              <div className="min-w-0">
                <Dialog.Title className="text-base font-semibold text-white">Relationship Graph</Dialog.Title>
                <Dialog.Description className="mt-1 text-sm text-slate-400">
                  {relationships.length} relationships across {data?.tables.length ?? graph.selectedTables.length} tables.
                </Dialog.Description>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Link
                href="/schema-graph"
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-slate-200/80 bg-white/70 px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100/80 hover:text-slate-950 dark:border-white/12 dark:bg-white/[0.04] dark:text-slate-200 dark:hover:bg-white/10 dark:hover:text-white"
              >
                Full Graph
                <ArrowUpRight className="h-4 w-4" />
              </Link>
              <Dialog.Close asChild>
                <button type="button" className="rounded-md p-2 text-slate-500 transition hover:bg-slate-900/[0.06] hover:text-slate-950 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-white" aria-label="Close relationship graph">
                  <X className="h-4 w-4" />
                </button>
              </Dialog.Close>
            </div>
          </div>
          <div className="grid max-h-[calc(92vh-86px)] gap-0 overflow-auto scrollbar-thin lg:grid-cols-[minmax(0,1fr)_300px]">
            <div className="h-[520px] min-h-[420px] border-b border-white/10 bg-[#020617] lg:border-b-0 lg:border-r">
              {isLoading ? (
                <div className="grid h-full place-items-center">
                  <Skeleton className="h-48 w-72" />
                </div>
              ) : graph.nodes.length ? (
                <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.25} maxZoom={1.6} nodesDraggable className="bg-slate-950/30">
                  <Background color="rgba(148,163,184,.16)" gap={22} />
                  <MiniMap nodeColor="#22d3ee" maskColor="rgba(2,6,23,.76)" pannable zoomable />
                  <Controls className="overflow-hidden rounded-md border border-white/10 bg-slate-950/90 text-white" />
                </ReactFlow>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-500">
                  No schema relationships are available.
                </div>
              )}
            </div>
            <aside className="space-y-4 p-5">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                  <div className="text-xs text-slate-500">Preview tables</div>
                  <div className="mt-1 text-xl font-semibold text-white">{graph.selectedTables.length}</div>
                </div>
                <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                  <div className="text-xs text-slate-500">Preview links</div>
                  <div className="mt-1 text-xl font-semibold text-white">{graph.visibleRelationships.length}</div>
                </div>
              </div>
              <div>
                <div className="mb-2 text-sm font-semibold text-white">Join tree</div>
                <div className="max-h-80 space-y-2 overflow-auto pr-1 scrollbar-thin">
                  {graph.visibleRelationships.slice(0, 18).map((relationship, index) => (
                    <div key={`${relationshipKey(relationship)}-${index}`} className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                      <div className="truncate text-sm text-slate-100">{relationship.from_table} to {relationship.to_table}</div>
                      <div className="mt-1 truncate text-xs text-cyan-100">{relationship.from_column}{" -> "}{relationship.to_column}</div>
                    </div>
                  ))}
                  {!graph.visibleRelationships.length ? (
                    <div className="rounded-md border border-dashed border-white/10 p-4 text-sm text-slate-500">
                      No relationship edges in the current preview.
                    </div>
                  ) : null}
                </div>
              </div>
            </aside>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
