import { AppShell } from "@/components/app-shell/app-shell";
import { PageHeader } from "@/components/app-shell/page-header";
import { SchemaGraphView } from "@/components/schema/schema-graph-view";

export default function SchemaGraphPage() {
  return (
    <AppShell>
      <PageHeader title="Schema Graph" description="Interactive relationship graph with zoom, pan, minimap, and animated join edges." />
      <SchemaGraphView />
    </AppShell>
  );
}
