from __future__ import annotations

import sqlite3

from rl.environment.sql_env import (
    SQLExecutionStats,
    compute_reward,
    ensure_feedback_table,
    execute_sql_for_stats,
    store_experience,
)


def test_reward_penalizes_dangerous_sql():
    reward = compute_reward(
        False,
        SQLExecutionStats(dangerous_operation=True, syntax_error=False),
    )
    assert reward <= -50


def test_reward_positive_for_valid_fast_non_empty_query():
    reward = compute_reward(
        True,
        SQLExecutionStats(execution_time=0.01, row_count=3, expected_results=True),
    )
    assert reward == 35


def test_feedback_table_persists_experience(tmp_path):
    db_path = tmp_path / "feedback.sqlite"
    ensure_feedback_table(db_path)
    store_experience(db_path, "count employees", "SELECT COUNT(*) FROM employees;", 35, 0.01, "Valid")

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT query, generated_sql, reward FROM agent_feedback").fetchone()

    assert row == ("count employees", "SELECT COUNT(*) FROM employees;", 35.0)


def test_execute_sql_for_stats_detects_empty_result(tmp_path):
    db_path = tmp_path / "sample.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()

    stats = execute_sql_for_stats(db_path, "SELECT * FROM employees;")

    assert stats.row_count == 0
    assert not stats.syntax_error

