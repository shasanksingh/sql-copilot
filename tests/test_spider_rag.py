from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

from backend.spider_rag import SpiderTextSqlRag


class _FakeGeneration:
    success = True
    provider = "nvidia"
    model = "openai/gpt-oss-20b"
    latency_ms = 3.0
    error_category = ""
    retry_count = 0
    data = {
        "sql": "SELECT name FROM singer ORDER BY age;",
        "explanation": "List singer names ordered by age.",
        "confidence": 84,
    }


class _FakeProvider:
    available = True

    def generate_structured(self, *_args, **_kwargs):
        return _FakeGeneration()

    def health_check(self, *, deep: bool = False) -> dict[str, object]:
        return {
            "provider": "nvidia",
            "model": "openai/gpt-oss-20b",
            "available": True,
            "configured": True,
            "status": "ready",
        }


class _UnavailableProvider:
    available = False

    def health_check(self, *, deep: bool = False) -> dict[str, object]:
        return {
            "provider": "local",
            "model": "deterministic",
            "available": False,
            "configured": False,
            "status": "fallback",
        }


def _write_spider_csv(path: Path) -> None:
    path.write_text(
        "text_query,sql_command\n"
        "\"List singer names ordered by age.\",\"SELECT name FROM singer ORDER BY age\"\n"
        "\"How many concerts are there?\",\"SELECT count(*) FROM concert\"\n",
        encoding="utf-8",
    )


def test_spider_rag_generates_generic_sql_with_provider(tmp_path: Path) -> None:
    csv_path = tmp_path / "spider.csv"
    _write_spider_csv(csv_path)
    rag = SpiderTextSqlRag(csv_path)

    answer = rag.answer("List singer names ordered by age", provider=_FakeProvider())

    assert answer is not None
    assert answer["sql"] == "SELECT name FROM singer ORDER BY age;"
    assert answer["llm_trace"]["provider"] == "nvidia"
    assert answer["llm_trace"]["fallback_used"] is False
    assert answer["examples"]


def test_generate_sql_uses_spider_only_without_enterprise_schema_anchor(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("backend.app")
    csv_path = tmp_path / "spider.csv"
    _write_spider_csv(csv_path)

    fake_result = SimpleNamespace(
        clarification_required=True,
        confidence=48,
        selected_tables=["clients"],
        selected_columns=["clients.client_name"],
        plan={"main_table": "clients", "selected_columns": [["clients", "client_name"]]},
        clarification_options=[],
    )
    fake_copilot = SimpleNamespace(run=lambda _query: fake_result)

    monkeypatch.setattr(app_module, "get_enterprise_copilot", lambda: fake_copilot)
    monkeypatch.setattr(app_module, "SPIDER_TEXT_SQL_FILE", csv_path)
    monkeypatch.setattr(app_module, "spider_text_sql_rag", None)
    monkeypatch.setattr(app_module, "LLM_PROVIDER_CLIENT", _UnavailableProvider())

    result = app_module.generate_sql(
        "List singer names ordered by age",
        app_module.SQLChatSession(),
    )

    assert result["insights"]["generic_sql"] is True
    assert result["insights"]["generic_mode"] == "spider_text_sql_rag"
    assert result["sql"].startswith("SELECT")


def test_generate_sql_keeps_schema_anchored_low_confidence_as_clarification(monkeypatch) -> None:
    app_module = importlib.import_module("backend.app")

    fake_result = SimpleNamespace(
        sql="I cannot generate reliable SQL",
        confidence=20,
        valid=False,
        validation="Confidence below threshold",
        clarification_required=True,
        clarification_options=["Map 'salary/pay/compensation' to a real schema column first."],
        intent={},
        entities={},
        selected_tables=["employees"],
        selected_columns=[],
        join_path=[],
        plan={"main_table": "employees"},
        optimizations=[],
        confidence_breakdown={},
        confidence_evidence=[],
        coverage_report={},
        agent_telemetry={},
        execution_trace={},
        runtime_metrics={},
        benchmark_record={},
        query_complexity="SIMPLE",
        confidence_band="LOW",
        provider_status={"provider": "nvidia", "model": "openai/gpt-oss-20b"},
        llm_trace={"provider": "nvidia", "model": "openai/gpt-oss-20b", "fallback_used": True},
        model_confidence=0,
        planner_confidence=20,
        validator_confidence=0,
        coverage_confidence=0,
        cache_hit=False,
    )
    fake_copilot = SimpleNamespace(run=lambda _query: fake_result)

    monkeypatch.setattr(app_module, "get_enterprise_copilot", lambda: fake_copilot)

    result = app_module.generate_sql(
        "Show employee salary",
        app_module.SQLChatSession(),
    )

    assert result["insights"].get("generic_sql") is not True
    assert result["insights"]["clarification_required"] is True
