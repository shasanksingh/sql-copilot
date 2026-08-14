"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  BrainCircuit,
  CheckCircle2,
  CircleSlash,
  Database,
  KeyRound,
  Loader2,
  LockKeyhole,
  MailCheck,
  Moon,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Zap
} from "lucide-react";
import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { configureEmail, configureProvider, getRuntimeConfig } from "@/features/api/client";
import { useCopilotStore } from "@/features/store/use-copilot-store";

const NVIDIA_DEFAULTS = {
  provider: "nvidia",
  model: "openai/gpt-oss-20b",
  baseUrl: "https://integrate.api.nvidia.com/v1",
  temperature: "1",
  topP: "1",
  maxTokens: "4096",
  maxRetries: "0",
  timeoutSeconds: "60"
};

type ProviderForm = typeof NVIDIA_DEFAULTS;

const PROVIDER_DEFAULTS: Record<string, Pick<ProviderForm, "model" | "baseUrl">> = {
  nvidia: {
    model: NVIDIA_DEFAULTS.model,
    baseUrl: NVIDIA_DEFAULTS.baseUrl
  },
  openai: {
    model: "",
    baseUrl: "https://api.openai.com/v1"
  },
  local: {
    model: "deterministic",
    baseUrl: ""
  }
};

const EMAIL_DEFAULTS = {
  backend: "smtp",
  host: "",
  port: "587",
  username: "",
  sender: "",
  useTls: true,
  useSsl: false,
  timeoutSeconds: "20",
  outboxDir: "",
  frontendOrigin: "http://127.0.0.1:4000",
  testRecipient: ""
};

type EmailForm = typeof EMAIL_DEFAULTS;

