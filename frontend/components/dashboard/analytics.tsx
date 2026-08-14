"use client";

import { Area, Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FeedbackTrendPoint } from "@/features/api/types";

type ChartDatum = {
  name: string;
  confidence: number;
  planner: number;
  validator: number;
  coverage: number;
  model: number | null;
  latencyMs: number;
  query: string;
  valid: boolean;
  fallback: boolean;
  provider: string;
};

function clampPercent(value?: number | null) {
  return Math.max(0, Math.min(100, Number(value ?? 0)));
}

function AnalyticsTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ payload: ChartDatum }>; label?: string }) {
  if (!active || !payload?.length) return null;
  const item = payload[0]?.payload;
  if (!item) return null;
  return (
    <div className="max-w-xs rounded-md border border-white/10 bg-slate-950/95 p-3 text-xs shadow-glow">
      <div className="font-medium text-white">{label}</div>
      <div className="mt-1 line-clamp-2 text-slate-400">{item.query || "Query event"}</div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-slate-300">
        <span>Confidence</span><span className="text-right text-cyan-100">{item.confidence.toFixed(1)}%</span>
        <span>Planner</span><span className="text-right text-indigo-100">{item.planner.toFixed(1)}%</span>
        <span>Validator</span><span className="text-right text-emerald-100">{item.validator.toFixed(1)}%</span>
        <span>Latency</span><span className="text-right text-amber-100">{Math.round(item.latencyMs)}ms</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone={item.valid ? "emerald" : "amber"} className="h-6">{item.valid ? "Valid" : "Review"}</Badge>
        <Badge tone={item.fallback ? "amber" : "cyan"} className="h-6">{item.fallback ? "Fallback" : item.provider}</Badge>
      </div>
    </div>
  );
}

export function AnalyticsChart({ trend = [] }: { trend?: FeedbackTrendPoint[] }) {
  const chartData = trend.slice(-24).map((point, index) => ({
    name: point.timestamp
      ? new Date(point.timestamp).toLocaleString([], {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit"
        })
      : `Run ${index + 1}`,
    confidence: clampPercent(point.system_confidence ?? point.confidence),
    planner: clampPercent(point.planner_score),
    validator: clampPercent(point.validator_score),
    coverage: clampPercent(point.coverage_confidence ?? point.confidence),
    model: point.model_confidence && !point.fallback_used ? clampPercent(point.model_confidence) : null,
    latencyMs: point.latency_ms ?? point.execution_time * 1000,
    query: point.query,
    valid: point.valid,
    fallback: Boolean(point.fallback_used),
    provider: point.provider === "nvidia" ? "NVIDIA" : point.provider ?? "local"
  }));
  const validRate = chartData.length
    ? Math.round((chartData.filter((item) => item.valid).length / chartData.length) * 100)
    : 0;
  const averageLatency = chartData.length
    ? Math.round(chartData.reduce((sum, item) => sum + item.latencyMs, 0) / chartData.length)
    : 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <div>
          <CardTitle>Query Analytics</CardTitle>
          <div className="mt-1 text-xs text-slate-500">Confidence, validation, fallback, and latency over the selected range.</div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Badge tone="emerald">{validRate}% valid</Badge>
          <Badge tone="amber">{averageLatency}ms avg</Badge>
        </div>
      </CardHeader>
      <CardContent className="h-72">
        {chartData.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 4, bottom: 0, left: -10 }}>
              <defs>
                <linearGradient id="confidence" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.45} />
                  <stop offset="95%" stopColor="#22d3ee" stopOpacity={0.03} />
                </linearGradient>
                <linearGradient id="latency" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.38} />
                  <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.08} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,.08)" />
              <XAxis dataKey="name" minTickGap={28} stroke="#94a3b8" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="score" domain={[0, 100]} stroke="#94a3b8" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="latency" orientation="right" stroke="#fbbf24" tick={{ fontSize: 12 }} width={42} />
              <Tooltip content={<AnalyticsTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#cbd5e1" }} />
              <ReferenceLine yAxisId="score" y={75} stroke="rgba(251,191,36,.7)" strokeDasharray="4 4" />
              <Bar yAxisId="latency" dataKey="latencyMs" name="Latency" radius={[4, 4, 0, 0]} barSize={14}>
                {chartData.map((item, index) => (
                  <Cell key={`${item.name}-${index}`} fill={item.fallback ? "rgba(251,191,36,.42)" : "url(#latency)"} />
                ))}
              </Bar>
              <Area yAxisId="score" type="monotone" dataKey="confidence" stroke="#22d3ee" fill="url(#confidence)" strokeWidth={2} />
              <Line yAxisId="score" type="monotone" dataKey="planner" name="Planner" stroke="#818cf8" strokeWidth={2.25} dot={false} />
              <Line yAxisId="score" type="monotone" dataKey="validator" name="Validator" stroke="#34d399" strokeWidth={2.25} dot={false} />
              <Line yAxisId="score" type="monotone" dataKey="coverage" name="Coverage" stroke="#f472b6" strokeWidth={1.75} dot={false} />
              <Line yAxisId="score" type="monotone" dataKey="model" name="Model" stroke="#fbbf24" strokeWidth={2} dot={{ r: 2 }} connectNulls={false} />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center rounded-md border border-dashed border-white/10 text-sm text-slate-500">
            Run SQL queries to populate live confidence and validation trends.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
