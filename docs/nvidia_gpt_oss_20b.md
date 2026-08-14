# NVIDIA GPT-OSS-20B Provider

NVIDIA GPT-OSS-20B is supported as an optional OpenAI-compatible server-side provider. The deterministic planner, schema graph, SQL validator, coverage agents, and confidence coordinator remain authoritative.

## Environment

Use a root `.env` or shell variables. The backend loads `.env` before provider initialization. Do not put real keys in source files.

```dotenv
SQL_COPILOT_LLM_PROVIDER=nvidia
NVIDIA_API_KEY=
NVIDIA_MODEL=openai/gpt-oss-20b
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=2
LLM_TEMPERATURE=0
LLM_TOP_P=1
LLM_MAX_TOKENS=4096
MAX_GENERATION_RETRIES=3
```

The generic aliases `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, and `LLM_API_BASE` are reserved for intentionally configured custom OpenAI-compatible providers. NVIDIA should use `NVIDIA_API_KEY`, `NVIDIA_MODEL`, and `NVIDIA_BASE_URL`.

The NVIDIA adapter uses the installed OpenAI Python SDK chat-completions API with:

```python
OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.environ["NVIDIA_API_KEY"])
client.chat.completions.create(model="openai/gpt-oss-20b", messages=[...])
```

Only `message.content` is parsed as structured JSON. Provider-specific reasoning fields are not logged or exposed to users.

## Fallback

Startup does not fail when the key is absent, invalid, rate limited, timed out, or unavailable. The provider layer categorizes the failure, records sanitized metrics, and the SQL path falls back to deterministic generation.

No API key, authorization header, credential, password, or session secret is sent to the frontend, logs, diagnostics, SQLite telemetry, or benchmark reports.

## Runtime Status

- `GET /health` includes shallow provider status.
- `GET /runtime/config` includes provider configuration and D-drive runtime paths.
- `GET /diagnostics/provider` is admin-only and can optionally run `?deep=1`.
- `GET /metrics` includes provider request count, success rate, fallback rate, p50/p95 latency, repair attempts, token usage when provided by the adapter, and sanitized error categories.

## Model Role

The model receives only a bounded context:

- validated query plan IR
- selected tables
- allowed columns and types
- relevant relationships
- business terms, measures, and filters
- deterministic SQL candidate

The model returns structured JSON for plan review, SQL generation, SQL repair, and SQL critique. Generated SQL is accepted only after planner-alignment checks and the deterministic SQL validator approve it.
