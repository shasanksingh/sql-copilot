# SQL Copilot

> Turn business questions into planned, validated, and explainable read-only SQL.

SQL Copilot is a local-first, schema-aware analytics workspace for teams that need more control than a single text-to-SQL prompt. It combines deterministic intent planning, entity extraction, role-aware schema linking, guarded SQL generation, coverage checks, and confidence scoring with a responsive enterprise interface.

The system can run without a remote LLM by using its deterministic agent pipeline. When a remote model is enabled, the same validation and governance boundaries remain in place.

<p align="center">
  <a href="https://sql-copilot-puce.vercel.app">
    <img src="https://img.shields.io/badge/Live%20Workspace-Open-2563EB?style=for-the-badge&logo=vercel&logoColor=white" alt="Open SQL Copilot" />
  </a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI backend" />
  <img src="https://img.shields.io/badge/Next.js-15-111827?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js 15" />
</p>

## Product At A Glance

| Concern | SQL Copilot approach |
| --- | --- |
| Natural-language analytics | Intent, entities, measures, dimensions, and time windows are planned before SQL generation. |
| Schema grounding | Tables, columns, relationships, and role-aware joins are linked against the active schema workbook. |
| Safety | Only one read-only `SELECT` statement is accepted; write, DDL, execution, and privilege operations are blocked. |
| Explainability | Planner steps, validation coverage, confidence signals, join status, and optimization guidance remain inspectable. |
| Deployment boundary | Local deterministic mode works without remote model credentials; production settings add secure auth and controlled origins. |

For local startup, signup troubleshooting, and administrator access, use [docs/local_setup_and_admin.md](docs/local_setup_and_admin.md). For endpoint details, use [docs/api_reference.md](docs/api_reference.md). For NVIDIA GPT-OSS-20B setup and evaluation, see [docs/nvidia_gpt_oss_20b.md](docs/nvidia_gpt_oss_20b.md), [docs/enterprise_query_planning.md](docs/enterprise_query_planning.md), and [docs/confidence_and_evaluation.md](docs/confidence_and_evaluation.md).

## Architecture

```text
.
|-- agentic/                  # intent, linking, planning, coverage, confidence
|-- backend/
|   |-- app.py                # Flask API, auth middleware, SQL orchestration
|   |-- auth.py               # users, sessions, resets, feedback, audit logs
|   |-- synthetic_enterprise_data.py
|   |-- data/RAG_DOC.xlsx     # default schema workbook
|   `-- requirements.txt
|-- frontend/                 # Next.js 15 and React 19 application
|-- rl/                       # optional PPO feedback and evaluation modules
|-- tests/                    # Python unit and API integration tests
|-- tools/                    # benchmark and metric utilities
|-- scripts/                  # benchmark analysis helpers
|-- docs/                     # architecture and setup documentation
`-- main.py                   # compatibility ASGI export
```

The SQL path is:

```text
authenticated request -> intent -> entities -> schema linking -> planner
                      -> query plan validation -> optional NVIDIA GPT-OSS-20B
                      -> SQL validation and repair -> coverage
                      -> confidence gate -> clarification or response
```

## Requirements

- Python 3.10 or newer
- Node.js 20.19 or newer
- npm

Remote LLM access is optional. Without remote credentials, the backend uses the local deterministic agent pipeline.

## D-Drive Runtime Layout

For machines where C: is low on space, prepare the D-drive layout before installing dependencies:

```powershell
.\scripts\prepare_d_drive.ps1 -CopyProject
cd D:\Projects\EnterpriseSQLCopilot
```

The backend now derives generated runtime data from `SQL_COPILOT_PROJECT_ROOT`, `SQL_COPILOT_RUNTIME_DIR`, and `SQL_COPILOT_MODEL_DIR`. Use the included `.env.example` or `.vscode/launch.json` values to keep SQLite files, FAISS indexes, logs, temp files, pip/npm caches, HuggingFace caches, Torch caches, and optional model artifacts under `D:\Projects\EnterpriseSQLCopilot` or `D:\AIModels`.

