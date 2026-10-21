# Oracle Cloud VM deployment

This bundle runs the Flask API on an Oracle Cloud Always Free VM and keeps SQLite, runtime secrets, and generated data on the VM's persistent block volume. Cloudflare continues to host the Next.js frontend and proxies API traffic through the existing Worker so authentication cookies stay same-origin.

## One-time VM requirements

1. Create an Always Free Ubuntu VM with a public IP and attach persistent block storage.
2. Open inbound TCP `80` and `443` in the Oracle VCN security list and the VM firewall.
3. Point `api.example.com` to the VM public IP. Replace the hostname in `Caddyfile` before enabling Caddy.
4. Install Docker Engine, Docker Compose, and Caddy on the VM.
5. Clone this repository under `/opt/sql-copilot`.

## Configure and start Flask

```bash
cd /opt/sql-copilot/deployment/oracle
cp .env.production.example .env.production
chmod 600 .env.production
# Set AUTH_JWT_SECRET and NVIDIA_API_KEY in .env.production using a secure editor.
docker compose -f compose.yml up -d --build
curl http://127.0.0.1:8000/health
```

Install the `Caddyfile` at `/etc/caddy/Caddyfile`, replace `api.example.com`, then reload Caddy. Caddy obtains and renews the TLS certificate automatically once DNS and ports 80/443 are reachable.

## Connect Cloudflare

After the Flask health endpoint responds at `https://api.example.com/health`:

1. In the Cloudflare Worker named `sql-copilot-frontend`, set the `API_ORIGIN` secret to `https://api.example.com`.
2. Build the frontend with `frontend/.env.production` copied from its example; it uses `https://sql-copilot-frontend.singhshasank50.workers.dev` as `NEXT_PUBLIC_API_BASE_URL`.
3. Deploy the Worker. Requests for `/auth/*`, `/sql`, schema, metadata, metrics, runtime, and diagnostics routes are then forwarded to Flask.

The backend's `FRONTEND_ORIGIN` and `FRONTEND_ORIGINS` must include the exact Worker URL shown in `.env.production.example`. If a custom Worker domain is added later, append it to `FRONTEND_ORIGINS` and rebuild the frontend with the custom URL.

## Validate

```bash
curl -fsS https://api.example.com/health
curl -fsS https://sql-copilot-frontend.singhshasank50.workers.dev/health
```

The second command travels through the Worker proxy. Then create a test account in the deployed UI and run one SQL prompt; the Settings page should report the NVIDIA provider as ready.