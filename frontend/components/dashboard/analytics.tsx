"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FeedbackTrendPoint } from "@/features/api/types";

const data = [
  { name: "Mon", confidence: 82, queries: 18 },
  { name: "Tue", confidence: 88, queries: 24 },
  { name: "Wed", confidence: 76, queries: 19 },
  { name: "Thu", confidence: 91, queries: 31 },
  { name: "Fri", confidence: 86, queries: 27 },
  { name: "Sat", confidence: 93, queries: 14 }
];

export function AnalyticsChart({ trend = [] }: { trend?: FeedbackTrendPoint[] }) {
  const chartData = trend.length
    ? trend.slice(-12).map((point, index) => ({
        name: point.timestamp ? new Date(point.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : `Run ${index + 1}`,
        confidence: Math.max(0, Math.min(100, point.reward * 100)),
        queries: point.execution_time
      }))
    : data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Query Analytics</CardTitle>
      </CardHeader>
      <CardContent className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="confidence" x1="0" x2="0" y1="0" y2="1">
                <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.5} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,.08)" />
            <XAxis dataKey="name" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" />
            <Tooltip contentStyle={{ background: "#020617", border: "1px solid rgba(255,255,255,.1)" }} />
            <Area type="monotone" dataKey="confidence" stroke="#22d3ee" fill="url(#confidence)" />
            <Area type="monotone" dataKey="queries" stroke="#818cf8" fill="transparent" />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