No local model is downloaded automatically. If a provider requires local inference, download confirmation and a `D:\AIModels` target should be handled before installing model files.

## Quick Start

From the repository root:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python -m uvicorn main:asgi_app --host 127.0.0.1 --port 5000
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:4000` and create an account at `/signup`.

To provision the first administrator, set these variables before starting the API:

```powershell
$env:BOOTSTRAP_ADMIN_NAME="SQL Copilot Admin"
$env:BOOTSTRAP_ADMIN_EMAIL="admin@example.com"
$env:BOOTSTRAP_ADMIN_PASSWORD="ChangeThis1!"
```

The account is created only when the email does not already exist.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:5000` | Frontend API base URL |
| `APP_ENV` | `development` | Use `production` to enable production auth defaults |
| `FRONTEND_ORIGIN` | `http://127.0.0.1:4000` | Exact credentialed CORS origin |
| `AUTH_DB_PATH` | runtime SQLite `sql_copilot.db` | Users, sessions, resets, feedback, and logs |
| `AUTH_JWT_SECRET` | generated and persisted locally | Managed JWT signing secret, at least 32 bytes |
| `AUTH_COOKIE_SECURE` | enabled in production | Marks auth and CSRF cookies secure |
| `AUTH_EXPOSE_RESET_TOKEN` | enabled outside production | Returns reset token for local development |
| `BOOTSTRAP_ADMIN_NAME` | `SQL Copilot Admin` | Initial administrator display name |
| `BOOTSTRAP_ADMIN_EMAIL` | empty | Initial administrator email |
| `BOOTSTRAP_ADMIN_PASSWORD` | empty | Initial administrator password |
| `SQL_COPILOT_PROJECT_ROOT` | repository root | Base root for relocatable project paths |
| `SQL_COPILOT_RUNTIME_DIR` | `.runtime` under project root | Generated runtime files |
| `SQL_COPILOT_CACHE_DIR` | runtime cache directory | FAISS, pip, npm, and process caches |
| `SQL_COPILOT_SQLITE_DIR` | runtime SQLite directory | Local SQLite databases |
| `SQL_COPILOT_LOG_DIR` | runtime logs directory | Agent, planner, benchmark, and API logs |
| `SQL_COPILOT_TEMP_DIR` | runtime temp directory | Temporary files via `TEMP` and `TMP` |
| `SQL_COPILOT_MODEL_DIR` | runtime model directory | Optional model/checkpoint root; use `D:\AIModels` on low-C systems |
| `SCHEMA_REQUEST_DB_PATH` | same as `AUTH_DB_PATH` | Schema request queue database |
| `SCHEMA_FILE` | `backend/data/RAG_DOC.xlsx` | Excel schema workbook |
| `DYNAMIC_SCHEMA_FILE` | runtime `dynamic_schema.json` | Live Schema Studio overlay persisted outside the workbook |
| `SQL_COPILOT_LLM_PROVIDER` | `nvidia` | `nvidia`, custom OpenAI-compatible `openai`, `ollama`, or `local` |
| `SQL_COPILOT_REMOTE_LLM` | enabled | Enables remote/provider chat when credentials or Ollama endpoint exist |
| `SQL_COPILOT_LLM_BASE_URL` | provider URL | OpenAI-compatible API base URL |
| `SQL_COPILOT_CHAT_MODEL` | provider default | Chat model name |
| `NVIDIA_API_KEY` | empty | NVIDIA provider key, server-side only |
| `NVIDIA_MODEL` | `openai/gpt-oss-20b` | NVIDIA chat model |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | NVIDIA OpenAI-compatible base URL |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE` | empty | Optional custom-provider aliases |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_TEMPERATURE`, `MAX_GENERATION_RETRIES` | provider defaults | Provider timeout, adapter retries, temperature, and SQL repair attempts |
| `CONFIDENCE_LOW_THRESHOLD`, `CONFIDENCE_HIGH_THRESHOLD` | `75`, `90` | LOW/MEDIUM/HIGH confidence band thresholds |
| `SQL_COPILOT_EMBEDDING_MODEL` | provider default | Embedding model name for supported providers |
| `AGENT_FEEDBACK_DB_PATH` | runtime SQLite `sql_agent_feedback.sqlite` | Agent feedback and telemetry |
| `RL_ENABLED` | `1` | Enables RL integration when dependencies exist |
| `RL_MODEL_PATH` | model root `rl/sql_ppo_agent.zip` | PPO model location |
| `ENTERPRISE_SYNTHETIC_TABLES` | `180` | Virtual enterprise catalog size |
| `PORT` | `5000` | Direct `backend/app.py` startup port |

