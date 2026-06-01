from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover - exercised when optional deps are absent
    gym = None
    spaces = None


ACTION_REGENERATE_SQL = 0
ACTION_MODIFY_JOIN_STRATEGY = 1
ACTION_MODIFY_FILTER_CONDITIONS = 2
ACTION_MODIFY_AGGREGATION_STRATEGY = 3
ACTION_KEEP_CURRENT_QUERY = 4

ACTION_NAMES = {
    ACTION_REGENERATE_SQL: "regenerate_sql",
    ACTION_MODIFY_JOIN_STRATEGY: "modify_join_strategy",
    ACTION_MODIFY_FILTER_CONDITIONS: "modify_filter_conditions",
    ACTION_MODIFY_AGGREGATION_STRATEGY: "modify_aggregation_strategy",
    ACTION_KEEP_CURRENT_QUERY: "keep_current_query",
}

DANGEROUS_SQL_PATTERN = re.compile(
    r"\b(delete|drop|update|insert|alter|truncate|grant|revoke|attach|detach|pragma|vacuum)\b",
    re.IGNORECASE,
)


@dataclass
class SQLExecutionStats:
    execution_time: float = 0.0
    row_count: int = 0
    syntax_error: bool = False
    invalid_table: bool = False
    hallucinated_column: bool = False
    dangerous_operation: bool = False
    expected_results: bool = False
    error_message: str = ""


@dataclass
class SQLState:
    user_query: str = ""
    schema_context: str = ""
    generated_sql: str = ""
    execution_stats: SQLExecutionStats = field(default_factory=SQLExecutionStats)
    validation_result: bool = False
    validation_message: str = ""


def ensure_feedback_table(db_path: str | Path | None) -> None:
    if not db_path:
        return
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                generated_sql TEXT NOT NULL,
                reward REAL NOT NULL,
                execution_time REAL NOT NULL,
                validation_status TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        conn.commit()


