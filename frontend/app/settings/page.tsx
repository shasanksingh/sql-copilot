"use client";

import { Bell, Database, LockKeyhole, Moon, SlidersHorizontal, Sun } from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { useCopilotStore } from "@/features/store/use-copilot-store";

export default function SettingsPage() {
  const theme = useCopilotStore((state) => state.theme);
  const setTheme = useCopilotStore((state) => state.setTheme);

  return (
    <AppShell>
      <PageHeader title="Settings" description="Configure database connections, query preferences, theme, and validation thresholds." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Database className="h-4 w-4 text-cyan-200" />Database Connections</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input defaultValue="PostgreSQL" aria-label="PostgreSQL connection" />
            <Input defaultValue="MySQL" aria-label="MySQL connection" />
            <Input defaultValue="SQL Server" aria-label="SQL Server connection" />
            <Input defaultValue="SQLite / backend/sql_agent_feedback.sqlite" aria-label="SQLite connection" />
            <Input defaultValue="127.0.0.1:5000" aria-label="Backend URL" />
            <Button variant="outline">Test connection</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><SlidersHorizontal className="h-4 w-4 text-cyan-200" />Agent Configuration</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <Input defaultValue="Confidence threshold: 70" aria-label="Confidence threshold" />
            <Input defaultValue="Validation strictness: high" aria-label="Validation strictness" />
            <SettingRow label="Require join path explanation" checked />
            <SettingRow label="Clarification mode" checked />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Retrieval Configuration</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <Input defaultValue="BM25 weight: 0.45" aria-label="BM25 weight" />
            <Input defaultValue="Vector weight: 0.55" aria-label="Vector weight" />
            <SettingRow label="Hybrid retrieval" checked />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><LockKeyhole className="h-4 w-4 text-cyan-200" />Security</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <SettingRow label="Allow SELECT only" checked />
            <SettingRow label="Block DDL" checked />
            <SettingRow label="Block DML" checked />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Theme Selection</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button variant={theme === "dark" ? "primary" : "outline"} onClick={() => setTheme("dark")}><Moon className="h-4 w-4" />Dark</Button>
            <Button variant={theme === "light" ? "primary" : "outline"} onClick={() => setTheme("light")}><Sun className="h-4 w-4" />Light</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Bell className="h-4 w-4 text-cyan-200" />Notifications and Audit Logs</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <SettingRow label="Validation alerts" checked />
            <SettingRow label="Schema request updates" checked />
            <SettingRow label="Audit log capture" checked />
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

function SettingRow({ label, checked }: { label: string; checked: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-white/10 bg-white/[0.04] p-3">
      <span className="text-sm text-slate-300">{label}</span>
      <Switch checked={checked} />
    </div>
  );
}
