import json
import os
from typing import Dict, List


class ConfidenceCoordinator:
    # weights aligned with requested spec
    DEFAULT_WEIGHTS = {
        "intent": 0.25,
        "entity": 0.20,
        "column": 0.15,
        "join": 0.15,
        "aggregation": 0.10,
        "semantic": 0.10,
        "validation": 0.05,
    }

    def __init__(self, weights: Dict[str, float] | None = None) -> None:
        configured = dict(weights or self.DEFAULT_WEIGHTS)
        raw = os.getenv("CONFIDENCE_WEIGHTS_JSON", "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    configured.update({
                        str(key): float(value)
                        for key, value in parsed.items()
                        if str(key) in self.DEFAULT_WEIGHTS
                    })
            except (TypeError, ValueError, json.JSONDecodeError):
                configured = dict(weights or self.DEFAULT_WEIGHTS)
        total = sum(configured.values()) or 1.0
        self.weights = {key: value / total for key, value in configured.items()}

    def compute_from_components(self, components: Dict[str, float], valid: bool, unresolved: List[str], ambiguities: List[str]) -> Dict[str, float]:
        # components expected to contain keys: intent, entity, column, join, aggregation, semantic, validation
        comp = {k: float(components.get(k, 100.0)) for k in self.weights.keys()}
        total = 0.0
        for k, w in self.weights.items():
            total += comp.get(k, 0.0) * w

        # penalties
        if not valid:
            total -= 25.0
        if unresolved:
            total -= min(30.0, len(unresolved) * 12.0)
        if ambiguities:
            total -= min(20.0, len(ambiguities) * 6.0)

        # additional penalties for low column/join coverage to avoid false highs
        col_score = comp.get("column", 100.0)
        if col_score < 50.0:
            total -= (50.0 - col_score) * 0.3
        join_score = comp.get("join", 100.0)
        if join_score < 50.0:
            total -= (50.0 - join_score) * 0.25
        entity_score = comp.get("entity", 100.0)
        if entity_score < 70.0:
            total -= (70.0 - entity_score) * 0.35
        semantic_score = comp.get("semantic", 100.0)
        if semantic_score < 70.0:
            total -= (70.0 - semantic_score) * 0.5

        # penalties for missing display columns
        missing_display = int(components.get("missing_display_count", 0))
        if missing_display > 0:
            # scale: 1 -> -20, 2 -> -30, 3+ -> -40 (cap at 40)
            total -= min(40.0, 20.0 + max(0, missing_display - 1) * 10.0)

        # penalties for missing joins
        missing_joins = int(components.get("missing_joins_count", 0))
        if missing_joins > 0:
            # scale: 1 -> -20, each additional adds up to cap 50
            total -= min(50.0, 20.0 + missing_joins * 10.0)

        # penalties for incomplete join paths
        incomplete_joins = int(components.get("incomplete_joins_count", 0))
        if incomplete_joins > 0:
            total -= min(30.0, 10.0 + incomplete_joins * 10.0)

        overall = max(0.0, min(100.0, round(total, 2)))

        breakdown = {
            "intent": comp["intent"],
            "entity": comp["entity"],
            "column": comp["column"],
            "join": comp["join"],
            "aggregation": comp["aggregation"],
            "semantic": comp["semantic"],
            "validation": comp["validation"],
            "overall": overall,
            "total_confidence": overall,
        }
        return breakdown

    def compute_from_sql_heuristic(self, sql: str, is_valid: bool, original_query: str) -> Dict[str, float]:
        # backward-compatible fallback that mirrors old heuristics but maps into component slots
        if not is_valid:
            return {"overall": 0.0, "intent": 0.0, "entity": 0.0, "column": 0.0, "join": 0.0, "aggregation": 0.0, "semantic": 0.0, "validation": 0.0, "total_confidence": 0.0}
        score = 80.0
        q = original_query.lower()
        s = (sql or "").lower()
        if any(w in q for w in ["count", "total", "how many"]) and "count(" in s:
            score += 5
        if any(w in q for w in ["group", "per", "each"]) and "group by" in s:
            score += 5
        if any(w in q for w in ["sort", "order", "top", "latest"]) and "order by" in s:
            score += 5
        if any(w in q for w in ["join", "with"]) and "join" in s:
            score += 5
        if "select *" in s and len(original_query.split()) > 5:
            score -= 5
        if len(s.strip()) < 15:
            score -= 30

        overall = max(0.0, min(100.0, score))
        # distribute heuristically across components
        breakdown = {
            "intent": min(100.0, overall),
            "entity": min(100.0, overall - 5.0),
            "column": min(100.0, overall - 10.0),
            "join": min(100.0, overall - 8.0),
            "aggregation": min(100.0, overall - 12.0),
            "semantic": min(100.0, overall - 10.0),
            "validation": 100.0 if is_valid else 0.0,
            "overall": round(overall, 2),
            "total_confidence": round(overall, 2),
        }
        return breakdown