export default function SettingsPage() {
  const theme = useCopilotStore((state) => state.theme);
  const setTheme = useCopilotStore((state) => state.setTheme);
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProviderForm>(NVIDIA_DEFAULTS);
  const [apiKey, setApiKey] = useState("");
  const [dirty, setDirty] = useState(false);
  const [emailForm, setEmailForm] = useState<EmailForm>(EMAIL_DEFAULTS);
  const [smtpPassword, setSmtpPassword] = useState("");
  const [emailDirty, setEmailDirty] = useState(false);

  const runtimeQuery = useQuery({
    queryKey: ["runtime-config"],
    queryFn: getRuntimeConfig,
    refetchInterval: 10_000
  });
  const runtime = runtimeQuery.data;
  const provider = runtime?.provider;
  const providerStatus = provider?.status;
  const email = runtime?.email;

  useEffect(() => {
    if (!provider || dirty) return;
    const selectedProvider = provider.selected || NVIDIA_DEFAULTS.provider;
    const defaults = PROVIDER_DEFAULTS[selectedProvider] ?? PROVIDER_DEFAULTS.nvidia;
    setForm({
      provider: selectedProvider,
      model: provider.chat_model || defaults.model,
      baseUrl: providerStatus?.base_url ?? defaults.baseUrl,
      temperature: String(provider.temperature ?? NVIDIA_DEFAULTS.temperature),
      topP: String(provider.top_p ?? NVIDIA_DEFAULTS.topP),
      maxTokens: String(provider.max_tokens ?? NVIDIA_DEFAULTS.maxTokens),
      maxRetries: String(provider.max_retries ?? NVIDIA_DEFAULTS.maxRetries),
      timeoutSeconds: String(provider.timeout_seconds ?? NVIDIA_DEFAULTS.timeoutSeconds)
    });
  }, [dirty, provider, providerStatus?.base_url]);

  useEffect(() => {
    if (!email || emailDirty) return;
    setEmailForm({
      backend: email.backend || EMAIL_DEFAULTS.backend,
      host: email.host || "",
      port: String(email.port ?? EMAIL_DEFAULTS.port),
      username: "",
      sender: email.sender || "",
      useTls: Boolean(email.use_tls),
      useSsl: Boolean(email.use_ssl),
      timeoutSeconds: String(email.timeout_seconds ?? EMAIL_DEFAULTS.timeoutSeconds),
      outboxDir: email.outbox_dir || "",
      frontendOrigin: email.frontend_origin || EMAIL_DEFAULTS.frontendOrigin,
      testRecipient: ""
    });
  }, [email, emailDirty]);

  const providerIsLocal = provider?.selected === "local" || providerStatus?.provider === "local";
  const providerNetworkBlocked = /network access is blocked/i.test(providerStatus?.reason ?? "");
  const statusTone = providerStatus?.available
    ? "emerald"
    : providerIsLocal
      ? "cyan"
    : providerNetworkBlocked
      ? "amber"
    : provider?.api_key_present
      ? "amber"
      : "slate";
  const statusLabel = providerStatus?.available
    ? "Ready"
    : providerIsLocal
      ? "Local fallback"
    : providerNetworkBlocked
      ? "Network blocked"
    : provider?.api_key_present
      ? "Configured"
      : "Missing NVIDIA key";
  const emailTone = email?.backend === "smtp" && email.smtp_configured
    ? "emerald"
    : email?.backend === "file"
      ? "amber"
      : "slate";
  const emailStatusLabel = email?.backend === "smtp" && email.smtp_configured
    ? "SMTP ready"
    : email?.backend === "file"
      ? "Outbox only"
      : "SMTP missing";

  const mutation = useMutation({
    mutationFn: (verify: boolean) => {
      const defaults = PROVIDER_DEFAULTS[form.provider] ?? PROVIDER_DEFAULTS.nvidia;
      return configureProvider({
        provider: form.provider,
        model: form.model || defaults.model,
        base_url: form.baseUrl || defaults.baseUrl,
        api_key: apiKey || undefined,
        temperature: toNumber(form.temperature, Number(NVIDIA_DEFAULTS.temperature)),
        top_p: toNumber(form.topP, Number(NVIDIA_DEFAULTS.topP)),
        max_tokens: toNumber(form.maxTokens, Number(NVIDIA_DEFAULTS.maxTokens)),
        max_retries: toNumber(form.maxRetries, Number(NVIDIA_DEFAULTS.maxRetries)),
        timeout_seconds: toNumber(form.timeoutSeconds, Number(NVIDIA_DEFAULTS.timeoutSeconds)),
        verify
      });
    },
    onSuccess: async () => {
      setApiKey("");
      setDirty(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["runtime-config"] }),
        queryClient.invalidateQueries({ queryKey: ["metrics"] })
      ]);
    }
  });

  const emailMutation = useMutation({
    mutationFn: (verify: boolean) =>
      configureEmail({
        backend: emailForm.backend,
        host: emailForm.host,
        port: toNumber(emailForm.port, Number(EMAIL_DEFAULTS.port)),
        username: emailForm.username || undefined,
        password: smtpPassword || undefined,
        sender: emailForm.sender,
        use_tls: emailForm.useTls,
        use_ssl: emailForm.useSsl,
        timeout_seconds: toNumber(emailForm.timeoutSeconds, Number(EMAIL_DEFAULTS.timeoutSeconds)),
        outbox_dir: emailForm.outboxDir || undefined,
        frontend_origin: emailForm.frontendOrigin,
        verify,
        test_recipient: emailForm.testRecipient || undefined
      }),
    onSuccess: async () => {
      setSmtpPassword("");
      setEmailDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["runtime-config"] });
    }
  });

  const errorMessage = useMemo(() => {
    if (!mutation.error) return "";
    const message = mutation.error instanceof Error ? mutation.error.message : String(mutation.error);
    try {
      return JSON.parse(message).error || message;
    } catch {
      return message;
    }
  }, [mutation.error]);

  const emailErrorMessage = useMemo(() => {
    if (!emailMutation.error) return "";
    const message = emailMutation.error instanceof Error ? emailMutation.error.message : String(emailMutation.error);
    try {
      return JSON.parse(message).error || message;
    } catch {
      return message;
    }
  }, [emailMutation.error]);

  function updateForm(key: keyof ProviderForm, value: string) {
    setDirty(true);
    setForm((current) => {
      if (key === "provider") {
        const defaults = PROVIDER_DEFAULTS[value] ?? PROVIDER_DEFAULTS.nvidia;
        return { ...current, provider: value, model: defaults.model, baseUrl: defaults.baseUrl };
      }
      return { ...current, [key]: value };
    });
  }

  function updateEmailForm<K extends keyof EmailForm>(key: K, value: EmailForm[K]) {
    setEmailDirty(true);
    setEmailForm((current) => ({ ...current, [key]: value }));
  }

  function submitProvider(verify: boolean) {
    mutation.mutate(verify);
  }

  function submitEmail(verify: boolean) {
    emailMutation.mutate(verify);
  }

  return (
    <AppShell>
      <PageHeader title="Settings" description="Runtime controls for provider access, schema retrieval, validation, and user preferences." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="xl:col-span-2">
          <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <CardTitle className="flex items-center gap-2">
              <BrainCircuit className="h-4 w-4 text-cyan-200" />
              LLM Provider
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={statusTone}>{statusLabel}</Badge>
              <Badge tone={provider?.runtime_configured ? "cyan" : "slate"}>
                {provider?.runtime_configured ? "Runtime saved" : "Session only"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-3 md:grid-cols-4">
              <RuntimeStat
                icon={<ServerCog className="h-4 w-4" />}
                label="Provider"
                value={providerStatus?.provider || form.provider}
              />
              <RuntimeStat
                icon={<Zap className="h-4 w-4" />}
                label="Model"
                value={providerStatus?.model || form.model}
              />
              <RuntimeStat
                icon={provider?.api_key_present ? <CheckCircle2 className="h-4 w-4" /> : <CircleSlash className="h-4 w-4" />}
                label="Key"
                value={providerIsLocal ? "Not used" : provider?.api_key_present ? "Stored" : "Required"}
              />
              <RuntimeStat
                icon={<ShieldCheck className="h-4 w-4" />}
                label="Adapter"
                value={providerStatus?.adapter || provider?.adapter || "N/A"}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="space-y-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="Provider">
                    <select
                      value={form.provider}
                      onChange={(event) => updateForm("provider", event.target.value)}
                      className="h-10 w-full rounded-md border border-white/10 bg-slate-950/70 px-3 text-sm text-white outline-none ring-cyan-300/30 focus:ring-4"
                      aria-label="LLM provider"
                    >
                      <option value="nvidia">NVIDIA</option>
                      <option value="openai">Custom OpenAI-Compatible</option>
                      <option value="local">Local Planner</option>
                    </select>
                  </Field>
                  <Field label="Model">
                    <Input
                      value={form.model}
                      onChange={(event) => updateForm("model", event.target.value)}
                      aria-label="LLM model"
                    />
                  </Field>
                </div>
                <Field label="Base URL">
                  <Input
                    value={form.baseUrl}
                    onChange={(event) => updateForm("baseUrl", event.target.value)}
                    aria-label="LLM base URL"
                  />
                </Field>
                <Field label="API Key">
                  <div className="relative">
                    <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                    <Input
                      value={apiKey}
                      onChange={(event) => setApiKey(event.target.value)}
                      type="password"
                      className="pl-9"
                      placeholder={provider?.api_key_present ? "Stored key will be reused" : "Enter provider key"}
                      aria-label="LLM API key"
                    />
                  </div>
                </Field>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                <Field label="Temperature">
                  <Input
                    value={form.temperature}
                    onChange={(event) => updateForm("temperature", event.target.value)}
                    inputMode="decimal"
                    aria-label="Temperature"
                  />
                </Field>
                <Field label="Top P">
                  <Input
                    value={form.topP}
                    onChange={(event) => updateForm("topP", event.target.value)}
                    inputMode="decimal"
                    aria-label="Top P"
                  />
                </Field>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="Tokens">
                    <Input
                      value={form.maxTokens}
                      onChange={(event) => updateForm("maxTokens", event.target.value)}
                      inputMode="numeric"
                      aria-label="Max tokens"
                    />
                  </Field>
                  <Field label="Retries">
                    <Input
                      value={form.maxRetries}
                      onChange={(event) => updateForm("maxRetries", event.target.value)}
                      inputMode="numeric"
                      aria-label="Max retries"
                    />
                  </Field>
                  <Field label="Timeout">
                    <Input
                      value={form.timeoutSeconds}
                      onChange={(event) => updateForm("timeoutSeconds", event.target.value)}
                      inputMode="numeric"
                      aria-label="LLM timeout seconds"
                    />
                  </Field>
                </div>
              </div>
            </div>

            {providerStatus?.reason ? (
              <div className={`rounded-md border px-3 py-2 text-sm ${providerIsLocal ? "border-cyan-300/25 bg-cyan-300/10 text-cyan-100" : "border-amber-300/25 bg-amber-300/10 text-amber-100"}`}>
                {providerStatus.reason}
              </div>
            ) : null}
            {errorMessage ? (
              <div className="rounded-md border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-sm text-rose-100">
                {errorMessage}
              </div>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button onClick={() => submitProvider(false)} disabled={mutation.isPending}>
                {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                {form.provider === "nvidia" ? "Activate NVIDIA" : "Activate provider"}
              </Button>
              <Button variant="outline" onClick={() => submitProvider(true)} disabled={mutation.isPending}>
                <RefreshCw className="h-4 w-4" />
                Save and test
              </Button>
              <Button variant="ghost" onClick={() => { void runtimeQuery.refetch(); }} disabled={runtimeQuery.isFetching}>
                <RefreshCw className="h-4 w-4" />
                Refresh status
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <CardTitle className="flex items-center gap-2">
              <MailCheck className="h-4 w-4 text-cyan-200" />
              Email Delivery
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={emailTone}>{emailStatusLabel}</Badge>
              <Badge tone={email?.password_present ? "emerald" : "slate"}>
                {email?.password_present ? "Password stored" : "Password required"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-3 md:grid-cols-4">
              <RuntimeStat
                icon={<ServerCog className="h-4 w-4" />}
                label="Backend"
                value={email?.backend || emailForm.backend}
              />
              <RuntimeStat
                icon={<Database className="h-4 w-4" />}
                label="Host"
                value={email?.host || "Not configured"}
              />
              <RuntimeStat
                icon={<MailCheck className="h-4 w-4" />}
                label="From"
                value={email?.sender || "Not configured"}
              />
              <RuntimeStat
                icon={<ShieldCheck className="h-4 w-4" />}
                label="Reset URL"
                value={email?.frontend_origin || emailForm.frontendOrigin}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
              <div className="space-y-3">
                <div className="grid gap-3 md:grid-cols-[0.7fr_1.3fr]">
                  <Field label="Backend">
                    <select
                      value={emailForm.backend}
                      onChange={(event) => updateEmailForm("backend", event.target.value)}
                      className="h-10 w-full rounded-md border border-white/10 bg-slate-950/70 px-3 text-sm text-white outline-none ring-cyan-300/30 focus:ring-4"
                      aria-label="Email backend"
                    >
                      <option value="smtp">SMTP</option>
                      <option value="file">Development outbox</option>
                    </select>
                  </Field>
                  <Field label="SMTP Host">
                    <Input
                      value={emailForm.host}
                      onChange={(event) => updateEmailForm("host", event.target.value)}
                      placeholder="smtp.gmail.com"
                      aria-label="SMTP host"
                    />
                  </Field>
                </div>
                <div className="grid gap-3 md:grid-cols-[0.5fr_1fr_1fr]">
                  <Field label="Port">
                    <Input
                      value={emailForm.port}
                      onChange={(event) => updateEmailForm("port", event.target.value)}
                      inputMode="numeric"
                      aria-label="SMTP port"
                    />
                  </Field>
                  <Field label="Username">
                    <Input
                      value={emailForm.username}
                      onChange={(event) => updateEmailForm("username", event.target.value)}
                      placeholder={email?.username_present ? "Stored username will be reused" : "SMTP username"}
                      aria-label="SMTP username"
                    />
                  </Field>
                  <Field label="From Address">
                    <Input
                      value={emailForm.sender}
                      onChange={(event) => updateEmailForm("sender", event.target.value)}
                      placeholder="sql-copilot@example.com"
                      aria-label="SMTP from address"
                    />
                  </Field>
                </div>
                <Field label="SMTP Password">
                  <div className="relative">
                    <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                    <Input
                      value={smtpPassword}
                      onChange={(event) => setSmtpPassword(event.target.value)}
                      type="password"
                      className="pl-9"
                      placeholder={email?.password_present ? "Stored password will be reused" : "SMTP password or app password"}
                      aria-label="SMTP password"
                    />
                  </div>
                </Field>
              </div>

              <div className="space-y-3">
                <Field label="Password Reset Base URL">
                  <Input
                    value={emailForm.frontendOrigin}
                    onChange={(event) => updateEmailForm("frontendOrigin", event.target.value)}
                    aria-label="Password reset base URL"
                  />
                </Field>
                <Field label="Outbox Directory">
                  <Input
                    value={emailForm.outboxDir}
                    onChange={(event) => updateEmailForm("outboxDir", event.target.value)}
                    aria-label="Email outbox directory"
                  />
                </Field>
                <div className="grid gap-3 md:grid-cols-2">
                  <ToggleField
                    label="STARTTLS"
                    checked={emailForm.useTls}
                    onCheckedChange={(checked) => updateEmailForm("useTls", checked)}
                  />
                  <ToggleField
                    label="SSL"
                    checked={emailForm.useSsl}
                    onCheckedChange={(checked) => updateEmailForm("useSsl", checked)}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-[0.6fr_1.4fr]">
                  <Field label="Timeout">
                    <Input
                      value={emailForm.timeoutSeconds}
                      onChange={(event) => updateEmailForm("timeoutSeconds", event.target.value)}
                      inputMode="numeric"
                      aria-label="SMTP timeout"
                    />
                  </Field>
                  <Field label="Test Recipient">
                    <Input
                      value={emailForm.testRecipient}
                      onChange={(event) => updateEmailForm("testRecipient", event.target.value)}
                      type="email"
                      placeholder="you@example.com"
                      aria-label="Email test recipient"
                    />
                  </Field>
                </div>
              </div>
            </div>

            {emailMutation.data?.delivery?.status ? (
              <div className="rounded-md border border-emerald-300/25 bg-emerald-300/10 px-3 py-2 text-sm text-emerald-100">
                Email test status: {emailMutation.data.delivery.status}
                {emailMutation.data.delivery.outbox_path ? ` at ${emailMutation.data.delivery.outbox_path}` : ""}
                {emailMutation.data.delivery.reason ? ` - ${emailMutation.data.delivery.reason}` : ""}
              </div>
            ) : null}
            {emailErrorMessage ? (
              <div className="rounded-md border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-sm text-rose-100">
                {emailErrorMessage}
              </div>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button onClick={() => submitEmail(false)} disabled={emailMutation.isPending}>
                {emailMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                Save email
              </Button>
              <Button variant="outline" onClick={() => submitEmail(true)} disabled={emailMutation.isPending}>
                <MailCheck className="h-4 w-4" />
                Save and send test
              </Button>
            </div>
          </CardContent>
        </Card>

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

function RuntimeStat({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-white/10 bg-slate-950/45 p-3">
      <div className="mb-2 flex items-center gap-2 text-slate-400">
        {icon}
        <span className="text-xs font-medium uppercase">{label}</span>
      </div>
      <div className="truncate text-sm font-semibold text-white" title={value}>{value}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium uppercase text-slate-400">{label}</span>
      {children}
    </label>
  );
}

function ToggleField({
  label,
  checked,
  onCheckedChange
}: {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex h-10 items-center justify-between gap-3 rounded-md border border-white/10 bg-slate-950/45 px-3">
      <span className="text-sm text-slate-300">{label}</span>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
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

function toNumber(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
