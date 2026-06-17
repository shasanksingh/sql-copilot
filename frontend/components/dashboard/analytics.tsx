"use client";

import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FeedbackTrendPoint } from "@/features/api/types";

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
    confidence: Math.max(0, Math.min(100, point.confidence)),
    planner: Math.max(0, Math.min(100, point.planner_score)),
    validator: Math.max(0, Math.min(100, point.validator_score)),
    latency: point.execution_time,
    query: point.query
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Query Analytics</CardTitle>
      </CardHeader>
      <CardContent className="h-72">
        {chartData.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="confidence" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.45} />
                  <stop offset="95%" stopColor="#22d3ee" stopOpacity={0.03} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,.08)" />
              <XAxis dataKey="name" minTickGap={28} stroke="#94a3b8" />
              <YAxis domain={[0, 100]} stroke="#94a3b8" />
              <Tooltip
                contentStyle={{ background: "#020617", border: "1px solid rgba(255,255,255,.1)" }}
                formatter={(value, name) => [`${Number(value).toFixed(1)}%`, String(name)]}
                labelFormatter={(label) => String(label)}
              />
              <Legend />
              <Area type="monotone" dataKey="confidence" stroke="#22d3ee" fill="url(#confidence)" strokeWidth={2} />
              <Area type="monotone" dataKey="planner" stroke="#818cf8" fill="transparent" strokeWidth={2} />
              <Area type="monotone" dataKey="validator" stroke="#34d399" fill="transparent" strokeWidth={2} />
            </AreaChart>
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
