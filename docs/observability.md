# Observability: LangSmith, Prometheus, and Grafana

SQL Copilot has two complementary observability paths:

- **LangSmith** traces the request lifecycle for evaluation and model debugging.
- **Prometheus and Grafana** expose operational trends: request rate, validation rate, cache use, confidence, and latency.

Both are optional. The SQL generation path remains available when neither service is configured.

## Privacy-first defaults

`LANGSMITH_REDACT_CONTENT=true` is the default. With this setting, traces record the request length, target language, timing, cache status, selected tables, validation status, confidence, and error type. They do not record the natural-language prompt or generated SQL.

Set `LANGSMITH_REDACT_CONTENT=false` only after confirming that prompts and SQL contain no restricted customer, employee, credential, or regulated data and that the LangSmith workspace is approved for that data class.

Secrets are backend-only. Never add `LANGSMITH_API_KEY`, `METRICS_BEARER_TOKEN`, or `GRAFANA_ADMIN_PASSWORD` to `NEXT_PUBLIC_*` variables.

## LangSmith setup

Add the following to the backend `.env` (locally) or `deployment/oracle/.env.production` (Oracle VM):

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_PROJECT=sql-copilot-production
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_REDACT_CONTENT=true
```

Restart the backend after changing the values. `GET /health` returns a sanitized `observability` object showing whether tracing is active; it never returns a key.

Each `POST /sql` request becomes a `sql-copilot.generate` chain run. The run captures high-level timing and validated result metadata, and links the plan/model result without exposing private content by default.

## Prometheus endpoint

`GET /observability/metrics` serves Prometheus exposition data. Set `METRICS_BEARER_TOKEN` to require `Authorization: Bearer <token>` for a direct request. On the Oracle bundle, Caddy explicitly blocks `/observability/metrics` from the public API hostname; Prometheus scrapes the Flask container over the private Docker network instead. `GET /metrics` remains the authenticated JSON feed used by the application dashboard.

Current metrics include:

| Metric | Meaning |
| --- | --- |
| `sql_copilot_query_requests_total` | Query outcomes by source and cache state. |
| `sql_copilot_query_duration_seconds` | End-to-end SQL generation latency histogram. |
| `sql_copilot_validation_total` | Reviewed SQL validation outcomes. |
| `sql_copilot_cache_total` | Cache hits and misses. |
| `sql_copilot_provider_available` | Current LLM provider availability. |
| `sql_copilot_response_confidence` | Confidence distribution for reviewed responses. |

Do not use prompt text, SQL strings, user IDs, emails, or raw error messages as Prometheus labels. They produce both sensitive telemetry and unbounded label cardinality.

## Grafana on the Oracle VM

The Oracle compose bundle contains an opt-in `observability` profile. It starts Prometheus and Grafana only when requested, so the API can continue to fit a small Always Free VM without the dashboard services.

```bash
cd /opt/sql-copilot/deployment/oracle
# Set a strong GRAFANA_ADMIN_PASSWORD in .env.production first.
sudo docker compose --profile observability up -d --build
sudo docker compose --profile observability ps
```

Grafana binds only to `127.0.0.1:3000` and Prometheus to `127.0.0.1:9090`. Use an SSH tunnel instead of exposing either service publicly:

```powershell
ssh -i "C:\path\to\oracle.key" -L 3000:127.0.0.1:3000 ubuntu@130.210.26.151
```

Then open `http://127.0.0.1:3000`, sign in with `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`, and open the provisioned **SQL Copilot / SQL Copilot Overview** dashboard.

The included dashboard shows request throughput, validation success, P95 latency, cache hit rate, and mean confidence. The Prometheus retention is 14 days by default; adjust this only after checking disk capacity.

## Operational checklist

1. Confirm `/health` reports the expected provider and observability state.
2. Run a reviewed SQL request, then verify `sql_copilot_query_requests_total` increases.
3. Ensure the Grafana dashboard receives the `sql-copilot-api` Prometheus target as `UP`.
4. Keep content redaction enabled unless a reviewed data policy permits richer traces.
5. Rotate LangSmith, Grafana, and metrics credentials using the VM environment file and restart the affected containers.