Do not commit `.env` files, credentials, generated databases, test reports, or model artifacts.

## Authentication And Security

- Passwords are hashed with bcrypt and require 8-128 characters, uppercase, lowercase, and a number.
- JWTs use HS256, include a unique session ID and expiration, and are stored in HTTP-only `SameSite=Lax` cookies.
- Sessions are checked against SQLite on every protected request and can be revoked on logout or password reset.
- Standard sessions last 8 hours; Remember Me sessions last 30 days.
- Unsafe authenticated requests require matching CSRF cookie, header, and server-side session values.
- Login, signup, forgot-password, and reset-password routes are rate limited.
- CORS accepts only `FRONTEND_ORIGIN` with credentials.
- API responses include clickjacking, MIME-sniffing, referrer, and permissions security headers.
- Schema request status updates and feedback review require the `admin` role.

The SQLite auth database contains `users`, `sessions`, `password_resets`, `feedback`, `schema_requests`, `audit_logs`, `frontend_logs`, `auth_logs`, `ui_errors`, `session_logs`, and `feedback_logs`.

## API

Public endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | API metadata |
| `GET` | `/health` | API and loaded-schema health |
| `POST` | `/auth/signup` | Create account and session |
| `POST` | `/auth/login` | Create session |
| `POST` | `/auth/forgot-password` | Create one-time 30-minute reset token |
| `POST` | `/auth/reset-password` | Replace password and revoke active sessions |
| `GET` | `/legacy` | Legacy static UI reference |

Authenticated endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/auth/me` | Validate and return the current session |
| `POST` | `/auth/logout` | Revoke the current session |
| `POST` | `/sql` | Generate and validate SQL from `{"query": "..."}` |
| `GET` | `/metrics` | KPI, telemetry, and schema-growth metrics |
| `GET` | `/schema/catalog` | Active workbook schema catalog |
| `GET` | `/schema/relationships` | Active foreign-key relationships |
| `GET` | `/schema/er` | Mermaid ER diagram |
| `GET` | `/metadata/status` | Dynamic metadata refresh status and live tables |
| `GET` | `/enterprise-schema` | Synthetic enterprise-scale catalog |
| `POST` | `/schema-request` | Submit table, schema, business, CSV, Excel, JSON, SQL DDL, or Parquet request |
| `GET` | `/schema-requests` | List the user's requests; admins see all |
| `GET` | `/runtime/config` | Authenticated provider and runtime-path diagnostics |
| `POST` | `/feedback` | Submit product feedback |
| `POST` | `/logs/frontend` | Store structured frontend diagnostics |

Administrator endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `PATCH` | `/schema-request/<id>/status` | Approve, generate, reject, or reset a request |
| `POST` | `/metadata/refresh` | Rebuild BM25/FAISS metadata and reset planner state |
| `POST` | `/schema/studio/tables` | Create or upsert a dynamic live table |
| `PATCH` | `/schema/studio/tables/<table>` | Edit a dynamic live table |
| `DELETE` | `/schema/studio/tables/<table>` | Delete a dynamic live table |
| `POST` | `/schema/studio/apply-request/<id>` | Apply a generated schema proposal without restart |
| `GET` | `/feedback` | Review all feedback |

The SQL validator accepts one read-only `SELECT` statement. It blocks write, DDL, execution, and privilege operations including `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `MERGE`, `EXEC`, `GRANT`, and `REVOKE`.

