"use client";

import { Database, Moon, ShieldCheck, Sun } from "lucide-react";
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
          <CardHeader><CardTitle className="flex items-center gap-2"><Database className="h-4 w-4 text-cyan-200" />Database Connection</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Input defaultValue="SQLite / Postgres compatible" aria-label="Database type" />
            <Input defaultValue="127.0.0.1:5000" aria-label="Backend URL" />
            <Input defaultValue="backend/data/RAG_DOC.xlsx" aria-label="Schema file" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-cyan-200" />Query Preferences</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <Input defaultValue="Confidence threshold: 80" aria-label="Confidence threshold" />
            <SettingRow label="Block SELECT *" checked />
            <SettingRow label="Require join path explanation" checked />
            <SettingRow label="Cache validated query plans" checked />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Theme Selection</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button variant={theme === "dark" ? "primary" : "outline"} onClick={() => setTheme("dark")}><Moon className="h-4 w-4" />Dark</Button>
            <Button variant={theme === "light" ? "primary" : "outline"} onClick={() => setTheme("light")}><Sun className="h-4 w-4" />Light</Button>
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
