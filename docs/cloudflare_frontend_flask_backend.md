# Cloudflare frontend, Oracle Flask backend, and NVIDIA

The Cloudflare Worker hosts the Next.js frontend and proxies API routes to Flask on an Oracle Cloud Always Free VM. This keeps browser requests and authentication cookies on one public origin while Flask receives the Worker URL as the request origin for its CORS allowlist.

## Configuration layout

| Location | Purpose | Commit status |
| --- | --- | --- |
| `.runtime/secrets/provider.env` | Active local NVIDIA configuration | Ignored |
| `.env` | Optional local backend override loaded first | Ignored / absent in this checkout |
| `frontend/.env.production` | Build-time Worker URL for the browser | Ignored |
| `deployment/oracle/.env.production` | Oracle Flask server secrets and production settings | Ignored |

Use the corresponding `*.example` file as a template. Never commit `NVIDIA_API_KEY` or `AUTH_JWT_SECRET`.

## Frontend configuration

Before deploying the Worker, copy `frontend/.env.production.example` to `frontend/.env.production`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://sql-copilot-frontend.singhshasank50.workers.dev
```

This URL is embedded into the browser bundle at build time. The Worker accepts API requests at that same origin, then forwards them to its `API_ORIGIN` secret. A Worker address with `:5000` is invalid.

## Flask CORS configuration

On the Oracle VM, set the following in `deployment/oracle/.env.production`:

```dotenv
APP_ENV=production
FRONTEND_ORIGIN=https://sql-copilot-frontend.singhshasank50.workers.dev
FRONTEND_ORIGINS=https://sql-copilot-frontend.singhshasank50.workers.dev
AUTH_COOKIE_SECURE=1
AUTH_JWT_SECRET=<at-least-32-byte-secret>
NVIDIA_API_KEY=<nvidia-api-key>
SQL_COPILOT_REMOTE_LLM=1
```

Add any future custom frontend domain as an additional comma-separated `FRONTEND_ORIGINS` value. The Flask app already permits credentialed CORS only for this allowlist.

## Oracle VM deployment

Use the Docker, Caddy, and persistent runtime setup in [the Oracle deployment bundle](../deployment/oracle/README.md). The VM needs a public HTTPS name (for example `api.example.com`) before its URL can be stored in the Worker `API_ORIGIN` secret.

## NVIDIA verification

The local provider check succeeded with the configured NVIDIA key, model `openai/gpt-oss-20b`, and `https://integrate.api.nvidia.com/v1`. The safe health request completed in roughly 18 seconds with status `ok`.