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
- Sidebar, theme, chat history, and active response persist; auth credentials do not enter local storage.
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

Suggestions cannot overlap messages or the textarea because they participate in normal flex layout. The strip preserves the complete cross-domain prompt catalog after a response and prepends at most two context-aware prompts from the selected tables. The composer is sticky inside the card, remains visible after results, and stays within mobile and desktop viewports. A message-end reference handles auto-scroll. Pending user messages keep the layout stable during requests, and long prose or highlighted SQL wraps instead of widening the page.

Chat history persists in local UI storage with active-response state, search, per-message delete, clear, export, and explainability re-open controls. Auth credentials do not enter local storage.

## Product Views

- Dashboard: four range-scoped quality KPIs, provider/model status, LLM success and fallback rates, p95 LLM latency, repair attempts, real per-query confidence/planner/validator trends, 10-second refresh, operational cards, five time ranges, loading, empty, error, and retry states.
- Planner: React Flow path from Intent through Entities, Business Rules, Tables, dynamic Join Graph nodes, Aggregations, Filters, Query Plan, SQL, and Confidence. Large join paths expand into one node per edge.
- Schema Explorer: table/column search, domain filter, column details, relationships, graph link, and join recommendations.
- Optimizer: original and optimized SQL, explanation, execution plan, cost reduction, and index suggestions.
- Explainable AI: expandable timeline with provider assist, business rules, join discovery, runtime trace, fallback reason, repair attempts, and explicit single-table, joined, or clarification planner status.
- Data Model Studio: table, schema, business requirement, CSV, Excel, JSON, SQL DDL, Parquet, feedback submissions, live metadata refresh, admin live apply, proposal apply, and dynamic table delete controls.
- Admin Review: request workflow, generated proposal apply action, and feedback queue.

## Schema Studio UX

Data Model Studio combines the request workflow and the live metadata engine. Normal users can submit governed schema requests with optional inferred upload samples. Administrators can apply the current form directly, promote generated proposals from the queue, refresh retrieval/planner metadata, and delete dynamic overlay tables. Query keys for schema catalog, relationships, metrics, request queues, and metadata status are invalidated together so the dashboard, schema explorer, and planner views reflect updates without a page reload.

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
