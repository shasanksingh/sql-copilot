from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from rl.environment.sql_env import (
    ACTION_NAMES,
    ACTION_KEEP_CURRENT_QUERY,
    SQLQueryOptimizationEnv,
    SQLState,
    compute_reward,
    execute_sql_for_stats,
    store_experience,
)


@dataclass
class AgenticResult:
    original_sql: str
    optimized_sql: str
    reward_score: float
    confidence_score: int
    optimization_reasoning: str
    validation_status: str
    execution_time: float
    action: str


class AgentManager:
    """Coordinates the agentic SQL workflow around the existing RAG pipeline."""

    def __init__(
        self,
        retriever: Callable[[str], tuple[list[Any], list[str]]],
        sql_generator: Callable[[str, list[Any]], str],
        validator: Callable[[str], tuple[bool, str]],
        confidence_fn: Callable[[str, bool, str], int],
        db_path: str | None = None,
        feedback_db_path: str | None = None,
        ppo_agent: Any | None = None,
    ) -> None:
        self.retriever = retriever
        self.sql_generator = sql_generator
        self.validator = validator
        self.confidence_fn = confidence_fn
        self.db_path = db_path
        self.feedback_db_path = feedback_db_path
        self.ppo_agent = ppo_agent

    def planner_agent(self, query: str) -> str:
        return query.strip()

    def retriever_agent(self, query: str) -> tuple[list[Any], list[str], str]:
        docs, hints = self.retriever(query)
        schema_context = "\n\n---\n\n".join(getattr(doc, "page_content", str(doc)) for doc in docs)
        return docs, hints, schema_context

    def sql_generation_agent(self, query: str, docs: list[Any]) -> str:
        return self.sql_generator(query, docs)

    def rl_optimization_agent(self, query: str, schema_context: str, sql: str) -> tuple[str, str]:
        if self.ppo_agent is None:
            return sql, "keep_current_query"

        env = SQLQueryOptimizationEnv(
            db_path=self.db_path,
            feedback_db_path=self.feedback_db_path,
            validator=self.validator,
        )
        obs, _ = env.reset(options={
            "state": SQLState(
                user_query=query,
                schema_context=schema_context,
                generated_sql=sql,
            )
        })
        action = self.ppo_agent.predict(obs)
        obs, reward, terminated, truncated, info = env.step(action)
        return info["optimized_sql"], ACTION_NAMES.get(action, "unknown")

    def validator_agent(self, sql: str) -> tuple[bool, str]:
        return self.validator(sql)

    def execution_agent(self, sql: str):
        return execute_sql_for_stats(self.db_path, sql)

    def explanation_agent(
        self,
        action: str,
        original_sql: str,
        optimized_sql: str,
        validation_message: str,
    ) -> str:
        if action == "keep_current_query" or original_sql == optimized_sql:
            return "The RL optimizer kept the generated SQL because it already satisfied validation and policy checks."
        return (
            f"The RL optimizer selected {action.replace('_', ' ')} to improve validation, "
            f"execution feedback, or result quality. Validator status: {validation_message}."
        )

    def run(self, query: str) -> AgenticResult:
        planned_query = self.planner_agent(query)
        docs, _hints, schema_context = self.retriever_agent(planned_query)
        original_sql = self.sql_generation_agent(planned_query, docs)
        optimized_sql, action = self.rl_optimization_agent(planned_query, schema_context, original_sql)
        valid, validation_message = self.validator_agent(optimized_sql)
        stats = self.execution_agent(optimized_sql)
        reward = compute_reward(valid, stats)
        confidence = self.confidence_fn(optimized_sql, valid, planned_query)
        store_experience(
            self.feedback_db_path,
            planned_query,
            optimized_sql,
            reward,
            stats.execution_time,
            validation_message,
        )
        return AgenticResult(
            original_sql=original_sql,
            optimized_sql=optimized_sql,
            reward_score=reward,
            confidence_score=confidence,
            optimization_reasoning=self.explanation_agent(
                action,
                original_sql,
                optimized_sql,
                validation_message,
            ),
            validation_status=validation_message,
            execution_time=stats.execution_time,
            action=action,
        )

