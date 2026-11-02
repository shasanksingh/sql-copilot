"""Optional LangSmith tracing and Prometheus metrics for SQL Copilot.

The application must keep working when no observability vendor is configured.
LangSmith is therefore opt-in, and the default trace payload contains only
operational metadata rather than the user's prompt or generated SQL.
"""

from __future__ import annotations

import hmac
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - dependency availability is covered in deployment
    from langsmith import Client as LangSmithClient
except ImportError:  # pragma: no cover
    LangSmithClient = None

try:  # pragma: no cover - dependency availability is covered in deployment
    from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
except ImportError:  # pragma: no cover
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"
    CollectorRegistry = Counter = Gauge = Histogram = None
    generate_latest = None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_label(value: object, default: str = "unknown") -> str:
    text = str(value or default).strip().lower()
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in text)
    return (cleaned[:64] or default)


@dataclass
class QueryTrace:
    run_id: str
    started_at: float
    query: str
    target_language: str
    langsmith_started: bool = False


class SQLCopilotObservability:
    """Small, failure-isolated adapter for application-level observability."""

    def __init__(self) -> None:
        self.redact_content = _truthy(os.getenv("LANGSMITH_REDACT_CONTENT", "1"))
        self.project = os.getenv("LANGSMITH_PROJECT", "sql-copilot")
        self.metrics_token = os.getenv("METRICS_BEARER_TOKEN", "")
        self.langsmith_enabled = bool(
            _truthy(os.getenv("LANGSMITH_TRACING"))
            and os.getenv("LANGSMITH_API_KEY")
            and LangSmithClient is not None
        )
        self.client: Any | None = None
        if self.langsmith_enabled:
            try:
                endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").rstrip("/")
                self.client = LangSmithClient(api_url=endpoint, api_key=os.getenv("LANGSMITH_API_KEY"))
            except Exception:
                # Observability must never stop a query from being handled.
                self.client = None
                self.langsmith_enabled = False

        self.registry = CollectorRegistry(auto_describe=True) if CollectorRegistry else None
        if self.registry and Counter and Histogram and Gauge:
            self.query_requests = Counter(
                "sql_copilot_query_requests_total",
                "SQL generation requests handled by outcome, source, and cache state.",
                ("outcome", "source", "cache_hit"),
                registry=self.registry,
            )
            self.query_duration = Histogram(
                "sql_copilot_query_duration_seconds",
                "End-to-end SQL generation duration.",
                ("outcome", "source"),
                registry=self.registry,
                buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 80),
            )
            self.validation_total = Counter(
                "sql_copilot_validation_total",
                "SQL validation outcomes.",
                ("valid",),
                registry=self.registry,
            )
            self.cache_total = Counter(
                "sql_copilot_cache_total",
                "Reviewed-response cache outcomes.",
                ("result",),
                registry=self.registry,
            )
            self.provider_status = Gauge(
                "sql_copilot_provider_available",
                "Whether the configured LLM provider is available (1) or unavailable (0).",
                registry=self.registry,
            )
            self.confidence = Histogram(
                "sql_copilot_response_confidence",
                "Validated SQL confidence score.",
                buckets=(0, 25, 50, 70, 80, 90, 95, 100),
                registry=self.registry,
            )
        else:
            self.query_requests = self.query_duration = self.validation_total = None
            self.cache_total = self.provider_status = self.confidence = None

    def begin_query(self, query: str, target_language: str) -> QueryTrace:
        trace = QueryTrace(
            run_id=str(uuid.uuid4()),
            started_at=time.perf_counter(),
            query=query,
            target_language=target_language,
        )
        if not self.client:
            return trace
        try:
            inputs: dict[str, object] = {
                "target_language": target_language,
                "query_length": len(query),
            }
            if not self.redact_content:
                inputs["query"] = query[:4_000]
            self.client.create_run(
                id=trace.run_id,
                name="sql-copilot.generate",
                run_type="chain",
                inputs=inputs,
                project_name=self.project,
                extra={"metadata": {"component": "sql-api", "content_redacted": self.redact_content}},
            )
            trace.langsmith_started = True
        except Exception:
            trace.langsmith_started = False
        return trace

    def finish_query(
        self,
        trace: QueryTrace,
        result: dict[str, object] | None = None,
        error: BaseException | None = None,
    ) -> None:
        elapsed = max(0.0, time.perf_counter() - trace.started_at)
        insights = dict((result or {}).get("insights") or {})
        valid = bool(insights.get("valid")) and error is None
        source = _safe_label(insights.get("source"), "unknown")
        cache_hit = bool(insights.get("cache_hit"))
        outcome = "success" if valid else "error"

        if self.query_requests:
            self.query_requests.labels(outcome=outcome, source=source, cache_hit=str(cache_hit).lower()).inc()
            self.query_duration.labels(outcome=outcome, source=source).observe(elapsed)
            self.validation_total.labels(valid=str(valid).lower()).inc()
            self.cache_total.labels(result="hit" if cache_hit else "miss").inc()
            self.confidence.observe(float(insights.get("confidence") or 0))
            provider = dict(insights.get("provider_status") or {})
            self.provider_status.set(1 if provider.get("available") else 0)

        if not self.client or not trace.langsmith_started:
            return
        try:
            outputs: dict[str, object] = {
                "valid": valid,
                "confidence": insights.get("confidence"),
                "selected_tables": list(insights.get("selected_tables") or insights.get("tables") or []),
                "cache_hit": cache_hit,
                "target_language": insights.get("target_language", trace.target_language),
                "duration_ms": round(elapsed * 1000, 2),
            }
            if error is not None:
                outputs["error_type"] = type(error).__name__
            elif not self.redact_content:
                outputs["sql"] = str((result or {}).get("sql") or "")[:8_000]
            self.client.update_run(
                trace.run_id,
                outputs=outputs,
                error=str(error)[:500] if error is not None else None,
            )
        except Exception:
            pass

    def metrics(self, authorization: str = "") -> tuple[bytes | str, int, str]:
        if self.metrics_token:
            supplied = authorization.removeprefix("Bearer ").strip()
            if not hmac.compare_digest(supplied, self.metrics_token):
                return "Unauthorized", 401, "text/plain; charset=utf-8"
        if not self.registry or not generate_latest:
            return "Prometheus metrics dependency is not installed.", 503, "text/plain; charset=utf-8"
        return generate_latest(self.registry), 200, CONTENT_TYPE_LATEST

    def status(self) -> dict[str, object]:
        return {
            "langsmith_enabled": self.langsmith_enabled,
            "langsmith_project": self.project if self.langsmith_enabled else "",
            "content_redacted": self.redact_content,
            "metrics_protected": bool(self.metrics_token),
        }
