# API Reference

The Flask backend serves the SQL copilot, authentication, schema governance, live metadata, metrics, feedback, and frontend diagnostics APIs.

## Public

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service metadata and endpoint index |
| `GET` | `/health` | Backend and loaded-schema health |
| `GET` | `/legacy` | Static legacy UI |
| `POST` | `/auth/signup` | Create user, session, and CSRF cookie |
| `POST` | `/auth/login` | Create session and CSRF cookie |
| `POST` | `/auth/forgot-password` | Create one-time reset token |
| `POST` | `/auth/reset-password` | Update password and revoke sessions |

## Authenticated

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/auth/me` | Current user and session expiry |
| `POST` | `/auth/logout` | Revoke current session |
| `POST` | `/sql` | Generate validated read-only SQL |
| `GET` | `/metrics` | Quality, latency, telemetry, and schema growth metrics |
| `GET` | `/runtime/config` | Provider and D-drive runtime path diagnostics |
| `GET` | `/schema/catalog` | Active workbook plus dynamic schema catalog |
| `GET` | `/schema/relationships` | Active relationship graph |
| `GET` | `/schema/er` | Mermaid ER diagram |
| `GET` | `/metadata/status` | Dynamic metadata refresh status and live tables |
| `GET` | `/enterprise-schema` | Synthetic enterprise-scale preview catalog |
| `POST` | `/schema-request` | Submit governed schema request or upload |
| `GET` | `/schema-requests` | User request queue; admins see all requests |
| `POST` | `/feedback` | Submit product feedback |
| `POST` | `/logs/frontend` | Store structured frontend diagnostics |

`/schema-request` accepts form or JSON fields such as `table_name`, `business_purpose`, `columns`, `relationships`, `sample_data`, and `business_rules`. File uploads support `.csv`, `.xlsx`, `.xls`, `.json`, `.sql`, and `.parquet` up to 5 MB.

## Administrator

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `PATCH` | `/schema-request/<id>/status` | Set `pending`, `approved`, `generated`, or `rejected` |
| `POST` | `/metadata/refresh` | Rebuild metadata indexes and reset planner state |
| `POST` | `/schema/studio/tables` | Create or upsert a dynamic live table |
| `PATCH` | `/schema/studio/tables/<table>` | Edit a dynamic live table |
| `DELETE` | `/schema/studio/tables/<table>` | Delete a dynamic live table |
| `POST` | `/schema/studio/apply-request/<id>` | Apply generated proposal to live metadata |
| `GET` | `/feedback` | Review all feedback |
| `GET` | `/diagnostics/provider` | Provider health and sanitized LLM metrics |

Unsafe authenticated methods require the `sql_copilot_csrf` cookie value in `X-CSRF-Token`.

`POST /sql` remains backward-compatible and now adds optional fields under `insights`: `query_complexity`, `confidence_band`, `provider_status`, `llm_trace`, `model_confidence`, `planner_confidence`, `validator_confidence`, `coverage_confidence`, `fallback_used`, `fallback_reason`, and `repair_attempts`. API keys are never returned.

## Schema Studio Payload

```json
{
  "name": "vendor_observability",
  "domain": "Dynamic Enterprise Schema",
  "purpose": "Track vendor telemetry and SLA health.",
  "owner": "admin@example.com",
  "tags": ["dynamic", "vendor"],
  "columns": [
    {"name": "vendor_observability_id", "data_type": "INTEGER", "is_pk": true},
    {"name": "vendor_name", "data_type": "TEXT"},
    {"name": "sla_score", "data_type": "DECIMAL(18,2)"}
  ],
  "relationships": [
    {"from_column": "supplier_id", "to_table": "suppliers", "to_column": "supplier_id"}
  ]
}
```

Live changes are persisted to `DYNAMIC_SCHEMA_FILE` and refresh retrieval, graph, planner, and dashboard-visible catalog state without a backend restart.
