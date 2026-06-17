# SQL Copilot Frontend

The frontend is a Next.js 15 App Router application for authenticated SQL generation, explainability, schema exploration, data-model governance, planning, optimization, and operational analytics.

## Stack

- React 19 and TypeScript
- Tailwind CSS and reusable UI primitives
- TanStack Query for server state
- Zustand persistence for sidebar and theme preferences
- React Flow for planner and schema graphs
- Recharts for analytics
- Framer Motion for transitions
- Playwright for responsive browser tests

## Run

```powershell
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. Set the backend address when it differs from the default:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5000
```

The API must allow this exact frontend origin through `FRONTEND_ORIGIN`.

## Routes

Public routes:

| Route | Purpose |
| --- | --- |
| `/login` | Email/password login, Remember Me, and validation |
| `/signup` | Account creation and password-strength validation |
| `/forgot-password` | Non-enumerating reset request |
| `/reset-password` | One-time token password replacement |

Protected workspace routes:

| Route | Purpose |
| --- | --- |
| `/dashboard` | KPIs, trends, confidence, latency, and activity |
| `/copilot` | Natural-language SQL chat and explainability |
| `/schema-explorer` | Searchable tables, columns, and relationships |
| `/schema-graph` | Interactive relationship graph |
| `/data-model-studio` | Schema request, upload, and feedback portal |
| `/execution` | SQL preview, result grid, and export |
| `/planner` | Interactive Intent-to-SQL node graph |
| `/optimizer` | SQL comparison, plan, cost, and index guidance |
| `/settings` | Connections, thresholds, benchmarks, API, and logging |
| `/admin/schema-requests` | Administrator request and feedback review |

Middleware redirects unauthenticated workspace requests to `/login?next=...`. The client auth provider then validates the server-side session with `/auth/me`; expired or revoked sessions return to login.

## Workspace Behavior

- The desktop sidebar remains fixed, scrolls internally, collapses smoothly, and persists its state.
- The mobile sidebar is a drawer with accessible open and close controls.
- The top bar uses responsive flex sizing and exposes the signed-in user, role, and logout.
- The Copilot message region is the only scrolling chat area.
- Suggestions are a horizontal strip directly above the composer.
- The strip always keeps the full cross-domain prompt catalog and prepends no more than two prompts related to the latest result.
- The composer remains at the bottom, supports Enter to submit and Shift+Enter for a newline, and stays visible after responses.
- Messages and SQL wrap safely without causing horizontal overflow.
- Route errors are recoverable and are reported to `/logs/frontend`.
- Explainable AI reports a completed single-table plan when no join is required instead of leaving a misleading planner-waiting state.
- Dashboard metrics refresh every 10 seconds and are recalculated from the events inside the selected Day, Week, Month, Quarter, or Year range.

## Authentication Contract

The typed client always sends credentials. The backend writes:

- `sql_copilot_access`: HTTP-only signed JWT
- `sql_copilot_csrf`: readable CSRF token

For `POST`, `PATCH`, `PUT`, and `DELETE`, the client mirrors the CSRF cookie into `X-CSRF-Token`. The backend verifies the header, cookie, and session record match.

## API Contract

```text
POST  /auth/signup
POST  /auth/login
GET   /auth/me
POST  /auth/logout
POST  /auth/forgot-password
POST  /auth/reset-password
POST  /sql
GET   /health
GET   /metrics
GET   /schema/catalog
GET   /schema/relationships
GET   /schema/er
GET   /enterprise-schema
POST  /schema-request
GET   /schema-requests
PATCH /schema-request/:id/status
POST  /feedback
GET   /feedback
POST  /logs/frontend
```

SQL responses include planning, validation, confidence, coverage, clarification, runtime, and optimizer fields. Schema requests use JSON for ordinary requests and `multipart/form-data` for CSV/JSON uploads.

`GET /metrics` trend points include per-query confidence, planner score, validator score, intent score, join score, validity, reward, and latency. The chart plots the real quality scores on a 0-100 axis; reward is not treated as confidence.

## Project Layout

```text
app/                    # public auth and protected workspace routes
app/admin/              # role-gated administrator routes
components/app-shell/   # sidebar, mobile navigation, top bar
components/auth/        # shared authentication layout
components/copilot/     # stable chat and explainability views
components/dashboard/   # analytics visualizations
components/schema/      # React Flow graph components
components/ui/          # reusable UI primitives
e2e/                    # Playwright browser tests
features/api/           # credentialed typed API client
features/auth/          # session provider and auth hooks
features/store/         # persistent workspace state
middleware.ts           # route access redirect
```

## Validation

```powershell
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

Playwright uses the production Next.js build and a local Uvicorn backend. It covers protected-route redirects, signup, SQL generation, suggestion/composer geometry, sidebar collapse, and mobile overflow.

## Execution Safety

The execution page is a preview and export workflow. It does not send arbitrary SQL to a live database because the backend deliberately exposes generation and validation, not general-purpose execution.
