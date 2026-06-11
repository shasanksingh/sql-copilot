# SQL Copilot Frontend

Modern production-grade frontend for SQL Copilot, built as a premium AI SaaS workspace.

## Stack

- Next.js 15 App Router
- React 19
- TypeScript
- Tailwind CSS
- shadcn/ui-style primitives
- React Query for server state
- Zustand for UI/session state
- Recharts for analytics
- React Flow for schema graph visualization
- Framer Motion for transitions

## Routes

```text
app/dashboard          statistics, analytics, confidence metrics, activity
app/copilot            chat, suggested prompts, SQL generation, explainability
app/schema-explorer    table search, column explorer, relationships
app/schema-graph       zoom/pan graph and join-path highlighting controls
app/execution          SQL editor, result grid, CSV/Excel export
app/planner            visual query planning stages and raw plan payload
app/optimizer          performance suggestions, missing indexes, warnings
app/settings           connections, preferences, theme controls
```

## Architecture

```text
app/                    route pages, root layout, React Query provider
components/app-shell    collapsible sidebar, mobile nav, topbar, command palette
components/copilot      chat workspace and Explainable AI panel
components/dashboard    Recharts analytics
components/schema       React Flow graph
components/ui           shadcn-style reusable primitives
features/api            typed backend client and response contracts
features/demo           fallback table/relationship/sample result data
features/store          Zustand stores for UI state, history, toasts
lib                     utilities
```

## API Integration

Set:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5000
```

Used endpoints:

```text
POST /sql
GET /health
GET /schema/relationships
GET /schema/er
GET /metrics
```

The execution page currently provides a production UI and export flow with preview rows. Add a backend execution endpoint before running arbitrary SQL against a live database.

## Commands

```bash
npm install
npm run dev
npm run lint
npm run build
```
