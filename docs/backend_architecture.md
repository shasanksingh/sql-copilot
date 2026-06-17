# Backend Architecture

The backend is a Flask application exposed through ASGI. Root `main.py` remains a compatibility export while runtime code lives under `backend/`.

```text
backend/
  app.py                       API, auth middleware, SQL orchestration, metrics
  auth.py                      identity, sessions, resets, feedback, structured logs
  synthetic_enterprise_data.py enterprise catalog and schema request repository
  main.py                      ASGI exports
  data/RAG_DOC.xlsx            active schema source
  static/index.html            legacy UI at /legacy
  requirements.txt             runtime dependencies
  requirements-rl.txt          optional RL dependencies
```

## Entrypoints

```powershell
python -m uvicorn main:asgi_app --host 127.0.0.1 --port 5000
python -m uvicorn backend.main:asgi_app --host 127.0.0.1 --port 5000
```

## Request Boundary

`before_request` leaves only API metadata, health, legacy UI, and authentication entry points public. All other routes require a valid JWT whose session ID is active in SQLite. Unsafe authenticated methods also require the CSRF token to match the cookie, request header, and stored session.

The API accepts either the access cookie or an `Authorization: Bearer` token. Browser clients use the cookie path. Administrator routes additionally require `role=admin`.

Credentialed CORS is restricted to the exact `FRONTEND_ORIGIN`. Responses add:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- restrictive camera, microphone, and geolocation permissions

## Identity Storage

`AuthStore` initializes a WAL-mode SQLite database at `AUTH_DB_PATH`. `AUTH_JWT_SECRET` supplies a managed signing key of at least 32 bytes in production; local development generates and persists one in `app_settings`.

| Table | Responsibility |
| --- | --- |
| `app_settings` | Persistent generated JWT signing secret |
| `users` | Identity, bcrypt hash, role, timestamps, active state |
| `sessions` | JWT ID, CSRF token, expiry, revocation, client metadata |
| `password_resets` | SHA-256 token digest, 30-minute expiry, one-time usage |
| `feedback` | User product feedback |
| `audit_logs` | Administrative changes |
| `frontend_logs` | Structured client diagnostics |
| `auth_logs` | Signup, login, and reset events |
| `ui_errors` | Client error boundary reports |
| `session_logs` | Session creation and revocation |
| `feedback_logs` | Feedback and schema request activity |

The schema request repository defaults to the same database and owns `schema_requests`. Existing databases are migrated in place with ownership, request kind, and attachment metadata columns.

Passwords require uppercase, lowercase, a number, and 8-128 characters. Standard sessions expire after 8 hours; Remember Me sessions expire after 30 days. Logout revokes one session. Password reset revokes every active session for the user.

## API Roles

Public:

```text
GET  /
GET  /health
GET  /legacy
POST /auth/signup
POST /auth/login
POST /auth/forgot-password
POST /auth/reset-password
```

Authenticated:

```text
GET  /auth/me
POST /auth/logout
POST /sql
GET  /metrics
GET  /schema/catalog
GET  /schema/relationships
GET  /schema/er
GET  /enterprise-schema
POST /schema-request
GET  /schema-requests
POST /feedback
POST /logs/frontend
```

Administrator:

```text
PATCH /schema-request/<id>/status
GET   /feedback
```

Normal users only receive their own schema requests. Administrators receive the full queue and can set `pending`, `approved`, `generated`, or `rejected`.

## Input Controls

- Auth fields are normalized and length constrained before storage.
- SQL requests are constrained by the existing read-only validator.
- Feedback is limited to 5,000 characters.
- CSV and JSON are the only accepted upload types.
- Uploads are capped at 1 MB and filenames are reduced to a basename.
- Attachment contents remain server-side; list responses expose only metadata and `has_attachment`.
- Login, signup, and password reset routes use a sliding-window IP limiter.

## Runtime Paths

| Path or variable | Purpose |
| --- | --- |
| `AUTH_DB_PATH` | Identity, sessions, feedback, and logs |
| `SCHEMA_REQUEST_DB_PATH` | Schema governance queue |
| `AGENT_FEEDBACK_DB_PATH` | Agent feedback and RL telemetry |
| `SCHEMA_FILE` | Active workbook schema |
| `backend/.cache/` | FAISS indexes |
| `RL_MODEL_PATH` | Optional PPO model |

## Semantic Planning

The planner resolves common SQL behavior from schema metadata and query structure:

- measure mapping for revenue, invoice amount, payment amount, project budget, and logged hours
- date grain and range mapping for month, quarter, week, today, due dates, end dates, payment dates, log dates, and deployment dates
- readable dimensions such as employee name, client name or tier, project name, priority, severity, payment method, industry, and environment
- role-aware foreign keys, including `assigned_to`, `reported_by`, and `deployed_by`
- multi-hop joins where the requested dimension is not directly attached to the measure table
- grouped counts, ranked aggregates, and partitioned running totals

Coverage treats aggregate measure columns as selected query output and does not require display labels from every joined table in an aggregate result.

## Metrics Contract

`GET /metrics` merges `agent_feedback` execution data with the nearest matching `agent_telemetry` event. Each trend point includes confidence, planner score, validator score, intent score, join score, validity, reward, execution time, query text, and timestamp. This lets the frontend calculate accurate range-scoped KPIs without converting reward into confidence.

## Deployment Boundaries

Production requires HTTPS, `APP_ENV=production`, `AUTH_JWT_SECRET`, the exact `FRONTEND_ORIGIN`, and secure cookies. Reset-token delivery must be integrated with an email provider; production does not expose tokens by default.

The built-in rate limiter is process-local, and SQLite targets local or single-node operation. Multi-worker or horizontally scaled deployment needs shared rate limiting and a shared transactional database.
