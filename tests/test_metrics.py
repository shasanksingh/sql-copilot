from __future__ import annotations

import importlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


class _FakeProvider:
    def metrics(self) -> dict[str, object]:
        return {
            "success_rate": 0,
            "fallback_rate": 0,
            "repair_attempts": 0,
        }

    def health_check(self, *, deep: bool = False) -> dict[str, object]:
        return {
            "provider": "nvidia",
            "model": "openai/gpt-oss-20b",
            "configured": True,
            "available": True,
            "status": "ready",
        }


def test_feedback_metrics_filters_selected_range(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("backend.app")
    db_path = tmp_path / "feedback.sqlite"
    app_module.ensure_feedback_table(db_path)
    now = datetime.now(timezone.utc)

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO agent_feedback (
                query, generated_sql, reward, execution_time, validation_status, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("old", "SELECT 1;", 1, 0.1, "Valid", (now - timedelta(days=45)).isoformat()),
                ("recent", "SELECT 2;", 1, 0.2, "Valid", (now - timedelta(days=2)).isoformat()),
            ],
        )

    monkeypatch.setattr(app_module, "FEEDBACK_DB_PATH", str(db_path))
    monkeypatch.setattr(app_module, "LLM_PROVIDER_CLIENT", _FakeProvider())

    metrics = app_module.load_feedback_metrics(days=30, range_key="month")

    assert metrics["range"]["key"] == "month"
    assert metrics["total"] == 1
    assert [point["query"] for point in metrics["trend"]] == ["recent"]
