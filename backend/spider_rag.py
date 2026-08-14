from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover - optional dependency fallback
    BM25Okapi = None


_SQL_INTENT_RE = re.compile(
    r"\b("
    r"show|list|get|find|count|how many|total|sum|average|avg|minimum|maximum|min|max|"
    r"which|what are|what is|order|rank|top|bottom|group|where|sql|query|select"
    r")\b",
    re.IGNORECASE,
)
_READ_ONLY_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_DANGEROUS_RE = re.compile(
    r"\b(delete|drop|truncate|update|insert|alter|create|merge|grant|revoke|execute|exec)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SpiderExample:
    text_query: str
    sql_command: str
    tokens: tuple[str, ...]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9_]*", str(text or "").lower().replace("-", " "))


def _is_read_only_sql(sql: str) -> bool:
    text = str(sql or "").strip()
    if not text or not _READ_ONLY_RE.match(text):
        return False
    return _DANGEROUS_RE.search(text) is None


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(cleaned[start:end + 1])
    return parsed if isinstance(parsed, dict) else {}


class SpiderTextSqlRag:
    def __init__(self, csv_path: Path, *, max_rows: int = 20_000) -> None:
        self.csv_path = Path(csv_path)
        self.examples: list[SpiderExample] = []
        self._bm25: Any | None = None
        self._load(max_rows=max_rows)

    @property
    def available(self) -> bool:
        return bool(self.examples)

    def _load(self, *, max_rows: int) -> None:
        if not self.csv_path.exists():
            return
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                if index >= max_rows:
                    break
                text_query = str(row.get("text_query") or "").strip()
                sql_command = str(row.get("sql_command") or "").strip()
                if not text_query or not _is_read_only_sql(sql_command):
                    continue
                self.examples.append(
                    SpiderExample(text_query=text_query, sql_command=sql_command, tokens=tuple(_tokens(text_query)))
                )
        if BM25Okapi is not None and self.examples:
            self._bm25 = BM25Okapi([list(example.tokens) for example in self.examples])

    def looks_like_text_to_sql(self, query: str) -> bool:
        return bool(_SQL_INTENT_RE.search(query or ""))

    def retrieve(self, query: str, *, k: int = 5) -> list[dict[str, object]]:
        if not self.examples:
            return []
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        if self._bm25 is not None:
            scores = self._bm25.get_scores(query_tokens)
            ranked = sorted(enumerate(scores), key=lambda item: float(item[1]), reverse=True)[:k]
            results = [
                {
                    "text_query": self.examples[index].text_query,
                    "sql_command": self.examples[index].sql_command,
                    "score": round(float(score), 3),
                }
                for index, score in ranked
                if float(score) > 0
            ]
            if results:
                return results

        query_set = set(query_tokens)
        ranked = []
        for index, example in enumerate(self.examples):
            example_set = set(example.tokens)
            overlap = len(query_set & example_set)
            if overlap:
                ranked.append((index, overlap / max(1, len(query_set | example_set))))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return [
            {
                "text_query": self.examples[index].text_query,
                "sql_command": self.examples[index].sql_command,
                "score": round(float(score), 3),
            }
            for index, score in ranked[:k]
        ]

    def answer(self, query: str, *, provider: Any | None = None, k: int = 5) -> dict[str, object] | None:
        if not self.available or not self.looks_like_text_to_sql(query):
            return None
        examples = self.retrieve(query, k=k)
        if not examples:
            return None

        started = time.perf_counter()
        llm_trace: dict[str, object] = {
            "provider": "local",
            "model": "spider-nearest-neighbor",
            "active": False,
            "fallback_used": False,
            "fallback_reason": "",
            "stages": [],
        }
        sql = str(examples[0]["sql_command"])
        explanation = "Used the closest Spider text-to-SQL example as a generic SQL pattern."
        confidence = 62.0

        if provider is not None and getattr(provider, "available", False):
            system_prompt = (
                "You generate generic, illustrative SQL for text-to-SQL questions that do not match "
                "the user's enterprise schema. Use the Spider examples as retrieval context and return "
                "only JSON with keys: sql, explanation, confidence. The SQL must be read-only SELECT/WITH. "
                "Do not mention or invent the enterprise application's schema."
            )
            payload = {
                "user_query": query,
                "retrieved_spider_examples": examples,
                "instruction": (
                    "Create a generic SQL solution using table and column names implied by the question "
                    "or by the closest Spider examples. It is illustrative and not guaranteed executable "
                    "against the enterprise database."
                ),
            }
            result = provider.generate_structured(system_prompt, payload)
            llm_trace.update({
                "provider": result.provider,
                "model": result.model,
                "active": True,
                "fallback_used": not result.success,
                "fallback_reason": result.error_category if not result.success else "",
                "latency_ms": result.latency_ms,
                "retry_count": result.retry_count,
                "stages": [
                    {
                        "stage": "spider_generic_generation",
                        "success": result.success,
                        "error_category": result.error_category,
                        "latency_ms": result.latency_ms,
                    }
                ],
            })
            data = result.data or {}
            candidate_sql = str(data.get("sql") or "").strip()
            if result.success and _is_read_only_sql(candidate_sql):
                sql = candidate_sql.rstrip(";") + ";"
                explanation = str(data.get("explanation") or explanation)
                try:
                    confidence = float(data.get("confidence", confidence))
                    if 0.0 <= confidence <= 1.0:
                        confidence *= 100.0
                    confidence = max(0.0, min(100.0, confidence))
                except (TypeError, ValueError):
                    confidence = 72.0
            elif result.success:
                llm_trace["fallback_used"] = True
                llm_trace["fallback_reason"] = "generic_candidate_failed_validation"

        return {
            "sql": sql.rstrip(";") + ";",
            "confidence": round(confidence, 2),
            "explanation": explanation,
            "examples": examples,
            "llm_trace": llm_trace,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
