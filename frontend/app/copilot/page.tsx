import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { CopilotChat } from "@/components/copilot/copilot-chat";

export default function CopilotPage() {
  return (
    <AppShell>
      <PageHeader
        compact
        title="SQL Copilot Chat"
        description="Ask business questions, receive reviewed SQL, and inspect the decision trail."
      />
      <CopilotChat />
    </AppShell>
  );
}
