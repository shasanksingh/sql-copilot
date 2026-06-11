import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { CopilotChat } from "@/components/copilot/copilot-chat";

export default function CopilotPage() {
  return (
    <AppShell>
      <PageHeader title="SQL Copilot Chat" description="Generate schema-linked SQL with validation, confidence gating, and explainable plans." />
      <CopilotChat />
    </AppShell>
  );
}