def store_experience(
    db_path: str | Path | None,
    query: str,
    generated_sql: str,
    reward: float,
    execution_time: float,
    validation_status: str,
) -> None:
    if not db_path:
        return
    ensure_feedback_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO agent_feedback (
                query, generated_sql, reward, execution_time, validation_status, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                query,
                generated_sql,
                float(reward),
                float(execution_time),
                validation_status,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def compute_reward(
    validation_result: bool,
    stats: SQLExecutionStats,
    latency_threshold: float = 1.0,
) -> float:
    reward = 0.0

    if not stats.dangerous_operation and not stats.syntax_error and validation_result:
        reward += 10
    if stats.expected_results or stats.row_count > 0:
        reward += 15
    if stats.execution_time > 0 and stats.execution_time <= latency_threshold:
        reward += 5
    if validation_result:
        reward += 5

    if stats.syntax_error:
        reward -= 20
    if stats.invalid_table:
        reward -= 25
    if stats.hallucinated_column:
        reward -= 25
    if validation_result and stats.row_count == 0 and not stats.error_message:
        reward -= 10
    if stats.dangerous_operation:
        reward -= 50

    return reward


def classify_execution_error(message: str) -> tuple[bool, bool, bool]:
    msg = message.lower()
    syntax_error = "syntax" in msg or "parse" in msg or "incomplete input" in msg
    invalid_table = "no such table" in msg or "unknown table" in msg
    hallucinated_column = "no such column" in msg or "unknown column" in msg
    return syntax_error, invalid_table, hallucinated_column


def execute_sql_for_stats(db_path: str | Path | None, sql: str) -> SQLExecutionStats:
    stats = SQLExecutionStats(dangerous_operation=bool(DANGEROUS_SQL_PATTERN.search(sql or "")))
    if stats.dangerous_operation:
        stats.error_message = "Dangerous SQL operation blocked"
        return stats
    if not db_path:
        return stats

    started = time.perf_counter()
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(sql)
            rows = cur.fetchmany(1000)
            stats.row_count = len(rows)
            stats.expected_results = stats.row_count > 0
    except Exception as exc:  # SQLite gives operational details used for reward shaping.
        stats.error_message = str(exc)
        (
            stats.syntax_error,
            stats.invalid_table,
            stats.hallucinated_column,
        ) = classify_execution_error(str(exc))
    finally:
        stats.execution_time = time.perf_counter() - started
    return stats


def _count_keywords(sql: str, keywords: list[str]) -> int:
    lowered = sql.lower()
    return sum(1 for keyword in keywords if keyword in lowered)


class SQLQueryOptimizationEnv(gym.Env if gym else object):
    """PPO-compatible SQL optimization environment.

    The full state contains natural-language query, retrieved schema context, SQL,
    execution statistics, and validation result. PPO receives a compact numeric
    observation derived from that state.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        db_path: str | Path | None = None,
        initial_state: SQLState | None = None,
        sql_generator: Callable[[str, str], str] | None = None,
        validator: Callable[[str], tuple[bool, str]] | None = None,
        latency_threshold: float = 1.0,
        max_steps: int = 5,
        feedback_db_path: str | Path | None = None,
    ) -> None:
        if gym is None or spaces is None:
            raise ImportError("gymnasium is required to use SQLQueryOptimizationEnv")

        self.db_path = db_path
        self.feedback_db_path = feedback_db_path or db_path
        self.sql_generator = sql_generator
        self.validator = validator or (lambda sql: (not DANGEROUS_SQL_PATTERN.search(sql or ""), "Valid"))
        self.latency_threshold = latency_threshold
        self.max_steps = max_steps
        self.current_state = initial_state or SQLState()
        self.steps = 0

        self.action_space = spaces.Discrete(len(ACTION_NAMES))
        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(12,), dtype=np.float32)

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        self.steps = 0
        if options and "state" in options:
            self.current_state = options["state"]
        elif options:
            self.current_state = SQLState(
                user_query=options.get("user_query", ""),
                schema_context=options.get("schema_context", ""),
                generated_sql=options.get("generated_sql", ""),
            )
        self._refresh_validation_and_stats()
        return self._observation(), self._info(0.0, "reset")

    def step(self, action: int):
        self.steps += 1
        original_sql = self.current_state.generated_sql
        self.current_state.generated_sql = self._apply_action(action)
        self._refresh_validation_and_stats()
        reward = compute_reward(
            self.current_state.validation_result,
            self.current_state.execution_stats,
            self.latency_threshold,
        )
        store_experience(
            self.feedback_db_path,
            self.current_state.user_query,
            self.current_state.generated_sql,
            reward,
            self.current_state.execution_stats.execution_time,
            self.current_state.validation_message,
        )
        terminated = action == ACTION_KEEP_CURRENT_QUERY
        truncated = self.steps >= self.max_steps
        return self._observation(), reward, terminated, truncated, self._info(reward, ACTION_NAMES[action], original_sql)

    def render(self) -> None:
        print(self.current_state)

    def _refresh_validation_and_stats(self) -> None:
        valid, message = self.validator(self.current_state.generated_sql)
        self.current_state.validation_result = bool(valid)
        self.current_state.validation_message = message
        self.current_state.execution_stats = execute_sql_for_stats(
            self.db_path,
            self.current_state.generated_sql,
        )

    def _apply_action(self, action: int) -> str:
        sql = (self.current_state.generated_sql or "").strip()
        if action == ACTION_REGENERATE_SQL and self.sql_generator:
            return self.sql_generator(self.current_state.user_query, self.current_state.schema_context)
        if action == ACTION_MODIFY_JOIN_STRATEGY:
            return self._normalize_joins(sql)
        if action == ACTION_MODIFY_FILTER_CONDITIONS:
            return self._tighten_filters(sql)
        if action == ACTION_MODIFY_AGGREGATION_STRATEGY:
            return self._normalize_aggregation(sql)
        return sql

    def _normalize_joins(self, sql: str) -> str:
        return re.sub(r"\b(left|right|full)\s+join\b", "JOIN", sql, flags=re.IGNORECASE)

    def _tighten_filters(self, sql: str) -> str:
        if not sql or re.search(r"\blimit\s+\d+\b", sql, re.IGNORECASE):
            return sql
        return sql.rstrip(";") + " LIMIT 100;"

    def _normalize_aggregation(self, sql: str) -> str:
        if "count(" in sql.lower() and "group by" not in sql.lower():
            return sql
        return re.sub(r"SELECT\s+\*", "SELECT COUNT(*) AS row_count", sql, count=1, flags=re.IGNORECASE)

    def _observation(self) -> np.ndarray:
        sql = self.current_state.generated_sql or ""
        stats = self.current_state.execution_stats
        features = np.array(
            [
                min(len(self.current_state.user_query) / 500.0, 1.0),
                min(len(self.current_state.schema_context) / 5000.0, 1.0),
                min(len(sql) / 2000.0, 1.0),
                1.0 if self.current_state.validation_result else -1.0,
                min(stats.execution_time / max(self.latency_threshold, 0.001), 1.0),
                min(stats.row_count / 100.0, 1.0),
                1.0 if stats.syntax_error else 0.0,
                1.0 if stats.invalid_table else 0.0,
                1.0 if stats.hallucinated_column else 0.0,
                1.0 if stats.dangerous_operation else 0.0,
                min(_count_keywords(sql, [" join ", " where ", " group by ", " order by "]) / 4.0, 1.0),
                min(self.steps / max(self.max_steps, 1), 1.0),
            ],
            dtype=np.float32,
        )
        return features

    def _info(self, reward: float, action_name: str, original_sql: str | None = None) -> dict[str, Any]:
        return {
            "action": action_name,
            "reward": reward,
            "original_sql": original_sql,
            "optimized_sql": self.current_state.generated_sql,
            "validation_status": self.current_state.validation_message,
            "execution_time": self.current_state.execution_stats.execution_time,
            "row_count": self.current_state.execution_stats.row_count,
        }

