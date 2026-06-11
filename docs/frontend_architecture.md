# Frontend Architecture

The frontend is a Next.js 15, React 19, TypeScript app in `frontend/`.

## Feature Layout

```text
app/                    App Router pages
components/app-shell    sidebar, mobile drawer, topbar, command palette
components/copilot      chat workspace and Explainable AI panel
components/dashboard    Recharts analytics
components/schema       React Flow schema graph
components/ui           shadcn-style primitives
features/api            typed API client
features/demo           fallback domain data
features/store          Zustand app state and toasts
```

## State

- React Query owns backend data: metrics, relationships, ER graph, SQL generation mutation.
- Zustand owns UI/session state: sidebar, mobile drawer, command palette, theme, active response, query history, toasts.
- The active Copilot response is shared across Explainable AI, Planner, Optimizer, and Execution pages.

## UI System

The interface uses glass panels, restrained gradients, 8px cards, lucide icons, skeletons, command palette, toast notifications, responsive layout, and animated route-level interactions. The app supports dark and light modes through document-level theme classes.

## API Contracts

```text
POST /sql                  natural language to SQL
GET /schema/relationships  table and relationship graph
GET /schema/er             Mermaid ER payload
GET /metrics               feedback and RL metrics
GET /health                backend health
```
