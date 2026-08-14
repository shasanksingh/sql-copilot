# SQL Copilot Local Setup And Admin Guide

This is the single setup guide for starting SQL Copilot, fixing signup connection errors, creating an administrator, and opening the admin page.

## Why Signup Shows "Failed To Fetch"

`Failed to fetch` is a browser connection error. It occurs before the backend can validate your name, email, or password.

The common causes are:

1. The backend is not running on port `5000`.
2. The frontend was opened with `http://localhost:4000` while the backend allowed only `http://127.0.0.1:4000`.
3. `NEXT_PUBLIC_API_BASE_URL` points to the wrong backend URL.
4. The frontend or backend was not restarted after configuration changed.

Development mode now accepts both local frontend addresses:

```text
http://127.0.0.1:4000
http://localhost:4000
```

The frontend also displays the backend address when it cannot connect.

## D-Drive Setup

If C: is low on space, prepare and copy the project to D: before installing dependencies:

```powershell
.\scripts\prepare_d_drive.ps1 -CopyProject
cd D:\Projects\EnterpriseSQLCopilot
```

Use `.env.example` or `.vscode/launch.json` as the runtime template. The backend loads a root `.env` file before resolving runtime paths and provider settings. The backend honors `SQL_COPILOT_RUNTIME_DIR`, `SQL_COPILOT_SQLITE_DIR`, `SQL_COPILOT_CACHE_DIR`, `SQL_COPILOT_LOG_DIR`, `SQL_COPILOT_TEMP_DIR`, and `SQL_COPILOT_MODEL_DIR` so generated databases, logs, caches, temp files, FAISS indexes, and optional model artifacts stay under `D:\Projects\EnterpriseSQLCopilot` or `D:\AIModels`.

The app never downloads a local model automatically.

## One-Time Installation

Open PowerShell in the repository root:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd frontend
npm install
cd ..
```

## Start The Application

Use two PowerShell terminals.

Terminal 1, from the repository root:

```powershell
venv\Scripts\Activate.ps1
python -m uvicorn main:asgi_app --host 127.0.0.1 --port 5000
```

Terminal 2:

```powershell
cd frontend
npm run dev
```

Open one of these URLs:

```text
http://127.0.0.1:4000
http://localhost:4000
```

Do not open the HTML files directly from the filesystem.

## Verify The Backend

Open:

```text
http://127.0.0.1:5000/health
```

A working backend returns JSON containing:

```json
{
  "status": "ok"
}
```

PowerShell check:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/health
```

If this fails, start or restart Terminal 1 before trying signup again.

## Create Or Promote An Admin

From the repository root:

```powershell
venv\Scripts\Activate.ps1
python scripts\manage_admin.py --email singhshasank50@gmail.com --name "Shashank Singh"
```

Behavior:

- If the email already has a normal account, it is promoted to `admin`. Its password does not change.
- If the email does not exist, the command securely asks for a new password twice and creates an admin.
- The password must be 8-128 characters and contain uppercase, lowercase, and a number.
- The password is prompted privately and is not placed in PowerShell history.

The command can run while the local backend is active. If SQLite reports that the database is locked, stop the backend, run the command again, and then restart it:

```powershell
python -m uvicorn main:asgi_app --host 127.0.0.1 --port 5000
```

Sign out and sign in again if the account was already open in the browser.

## Open The Admin Page

1. Sign in with the administrator email and password.
2. Open:

```text
http://127.0.0.1:4000/admin/schema-requests
```

3. The sidebar also shows `Admin Review` for administrator accounts.

The page supports:

- reviewing all schema requests
- approving requests
- applying generated schema proposals to the live metadata overlay
- marking schemas generated
- rejecting requests
- reviewing user feedback

A normal user receives `403 Administrator access required` from admin APIs and does not see the admin navigation item.

## Schema Uploads And Live Metadata

Open `/data-model-studio` to submit table or schema requests. Uploads can be CSV, Excel, JSON, SQL DDL, or Parquet up to 5 MB. The backend infers column names, SQL types, primary keys, foreign-key hints, indexes, and preview rows before creating the generated proposal.

Administrators can also use `Apply Live`, `Apply proposal`, and `Refresh` from Data Model Studio. These actions update `DYNAMIC_SCHEMA_FILE` under `.runtime`, refresh BM25/FAISS metadata, reset the local planner instance, and update catalog/relationship/dashboard views without restarting the backend. Workbook tables remain read-only; only dynamic overlay tables can be deleted.

## Alternative Bootstrap Admin Method