## Frontend

The protected workspace includes:

- Responsive SQL Copilot chat with stable sticky composer, suggestion strip, auto-scroll, persistent history, search, export, delete, and highlighted SQL wrapping
- Mixed query suggestions that keep the full cross-domain prompt set and prepend at most two context-aware prompts
- Planner Accuracy, SQL Accuracy, Validator Precision, and Confidence Reliability dashboard KPIs
- Live, 10-second dashboard refresh with Day, Week, Month, Quarter, and Year range-specific KPIs, activity, and trends
- Interactive Intent-to-SQL planner graph
- Searchable schema and column explorer with relationships and join recommendations
- Original/optimized SQL comparison, execution plan, cost reduction, and index suggestions
- Expandable explainability timeline and runtime trace
- Explainable join status that distinguishes single-table plans, completed join plans, and clarification stops
- Schema request and feedback portal with CSV, Excel, JSON, SQL DDL, and Parquet inference
- Live Schema Studio controls for admin apply, refresh, proposal promotion, and dynamic table deletion
- Administrator request and feedback review with proposal apply action
- Persistent desktop sidebar, mobile drawer, theme, and authenticated user controls

The Query Execution page is a preview and export workflow. The backend intentionally does not expose arbitrary database execution.

## Semantic Query Coverage

The deterministic planner applies reusable schema rules instead of relying on exact prompt text. Supported patterns include:

- time-bucketed measures such as invoice amount by month, revenue by quarter, and project budget by period
- running totals partitioned by a business dimension, such as running hours by employee each month
- date windows such as tasks due this week, invoices due this month, projects ending this week, and recent deployments
- readable related dimensions such as assignee name, client tier, client name, project name, department, severity, priority, and environment
- grouped counts and ranked measures across employees, clients, projects, tasks, bugs, invoices, payments, sprints, deployments, and time logs

Role-aware joins prefer the requested relationship. For example, an assignee query uses `assigned_to`, not `reported_by`.

## Validation

Run Python tests and compilation:

```powershell
python -m pytest -q
python -m py_compile backend\auth.py backend\app.py backend\synthetic_enterprise_data.py
```

Run frontend checks:

```powershell
cd frontend
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

The Playwright suite starts the production frontend and backend, then verifies auth redirects, signup, live SQL generation, desktop chat stability, sidebar collapse, and mobile viewport behavior.

## Production Boundaries

- Run behind HTTPS and a reverse proxy, set `APP_ENV=production`, provide `AUTH_JWT_SECRET`, set the exact `FRONTEND_ORIGIN`, and keep secure cookies enabled.
- Reset-token email delivery is not included; production suppresses reset tokens from API responses.
- The built-in rate limiter is process-local. Multi-worker deployments need a shared rate-limit store.
- SQLite is suitable for local and single-node deployments. High concurrency or horizontal scaling needs a shared transactional database.
- The backend validates generated SQL but does not provide a general-purpose execution endpoint.

## Schema Workbook

The first worksheet must contain:

- `Table Name`
- `Column Name`
- `Data Type`
- `Description`
- `What this table stores`

An optional `foreign_keys` worksheet may define:

- `from_table`
- `from_column`
- `to_table`
- `to_column`

When the foreign-key worksheet is absent, the backend attempts conservative relationship inference from schema descriptions.

## Dynamic Metadata Engine

Schema Studio writes approved live schema changes to `DYNAMIC_SCHEMA_FILE` under the runtime directory. Each create, update, delete, or proposal apply refreshes in-memory schema maps, table and column documents, BM25 retrieval, FAISS indexes when embeddings are enabled, the relationship graph, planner hints, and the local enterprise copilot instance. Excel-backed workbook tables are read-only; dynamic tables are an overlay and can be removed without changing `backend/data/RAG_DOC.xlsx`.
