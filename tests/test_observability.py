from __future__ import annotations

from backend.observability import SQLCopilotObservability


def test_observability_records_safe_query_metrics(monkeypatch) -> None:
    """Metrics stay useful without enabling or exposing LangSmith content."""
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    observer = SQLCopilotObservability()

    trace = observer.begin_query("show all customer details", "sql")
    observer.finish_query(
        trace,
        {
            "sql": "SELECT * FROM clients;",
            "insights": {
                "valid": True,
                "confidence": 96,
                "source": "schema",
                "cache_hit": False,
                "provider_status": {"available": True},
            },
        },
    )

    assert observer.status()["langsmith_enabled"] is False
    content, status, content_type = observer.metrics()
    assert status == 200
    assert "text/plain" in content_type
    assert b"sql_copilot_query_requests_total" in content
    assert b'sql_copilot_validation_total{valid="true"}' in content


def test_metrics_token_rejects_anonymous_access(monkeypatch) -> None:
    monkeypatch.setenv("METRICS_BEARER_TOKEN", "metrics-secret")
    observer = SQLCopilotObservability()

    _, status, _ = observer.metrics()
    assert status == 401

    _, status, _ = observer.metrics("Bearer metrics-secret")
    assert status == 200