You can provision an administrator when the backend starts:

```powershell
$env:BOOTSTRAP_ADMIN_NAME="Shashank Singh"
$env:BOOTSTRAP_ADMIN_EMAIL="singhshasank50@gmail.com"
$env:BOOTSTRAP_ADMIN_PASSWORD="ChooseAStrongPassword1"
python -m uvicorn main:asgi_app --host 127.0.0.1 --port 5000
```

If the account already exists, it is promoted and keeps its existing password. If it does not exist, it is created with `BOOTSTRAP_ADMIN_PASSWORD`.

The management script is preferred because it does not put a password in the environment or command history.

## Local Configuration

The frontend API default is:

```text
http://127.0.0.1:5000
```

To set it explicitly, create `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5000
```

## Optional NVIDIA GPT-OSS-20B

NVIDIA is server-side only. Put real credentials in your local `.env` or shell, never in frontend files:

```dotenv
SQL_COPILOT_LLM_PROVIDER=nvidia
NVIDIA_API_KEY=
NVIDIA_MODEL=openai/gpt-oss-20b
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
```

If the key is missing or the provider fails, the backend starts normally and `/sql` uses deterministic fallback. Check status with authenticated `GET /runtime/config`; administrators can inspect sanitized provider diagnostics at `GET /diagnostics/provider`.

Restart `npm run dev` after changing `.env.local`.

The local authentication database defaults to:

```text
.runtime/sqlite/sql_copilot.db
```

To use another database:

```powershell
$env:AUTH_DB_PATH="D:\Projects\EnterpriseSQLCopilot\.runtime\sqlite\sql_copilot.db"
python -m uvicorn main:asgi_app --host 127.0.0.1 --port 5000
```

Use the same `AUTH_DB_PATH` with `scripts\manage_admin.py`.

## Common Problems

### Dashboard Looks Flat Or Does Not Update

Run several different queries in `/copilot`, then open `/dashboard`. The dashboard refreshes every 10 seconds and the Refresh button forces an immediate reload. Its KPIs, chart, success badge, latency, and recent activity are calculated from the selected time range.

The chart uses real per-query confidence, planner, and validator scores. Older builds incorrectly converted the RL reward into a percentage, which made the chart appear fixed at 100%.

### Explainable AI Says No Join Is Required

This is expected for a single-table query such as `Revenue by payment method`. A joined query such as `Invoices due this week by client` displays the actual join path. If planning stops for a missing or ambiguous schema concept, the panel reports that clarification is required.

Useful verification queries:

```text
Invoice amount by month
Running hours by employee each month
Critical bugs by assignee
Invoices due this week by client
Deployments this week by environment
Sprints ending this month by project
```

### Cannot Connect To The SQL Copilot API

Check the backend:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/health
```

Check whether ports are listening:

```powershell
netstat -ano | Select-String ':4000\s|:5000\s'
```

Then restart both servers.

### Email Already Exists

Use `/login` instead of creating the account again. To make that account an administrator:

```powershell
python scripts\manage_admin.py --email your-email@example.com
```

### Admin Page Redirects To Login

The access cookie is missing or expired. Sign in again. Standard sessions last 8 hours; Remember Me sessions last 30 days.

### Admin Page Shows Access Denied

The account role is still `user`. Run the admin management command, restart the backend, then sign out and sign in again.

### CORS Error In Browser Console

For local development, use port `4000`. If a different frontend port is required:

```powershell
$env:FRONTEND_ORIGINS="http://127.0.0.1:4000,http://localhost:4000,http://127.0.0.1:4100"
python -m uvicorn main:asgi_app --host 127.0.0.1 --port 5000
```

Restart the backend after changing allowed origins.

### Forgot Password

In development, request a reset from `/forgot-password`. The reset token is returned to the UI because `AUTH_EXPOSE_RESET_TOKEN` defaults to enabled outside production.

Production requires an email delivery integration and must not expose reset tokens.

## Production Settings

At minimum, configure:

```powershell
$env:APP_ENV="production"
$env:FRONTEND_ORIGIN="https://sql.example.com"
$env:AUTH_JWT_SECRET="use-a-managed-random-secret-of-at-least-32-bytes"
$env:AUTH_COOKIE_SECURE="1"
$env:AUTH_EXPOSE_RESET_TOKEN="0"
```

Production does not automatically allow localhost. Use HTTPS and set the exact deployed frontend origin.

The built-in SQLite database and in-memory rate limiter target local or single-node deployments. Multi-instance production should use a shared transactional database and shared rate-limit store.
