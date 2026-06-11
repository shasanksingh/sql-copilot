"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Database, Gauge, ShieldCheck, Timer } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { AnalyticsChart } from "@/components/dashboard/analytics";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { getMetrics, getRelationships } from "@/features/api/client";

export default function DashboardPage() {
  const metricsQuery = useQuery({ queryKey: ["metrics"], queryFn: getMetrics });
  const schemaQuery = useQuery({ queryKey: ["relationships"], queryFn: getRelationships });
  const metrics = metricsQuery.data;
  const stats = [
    { label: "Validated queries", value: metrics ? metrics.total.toLocaleString() : "0", icon: ShieldCheck, tone: "cyan" },
    { label: "SQL accuracy", value: metrics ? `${metrics.sql_accuracy}%` : "0%", icon: Gauge, tone: "emerald" },
    { label: "Schema tables", value: `${schemaQuery.data?.tables.length ?? 0}`, icon: Database, tone: "indigo" },
    { label: "Avg latency", value: metrics ? `${metrics.average_latency}s` : "0s", icon: Timer, tone: "amber" }
  ];

  return (
    <AppShell>
      <PageHeader title="Dashboard" description="Operational view of SQL generation quality, confidence, schema coverage, and recent activity." />
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
        <AnalyticsChart trend={metrics?.trend} />
        <Card>
          <CardContent>
            <div className="mb-4 flex items-center justify-between">
              <div className="text-sm font-semibold text-white">Recent Activity</div>
              <Badge tone="cyan">{metrics?.query_success_rate ?? 0}% success</Badge>
            </div>
            {(metrics?.trend.length ? metrics.trend.slice(-6).reverse() : []).map((item) => (
              <div key={`${item.query}-${item.timestamp}`} className="border-b border-white/10 py-3 last:border-0">
                <div className="line-clamp-1 text-sm text-slate-200">{item.query}</div>
                <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                  <Activity className="h-3.5 w-3.5" />
                  {item.validation_status} / reward {item.reward}
                </div>
              </div>
            ))}
            {!metrics?.trend.length ? (
              <div className="rounded-md border border-dashed border-white/10 p-6 text-center text-sm text-slate-500">
                Generate a few SQL queries to populate live activity.
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
