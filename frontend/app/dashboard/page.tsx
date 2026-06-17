"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, BrainCircuit, Database, Gauge, Network, RefreshCw, ShieldCheck, Timer } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { AnalyticsChart } from "@/components/dashboard/analytics";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { getMetrics, getRelationships } from "@/features/api/client";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

const ranges = {
  Day: 1,
  Week: 7,
  Month: 30,
  Quarter: 90,
  Year: 365
} as const;

export default function DashboardPage() {
  const [range, setRange] = useState<keyof typeof ranges>("Week");
  const metricsQuery = useQuery({
    queryKey: ["metrics"],
    queryFn: getMetrics,
    refetchInterval: 10_000,
    refetchOnWindowFocus: true
  });
  const schemaQuery = useQuery({ queryKey: ["relationships"], queryFn: getRelationships });
  const metrics = metricsQuery.data;
  const filteredTrend = useMemo(() => {
    const trend = metrics?.trend ?? [];
    const cutoff = Date.now() - ranges[range] * 86_400_000;
    return trend.filter((point) => {
      const timestamp = Date.parse(point.timestamp);
      return Number.isNaN(timestamp) || timestamp >= cutoff;
    });
  }, [metrics?.trend, range]);
  const rangeMetrics = useMemo(() => {
    const count = filteredTrend.length;
    const average = (values: number[]) => (
      values.length
        ? values.reduce((sum, value) => sum + value, 0) / values.length
        : 0
    );
    const validCount = filteredTrend.filter((point) => point.valid).length;
    const successfulCount = filteredTrend.filter((point) => point.valid && point.reward > 0).length;
    return {
      plannerAccuracy: average(filteredTrend.map((point) => point.planner_score)),
      sqlAccuracy: count ? (validCount / count) * 100 : 0,
      validatorPrecision: average(filteredTrend.map((point) => point.validator_score)),
      confidenceReliability: average(
        filteredTrend.map((point) => point.valid ? point.confidence : 100 - point.confidence)
      ),
      successRate: count ? (successfulCount / count) * 100 : 0,
      averageLatency: average(filteredTrend.map((point) => point.execution_time)),
      validCount
    };
  }, [filteredTrend]);
  const percent = (value: number) => `${Math.round(value * 100) / 100}%`;
  const stats = [
    { label: "Planner Accuracy", value: percent(rangeMetrics.plannerAccuracy), icon: BrainCircuit },
    { label: "SQL Accuracy", value: percent(rangeMetrics.sqlAccuracy), icon: Gauge },
    { label: "Validator Precision", value: percent(rangeMetrics.validatorPrecision), icon: ShieldCheck },
    { label: "Confidence Reliability", value: percent(rangeMetrics.confidenceReliability), icon: Activity }
  ];

  return (
    <AppShell>
      <PageHeader title="Dashboard" description="Operational view of SQL generation quality, confidence, schema coverage, and recent activity." />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {Object.keys(ranges).map((item) => (
            <Button key={item} variant={range === item ? "primary" : "outline"} className="h-8 px-3 text-xs" onClick={() => setRange(item as keyof typeof ranges)}>
              {item}
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Badge tone="cyan">{filteredTrend.length} events in range</Badge>
          <Button
            variant="outline"
            className="h-8 px-3 text-xs"
            onClick={() => { void metricsQuery.refetch(); void schemaQuery.refetch(); }}
            disabled={metricsQuery.isFetching || schemaQuery.isFetching}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${metricsQuery.isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>
      {metricsQuery.isError || schemaQuery.isError ? (
        <Card className="mb-4 border-rose-300/20">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-medium text-rose-100">Dashboard data is unavailable</div>
              <div className="mt-1 text-sm text-slate-400">Check the authenticated API session and backend health.</div>
            </div>
            <Button variant="outline" onClick={() => { void metricsQuery.refetch(); void schemaQuery.refetch(); }}><RefreshCw className="h-4 w-4" />Retry</Button>
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {stats.map((item) => {
          const Icon = item.icon;
          return (
            <Card key={item.label}>
              <CardContent className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-slate-400">{item.label}</div>
                  {metricsQuery.isLoading || schemaQuery.isLoading ? <Skeleton className="mt-3 h-8 w-24" /> : <div className="mt-2 text-3xl font-semibold text-white">{item.value}</div>}
                </div>
                <div className="rounded-md bg-cyan-300/10 p-3 text-cyan-200">
                  <Icon className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <AnalyticsChart trend={filteredTrend} />
        <Card>
          <CardContent>
            <div className="mb-4 flex items-center justify-between">
              <div className="text-sm font-semibold text-white">Recent Activity</div>
              <Badge tone="cyan">{percent(rangeMetrics.successRate)} success</Badge>
            </div>
            {filteredTrend.slice(-6).reverse().map((item, index) => (
              <div key={`${item.query}-${item.timestamp}-${index}`} className="border-b border-white/10 py-3 last:border-0">
                <div className="line-clamp-1 text-sm text-slate-200">{item.query}</div>
                <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                  <Activity className="h-3.5 w-3.5" />
                  {item.valid ? "Valid" : "Needs review"} / {Math.round(item.confidence)}% confidence / {item.execution_time.toFixed(3)}s
                </div>
              </div>
            ))}
            {!filteredTrend.length ? (
              <div className="rounded-md border border-dashed border-white/10 p-6 text-center text-sm text-slate-500">
                No query activity exists in the selected range.
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Validated queries", value: rangeMetrics.validCount, icon: ShieldCheck },
          { label: "Average latency", value: `${rangeMetrics.averageLatency.toFixed(3)}s`, icon: Timer },
          { label: "Schema tables", value: metrics?.enterprise_schema?.tables_count ?? schemaQuery.data?.tables.length ?? 0, icon: Database },
          { label: "Relationships", value: metrics?.enterprise_schema?.relationships_count ?? 0, icon: Network }
        ].map((item) => {
          const Icon = item.icon;
          return (
          <Card key={item.label}>
            <CardContent className="flex items-center justify-between">
              <div><div className="text-xs text-slate-500">{item.label}</div><div className="mt-1 text-xl font-semibold text-white">{String(item.value)}</div></div>
              <Icon className="h-5 w-5 text-indigo-200" />
            </CardContent>
          </Card>
        );})}
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card>
          <CardContent>
            <div className="mb-4 text-sm font-semibold text-white">Agent Telemetry</div>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ["Intent accuracy", percent(filteredTrend.length ? filteredTrend.reduce((sum, point) => sum + point.intent_score, 0) / filteredTrend.length : 0)],
                ["Planner accuracy", percent(rangeMetrics.plannerAccuracy)],
                ["Validation accuracy", percent(rangeMetrics.validatorPrecision)],
                ["Optimization accuracy", percent(rangeMetrics.successRate)]
              ].map(([label, value]) => (
                <div key={label} className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                  <div className="text-xs text-slate-500">{label}</div>
                  <div className="mt-1 text-xl font-semibold text-white">{value}</div>
                </div>
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
              <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                <div className="text-xs text-slate-500">Virtual tables</div>
                <div className="mt-1 text-xl font-semibold text-white">{metrics?.enterprise_schema?.tables_count ?? 0}</div>
              </div>
              <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                <div className="text-xs text-slate-500">Relationships</div>
                <div className="mt-1 text-xl font-semibold text-white">{metrics?.enterprise_schema?.relationships_count ?? 0}</div>
              </div>
              <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                <div className="text-xs text-slate-500">Pending requests</div>
                <div className="mt-1 text-xl font-semibold text-white">{metrics?.schema_growth?.pending_requests ?? 0}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
