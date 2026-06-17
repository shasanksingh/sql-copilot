# Frontend Architecture

The frontend is a Next.js 15, React 19, TypeScript App Router application in `frontend/`.

## Feature Layout

```text
app/                    auth and workspace routes
app/admin/              administrator review pages
components/app-shell/   fixed sidebar, mobile drawer, top bar, command palette
components/auth/        shared public authentication shell
components/copilot/     stable chat workspace and Explainable AI panel
components/dashboard/   Recharts analytics
components/schema/      React Flow schema graph
components/ui/          reusable buttons, cards, forms, tables, dialogs, tabs
e2e/                    Playwright browser coverage
features/api/           typed credentialed API client
features/auth/          auth provider and session state
features/store/         persistent UI and Copilot state
middleware.ts           protected-route redirect
```

## Route Model

`/login`, `/signup`, `/forgot-password`, and `/reset-password` are public. Every workspace route requires the auth cookie at middleware time and `/auth/me` validation in the browser. The auth provider clears stale state and returns expired or revoked sessions to login.

`/admin/schema-requests` renders only for administrators. The API independently enforces the same role boundary.

## State Ownership

- TanStack Query owns API state such as metrics, schema catalogs, request queues, and feedback.
- AuthProvider owns the validated user and session-loading state.
- Zustand owns UI state, active Copilot response, history, toasts, sidebar state, and theme.
- Sidebar and theme preferences persist; auth credentials do not enter local storage.
- The active Copilot response is shared across Explainable AI, Planner, Optimizer, and Execution.

The typed API client sends `credentials: include`. Unsafe requests copy `sql_copilot_csrf` into `X-CSRF-Token`.

## Responsive Shell

The application shell uses dynamic viewport height and constrains page overflow. The desktop sidebar has a stable fixed column, internal navigation scroll, smooth width transition, active nested-route matching, and persistent collapse state. Mobile navigation uses a drawer.

The top bar has one desktop collapse control, responsive spacing, user identity, role, and logout.

## Copilot Layout

The Copilot card is a bounded flex column:

```text
header
message region (only scroll container)
horizontal suggestions
composer
```

Suggestions cannot overlap messages or the textarea because they participate in normal flex layout. The strip preserves the complete cross-domain prompt catalog after a response and prepends at most two context-aware prompts from the selected tables. The composer is `shrink-0`, remains visible after results, and stays within mobile and desktop viewports. A message-end reference handles auto-scroll. Pending user messages keep the layout stable during requests, and long prose or SQL wraps instead of widening the page.

## Product Views

- Dashboard: four range-scoped quality KPIs, real per-query confidence/planner/validator trends, 10-second refresh, operational cards, five time ranges, loading, empty, error, and retry states.
- Planner: React Flow path from Intent through Entities, Tables, Joins, Aggregations, and SQL.
- Schema Explorer: table/column search, domain filter, column details, relationships, graph link, and join recommendations.
- Optimizer: original and optimized SQL, explanation, execution plan, cost reduction, and index suggestions.
- Explainable AI: expandable seven-stage timeline, runtime trace, and explicit single-table, joined, or clarification planner status.
- Data Model Studio: table, schema, business requirement, CSV, JSON, and feedback submissions.
- Admin Review: request workflow and feedback queue.

## Failure Handling

The root route error boundary presents retry controls and submits structured diagnostics to `/logs/frontend`. Query-driven pages expose loading, empty, and API error states. Authentication errors are normalized by the API client.

## Validation

```powershell
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser tests run against the production Next.js build and local API. Coverage includes auth redirect, signup, real SQL generation, contextual plus cross-domain suggestions, desktop suggestion/composer geometry, sidebar collapse, and mobile navigation and overflow.
