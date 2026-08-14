from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable
from .coverage_agents import (
    IntentCoverageAgent,
    EntityCoverageAgent,
    ColumnCoverageAgent,
    JoinCoverageAgent,
    AggregationCoverageAgent,
    DisplayColumnSelectionAgent,
    JoinPathCoverageAgent,
)
from .confidence_coordinator import ConfidenceCoordinator
from .custody_balance_domain import (
    BalanceRequest,
    CUSTODY_BALANCE_RELATIONSHIPS,
    balance_request_summary,
    build_available_balance_sql,
    parse_balance_request,
)
from .langgraph_workflow import build_sql_copilot_workflow

try:
    import networkx as nx
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    nx = None

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


TokenSet = set[str]
QUERY_CACHE_VERSION = "enterprise-v9"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9_]*", text.lower().replace("-", " "))


def _expanded_identifier_terms(terms: Iterable[str]) -> set[str]:
    expanded: set[str] = set()
    for term in terms:
        cleaned = str(term or "").strip().lower()
        if not cleaned:
            continue
        expanded.add(cleaned)
        expanded.add(_singular(cleaned))
        expanded.update(_tokens(cleaned.replace("_", " ")))
    return {term for term in expanded if term}


def _singular(word: str) -> str:
    if word in {"this", "status"}:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ss", "us")):
        return word
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def _score_text(query_terms: TokenSet, candidate: str) -> int:
    candidate_terms = set(_tokens(candidate.replace("_", " ")))
    expanded = candidate_terms | {_singular(term) for term in candidate_terms}
    exact = len(query_terms & expanded) * 30
    if fuzz is None:
        return exact
    fuzzy = max((fuzz.token_set_ratio(" ".join(query_terms), candidate.replace("_", " ")) for _ in [0]), default=0)
    return exact + int(fuzzy * 0.45)


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SchemaColumn:
    table: str
    name: str
    data_type: str = ""
    description: str = ""
    is_pk: bool = False
    is_fk: bool = False


@dataclass
class SchemaRelationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass
class Intent:
    operation: str = "SELECT"
    aggregations: list[str] = field(default_factory=list)
    group_by: bool = False
    order_by: str | None = None
    order_direction: str | None = None
    limit: int | None = None
    filters: list[dict[str, str]] = field(default_factory=list)
    requires_join: bool = False
    time_granularity: str | None = None
    time_range: str | None = None
    running_total: bool = False


@dataclass
class EntityExtraction:
    raw_terms: list[str]
    canonical_terms: list[str]
    tables: list[str]
    columns: list[str]
    measures: list[str]
    filters: list[dict[str, str]]
    unresolved_terms: list[str]


@dataclass
class SchemaMatch:
    kind: str
    table: str
    column: str | None
    score: int
    reason: str


@dataclass
class QueryPlan:
    main_table: str
    selected_columns: list[tuple[str, str]]
    joins: list[SchemaRelationship]
    filters: list[dict[str, str]]
    aggregations: list[dict[str, str]]
    group_by: list[tuple[str, str]]
    order_by: tuple[str, str] | None
    limit: int | None
    confidence: int
    unresolved_terms: list[str] = field(default_factory=list)
    ambiguity_options: list[str] = field(default_factory=list)
    time_granularity: str | None = None
    time_table: str | None = None
    time_column: str | None = None
    running_total: bool = False
    window_partition_by: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class CopilotResult:
    sql: str
    confidence: int
    valid: bool
    validation: str
    clarification_required: bool
    clarification_options: list[str]
    intent: dict
    entities: dict
    selected_tables: list[str]
    selected_columns: list[str]
    join_path: list[str]
    plan: dict | None
    optimizations: list[str]
    confidence_breakdown: dict[str, float] = field(default_factory=dict)
    confidence_evidence: list[dict[str, object]] = field(default_factory=list)
    coverage_report: dict[str, object] = field(default_factory=dict)
    agent_telemetry: dict[str, object] = field(default_factory=dict)
    execution_trace: dict[str, object] = field(default_factory=dict)
    runtime_metrics: dict[str, object] = field(default_factory=dict)
    benchmark_record: dict[str, object] = field(default_factory=dict)
    missing_entities: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    missing_joins: list[str] = field(default_factory=list)
    missing_aggregations: list[str] = field(default_factory=list)
    query_complexity: str = "SIMPLE"
    confidence_band: str = "LOW"
    provider_status: dict[str, object] = field(default_factory=dict)
    llm_trace: dict[str, object] = field(default_factory=dict)
    model_confidence: float = 0.0
    planner_confidence: float = 0.0
    validator_confidence: float = 0.0
    coverage_confidence: float = 0.0
    cache_hit: bool = False


class BusinessVocabularyEngine:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.synonyms: dict[str, set[str]] = {
            "employee": {"employee", "employees", "staff", "worker", "workers", "personnel", "developer", "manager"},
            "client": {"client", "clients", "customer", "customers", "organization"},
            "invoice": {"invoice", "invoices", "bill", "billing"},
            "department": {"department", "departments", "division", "team", "dept"},
            "project": {"project", "projects"},
            "task": {"task", "tasks", "work item", "todo"},
            "bug": {"bug", "bugs", "defect", "issue", "issues"},
            "salary": {"salary", "pay", "paid", "payroll", "compensation", "income", "wage", "ctc", "annual_ctc"},
            "amount": {"amount", "money", "payment", "paid", "revenue"},
            "budget": {"budget", "budgets", "project_budget", "allocated_budget"},
            "vendor": {"vendor", "vendors", "supplier", "suppliers"},
            "product": {"product", "products", "item", "items", "sku"},
            "status": {"status", "state"},
        }
        self.synonyms["employee"].update({"assignee", "performer", "performers"})
        self.business_rules: dict[str, dict[str, object]] = {
            "revenue": {
                "measure": "payments.amount_paid",
                "aggregation": "SUM(payments.amount_paid)",
                "description": "Cash revenue from received payment amounts when payments are in scope.",
            },
            "invoice_amount": {
                "measure": "invoices.amount",
                "aggregation": "SUM(invoices.amount)",
                "description": "Billed invoice amount when invoices are in scope.",
            },
            "project_budget": {
                "measure": "projects.budget",
                "aggregation": "SUM(projects.budget)",
                "description": "Allocated project budget.",
            },
            "logged_hours": {
                "measure": "time_logs.hours_spent",
                "aggregation": "SUM(time_logs.hours_spent)",
                "description": "Time logged by employees against tasks.",
            },
        }
        self._ensure_tables()
        self._load_learned_mappings()

    def _ensure_tables(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learned_mappings (
                    term TEXT PRIMARY KEY,
                    schema_target TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _load_learned_mappings(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            for term, target in conn.execute("SELECT term, schema_target FROM learned_mappings"):
                self.synonyms.setdefault(term.lower(), set()).add(target.lower())

    def canonicalize(self, terms: Iterable[str]) -> list[str]:
        canonical: list[str] = []
        for term in terms:
            normalized = _singular(term.lower())
            matched = normalized
            for root, variants in self.synonyms.items():
                if normalized in variants:
                    matched = root
                    break
            canonical.append(matched)
        return canonical

    def variants_for(self, term: str) -> set[str]:
        return self.synonyms.get(term, {term})

    def rules_for_terms(self, terms: Iterable[str]) -> dict[str, dict[str, object]]:
        term_set = {str(term).lower() for term in terms}
        matched: dict[str, dict[str, object]] = {}
        for name, rule in self.business_rules.items():
            variants = self.synonyms.get(name, {name})
            if name in term_set or term_set & variants:
                matched[name] = rule
        return matched


class QueryCacheLayer:
    def __init__(self, db_path: Path, namespace: str = "local") -> None:
        self.db_path = db_path
        self.namespace = namespace
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_cache (
                    nl_query TEXT PRIMARY KEY,
                    sql TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    explanation_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get(self, query: str) -> CopilotResult | None:
        cache_key = self._key(query)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT sql, confidence, explanation_json FROM query_cache WHERE nl_query = ?",
                (cache_key,),
            ).fetchone()
        if not row:
            return None
        data = json.loads(row[2])
        data.setdefault("confidence_breakdown", {})
        data.setdefault("confidence_evidence", [])
        data.setdefault("coverage_report", {})
        data.setdefault("agent_telemetry", {})
        data.setdefault("execution_trace", {})
        data.setdefault("runtime_metrics", {})
        data.setdefault("benchmark_record", {})
        data.setdefault("query_complexity", "SIMPLE")
        data.setdefault("confidence_band", "LOW")
        data.setdefault("provider_status", {})
        data.setdefault("llm_trace", {})
        if (
            isinstance(data.get("llm_trace"), dict)
            and data["llm_trace"].get("active")
            and data["llm_trace"].get("fallback_used")
        ):
            return None
        data.setdefault("model_confidence", 0.0)
        data.setdefault("planner_confidence", 0.0)
        data.setdefault("validator_confidence", 0.0)
        data.setdefault("coverage_confidence", 0.0)
        data.update({"sql": row[0], "confidence": row[1], "cache_hit": True})
        return CopilotResult(**data)

    def put(self, query: str, result: CopilotResult) -> None:
        cache_key = self._key(query)
        data = asdict(result)
        sql = data.pop("sql")
        confidence = data.pop("confidence")
        data["cache_hit"] = False
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO query_cache (nl_query, sql, confidence, explanation_json)
                VALUES (?, ?, ?, ?)
                """,
                (cache_key, sql, confidence, json.dumps(data)),
            )

    def _key(self, query: str) -> str:
        return f"{QUERY_CACHE_VERSION}:{self.namespace}:{query.strip().lower()}"


class SchemaGraphEngine:
    def __init__(
        self,
        tables: set[str],
        columns: dict[str, set[str]],
        column_order: dict[str, list[str]],
        column_types: dict[str, dict],
        relationships: dict[str, list[tuple[str, str, str]]],
    ) -> None:
        self.tables = tables
        self.columns = columns
        self.column_order = column_order
        self.column_types = column_types
        self.relationships = [
            SchemaRelationship(ft, fc, tt, tc)
            for ft, rels in relationships.items()
            for fc, tt, tc in rels
        ]
        self._adjacency: dict[str, list[SchemaRelationship]] = defaultdict(list)
        self.graph = nx.Graph() if nx is not None else None
        self._build()

    def _build(self) -> None:
        for table in self.tables:
            if self.graph is not None:
                self.graph.add_node(table, kind="table")
            for column in self.columns.get(table, set()):
                if self.graph is not None:
                    self.graph.add_node(f"{table}.{column}", kind="column")
                    self.graph.add_edge(table, f"{table}.{column}", kind="has_column")
        for rel in self.relationships:
            self._adjacency[rel.from_table].append(rel)
            reverse = SchemaRelationship(rel.to_table, rel.to_column, rel.from_table, rel.from_column)
            self._adjacency[rel.to_table].append(reverse)
            if self.graph is not None:
                self.graph.add_edge(
                    rel.from_table,
                    rel.to_table,
                    kind="fk",
                    from_column=rel.from_column,
                    to_column=rel.to_column,
                )

    def shortest_join_path(
        self,
        source: str,
        target: str,
        *,
        max_depth: int | None = None,
        role_hint: str = "",
        query: str = "",
    ) -> list[SchemaRelationship]:
        candidates = self.join_path_candidates(
            source,
            target,
            max_depth=max_depth,
            role_hint=role_hint,
            query=query,
            limit=1,
        )
        return candidates[0]["path"] if candidates else []

    def join_path_candidates(
        self,
        source: str,
        target: str,
        *,
        max_depth: int | None = None,
        role_hint: str = "",
        query: str = "",
        limit: int = 3,
    ) -> list[dict[str, object]]:
        if source == target:
            return [{"path": [], "score": 100.0, "depth": 0, "reason": "same_table"}]
        depth_limit = max_depth if max_depth is not None else max(1, len(self.tables))
        queue = deque([(source, [])])
        candidates: list[list[SchemaRelationship]] = []
        while queue:
            table, path = queue.popleft()
            if len(path) >= depth_limit:
                continue
            for rel in self._adjacency.get(table, []):
                visited = {source, *[step.to_table for step in path], *[step.from_table for step in path]}
                if rel.to_table in visited:
                    continue
                next_path = path + [rel]
                if rel.to_table == target:
                    candidates.append(next_path)
                    continue
                queue.append((rel.to_table, next_path))
        scored = [
            {
                "path": path,
                "score": self.score_join_path(path, role_hint=role_hint, query=query),
                "depth": len(path),
                "reason": "fk_path",
            }
            for path in candidates
        ]
        scored.sort(key=lambda item: (-float(item["score"]), int(item["depth"])))
        return scored[:limit]

    def score_join_path(
        self,
        path: list[SchemaRelationship],
        *,
        role_hint: str = "",
        query: str = "",
    ) -> float:
        if not path:
            return 100.0
        score = 100.0 - max(0, len(path) - 1) * 6.0
        query_text = query.lower()
        for rel in path:
            columns = {rel.from_column.lower(), rel.to_column.lower()}
            if role_hint and role_hint.lower() in columns:
                score += 10.0
            if any(token in columns for token in ("assigned_to", "reported_by", "reviewed_by", "created_by", "approved_by", "deployed_by")):
                for token in columns:
                    if token.replace("_", " ") in query_text or token in query_text:
                        score += 8.0
            parallel_edges = [
                candidate for candidate in self.relationships
                if {candidate.from_table, candidate.to_table} == {rel.from_table, rel.to_table}
            ]
            if len(parallel_edges) > 1 and not role_hint:
                score -= 8.0
        return round(max(0.0, min(100.0, score)), 2)

    def relationship_map(self) -> dict[str, list[dict[str, str]]]:
        return {
            table: [asdict(rel) for rel in rels]
            for table, rels in sorted(self._adjacency.items())
        }

    def er_diagram_mermaid(self) -> str:
        lines = ["erDiagram"]
        for rel in self.relationships:
            lines.append(
                f"  {rel.to_table} ||--o{{ {rel.from_table} : \"{rel.from_column} -> {rel.to_column}\""
            )
        return "\n".join(lines)


class IntentDetectionAgent:
    def detect(self, query: str) -> Intent:
        q = query.lower()
        intent = Intent()
        if re.search(r"\b(count|how many|number of)\b", q):
            intent.aggregations.append("COUNT")
        if re.search(r"\b(sum|total)\b", q):
            intent.aggregations.append("SUM")
        if re.search(r"\b(avg|average|mean)\b", q):
            intent.aggregations.append("AVG")
        if re.search(r"\brevenue\b", q) and "SUM" not in intent.aggregations:
            intent.aggregations.append("SUM")
        if re.search(r"\bperformers?\b", q) and "SUM" not in intent.aggregations:
            intent.aggregations.append("SUM")
        if re.search(r"\bquarter(?:ly)?\b", q):
            intent.time_granularity = "quarter"
        elif re.search(r"\bmonth(?:ly)?\b", q):
            intent.time_granularity = "month"
        elif re.search(r"\bweek(?:ly)?\b", q):
            intent.time_granularity = "week"
        range_match = re.search(r"\b(this\s+(week|month|quarter)|today)\b", q)
        if range_match:
            range_name = range_match.group(1).replace(" ", "_")
            intent.time_range = "today" if range_name == "today" else range_name
            intent.time_granularity = None
        intent.running_total = bool(re.search(r"\b(running|cumulative)\b", q))
        explicit_group = bool(re.search(r"\b(grouped by|group by|per|each)\b", q))
        aggregate_by = bool(intent.aggregations and re.search(r"\bby\b", q))
        intent.group_by = explicit_group or aggregate_by
        if re.search(r"\b(lowest|least|min|minimum|oldest|earliest)\b", q):
            intent.order_by = "requested"
            intent.order_direction = "ASC"
        elif re.search(r"\b(top|highest|most|max|maximum|largest|latest|recent|newest)\b", q):
            intent.order_by = "requested"
            intent.order_direction = "DESC"
        match = re.search(r"\b(?:top|first|limit|last)\s+(\d{1,4})\b", q)
        intent.limit = min(int(match.group(1)), 1000) if match else (10 if re.search(r"\btop\b", q) else None)
        intent.requires_join = bool(re.search(r"\bwith|and|by|per|for each\b", q))
        return intent
class EntityExtractionAgent:
    def __init__(self, vocabulary: BusinessVocabularyEngine, value_filters: dict[str, dict]) -> None:
        self.vocabulary = vocabulary
        self.value_filters = value_filters

    def extract(self, query: str) -> EntityExtraction:
        raw = _tokens(query)
        canonical = self.vocabulary.canonicalize(raw)
        filters: list[dict[str, str]] = []
        q = query.lower().replace("-", " ")
        for table, columns in self.value_filters.items():
            for column, values in columns.items():
                for phrase, value in values.items():
                    if re.search(rf"(?<!\w){re.escape(phrase.replace('_', ' '))}(?!\w)", q):
                        filters.append({"table": table, "column": column, "operator": "=", "value": value})
        measures = [term for term in canonical if term in {"salary", "amount", "budget", "hours", "revenue"}]
        return EntityExtraction(raw, canonical, [], [], measures, filters, [])
class SchemaLinkingEngine:
    def __init__(
        self,
        graph: SchemaGraphEngine,
        table_hints: dict[str, set[str]],
        column_hints: dict[str, dict[str, set[str]]],
        vocabulary: BusinessVocabularyEngine,
    ) -> None:
        self.graph = graph
        self.table_hints = table_hints
        self.column_hints = column_hints
        self.vocabulary = vocabulary

    def link(self, query: str, entities: EntityExtraction) -> tuple[list[SchemaMatch], list[str], list[str]]:
        query_terms = _expanded_identifier_terms([
            *entities.canonical_terms,
            *entities.raw_terms,
        ])
        query_text = query.lower().replace("-", "_")
        matches: list[SchemaMatch] = []
        for table in self.graph.tables:
            text = " ".join([table, table.replace("_", " "), *self.table_hints.get(table, set())])
            score = _score_text(query_terms, text)
            if re.search(rf"(?<!\w){re.escape(table.lower())}(?!\w)", query_text):
                score += 140
            elif re.search(rf"(?<!\w){re.escape(table.lower().replace('_', ' '))}(?!\w)", query.lower().replace("-", " ")):
                score += 120
            if score >= 30:
                matches.append(SchemaMatch("table", table, None, score, "table/hint match"))
            for column in self.graph.column_order.get(table, []):
                hints = self.column_hints.get(table, {}).get(column, set())
                column_text = " ".join([column, column.replace("_", " "), *hints])
                col_score = _score_text(query_terms, column_text)
                column_name = column.lower()
                qualified = f"{table.lower()}.{column_name}"
                if qualified in query_text or re.search(rf"(?<!\w){re.escape(column_name)}(?!\w)", query_text):
                    col_score += 140
                elif re.search(rf"(?<!\w){re.escape(column_name.replace('_', ' '))}(?!\w)", query.lower().replace("-", " ")):
                    col_score += 120
                if col_score >= 30:
                    matches.append(SchemaMatch("column", table, column, col_score, "column/hint match"))

        unresolved: list[str] = []
        if "salary" in entities.canonical_terms:
            compensation_cols = [
                match for match in matches
                if match.kind == "column" and match.table == "employees"
                and (match.column or "") in {"salary", "annual_ctc", "compensation", "income", "pay"}
            ]
            if not compensation_cols:
                unresolved.append("salary/pay/compensation")
                if "employee" in entities.canonical_terms:
                    matches.append(SchemaMatch("table", "employees", None, 90, "employee compensation context"))

        status_matches = [
            f"{table}.status"
            for table, columns in self.graph.columns.items()
            if "status" in columns
        ]
        action_terms = {"show", "list", "get", "all", "display", "status", "state"}
        domain_terms = query_terms - action_terms
        ambiguities = status_matches if "status" in query_terms and not domain_terms else []
        return sorted(matches, key=lambda item: item.score, reverse=True), unresolved, ambiguities


class JoinDiscoveryAgent:
    def __init__(self, graph: SchemaGraphEngine, max_depth: int = 8) -> None:
        self.graph = graph
        self.max_depth = max_depth
        self.last_diagnostics: dict[str, object] = {}

    def discover(self, main_table: str, tables: Iterable[str]) -> list[SchemaRelationship]:
        join_chain: list[SchemaRelationship] = []
        joined = {main_table}
        diagnostics: list[dict[str, object]] = []
        for table in tables:
            if table in joined:
                continue
            candidates = self.graph.join_path_candidates(main_table, table, max_depth=self.max_depth)
            best_path = candidates[0]["path"] if candidates else []
            diagnostics.append({
                "target_table": table,
                "selected_score": candidates[0]["score"] if candidates else 0.0,
                "selected_depth": candidates[0]["depth"] if candidates else 0,
                "candidate_count": len(candidates),
                "path": [
                    f"{rel.from_table}.{rel.from_column}->{rel.to_table}.{rel.to_column}"
                    for rel in best_path
                ],
            })
            for rel in best_path:
                key = (rel.from_table, rel.from_column, rel.to_table, rel.to_column)
                existing = {
                    (item.from_table, item.from_column, item.to_table, item.to_column)
                    for item in join_chain
                }
                if key not in existing:
                    join_chain.append(rel)
                joined.add(rel.from_table)
                joined.add(rel.to_table)
        self.last_diagnostics = {
            "max_depth": self.max_depth,
            "requested_tables": sorted(set(tables)),
            "paths": diagnostics,
        }
        return join_chain


class QueryPlannerAgent:
    def __init__(
        self,
        graph: SchemaGraphEngine,
        joiner: JoinDiscoveryAgent,
        defaults: dict[str, list[str]],
        labels: dict[str, str],
        column_hints: dict[str, dict[str, set[str]]],
    ) -> None:
        self.graph = graph
        self.joiner = joiner
        self.defaults = defaults
        self.labels = labels
        self.column_hints = column_hints

    def plan(
        self,
        intent: Intent,
        entities: EntityExtraction,
        matches: list[SchemaMatch],
        unresolved: list[str],
        ambiguities: list[str],
        query: str = "",
    ) -> QueryPlan | None:
        if unresolved or ambiguities or not matches:
            main = matches[0].table if matches else ""
            return QueryPlan(main, [], [], entities.filters, [], [], None, intent.limit, 20, unresolved, ambiguities)

        specialized = self._specialized_plan(intent, entities, query)
        if specialized is not None:
            return specialized

        table_scores: dict[str, int] = defaultdict(int)
        for match in matches:
            table_scores[match.table] += match.score if match.kind == "table" else int(match.score * 0.65)
        query_terms = _expanded_identifier_terms([
            *entities.canonical_terms,
            *entities.raw_terms,
        ])
        for table in list(table_scores):
            table_terms = _expanded_identifier_terms([table])
            if table_terms and table_terms.issubset(query_terms):
                table_scores[table] += 60
            elif query_terms & table_terms:
                table_scores[table] += 20
        main_table = max(table_scores.items(), key=lambda item: item[1])[0]
        selected_tables = {main_table}
        relationship_terms = {
            "assignee", "assigned", "assignment", "client", "customer", "department",
            "employee", "member", "owner", "reporter", "reported", "team", "vendor",
        }
        relationship_context = bool(intent.group_by or intent.aggregations or query_terms & relationship_terms)
        for match in matches:
            if not getattr(match, "table", None) or match.table == main_table:
                continue
            table_terms = _expanded_identifier_terms([match.table])
            column_terms = _expanded_identifier_terms([match.column or ""])
            explicit_table = bool(table_terms and table_terms.issubset(query_terms))
            explicit_column = bool(query_terms & column_terms) and not column_terms <= {"id", "name", "status"}
            bridge_terms = {"assignment", "bridge", "link", "mapping", "member", "team", "xref"}
            table_columns = self.graph.columns.get(match.table, set())
            id_like_columns = {col for col in table_columns if col == "id" or col.endswith("_id")}
            bridge_like = (
                len(table_columns) > 0
                and len(id_like_columns) >= max(2, len(table_columns) - 1)
                and not query_terms & bridge_terms
            )
            if bridge_like:
                continue
            if match.kind == "table" and (explicit_table or (match.score >= 75 and relationship_context)):
                selected_tables.add(match.table)
            elif match.kind == "column" and match.score >= 85 and explicit_table:
                selected_tables.add(match.table)

        # discover joins including multi-hop paths for all selected tables
        joins = self.joiner.discover(main_table, selected_tables)
        # ensure join path completion: for any selected_table not present in planned joins, try to append shortest path
        planned_tables = {main_table} | {rel.to_table for rel in joins} | {rel.from_table for rel in joins}
        for table in list(selected_tables):
            if table in planned_tables:
                continue
            # compute shortest path and append missing rels
            path = self.graph.shortest_join_path(main_table, table)
            for rel in path:
                if rel.to_table not in planned_tables or rel.from_table not in planned_tables:
                    joins.append(rel)
                    planned_tables.add(rel.from_table)
                    planned_tables.add(rel.to_table)

        plan_filters = [
            item for item in entities.filters
            if item.get("table") in planned_tables
        ]

        selected_columns = self._explicit_requested_columns(main_table, entities)
        display_triggers = {"show", "list", "display", "view", "get"}
        raw_terms = set(entities.raw_terms or [])
        # If no explicit requested columns, pick readable columns for main table
        if not selected_columns:
            selected_columns = self._concise_display_columns(main_table, entities)

        # For display intents, ensure readable/display columns are selected for all relevant tables (multi-table displays)
        try:
            if getattr(self, "display_selector", None) and raw_terms & display_triggers:
                for tbl in sorted(selected_tables):
                    if tbl == main_table:
                        continue
                    # avoid duplicate columns
                    existing_cols = {c for t, c in selected_columns}
                    sel = self.display_selector.select(tbl, self.graph.columns, self.graph.column_order, self.defaults, self.labels, explicit_requested=None)
                    for c in sel:
                        if c == "id" or c.endswith("_id"):
                            continue
                        if c not in existing_cols:
                            selected_columns.append((tbl, c))
                            existing_cols.add(c)
        except Exception:
            pass

        aggregations: list[dict[str, str]] = []
        group_by: list[tuple[str, str]] = []
        if intent.aggregations:
            agg = intent.aggregations[0]
            target = self._best_aggregation_column(agg, main_table, matches, entities)
            alias = "record_count" if agg == "COUNT" else f"{agg.lower()}_{target.replace('*', 'rows')}"
            aggregations.append({"function": agg, "table": main_table, "column": target, "alias": alias})
            if intent.group_by:
                group_candidates = [
                    match.column for match in matches
                    if match.kind == "column" and match.column and match.table == main_table and match.column != target
                ]
                group_col = group_candidates[0] if group_candidates else self._default_group_column(main_table)
                if group_col:
                    group_by.append((main_table, group_col))
                    selected_columns = [(main_table, group_col)]
                else:
                    selected_columns = []
            else:
                selected_columns = []

        order_by = None
        if intent.order_by:
            if aggregations:
                order_by = (aggregations[0]["alias"], intent.order_direction or "DESC")
            else:
                order_col = self._best_order_column(main_table, matches)
                if order_col:
                    order_by = (f"{main_table}.{order_col}", intent.order_direction or "DESC")

        confidence = min(96, max(55, table_scores[main_table] + 35))
        if any(item["table"] == main_table for item in entities.filters):
            confidence = min(96, confidence + 8)
        return QueryPlan(
            main_table,
            selected_columns,
            joins,
            plan_filters,
            aggregations,
            group_by,
            order_by,
            intent.limit,
            confidence,
        )

    def _specialized_plan(
        self,
        intent: Intent,
        entities: EntityExtraction,
        query: str,
    ) -> QueryPlan | None:
        q = query.lower()

        if (
            "performer" in q
            and "department" in entities.canonical_terms
            and self._has_columns("employees", "employee_id", "full_name", "department")
            and self._has_columns("time_logs", "employee_id", "hours_spent")
        ):
            joins = self.joiner.discover("employees", ["time_logs"])
            return QueryPlan(
                main_table="employees",
                selected_columns=[
                    ("employees", "department"),
                    ("employees", "full_name"),
                ],
                joins=joins,
                filters=[],
                aggregations=[{
                    "function": "SUM",
                    "table": "time_logs",
                    "column": "hours_spent",
                    "alias": "total_hours",
                }],
                group_by=[
                    ("employees", "department"),
                    ("employees", "full_name"),
                ],
                order_by=("total_hours", "DESC"),
                limit=intent.limit or 10,
                confidence=94,
            )

        range_plan = self._semantic_date_range_plan(intent, entities, q)
        if range_plan is not None:
            return range_plan

        aggregate_plan = self._semantic_aggregate_plan(intent, entities, q)
        if aggregate_plan is not None:
            return aggregate_plan

        related_plan = self._semantic_related_dimension_plan(intent, entities, q)
        if related_plan is not None:
            return related_plan

        return None

    def _semantic_aggregate_plan(
        self,
        intent: Intent,
        entities: EntityExtraction,
        query: str,
    ) -> QueryPlan | None:
        function = intent.aggregations[0] if intent.aggregations else None
        base_table = self._resolve_base_table(query, entities)
        measure = self._resolve_measure(query)

        if function is None and measure:
            function = "SUM"
        if function is None and self._should_infer_count(query, base_table):
            function = "COUNT"
        if function is None:
            return None

        if function == "COUNT":
            if not base_table:
                return None
            measure_table, measure_column, alias = base_table, "*", "record_count"
        else:
            if not measure:
                return None
            measure_table, measure_column, alias = measure
            base_table = measure_table
            if intent.running_total:
                alias = alias.replace("total_", "running_", 1)
                if not alias.startswith("running_"):
                    alias = f"running_{alias}"

        dimension_text = self._dimension_text(query, measure_table, measure_column)
        dimensions = self._resolve_dimensions(dimension_text, base_table, query)
        joins = self._joins_for_dimensions(base_table, dimensions, query)
        planned_tables = self._planned_tables(base_table, joins)
        dimensions = [
            dimension for dimension in dimensions
            if dimension[0] in planned_tables
        ]
        selected_columns = [(table, column) for table, column, _role in dimensions]
        group_by = list(selected_columns)
        time_column = None
        if intent.time_granularity:
            time_column = self._resolve_date_column(base_table, query)
            if not time_column:
                return None
            group_by.insert(0, (base_table, time_column))

        filters = [
            item for item in entities.filters
            if item.get("table") in planned_tables
        ]
        aggregation = {
            "function": function,
            "table": measure_table,
            "column": measure_column,
            "alias": alias,
        }
        order_by = None
        if intent.order_by:
            order_by = (alias, intent.order_direction or "DESC")

        return QueryPlan(
            main_table=base_table,
            selected_columns=selected_columns,
            joins=joins,
            filters=filters,
            aggregations=[aggregation],
            group_by=group_by,
            order_by=order_by,
            limit=intent.limit,
            confidence=95,
            time_granularity=intent.time_granularity,
            time_table=base_table if time_column else None,
            time_column=time_column,
            running_total=intent.running_total,
            window_partition_by=selected_columns if intent.running_total else [],
        )

    def _semantic_date_range_plan(
        self,
        intent: Intent,
        entities: EntityExtraction,
        query: str,
    ) -> QueryPlan | None:
        if not intent.time_range:
            return None
        base_table = self._resolve_base_table(query, entities)
        if not base_table:
            return None
        date_column = self._resolve_date_column(base_table, query)
        if not date_column:
            return None

        dimensions = self._resolve_dimensions(self._dimension_text(query), base_table, query)
        joins = self._joins_for_dimensions(base_table, dimensions, query)
        planned_tables = self._planned_tables(base_table, joins)
        dimensions = [
            dimension for dimension in dimensions
            if dimension[0] in planned_tables
        ]
        selected_columns = [(table, column) for table, column, _role in dimensions]
        selected_columns.extend(self._readable_base_columns(base_table, entities))
        selected_columns.append((base_table, date_column))
        selected_columns = self._dedupe_columns(selected_columns)
        filters = [
            item for item in entities.filters
            if item.get("table") in planned_tables
        ]
        filters.append({
            "table": base_table,
            "column": date_column,
            "operator": intent.time_range,
            "value": "",
        })
        return QueryPlan(
            main_table=base_table,
            selected_columns=selected_columns,
            joins=joins,
            filters=filters,
            aggregations=[],
            group_by=[],
            order_by=(f"{base_table}.{date_column}", "ASC"),
            limit=intent.limit,
            confidence=95,
            time_table=base_table,
            time_column=date_column,
        )

    def _semantic_related_dimension_plan(
        self,
        intent: Intent,
        entities: EntityExtraction,
        query: str,
    ) -> QueryPlan | None:
        if " by " not in f" {query} ":
            return None
        base_table = self._resolve_base_table(query, entities)
        if not base_table:
            return None
        dimensions = self._resolve_dimensions(self._dimension_text(query), base_table, query)
        related_dimensions = [
            dimension for dimension in dimensions
            if dimension[0] != base_table
        ]
        if not related_dimensions:
            return None
        joins = self._joins_for_dimensions(base_table, dimensions, query)
        planned_tables = self._planned_tables(base_table, joins)
        if any(table not in planned_tables for table, _column, _role in related_dimensions):
            return None

        selected_columns = [(table, column) for table, column, _role in dimensions]
        selected_columns.extend(self._readable_base_columns(base_table, entities))
        selected_columns = self._dedupe_columns(selected_columns)
        filters = [
            item for item in entities.filters
            if item.get("table") in planned_tables
        ]
        first_table, first_column, _role = dimensions[0]
        return QueryPlan(
            main_table=base_table,
            selected_columns=selected_columns,
            joins=joins,
            filters=filters,
            aggregations=[],
            group_by=[],
            order_by=(f"{first_table}.{first_column}", intent.order_direction or "ASC"),
            limit=intent.limit,
            confidence=95,
        )

    def _resolve_measure(self, query: str) -> tuple[str, str, str] | None:
        candidates = [
            (r"\b(hours?|time\s+spent|logged\s+time)\b", "time_logs", "hours_spent", "total_hours"),
            (r"\bbudgets?\b", "projects", "budget", "total_budget"),
            (r"\b(invoice|invoices|billed)\b.*\bamount\b|\binvoice\s+amount\b", "invoices", "amount", "total_invoice_amount"),
            (r"\b(payment|payments|paid)\b.*\bamount\b|\bamount\s+paid\b", "payments", "amount_paid", "total_amount_paid"),
            (r"\brevenue\b", "payments", "amount_paid", "revenue"),
        ]
        for pattern, table, column, alias in candidates:
            if re.search(pattern, query) and self._has_columns(table, column):
                return table, column, alias
        if re.search(r"\bamount\b", query):
            for table, column, alias in (
                ("invoices", "amount", "total_invoice_amount"),
                ("payments", "amount_paid", "total_amount_paid"),
            ):
                if re.search(rf"\b{_singular(table)}s?\b", query) and self._has_columns(table, column):
                    return table, column, alias
        return None

    def _resolve_base_table(
        self,
        query: str,
        entities: EntityExtraction,
    ) -> str | None:
        query_text = query.lower().replace("-", " ")
        query_identifier_text = query.lower().replace("-", "_")
        canonical = _expanded_identifier_terms([
            *entities.canonical_terms,
            *entities.raw_terms,
        ])
        candidates: list[tuple[int, int, str]] = []
        for table in self.graph.tables:
            table_lower = table.lower()
            table_phrase = table_lower.replace("_", " ")
            score = 0
            positions: list[int] = []
            identifier_match = re.search(rf"(?<!\w){re.escape(table_lower)}(?!\w)", query_identifier_text)
            phrase_match = re.search(rf"(?<!\w){re.escape(table_phrase)}(?!\w)", query_text)
            if identifier_match:
                score = 140
                positions.append(identifier_match.start())
            elif phrase_match:
                score = 120
                positions.append(phrase_match.start())
            table_terms = _expanded_identifier_terms([table])
            if table_terms and table_terms <= canonical:
                score += 80
            if score:
                candidates.append((score, min(positions) if positions else len(query), table))

        aliases = {
            "employees": {"employee", "employees", "staff", "worker", "workers"},
            "clients": {"client", "clients", "customer", "customers"},
            "projects": {"project", "projects"},
            "project_team": {"project team", "team member", "team members"},
            "tasks": {"task", "tasks", "todo"},
            "time_logs": {"time log", "time logs"},
            "bugs": {"bug", "bugs", "defect", "defects", "issue", "issues"},
            "departments": {"department", "departments", "division"},
            "invoices": {"invoice", "invoices", "bill", "bills"},
            "payments": {"payment", "payments", "receipt", "receipts"},
            "sprints": {"sprint", "sprints"},
            "deployments": {"deployment", "deployments", "release", "releases"},
        }
        for table, phrases in aliases.items():
            if table not in self.graph.tables:
                continue
            positions = [
                match.start()
                for phrase in phrases
                if (match := re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", query))
            ]
            score = 100 if positions else 0
            root = _singular(table)
            if root in canonical:
                score += 30
            if score:
                candidates.append((score, min(positions) if positions else len(query), table))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        return candidates[0][2]

    def _dimension_text(
        self,
        query: str,
        measure_table: str | None = None,
        measure_column: str | None = None,
    ) -> str:
        if " by " not in f" {query} ":
            return query
        before, after = query.rsplit(" by ", 1)
        measure_words = set(_tokens((measure_column or "").replace("_", " ")))
        after_terms = set(_tokens(after))
        return before if measure_words and measure_words & after_terms else after

    def _resolve_dimensions(
        self,
        text: str,
        base_table: str,
        query: str,
    ) -> list[tuple[str, str, str]]:
        dimensions: list[tuple[str, str, str]] = []

        def add(table: str, column: str, role: str = "") -> None:
            if self._has_columns(table, column):
                item = (table, column, role)
                if item not in dimensions:
                    dimensions.append(item)

        has_tier = bool(re.search(r"\b(client\s+|customer\s+)?tier\b|\bsegment\b", text))
        if has_tier:
            add("clients", "tier", "client")
        if re.search(r"\bpayment\s+method\b|\bmethod\b", text):
            add("payments", "payment_method")
        if re.search(r"\bassignee\b|\bassigned\s+to\b", text):
            add("employees", "full_name", "assigned_to")
        elif re.search(r"\breporter\b|\breported\s+by\b|\bfound\s+by\b", text):
            add("employees", "full_name", "reported_by")
        elif re.search(r"\bdeployed\s+by\b|\breleaser\b", text):
            add("employees", "full_name", "deployed_by")
        elif re.search(r"\bcreated\s+by\b|\bcreator\b", text):
            add("employees", "full_name", "created_by")
        elif re.search(r"\bapproved\s+by\b|\bapprover\b", text):
            add("employees", "full_name", "approved_by")
        elif re.search(r"\breviewed\s+by\b|\breviewer\b", text):
            add("employees", "full_name", "reviewed_by")
        if re.search(r"\bdepartments?\b|\bdept\b|\bdivision\b", text):
            add("employees", "department")
        elif re.search(r"\bemployees?\b|\bstaff\b|\bperformers?\b", text):
            add("employees", "full_name", "employee_id")
        if not has_tier and re.search(r"\bclients?\b|\bcustomers?\b", text):
            add("clients", "client_name", "client_id")
        if re.search(r"\bprojects?\b", text):
            add("projects", "project_name", "project_id")
        if re.search(r"\binvoices?\b|\bbills?\b", text):
            add("invoices", "invoice_number", "invoice_id")
        if re.search(r"\bpriority\b", text):
            add("tasks", "priority")
        if re.search(r"\bseverity\b", text):
            add("bugs", "severity")
        if re.search(r"\bindustry\b|\bdomain\b", text):
            add("clients", "industry")
        if re.search(r"\benvironment\b", text):
            add("deployments", "environment")
        if re.search(r"\bsprints?\b", text):
            add("sprints", "sprint_name")
        if re.search(r"\bstatus\b|\bstate\b", text):
            add(base_table, "status")

        if not dimensions:
            text_terms = _expanded_identifier_terms(_tokens(text))
            ignored = {
                "id", "name", "date", "month", "quarter", "week", "year",
                "amount", "budget", "hours", "revenue", "total", "running",
            }
            for column in self.graph.column_order.get(base_table, []):
                column_terms = _expanded_identifier_terms([column]) - ignored
                if column_terms and column_terms <= text_terms:
                    dtype = str(self.graph.column_types.get(base_table, {}).get(column, "")).lower()
                    if not any(token in dtype for token in ("date", "time", "decimal", "float", "double")):
                        add(base_table, column)
                        break
        return dimensions

    def _joins_for_dimensions(
        self,
        base_table: str,
        dimensions: list[tuple[str, str, str]],
        query: str,
    ) -> list[SchemaRelationship]:
        joins: list[SchemaRelationship] = []
        keys: set[tuple[str, str, str, str]] = set()
        for target_table, _column, role in dimensions:
            if target_table == base_table:
                continue
            direct = self._preferred_direct_relationship(base_table, target_table, role, query)
            path = [direct] if direct else self.graph.shortest_join_path(
                base_table,
                target_table,
                max_depth=getattr(self.joiner, "max_depth", None),
                role_hint=role,
                query=query,
            )
            for rel in path:
                key = (rel.from_table, rel.from_column, rel.to_table, rel.to_column)
                if key not in keys:
                    joins.append(rel)
                    keys.add(key)
        return joins

    def _preferred_direct_relationship(
        self,
        base_table: str,
        target_table: str,
        role: str,
        query: str,
    ) -> SchemaRelationship | None:
        direct = [
            rel for rel in self.graph.relationships
            if {rel.from_table, rel.to_table} == {base_table, target_table}
        ]
        if not direct:
            return None
        preferred_columns = [
            "assigned_to" if "assignee" in query else "",
            "reported_by" if re.search(r"\breporter\b|\breported\s+by\b", query) else "",
            "deployed_by" if "deployed" in query else "",
            "created_by" if re.search(r"\bcreated\s+by\b|\bcreator\b", query) else "",
            "approved_by" if re.search(r"\bapproved\s+by\b|\bapprover\b", query) else "",
            "reviewed_by" if re.search(r"\breviewed\s+by\b|\breviewer\b", query) else "",
            role,
            f"{_singular(target_table)}_id",
            "employee_id" if target_table == "employees" else "",
            "client_id" if target_table == "clients" else "",
            "project_id" if target_table == "projects" else "",
        ]
        for preferred in preferred_columns:
            if not preferred:
                continue
            for rel in direct:
                if preferred in {rel.from_column, rel.to_column}:
                    return rel
        return direct[0]

    def _resolve_date_column(self, table: str, query: str) -> str | None:
        phrase_candidates = [
            (r"\bdue\b|\bdeadline\b", ("due_date", "end_date")),
            (r"\bending\b|\bend(?:ing)?\s+date\b", ("end_date", "due_date")),
            (r"\bpayment\b|\bpaid\b|\brevenue\b", ("payment_date", "issued_date")),
            (r"\bissued\b|\binvoice\b", ("issued_date", "due_date")),
            (r"\blogged\b|\bhours?\b", ("log_date",)),
            (r"\bdeployed\b|\brelease\b", ("deployed_at",)),
            (r"\bstart(?:ed|ing)?\b", ("start_date",)),
            (r"\bcreated\b|\breported\b", ("created_at",)),
        ]
        for pattern, candidates in phrase_candidates:
            if re.search(pattern, query):
                for column in candidates:
                    if column in self.graph.columns.get(table, set()):
                        return column
        for column in (
            "payment_date", "log_date", "issued_date", "due_date", "end_date",
            "deployed_at", "start_date", "created_at", "joining_date", "assigned_at",
        ):
            if column in self.graph.columns.get(table, set()):
                return column
        return None

    def _readable_base_columns(
        self,
        table: str,
        entities: EntityExtraction,
    ) -> list[tuple[str, str]]:
        selected: list[tuple[str, str]] = []
        label = self.labels.get(table)
        if label and label in self.graph.columns.get(table, set()):
            selected.append((table, label))
        for item in self._explicit_requested_columns(table, entities):
            column = item[1]
            if column.endswith("_id") and item != (table, label):
                continue
            selected.append(item)
        for item in entities.filters:
            if item.get("table") == table:
                selected.append((table, str(item["column"])))
        if not selected:
            selected = self._concise_display_columns(table, entities)
        return self._dedupe_columns(selected)[:4]

    def _planned_tables(
        self,
        main_table: str,
        joins: list[SchemaRelationship],
    ) -> set[str]:
        return {
            main_table,
            *[rel.from_table for rel in joins],
            *[rel.to_table for rel in joins],
        }

    def _dedupe_columns(
        self,
        columns: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in columns:
            if item not in seen:
                result.append(item)
                seen.add(item)
        return result

    def _should_infer_count(self, query: str, base_table: str | None) -> bool:
        if not base_table or " by " not in f" {query} ":
            return False
        if re.search(r"\b(grouped\s+by|group\s+by)\b", query):
            return True
        if base_table == "projects":
            return False
        display_verbs = {"show", "list", "find", "display", "get"}
        return not (set(_tokens(query)) & display_verbs)

    def _has_columns(self, table: str, *columns: str) -> bool:
        available = self.graph.columns.get(table, set())
        return table in self.graph.tables and all(column in available for column in columns)

    def _default_group_column(self, table: str) -> str | None:
        for candidate in ("department", "status", "role", "priority", "severity", "industry"):
            if candidate in self.graph.columns.get(table, set()):
                return candidate
        return None

    def _best_aggregation_column(
        self,
        function: str,
        table: str,
        matches: list[SchemaMatch],
        entities: EntityExtraction,
    ) -> str:
        if function == "COUNT":
            return "*"

        table_columns = self.graph.column_order.get(table, [])
        numeric_columns = [
            column for column in table_columns
            if any(
                token in str(self.graph.column_types.get(table, {}).get(column, "")).lower()
                for token in ("int", "decimal", "number", "float", "double", "real")
            )
        ]
        measure_terms = set(entities.measures) | {"amount", "revenue", "budget", "salary"}
        for match in matches:
            if match.table == table and match.column:
                column_terms = set(_tokens(match.column.replace("_", " ")))
                if column_terms & measure_terms and (not numeric_columns or match.column in numeric_columns):
                    return match.column
        for candidate in (
            "invoice_amount", "total_amount", "amount", "revenue", "budget",
            "project_budget", "salary", "employee_salary", "hours_spent",
        ):
            if candidate in self.graph.columns.get(table, set()):
                return candidate
        for column in numeric_columns:
            if not column.endswith("_id") and column != "id":
                return column
        id_cols = [col for col in table_columns if col.endswith("_id") or col == "id"]
        return id_cols[0] if id_cols else "*"

    def _explicit_requested_columns(self, table: str, entities: EntityExtraction) -> list[tuple[str, str]]:
        query_terms = set(entities.raw_terms) | set(entities.canonical_terms)
        selected: list[str] = []
        for column in self.graph.column_order.get(table, []):
            phrases = {column, column.replace("_", " ")}
            phrases.update(self.column_hints.get(table, {}).get(column, set()))
            if any(self._phrase_terms_match(phrase, query_terms) for phrase in phrases):
                selected.append(column)

        if "name" in query_terms:
            label = self.labels.get(table)
            if label and label in self.graph.columns.get(table, set()) and label not in selected:
                selected.insert(0, label)

        return [(table, column) for column in selected if column in self.graph.columns.get(table, set())]

    def _phrase_terms_match(self, phrase: str, query_terms: set[str]) -> bool:
        terms = set(_tokens(phrase))
        if not terms:
            return False
        if len(terms) == 1:
            term = next(iter(terms))
            return term in query_terms and term not in {"id", "active", "inactive", "completed", "open"}
        return terms.issubset(query_terms)

    def _concise_display_columns(self, table: str, entities: EntityExtraction) -> list[tuple[str, str]]:
        query_terms = set(entities.raw_terms or []) | set(entities.canonical_terms or [])
        detailed_display_terms = {"detail", "details", "profile", "record", "records", "full", "complete"}
        if query_terms & detailed_display_terms:
            detail_columns = [
                col for col in self.defaults.get(table, self.graph.column_order.get(table, [])[:6])
                if col in self.graph.columns.get(table, set())
            ][:8]
            if detail_columns:
                return [(table, column) for column in detail_columns]

        columns: list[str] = []
        label = self.labels.get(table)
        if label and label in self.graph.columns.get(table, set()):
            columns.append(label)

        for item in entities.filters:
            if item["table"] == table and item["column"] not in columns:
                columns.append(item["column"])

        if not columns:
            columns = [
                col for col in self.defaults.get(table, self.graph.column_order.get(table, [])[:3])
                if col in self.graph.columns.get(table, set()) and not col.endswith("_id")
            ][:4]

        if not columns:
            columns = self.graph.column_order.get(table, [])[:1]

        return [(table, column) for column in columns]

    def _best_order_column(self, table: str, matches: list[SchemaMatch]) -> str | None:
        for match in matches:
            if match.kind == "column" and match.table == table and match.column:
                dtype = self.graph.column_types.get(table, {}).get(match.column, "")
                if any(token in str(dtype).lower() for token in ("int", "decimal", "date", "timestamp")):
                    return match.column
        for candidate in ("budget", "amount", "amount_paid", "hours_spent", "created_at", "start_date", "joining_date"):
            if candidate in self.graph.columns.get(table, set()):
                return candidate
        return None


class SQLGenerationAgent:
    def __init__(self, aliases: dict[str, str]) -> None:
        self.aliases = aliases
        self.last_alignment: dict[str, object] = {}

    def generate(self, plan: QueryPlan) -> str:
        if plan.unresolved_terms:
            return "The schema does not have enough information to answer this query."
        if plan.ambiguity_options:
            return "Clarification required before SQL generation."

        aliases = {plan.main_table: self.aliases.get(plan.main_table, plan.main_table[:1])}
        for rel in plan.joins:
            aliases.setdefault(rel.from_table, self.aliases.get(rel.from_table, rel.from_table[:1]))
            aliases.setdefault(rel.to_table, self.aliases.get(rel.to_table, rel.to_table[:1]))
        # ensure aliases exist for any tables referenced in selected_columns even if joins are missing
        for table, _ in getattr(plan, 'selected_columns', []):
            aliases.setdefault(table, self.aliases.get(table, table[:1]))
        for agg in plan.aggregations:
            table = agg["table"]
            aliases.setdefault(table, self.aliases.get(table, table[:1]))

        select_parts: list[str] = []
        time_expression = None
        if plan.time_granularity and plan.time_table and plan.time_column:
            time_alias = aliases[plan.time_table]
            time_expression = (
                f"DATE_TRUNC('{plan.time_granularity}', "
                f"{time_alias}.{plan.time_column})"
            )
            select_parts.append(f"{time_expression} AS {plan.time_granularity}")
        for table, column in plan.selected_columns:
            select_parts.append(f"{aliases[table]}.{column}")
        for agg in plan.aggregations:
            table = agg["table"]
            column = agg["column"]
            target = "*" if column == "*" else f"{aliases[table]}.{column}"
            if plan.running_total and time_expression:
                partition_columns = [
                    f"{aliases[partition_table]}.{partition_column}"
                    for partition_table, partition_column in plan.window_partition_by
                ]
                partition_clause = (
                    "PARTITION BY " + ", ".join(partition_columns) + " "
                    if partition_columns else ""
                )
                select_parts.append(
                    f"SUM(SUM({target})) OVER ({partition_clause}ORDER BY {time_expression}) "
                    f"AS {agg['alias']}"
                )
            else:
                select_parts.append(f"{agg['function']}({target}) AS {agg['alias']}")
        if not select_parts:
            select_parts = [f"{aliases[plan.main_table]}.*"]

        lines = ["SELECT", "  " + ",\n  ".join(select_parts), f"FROM {plan.main_table} {aliases[plan.main_table]}"]
        emitted = {plan.main_table}
        pending = list(plan.joins)
        while pending:
            next_pending: list[SchemaRelationship] = []
            progressed = False
            for rel in pending:
                left_alias = aliases[rel.from_table]
                right_alias = aliases[rel.to_table]
                if rel.from_table in emitted and rel.to_table not in emitted:
                    lines.append(
                        f"JOIN {rel.to_table} {right_alias} ON {left_alias}.{rel.from_column} = {right_alias}.{rel.to_column}"
                    )
                    emitted.add(rel.to_table)
                    progressed = True
                elif rel.to_table in emitted and rel.from_table not in emitted:
                    lines.append(
                        f"JOIN {rel.from_table} {left_alias} ON {left_alias}.{rel.from_column} = {right_alias}.{rel.to_column}"
                    )
                    emitted.add(rel.from_table)
                    progressed = True
                elif rel.from_table in emitted and rel.to_table in emitted:
                    progressed = True
                else:
                    next_pending.append(rel)
            if not progressed:
                break
            pending = next_pending

        filters = []
        for item in plan.filters:
            table = item.get("table", "")
            if table not in aliases:
                continue
            alias = aliases[table]
            if item.get("operator") in {"today", "this_week", "this_month", "this_quarter"}:
                column = item["column"]
                operator = item["operator"]
                if operator == "today":
                    start = "CURRENT_DATE"
                    end = "CURRENT_DATE + INTERVAL '1 day'"
                else:
                    grain = operator.removeprefix("this_")
                    interval = {
                        "week": "7 days",
                        "month": "1 month",
                        "quarter": "3 months",
                    }[grain]
                    start = f"DATE_TRUNC('{grain}', CURRENT_DATE)"
                    end = f"{start} + INTERVAL '{interval}'"
                filters.append(f"{alias}.{column} >= {start} AND {alias}.{column} < {end}")
            else:
                filters.append(
                    f"LOWER({alias}.{item['column']}) {item.get('operator', '=')} "
                    f"'{str(item.get('value', '')).lower()}'"
                )
        if filters:
            lines.append("WHERE " + " AND ".join(filters))
        if plan.group_by:
            group_expressions: list[str] = []
            if time_expression:
                group_expressions.append(time_expression)
            for table, column in plan.group_by:
                if (
                    time_expression
                    and table == plan.time_table
                    and column == plan.time_column
                ):
                    continue
                expression = f"{aliases[table]}.{column}"
                if expression not in group_expressions:
                    group_expressions.append(expression)
            lines.append("GROUP BY " + ", ".join(group_expressions))
        if time_expression:
            lines.append(f"ORDER BY {time_expression} ASC")
        if plan.order_by:
            expr, direction = plan.order_by
            if "." in expr:
                table, col = expr.split(".", 1)
                expr = f"{aliases.get(table, table)}.{col}"
            if not time_expression:
                lines.append(f"ORDER BY {expr} {direction}")
        if plan.limit:
            lines.append(f"LIMIT {plan.limit}")
        sql = "\n".join(lines) + ";"
        self.last_alignment = self.audit_alignment(plan, sql)
        return sql

    def audit_alignment(self, plan: QueryPlan | None, sql: str) -> dict[str, object]:
        if not plan:
            return {"aligned": False, "critical_mismatches": ["missing_plan"]}
        sql_lower = (sql or "").lower()
        sql_tables = set(re.findall(r"\bfrom\s+([a-z_][a-z0-9_]*)\b", sql_lower))
        sql_tables.update(re.findall(r"\bjoin\s+([a-z_][a-z0-9_]*)\b", sql_lower))
        planned_tables = {plan.main_table}
        planned_tables.update(rel.from_table for rel in plan.joins)
        planned_tables.update(rel.to_table for rel in plan.joins)
        selected_columns = {f"{table}.{column}" for table, column in plan.selected_columns}
        selected_column_names = {column for _, column in plan.selected_columns}
        sql_tokens = set(_tokens(sql_lower.replace(".", " ")))
        missing_tables = sorted(planned_tables - sql_tables)
        extra_tables = sorted(sql_tables - planned_tables)
        missing_columns = sorted(
            column for column in selected_column_names
            if column != "*" and column not in sql_tokens
        )
        missing_aggs = sorted(
            agg["function"] for agg in plan.aggregations
            if not re.search(rf"\b{re.escape(agg['function'])}\s*\(", sql, re.IGNORECASE)
        )
        missing_group_by = []
        if plan.group_by and not re.search(r"\bgroup\s+by\b", sql_lower):
            missing_group_by = [f"{table}.{column}" for table, column in plan.group_by]
        critical = missing_tables + extra_tables + missing_aggs + missing_group_by
        return {
            "aligned": not critical and not missing_columns,
            "planned_tables": sorted(planned_tables),
            "sql_tables": sorted(sql_tables),
            "selected_columns": sorted(selected_columns),
            "missing_tables": missing_tables,
            "extra_tables": extra_tables,
            "missing_columns": missing_columns,
            "missing_aggregations": missing_aggs,
            "missing_group_by": missing_group_by,
            "critical_mismatches": critical,
        }


class SQLValidationAgent:
    FORBIDDEN_OPS = {
        "delete", "drop", "truncate", "update", "insert", "alter", "create",
        "exec", "execute", "merge", "grant", "revoke",
    }

    def __init__(self, validator: Callable[[str], tuple[bool, str]]) -> None:
        self.validator = validator

    def validate(self, sql: str, intent: Intent, entities: EntityExtraction, plan: QueryPlan | None) -> tuple[bool, str]:
        sql_lower = sql.lower().strip()
        if not sql_lower.startswith("select"):
            return False, "SQL generation was rejected before SELECT validation"
        if ";" in sql_lower.rstrip(";"):
            return False, "Multiple SQL statements are not allowed"
        for op in self.FORBIDDEN_OPS:
            if re.search(rf"\b{op}\b", sql_lower):
                return False, f"Forbidden operation: '{op}'"
        valid, message = self.validator(sql)
        if not valid:
            return valid, message
        if plan and intent.limit and f"limit {intent.limit}" not in sql.lower():
            return False, "Requested LIMIT is missing"
        for term in plan.unresolved_terms if plan else []:
            return False, f"Unresolved business term: {term}"
        if plan:
            alignment = SQLGenerationAgent({}).audit_alignment(plan, sql)
            if alignment["critical_mismatches"]:
                return False, "Generated SQL does not match planner output: " + ", ".join(alignment["critical_mismatches"])
        return True, "Valid"


_NON_ENTITY_TERMS = {
    "a", "an", "and", "all", "as", "by", "for", "from", "get", "give", "group",
    "list", "me", "of", "on", "per", "show", "the", "to", "top", "with",
}


def _coverage_score(required: list[str], matched: list[str]) -> int:
    unique_required = sorted(set(required))
    if not unique_required:
        return 100
    unique_matched = set(matched)
    return int(round((len(unique_matched & set(unique_required)) / len(unique_required)) * 100))


class SemanticCoverageAgent:
    """Compares the user intent graph to the SQL graph before confidence is assigned."""

    def evaluate(
        self,
        query: str,
        sql: str,
        intent: Intent,
        entities: EntityExtraction,
        matches: list[SchemaMatch],
        plan: QueryPlan | None,
        valid: bool,
        unresolved: list[str],
        ambiguities: list[str],
    ) -> dict[str, object]:
        sql_terms = set(_tokens(sql.replace(".", " ")))
        schema_terms = set()
        for match in matches:
            schema_terms.update(_tokens(match.table.replace("_", " ")))
            if match.column:
                schema_terms.update(_tokens(match.column.replace("_", " ")))

        required_terms = [
            term for term in entities.canonical_terms
            if term not in _NON_ENTITY_TERMS and len(term) > 2
        ]
        matched_terms = [
            term for term in required_terms
            if term in schema_terms or term in sql_terms
        ]

        requested_columns = [
            match.column for match in matches
            if match.kind == "column" and match.column
        ]
        selected_columns = [column for _, column in plan.selected_columns] if plan else []
        sql_column_terms = [
            column for column in requested_columns
            if column in selected_columns or column in sql_terms
        ]

        selected_tables = set()
        if plan:
            selected_tables.add(plan.main_table)
            selected_tables.update(rel.from_table for rel in plan.joins)
            selected_tables.update(rel.to_table for rel in plan.joins)
        required_tables = [
            match.table for match in matches
            if match.kind == "table" or match.score >= 70
        ]
        joined_tables = sorted(selected_tables & set(required_tables))

        requested_aggs = intent.aggregations[:]
        matched_aggs = [
            agg for agg in requested_aggs
            if re.search(rf"\b{re.escape(agg)}\s*\(", sql, re.IGNORECASE)
        ]
        if intent.group_by:
            requested_aggs.append("GROUP_BY")
            if re.search(r"\bGROUP\s+BY\b", sql, re.IGNORECASE):
                matched_aggs.append("GROUP_BY")

        intent_required = required_terms + requested_aggs
        intent_matched = matched_terms + matched_aggs
        join_required = len(set(required_tables)) > 1 or intent.requires_join
        join_score = 100
        if join_required:
            join_score = 100 if plan and plan.joins and len(joined_tables) >= 2 else 35

        coverage = {
            "intent": {
                "score": _coverage_score(intent_required, intent_matched),
                "required": sorted(set(intent_required)),
                "matched": sorted(set(intent_matched)),
                "missing": sorted(set(intent_required) - set(intent_matched)),
            },
            "entity": {
                "score": _coverage_score(required_terms, matched_terms),
                "required": sorted(set(required_terms)),
                "matched": sorted(set(matched_terms)),
                "missing": sorted(set(required_terms) - set(matched_terms) | set(unresolved)),
            },
            "join": {
                "score": join_score,
                "required_tables": sorted(set(required_tables)),
                "joined_tables": joined_tables,
                "missing": [] if join_score == 100 else sorted(set(required_tables) - selected_tables),
            },
            "column": {
                "score": _coverage_score(requested_columns, sql_column_terms),
                "required": sorted(set(requested_columns)),
                "matched": sorted(set(sql_column_terms)),
                "missing": sorted(set(requested_columns) - set(sql_column_terms)),
            },
            "aggregation": {
                "score": _coverage_score(requested_aggs, matched_aggs),
                "required": requested_aggs,
                "matched": matched_aggs,
                "missing": sorted(set(requested_aggs) - set(matched_aggs)),
            },
            "semantic": {
                "valid_sql": valid,
                "unresolved_terms": unresolved,
                "ambiguities": ambiguities,
            },
        }
        semantic_score = int(round((
            coverage["intent"]["score"]
            + coverage["entity"]["score"]
            + coverage["join"]["score"]
            + coverage["column"]["score"]
            + coverage["aggregation"]["score"]
        ) / 5))
        coverage["semantic"]["score"] = semantic_score
        return coverage


class ConfidenceScoringAgentV2:
    weights = {
        "intent_match": 0.30,
        "entity_coverage": 0.25,
        "join_coverage": 0.20,
        "column_coverage": 0.15,
        "aggregation_coverage": 0.10,
    }

    def score(
        self,
        valid: bool,
        unresolved: list[str],
        ambiguities: list[str],
        coverage: dict[str, object],
    ) -> dict[str, float]:
        component_scores = {
            "intent_match": float(coverage["intent"]["score"]),
            "entity_coverage": float(coverage["entity"]["score"]),
            "join_coverage": float(coverage["join"]["score"]),
            "column_coverage": float(coverage["column"]["score"]),
            "aggregation_coverage": float(coverage["aggregation"]["score"]),
        }
        overall = sum(component_scores[name] * weight for name, weight in self.weights.items())
        if not valid:
            overall -= 25
        if unresolved:
            overall -= min(30, len(unresolved) * 12)
        if ambiguities:
            overall -= min(20, len(ambiguities) * 6)
        component_scores["semantic_coverage"] = float(coverage["semantic"]["score"])
        component_scores["overall"] = round(max(0, min(100, overall)), 2)
        return component_scores


class AgentTelemetryAgent:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    query TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    valid INTEGER NOT NULL,
                    intent_score REAL NOT NULL,
                    entity_score REAL NOT NULL,
                    join_score REAL NOT NULL,
                    column_score REAL NOT NULL,
                    aggregation_score REAL NOT NULL,
                    semantic_score REAL NOT NULL,
                    missing_concepts TEXT NOT NULL
                )
                """
            )
            existing_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(agent_telemetry)").fetchall()
            }
            migrations = {
                "provider": "TEXT DEFAULT 'local'",
                "model": "TEXT DEFAULT 'deterministic'",
                "complexity": "TEXT DEFAULT 'SIMPLE'",
                "system_confidence": "REAL DEFAULT 0",
                "model_confidence": "REAL DEFAULT 0",
                "planner_confidence": "REAL DEFAULT 0",
                "validator_confidence": "REAL DEFAULT 0",
                "coverage_confidence": "REAL DEFAULT 0",
                "fallback_used": "INTEGER DEFAULT 0",
                "retry_count": "INTEGER DEFAULT 0",
                "latency_ms": "REAL DEFAULT 0",
            }
            for column, ddl in migrations.items():
                if column not in existing_columns:
                    conn.execute(f"ALTER TABLE agent_telemetry ADD COLUMN {column} {ddl}")

    def record(
        self,
        query: str,
        valid: bool,
        breakdown: dict[str, float],
        coverage: dict[str, object],
        provider_trace: dict[str, object] | None = None,
        complexity: str = "SIMPLE",
    ) -> dict[str, object]:
        provider_trace = provider_trace or {}
        missing = sorted(set(
            coverage["intent"].get("missing", [])
            + coverage["entity"].get("missing", [])
            + coverage["column"].get("missing", [])
            + coverage["aggregation"].get("missing", [])
            + coverage["join"].get("missing", [])
        ))
        payload = {
            "confidence": breakdown["overall"],
            "valid": valid,
            "intent_accuracy": breakdown.get("intent", 0.0),
            "planner_accuracy": breakdown.get("entity", 0.0),
            "validation_accuracy": breakdown.get("semantic", 0.0),
            "optimization_accuracy": 100.0 if valid else 0.0,
            "missing_concepts": missing,
            "provider": provider_trace.get("provider", "local"),
            "model": provider_trace.get("model", "deterministic"),
            "complexity": complexity,
            "system_confidence": breakdown.get("system_confidence", breakdown.get("overall", 0.0)),
            "model_confidence": breakdown.get("model_confidence", 0.0),
            "planner_confidence": breakdown.get("planner_confidence", 0.0),
            "validator_confidence": breakdown.get("validator_confidence", 0.0),
            "coverage_confidence": breakdown.get("coverage_confidence", 0.0),
            "fallback_used": bool(provider_trace.get("fallback_used")),
            "retry_count": int(provider_trace.get("retry_count") or 0),
            "latency_ms": sum(
                float(stage.get("latency_ms") or 0.0)
                for stage in provider_trace.get("stages", [])
                if isinstance(stage, dict)
            ),
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agent_telemetry (
                    query, confidence, valid, intent_score, entity_score, join_score,
                    column_score, aggregation_score, semantic_score, missing_concepts,
                    provider, model, complexity, system_confidence, model_confidence,
                    planner_confidence, validator_confidence, coverage_confidence,
                    fallback_used, retry_count, latency_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query,
                    breakdown["overall"],
                    int(valid),
                    breakdown.get("intent", 0.0),
                    breakdown.get("entity", 0.0),
                    breakdown.get("join", 0.0),
                    breakdown.get("column", 0.0),
                    breakdown.get("aggregation", 0.0),
                    breakdown.get("semantic", 0.0),
                    json.dumps(missing),
                    str(payload["provider"]),
                    str(payload["model"]),
                    complexity,
                    float(payload["system_confidence"]),
                    float(payload["model_confidence"]),
                    float(payload["planner_confidence"]),
                    float(payload["validator_confidence"]),
                    float(payload["coverage_confidence"]),
                    int(payload["fallback_used"]),
                    int(payload["retry_count"]),
                    float(payload["latency_ms"]),
                ),
            )
        return payload


class SQLOptimizationEngine:
    def analyze(self, sql: str, plan: QueryPlan | None) -> list[str]:
        suggestions: list[str] = []
        if re.search(r"\bselect\s+\w+\.\*", sql, re.IGNORECASE):
            suggestions.append("Avoid SELECT * in production views; prefer explicit columns.")
        if plan:
            for rel in plan.joins:
                suggestions.append(f"Index suggested: {rel.from_table}.{rel.from_column}")
                suggestions.append(f"Index suggested: {rel.to_table}.{rel.to_column}")
            for item in plan.filters:
                suggestions.append(f"Index suggested for filter: {item['table']}.{item['column']}")
        return sorted(set(suggestions))


class EnterpriseSQLCopilot:
    def __init__(
        self,
        tables: set[str],
        columns: dict[str, set[str]],
        column_order: dict[str, list[str]],
        column_types: dict[str, dict],
        relationships: dict[str, list[tuple[str, str, str]]],
        table_hints: dict[str, set[str]],
        column_hints: dict[str, dict[str, set[str]]],
        value_filters: dict[str, dict],
        aliases: dict[str, str],
        defaults: dict[str, list[str]],
        labels: dict[str, str],
        validator: Callable[[str], tuple[bool, str]],
        state_db_path: Path,
        logs_root: Path | None = None,
        llm_provider: Any | None = None,
        max_generation_retries: int = 3,
        confidence_low_threshold: int = 75,
        confidence_high_threshold: int = 90,
        max_join_depth: int | None = None,
    ) -> None:
        self.graph = SchemaGraphEngine(tables, columns, column_order, column_types, relationships)
        self.vocabulary = BusinessVocabularyEngine(state_db_path)
        self.llm_provider = llm_provider
        self.cache_namespace = self._provider_cache_namespace(llm_provider)
        self.cache = QueryCacheLayer(state_db_path, namespace=self.cache_namespace)
        self.intent_agent = IntentDetectionAgent()
        self.entity_agent = EntityExtractionAgent(self.vocabulary, value_filters)
        self.linking_agent = SchemaLinkingEngine(self.graph, table_hints, column_hints, self.vocabulary)
        configured_join_depth = max_join_depth or int(os.getenv("SQL_COPILOT_MAX_JOIN_DEPTH", "8"))
        self.join_agent = JoinDiscoveryAgent(self.graph, max_depth=configured_join_depth)
        self.planner_agent = QueryPlannerAgent(self.graph, self.join_agent, defaults, labels, column_hints)
        # attach display selector and join-path coverage agent if available
        try:
            from .coverage_agents import DisplayColumnSelectionAgent, JoinPathCoverageAgent
            self.planner_agent.display_selector = DisplayColumnSelectionAgent()
            self.join_path_coverage = JoinPathCoverageAgent()
        except Exception:
            self.join_path_coverage = None
        self.sql_agent = SQLGenerationAgent(aliases)
        self.validation_agent = SQLValidationAgent(validator)
        self.semantic_agent = SemanticCoverageAgent()
        self.workflow = build_sql_copilot_workflow()
        self.max_generation_retries = max(1, int(max_generation_retries))
        self.confidence_low_threshold = int(confidence_low_threshold)
        self.confidence_high_threshold = int(confidence_high_threshold)
        production = os.getenv("APP_ENV", "development").lower() == "production"
        self.experiment_flags = {
            "USE_SCHEMA_GRAPH": _env_flag("USE_SCHEMA_GRAPH", True),
            "USE_BUSINESS_LOGIC": _env_flag("USE_BUSINESS_LOGIC", True),
            "USE_HYBRID_RETRIEVAL": _env_flag("USE_HYBRID_RETRIEVAL", True),
            "USE_LLM_PLANNER": _env_flag("USE_LLM_PLANNER", True),
            "USE_LLM_CRITIC": _env_flag("USE_LLM_CRITIC", True),
            "USE_VALIDATOR": True if production else _env_flag("USE_VALIDATOR", True),
        }
        # coverage agents
        self.intent_coverage = IntentCoverageAgent()
        self.entity_coverage = EntityCoverageAgent()
        self.column_coverage = ColumnCoverageAgent()
        self.join_coverage = JoinCoverageAgent()
        self.agg_coverage = AggregationCoverageAgent()
        # coordinator
        self.confidence_coordinator = ConfidenceCoordinator()
        self.telemetry_agent = AgentTelemetryAgent(state_db_path)
        self.optimization_agent = SQLOptimizationEngine()
        self.logs_root = logs_root or Path("logs")
        self.runtime_counters = {
            "intent_agent_calls": 0,
            "entity_agent_calls": 0,
            "schema_retrieval_calls": 0,
            "planner_calls": 0,
            "validator_calls": 0,
            "confidence_calls": 0,
            "sql_generator_calls": 0,
            "resolver_calls": 0,
            "coverage_calls": 0,
        }
        for name in ("planner", "validator", "benchmark", "confidence", "feedback", "frontend", "api"):
            try:
                (self.logs_root / name).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

    def _provider_cache_namespace(self, provider: Any | None) -> str:
        if provider is None or not hasattr(provider, "health_check"):
            return "local:deterministic:unavailable"
        try:
            status = dict(provider.health_check(deep=False))
        except Exception:
            return "unknown:unknown:unavailable"
        parts = [
            str(status.get("provider") or "local"),
            str(status.get("adapter") or ""),
            str(status.get("model") or "deterministic"),
            "available" if status.get("available") else "unavailable",
        ]
        return re.sub(r"[^a-zA-Z0-9_.:-]+", "_", ":".join(parts))[:180]

    def _trace_mark(
        self,
        trace: dict[str, object],
        counter_name: str,
        stage: str,
        started_at: float,
        extra: dict[str, object] | None = None,
    ) -> None:
        self.runtime_counters[counter_name] = self.runtime_counters.get(counter_name, 0) + 1
        event = {
            "stage": stage,
            "counter": counter_name,
            "count": self.runtime_counters[counter_name],
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
        }
        if extra:
            event.update(extra)
        trace.setdefault("events", []).append(event)

    def _write_runtime_logs(self, request_id: str, payload: dict[str, object]) -> None:
        for name, keys in {
            "api": ("query", "sql", "valid", "execution_trace", "runtime_metrics"),
            "planner": ("query", "plan", "selected_tables", "selected_columns", "join_path"),
            "confidence": ("query", "confidence_breakdown", "confidence_evidence", "coverage_report", "llm_trace"),
            "benchmark": ("benchmark_record",),
        }.items():
            try:
                target = self.logs_root / name / f"{request_id}.json"
                data = {key: payload.get(key) for key in keys}
                target.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            except OSError:
                continue

    def _provider_status(self) -> dict[str, object]:
        provider = self.llm_provider
        if provider is None or not hasattr(provider, "health_check"):
            return {
                "provider": "local",
                "model": "deterministic",
                "configured": False,
                "available": False,
                "status": "fallback",
            }
        try:
            return dict(provider.health_check(deep=False))
        except Exception:
            return {
                "provider": "unknown",
                "model": "unknown",
                "configured": False,
                "available": False,
                "status": "fallback",
            }

    def _provider_metrics(self) -> dict[str, object]:
        provider = self.llm_provider
        if provider is None or not hasattr(provider, "metrics"):
            return {}
        try:
            return dict(provider.metrics())
        except Exception:
            return {}

    def _coverage_applicable(self, report: dict[str, object] | None, *, join: bool = False) -> bool:
        report = report or {}
        if join:
            required_tables = list(report.get("required_tables") or [])
            joined_tables = list(report.get("joined_tables") or [])
            return len(required_tables) > 1 or len(joined_tables) > 1 or bool(report.get("missing"))
        return bool(report.get("required") or report.get("matched") or report.get("missing"))

    def _confidence_evidence_item(
        self,
        key: str,
        label: str,
        score: float | None,
        report: dict[str, object] | None = None,
        *,
        applicable: bool = True,
        note: str = "",
    ) -> dict[str, object]:
        report = report or {}
        missing = list(report.get("missing") or report.get("missing_joins") or [])
        required = list(report.get("required") or report.get("required_tables") or [])
        matched = list(report.get("matched") or report.get("joined_tables") or [])
        if not applicable:
            status = "not_applicable"
        elif missing:
            status = "failed"
        elif score is None:
            status = "not_applicable"
        elif score >= 90:
            status = "passed"
        elif score >= 70:
            status = "warning"
        else:
            status = "failed"
        return {
            "key": key,
            "label": label,
            "score": None if not applicable else round(float(score or 0.0), 2),
            "applicable": applicable,
            "status": status,
            "required": [str(item) for item in required],
            "matched": [str(item) for item in matched],
            "missing": [str(item) for item in missing],
            "note": note,
        }

    def _confidence_evidence(
        self,
        components: dict[str, float],
        coverage: dict[str, object],
        component_applicability: dict[str, bool],
        *,
        plan: QueryPlan | None,
        llm_trace: dict[str, object],
        planner_confidence: float,
        validator_confidence: float,
        coverage_confidence: float,
        model_confidence: float,
    ) -> list[dict[str, object]]:
        model_applicable = bool(llm_trace.get("active")) and not bool(llm_trace.get("fallback_used"))
        model_note = self._model_evidence_note(llm_trace, model_applicable)
        model_report = (
            {
                "required": ["nvidia_sql_assist"],
                "matched": ["nvidia_sql_assist"],
                "missing": [],
            }
            if model_applicable
            else {"required": [], "matched": [], "missing": []}
        )
        return [
            self._confidence_evidence_item(
                "intent",
                "Intent",
                components.get("intent", 0.0),
                coverage.get("intent") if isinstance(coverage.get("intent"), dict) else {},
                applicable=component_applicability.get("intent", True),
                note="Operation, grouping, time range, and aggregation intent.",
            ),
            self._confidence_evidence_item(
                "entity",
                "Entity Resolution",
                components.get("entity", 0.0),
                coverage.get("entity") if isinstance(coverage.get("entity"), dict) else {},
                applicable=component_applicability.get("entity", False),
                note="Business terms mapped to schema concepts.",
            ),
            self._confidence_evidence_item(
                "column",
                "Column Coverage",
                components.get("column", 0.0),
                coverage.get("column") if isinstance(coverage.get("column"), dict) else {},
                applicable=component_applicability.get("column", False),
                note="Explicitly requested columns present in the plan.",
            ),
            self._confidence_evidence_item(
                "join",
                "Join Path",
                components.get("join", 0.0),
                coverage.get("join") if isinstance(coverage.get("join"), dict) else {},
                applicable=component_applicability.get("join", False),
                note="Required table hops resolved through the schema graph.",
            ),
            self._confidence_evidence_item(
                "aggregation",
                "Aggregation",
                components.get("aggregation", 0.0),
                coverage.get("aggregation") if isinstance(coverage.get("aggregation"), dict) else {},
                applicable=component_applicability.get("aggregation", False),
                note="COUNT, SUM, GROUP BY, and window requirements.",
            ),
            self._confidence_evidence_item(
                "semantic",
                "Semantic Alignment",
                components.get("semantic", 0.0),
                coverage.get("semantic") if isinstance(coverage.get("semantic"), dict) else {},
                applicable=component_applicability.get("semantic", True),
                note="Final SQL terms compared with the request.",
            ),
            self._confidence_evidence_item(
                "validation",
                "SQL Validator",
                validator_confidence,
                coverage.get("validation") if isinstance(coverage.get("validation"), dict) else {},
                applicable=True,
                note=str((coverage.get("validation") or {}).get("message", "")) if isinstance(coverage.get("validation"), dict) else "",
            ),
            self._confidence_evidence_item(
                "planner_confidence",
                "Planner",
                planner_confidence,
                {"required": ["query_plan"], "matched": ["query_plan"] if plan else [], "missing": [] if plan else ["query_plan"]},
                applicable=True,
                note="Deterministic plan quality before SQL generation.",
            ),
            self._confidence_evidence_item(
                "coverage_confidence",
                "Applicable Coverage",
                coverage_confidence,
                {"required": [key for key, enabled in component_applicability.items() if enabled]},
                applicable=True,
                note="Average across checks that apply to this request.",
            ),
            self._confidence_evidence_item(
                "model_confidence",
                "LLM Model",
                model_confidence,
                model_report,
                applicable=model_applicable,
                note=model_note,
            ),
        ]

    def _model_evidence_note(self, llm_trace: dict[str, object], model_applicable: bool) -> str:
        if model_applicable:
            return "NVIDIA critique/generation used for this request."
        if llm_trace.get("skip_reason") == "deterministic_plan_validated":
            return "Deterministic plan validated; LLM assist was not needed."
        reason = str(llm_trace.get("fallback_reason") or "")
        if not llm_trace.get("active"):
            return "LLM assist was skipped; deterministic SQL was used."
        if reason == "provider_error":
            return "NVIDIA assist could not connect; deterministic SQL was used."
        if reason == "timeout":
            return "NVIDIA assist timed out; deterministic SQL was used."
        if reason == "rate_limit":
            return "NVIDIA assist was rate limited; deterministic SQL was used."
        if reason == "configuration":
            return "NVIDIA assist needs a valid provider configuration; deterministic SQL was used."
        if reason == "network_blocked":
            return "Backend network access to NVIDIA is blocked; deterministic SQL was used."
        if reason == "candidate_failed_validation":
            return "NVIDIA candidate failed deterministic validation; deterministic SQL was used."
        if reason == "provider_unavailable":
            return "NVIDIA assist is unavailable; deterministic SQL was used."
        return "LLM assist was not applied; deterministic SQL was used."

    def _confidence_band(self, confidence: float) -> str:
        if confidence >= self.confidence_high_threshold:
            return "HIGH"
        if confidence >= self.confidence_low_threshold:
            return "MEDIUM"
        return "LOW"

    def _plan_tables(self, plan: QueryPlan | None) -> set[str]:
        if not plan:
            return set()
        return {
            plan.main_table,
            *[rel.from_table for rel in plan.joins],
            *[rel.to_table for rel in plan.joins],
            *[table for table, _column in plan.selected_columns],
            *[table for table, _column in plan.group_by],
            *[str(item.get("table", "")) for item in plan.filters],
            *[str(item.get("table", "")) for item in plan.aggregations],
        } - {""}

    def _query_complexity(
        self,
        intent: Intent,
        entities: EntityExtraction,
        matches: list[SchemaMatch],
        plan: QueryPlan | None,
    ) -> str:
        table_count = len(self._plan_tables(plan))
        join_count = len(plan.joins) if plan else 0
        filter_count = len(plan.filters) if plan else len(entities.filters)
        dimension_count = len(plan.group_by or plan.selected_columns) if plan else 0
        aggregation_count = len(intent.aggregations)
        high_score_matches = len([match for match in matches if match.score >= 70])
        if table_count >= 5 or join_count >= 4:
            return "ENTERPRISE"
        if table_count >= 3 or join_count >= 2 or (aggregation_count and dimension_count >= 2):
            return "COMPLEX"
        if table_count == 2 or aggregation_count or filter_count or high_score_matches >= 3:
            return "MODERATE"
        return "SIMPLE"

    def _relationship_exists(self, rel: SchemaRelationship) -> bool:
        for existing in self.graph.relationships:
            if (
                existing.from_table == rel.from_table
                and existing.from_column == rel.from_column
                and existing.to_table == rel.to_table
                and existing.to_column == rel.to_column
            ):
                return True
            if (
                existing.from_table == rel.to_table
                and existing.from_column == rel.to_column
                and existing.to_table == rel.from_table
                and existing.to_column == rel.from_column
            ):
                return True
        return False

    def _validate_query_plan(self, plan: QueryPlan | None) -> list[str]:
        if plan is None:
            return ["missing_plan"]
        errors: list[str] = []
        for table in self._plan_tables(plan):
            if table not in self.graph.tables:
                errors.append(f"unknown_table:{table}")
        for table, column in [
            *plan.selected_columns,
            *plan.group_by,
            *[(str(item.get("table", "")), str(item.get("column", ""))) for item in plan.filters],
        ]:
            if table and column and table in self.graph.tables and column not in self.graph.columns.get(table, set()):
                errors.append(f"unknown_column:{table}.{column}")
        for aggregation in plan.aggregations:
            table = str(aggregation.get("table", ""))
            column = str(aggregation.get("column", ""))
            if table and table not in self.graph.tables:
                errors.append(f"unknown_aggregation_table:{table}")
            if column and column != "*" and table in self.graph.tables and column not in self.graph.columns.get(table, set()):
                errors.append(f"unknown_aggregation_column:{table}.{column}")
        for rel in plan.joins:
            if not self._relationship_exists(rel):
                errors.append(
                    "unknown_relationship:"
                    f"{rel.from_table}.{rel.from_column}->{rel.to_table}.{rel.to_column}"
                )
        if len(self._plan_tables(plan)) > 1 and not plan.joins:
            errors.append("disconnected_tables")
        return sorted(set(errors))

    def _plan_ir(
        self,
        intent: Intent,
        entities: EntityExtraction,
        plan: QueryPlan | None,
        complexity: str,
    ) -> dict[str, object]:
        if plan is None:
            return {"intent": intent.operation, "complexity": complexity, "tables": []}
        return {
            "intent": intent.operation,
            "complexity": complexity,
            "measures": list(entities.measures),
            "dimensions": [f"{table}.{column}" for table, column in plan.selected_columns],
            "tables": sorted(self._plan_tables(plan)),
            "main_table": plan.main_table,
            "joins": [
                {
                    "from_table": rel.from_table,
                    "from_column": rel.from_column,
                    "to_table": rel.to_table,
                    "to_column": rel.to_column,
                }
                for rel in plan.joins
            ],
            "filters": list(plan.filters),
            "aggregations": list(plan.aggregations),
            "group_by": [f"{table}.{column}" for table, column in plan.group_by],
            "order_by": plan.order_by,
            "limit": plan.limit,
            "time_granularity": plan.time_granularity,
            "running_total": plan.running_total,
        }

    def _llm_schema_context(
        self,
        plan: QueryPlan | None,
        matches: list[SchemaMatch],
        *,
        top_k_tables: int = 10,
        top_k_columns: int = 80,
    ) -> dict[str, object]:
        plan_tables = list(self._plan_tables(plan))
        ranked_tables: list[str] = []
        for table in plan_tables:
            if table and table not in ranked_tables:
                ranked_tables.append(table)
        for match in matches:
            if match.table not in ranked_tables and len(ranked_tables) < top_k_tables:
                ranked_tables.append(match.table)
        allowed_tables = [table for table in ranked_tables if table in self.graph.tables][:top_k_tables]
        allowed_columns: dict[str, list[dict[str, str]]] = {}
        remaining_columns = top_k_columns
        for table in allowed_tables:
            table_columns = []
            for column in self.graph.column_order.get(table, []):
                if remaining_columns <= 0:
                    break
                table_columns.append({
                    "name": column,
                    "data_type": str(self.graph.column_types.get(table, {}).get(column, "")),
                })
                remaining_columns -= 1
            allowed_columns[table] = table_columns
        allowed_relationships = []
        allowed_set = set(allowed_tables)
        for rel in self.graph.relationships:
            if rel.from_table in allowed_set and rel.to_table in allowed_set:
                allowed_relationships.append({
                    "from_table": rel.from_table,
                    "from_column": rel.from_column,
                    "to_table": rel.to_table,
                    "to_column": rel.to_column,
                })
        return {
            "tables": allowed_tables,
            "columns": allowed_columns,
            "relationships": allowed_relationships if self.experiment_flags.get("USE_SCHEMA_GRAPH", True) else [],
        }

    def _strip_sql_fences(self, value: object) -> str:
        sql = str(value or "").strip()
        sql = re.sub(r"^```[a-zA-Z]*\n?", "", sql).rstrip("`").strip()
        return sql

    def _model_confidence(self, data: dict[str, Any] | None) -> float:
        if not data:
            return 0.0
        raw = data.get("model_confidence", data.get("confidence", 0))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 0.0
        if 0 <= value <= 1:
            value *= 100
        return round(max(0.0, min(100.0, value)), 2)

    def _llm_payload(
        self,
        query: str,
        intent: Intent,
        entities: EntityExtraction,
        matches: list[SchemaMatch],
        plan: QueryPlan | None,
        complexity: str,
        deterministic_sql: str,
        plan_validation_errors: list[str],
    ) -> dict[str, object]:
        return {
            "user_request": query,
            "query_complexity": complexity,
            "validated_plan": self._plan_ir(intent, entities, plan, complexity),
            "plan_validation": {
                "valid": not plan_validation_errors,
                "errors": plan_validation_errors,
            },
            "allowed_schema": self._llm_schema_context(plan, matches),
            "business_terms": {
                "canonical_terms": entities.canonical_terms,
                "measures": entities.measures,
                "filters": entities.filters,
                "registered_rules": (
                    self.vocabulary.rules_for_terms(entities.canonical_terms)
                    if self.experiment_flags.get("USE_BUSINESS_LOGIC", True)
                    else {}
                ),
            },
            "experiment_flags": dict(self.experiment_flags),
            "deterministic_sql_candidate": deterministic_sql,
            "strict_rules": [
                "Return one read-only SELECT statement only.",
                "Use only tables, columns, and relationships from allowed_schema.",
                "Do not invent schema objects, aliases, joins, or business rules.",
                "If the provided schema cannot satisfy the request, return clarification_required=true and sql=null.",
                "Return concise reasoning summaries only; do not include hidden chain-of-thought.",
            ],
        }

    def _record_provider_fallback(self, category: str) -> None:
        provider = self.llm_provider
        if provider is not None and hasattr(provider, "record_fallback"):
            try:
                provider.record_fallback(category)
            except Exception:
                pass

    def _generate_sql_with_optional_llm(
        self,
        query: str,
        intent: Intent,
        entities: EntityExtraction,
        matches: list[SchemaMatch],
        plan: QueryPlan | None,
        complexity: str,
        deterministic_sql: str,
        deterministic_alignment: dict[str, object],
        plan_validation_errors: list[str],
    ) -> tuple[str, dict[str, object], dict[str, object]]:
        status = self._provider_status()
        trace: dict[str, object] = {
            "provider": status.get("provider", "local"),
            "model": status.get("model", "deterministic"),
            "active": False,
            "fallback_used": False,
            "fallback_reason": "",
            "retry_count": 0,
            "stages": [],
            "plan_validation": {
                "valid": not plan_validation_errors,
                "errors": plan_validation_errors,
            },
        }
        provider = self.llm_provider
        deterministic_ready = bool(
            plan
            and not plan_validation_errors
            and plan.confidence >= 90
            and str(deterministic_sql or "").lstrip().lower().startswith("select")
            and deterministic_alignment.get("aligned")
            and complexity in {"SIMPLE", "MODERATE"}
        )
        if deterministic_ready:
            trace["skip_reason"] = "deterministic_plan_validated"
            return deterministic_sql, deterministic_alignment, trace

        if (
            provider is None
            or not getattr(provider, "available", False)
            or plan is None
            or plan_validation_errors
            or plan.unresolved_terms
            or plan.ambiguity_options
        ):
            reason = "provider_unavailable"
            if plan_validation_errors:
                reason = "plan_validation_failed"
            elif plan and (plan.unresolved_terms or plan.ambiguity_options):
                reason = "clarification_required_before_llm"
            trace.update({"fallback_used": True, "fallback_reason": reason})
            self._record_provider_fallback(reason)
            return deterministic_sql, deterministic_alignment, trace

        payload = self._llm_payload(
            query,
            intent,
            entities,
            matches,
            plan,
            complexity,
            deterministic_sql,
            plan_validation_errors,
        )
        trace["active"] = True
        model_confidence = 0.0

        if complexity in {"COMPLEX", "ENTERPRISE"} and self.experiment_flags.get("USE_LLM_PLANNER", True):
            review_prompt = (
                "You are reviewing a deterministic, schema-grounded text-to-SQL plan. "
                "Return only JSON with keys: approved, issues, missing_requirements, "
                "unnecessary_joins, aggregation_issues, semantic_issues, "
                "reasoning_summary, clarification_required, clarification_question, model_confidence. "
                "This review is advisory; the deterministic validator remains authoritative."
            )
            review = provider.generate_structured(review_prompt, payload)
            trace["stages"].append({
                "stage": "plan_review",
                "success": review.success,
                "latency_ms": review.latency_ms,
                "error_category": review.error_category,
                "error_message": getattr(review, "error_message", ""),
                "retry_count": review.retry_count,
                "summary": (review.data or {}).get("reasoning_summary") if review.data else "",
                "approved": (review.data or {}).get("approved") if review.data else None,
            })
            model_confidence = max(model_confidence, self._model_confidence(review.data))
            if not review.success:
                trace.update({
                    "fallback_used": True,
                    "fallback_reason": review.error_category or "plan_review_failed",
                })
                return deterministic_sql, deterministic_alignment, trace

        generation_prompt = (
            "Generate SQL from the validated query plan and allowed schema. "
            "Return only JSON with keys: intent, entities, measures, dimensions, filters, "
            "required_tables, join_requirements, aggregations, group_by, order_by, "
            "query_plan_reasoning, sql, clarification_required, clarification_question, model_confidence. "
            "The SQL must be a single read-only SELECT using only the allowed schema and validated plan."
        )
        generation = provider.generate_structured(generation_prompt, payload)
        trace["stages"].append({
            "stage": "sql_generation",
            "success": generation.success,
            "latency_ms": generation.latency_ms,
            "error_category": generation.error_category,
            "error_message": getattr(generation, "error_message", ""),
            "retry_count": generation.retry_count,
            "summary": (generation.data or {}).get("query_plan_reasoning") if generation.data else "",
        })
        model_confidence = max(model_confidence, self._model_confidence(generation.data))
        if not generation.success:
            trace.update({
                "fallback_used": True,
                "fallback_reason": generation.error_category or "generation_failed",
                "model_confidence": model_confidence,
            })
            return deterministic_sql, deterministic_alignment, trace

        candidate_sql = self._strip_sql_fences((generation.data or {}).get("sql"))
        if not candidate_sql:
            trace.update({
                "fallback_used": True,
                "fallback_reason": "schema_insufficient" if (generation.data or {}).get("clarification_required") else "empty_sql",
                "clarification_question": (generation.data or {}).get("clarification_question"),
                "model_confidence": model_confidence,
            })
            self._record_provider_fallback(str(trace["fallback_reason"]))
            return deterministic_sql, deterministic_alignment, trace

        validation_attempts: list[dict[str, object]] = []
        candidate_alignment: dict[str, object] = {}
        for attempt in range(0, self.max_generation_retries):
            valid, validation_message = self.validation_agent.validate(candidate_sql, intent, entities, plan)
            candidate_alignment = self.sql_agent.audit_alignment(plan, candidate_sql)
            aligned = bool(candidate_alignment.get("aligned"))
            validation_attempts.append({
                "attempt": attempt + 1,
                "valid": valid,
                "aligned": aligned,
                "validation": validation_message,
                "alignment": candidate_alignment,
            })
            if valid and aligned:
                critique_score = 0.0
                if complexity in {"COMPLEX", "ENTERPRISE"} and self.experiment_flags.get("USE_LLM_CRITIC", True):
                    critique_prompt = (
                        "Critique this generated SQL against the user request, validated query plan, "
                        "allowed schema, and validator result. Return only JSON with keys: issues, "
                        "missing_requirements, unnecessary_joins, aggregation_issues, semantic_issues, "
                        "approved, reasoning_summary, model_confidence."
                    )
                    critique_payload = {
                        **payload,
                        "generated_sql": candidate_sql,
                        "validation_result": validation_attempts[-1],
                    }
                    critique = provider.generate_structured(critique_prompt, critique_payload)
                    trace["stages"].append({
                        "stage": "sql_critique",
                        "success": critique.success,
                        "latency_ms": critique.latency_ms,
                        "error_category": critique.error_category,
                        "error_message": getattr(critique, "error_message", ""),
                        "summary": (critique.data or {}).get("reasoning_summary") if critique.data else "",
                        "approved": (critique.data or {}).get("approved") if critique.data else None,
                    })
                    critique_score = self._model_confidence(critique.data)
                trace.update({
                    "fallback_used": False,
                    "fallback_reason": "",
                    "retry_count": attempt,
                    "validation_attempts": validation_attempts,
                    "model_confidence": max(model_confidence, critique_score),
                })
                return candidate_sql, candidate_alignment, trace

            if attempt >= self.max_generation_retries - 1:
                break
            if hasattr(provider, "repair_attempts"):
                try:
                    provider.repair_attempts += 1
                except Exception:
                    pass
            repair_prompt = (
                "Repair the SQL using the exact validator and planner-alignment failures. "
                "Return only JSON with keys: sql, query_plan_reasoning, clarification_required, "
                "clarification_question, model_confidence. Use only the allowed schema and validated plan."
            )
            repair_payload = {
                **payload,
                "bad_sql": candidate_sql,
                "validation_failure": validation_message,
                "alignment_failure": candidate_alignment,
            }
            repair_result = provider.generate_structured(repair_prompt, repair_payload)
            trace["stages"].append({
                "stage": "sql_repair",
                "success": repair_result.success,
                "latency_ms": repair_result.latency_ms,
                "error_category": repair_result.error_category,
                "error_message": getattr(repair_result, "error_message", ""),
                "retry_count": attempt + 1,
                "summary": (repair_result.data or {}).get("query_plan_reasoning") if repair_result.data else "",
            })
            trace["retry_count"] = attempt + 1
            model_confidence = max(model_confidence, self._model_confidence(repair_result.data))
            if not repair_result.success:
                break
            repaired_sql = self._strip_sql_fences((repair_result.data or {}).get("sql"))
            if not repaired_sql:
                break
            candidate_sql = repaired_sql

        trace.update({
            "fallback_used": True,
            "fallback_reason": "candidate_failed_validation",
            "validation_attempts": validation_attempts,
            "model_confidence": model_confidence,
        })
        self._record_provider_fallback("candidate_failed_validation")
        return deterministic_sql, deterministic_alignment, trace

    def _custody_balance_relationships(self) -> list[SchemaRelationship]:
        required = {
            ("custody_position", "portfolio_id", "portfolio", "portfolio_id"),
            ("custody_position", "business_partner_id", "portfolio", "business_partner_id"),
            ("security_movement", "customer_reference", "custody_position", "business_partner_id"),
            ("security_movement", "portfolio_number", "custody_position", "portfolio_id"),
            ("security_movement", "instrument_id", "custody_position", "instrument_id"),
            ("security_movement", "custody_position_number", "custody_position", "position_number"),
            ("security_movement", "custody_position_type", "custody_position", "position_type"),
            ("custody_block", "business_partner_id", "custody_position", "business_partner_id"),
            ("custody_block", "portfolio_id", "custody_position", "portfolio_id"),
            ("custody_block", "instrument_id", "custody_position", "instrument_id"),
            ("custody_block", "position_number", "custody_position", "position_number"),
            ("custody_block", "position_type", "custody_position", "position_type"),
        }
        joins: list[SchemaRelationship] = []
        for rel in CUSTODY_BALANCE_RELATIONSHIPS:
            key = (
                str(rel.get("from_table", "")),
                str(rel.get("from_column", "")),
                str(rel.get("to_table", "")),
                str(rel.get("to_column", "")),
            )
            if key in required:
                joins.append(SchemaRelationship(*key))
        return joins

    def _custody_balance_matches(self) -> list[SchemaMatch]:
        matches: list[SchemaMatch] = [
            SchemaMatch("table", "portfolio", None, 96, "custody balance business logic"),
            SchemaMatch("table", "custody_position", None, 100, "position-level balance source"),
            SchemaMatch("table", "security_movement", None, 98, "settled balance source"),
            SchemaMatch("table", "custody_block", None, 98, "blocked balance source"),
        ]
        for table, columns in {
            "custody_position": [
                "business_partner_id",
                "portfolio_id",
                "position_number",
                "position_type",
                "instrument_id",
            ],
            "security_movement": [
                "customer_reference",
                "portfolio_number",
                "credit_and_debit_flag",
                "amount_quantity",
                "trade_date",
                "value_date",
                "transaction_date",
            ],
            "custody_block": [
                "block_quantity_amount",
                "block_valid_from_date",
                "block_release_date",
                "block_status",
                "block_status_code",
            ],
        }.items():
            matches.extend(
                SchemaMatch("column", table, column, 94, "custody balance rule column")
                for column in columns
            )
        return matches

    def _custody_balance_provider_review(
        self,
        query: str,
        request: BalanceRequest,
        sql: str,
        plan: QueryPlan,
        validation: str,
    ) -> tuple[dict[str, object], float]:
        status = self._provider_status()
        trace: dict[str, object] = {
            "provider": status.get("provider", "local"),
            "model": status.get("model", "deterministic"),
            "active": False,
            "fallback_used": False,
            "fallback_reason": "",
            "retry_count": 0,
            "stages": [
                {
                    "stage": "business_logic_lookup",
                    "success": True,
                    "summary": "Matched custody available-balance rule and assembled schema-grounded SQL.",
                    "matched_rule": "custody_available_balance",
                }
            ],
            "plan_validation": {"valid": True, "errors": []},
            "model_confidence": 0.0,
        }
        provider = self.llm_provider
        if provider is None or not getattr(provider, "available", False):
            return trace, 0.0

        trace["active"] = True
        prompt = (
            "Review this schema-grounded custody balance SQL against the business rule. "
            "Return only JSON with keys: approved, issues, missing_requirements, "
            "reasoning_summary, model_confidence. Do not rewrite the SQL unless it violates "
            "the provided rule."
        )
        payload = {
            "user_request": query,
            "business_rule": {
                "name": "custody_available_balance",
                "inputs": balance_request_summary(request),
                "steps": [
                    "Validate portfolio exists for the requested customer and portfolio.",
                    "Fetch position-level custody_position records.",
                    "Calculate settled balance from security_movement amount_quantity; credit_and_debit_flag 1 adds, 2 subtracts.",
                    "Calculate blocked balance from active custody_block rows valid as of the balance date.",
                    "Return available_balance as settled_balance minus blocked_balance.",
                ],
            },
            "validated_plan": self._plan_ir(
                Intent(aggregations=["SUM"], requires_join=True),
                EntityExtraction(_tokens(query), _tokens(query), [], [], ["available_balance"], [], []),
                plan,
                "ENTERPRISE",
            ),
            "validator_result": validation,
            "sql": sql,
        }
        review = provider.generate_structured(prompt, payload)
        confidence = self._model_confidence(review.data) if review.success else 0.0
        if review.success and confidence <= 0:
            confidence = 94.0
        trace["stages"].append({
            "stage": "business_logic_review",
            "success": review.success,
            "latency_ms": review.latency_ms,
            "error_category": review.error_category,
            "error_message": getattr(review, "error_message", ""),
            "retry_count": review.retry_count,
            "summary": (review.data or {}).get("reasoning_summary") if review.data else "",
            "approved": (review.data or {}).get("approved") if review.data else None,
        })
        trace["model_confidence"] = confidence
        trace["retry_count"] = int(getattr(review, "retry_count", 0) or 0)
        if not review.success:
            reason = review.error_category or "business_logic_review_failed"
            trace.update({"fallback_used": True, "fallback_reason": reason})
            self._record_provider_fallback(reason)
        return trace, confidence

    def _extract_custody_parameter(
        self,
        query: str,
        patterns: tuple[str, ...],
    ) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                value = str(match.group(1)).strip().strip("'\".,;")
                if value:
                    return value
        return None

    def _custody_sql_value(self, value: str | None, placeholder: str) -> str:
        if not value:
            return f":{placeholder}"
        return "'" + value.replace("'", "''") + "'"

    def _parse_custody_customer_rule(self, query: str) -> dict[str, object] | None:
        if "custody_position" not in self.graph.tables:
            return None
        q = re.sub(r"\s+", " ", query.lower().replace("_", " ").replace("-", " ")).strip()
        if not q:
            return None

        customer_context = bool(
            re.search(r"\bcustomers?\b", q)
            or re.search(r"\bbusiness\s+partners?\b", q)
            or re.search(r"\bbp\s+id\b", q)
            or "custody" in q
        )
        # Keep the earlier sample CRM schema intact: "client" alone should still
        # resolve to clients unless the prompt is explicitly a custody/balance query.
        if not customer_context:
            return None

        business_partner_id = self._extract_custody_parameter(query, (
            r"\bbusiness\s+partner(?:\s+id)?\s*(?:is|=|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
            r"\bbp(?:\s+|_)?id\s*(?:is|=|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
            r"\bcustomer(?:\s+reference|\s+id)?\s*(?:is|=|:)\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
            r"\bcustomer\s+([0-9][A-Za-z0-9_-]*)\b",
        ))
        instrument_id = self._extract_custody_parameter(query, (
            r"\binstrument(?:\s+id)?\s*(?:is|=|:)\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
            r"\binstrmnt(?:\s+id)?\s*(?:is|=|:)\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
            r"\bgiven\s+instrument\s+([A-Za-z0-9][A-Za-z0-9_-]*)\b",
        ))

        if "portfolio" in q and re.search(r"\b(find|list|show|get|give|fetch|all)\b", q):
            return {
                "name": "custody_customer_portfolios",
                "main_table": "custody_position",
                "selected_columns": [("custody_position", "portfolio_id")],
                "filters": [
                    {
                        "table": "custody_position",
                        "column": "business_partner_id",
                        "operator": "=",
                        "value": business_partner_id or ":business_partner_id",
                    }
                ],
                "sql": (
                    "SELECT DISTINCT\n"
                    "  portfolio_id\n"
                    "FROM custody_position\n"
                    f"WHERE business_partner_id = {self._custody_sql_value(business_partner_id, 'business_partner_id')};"
                ),
                "required": ["customer", "portfolio_id"],
                "matched": ["customer", "portfolio_id"],
                "complexity": "MODERATE",
            }

        has_given_instrument = bool(
            re.search(r"\bgiven\s+instrument\b", q)
            or re.search(r"\binstrument(?:\s+id)?\s*(?:is|=|:)", q)
            or re.search(r"\binstrmnt(?:\s+id)?\s*(?:is|=|:)", q)
        )
        has_buy_stock = bool(re.search(r"\b(buy|bought|purchase|purchased)\b", q) and "stock" in q)
        if has_buy_stock and has_given_instrument:
            return {
                "name": "custody_customers_by_instrument",
                "main_table": "custody_position",
                "selected_columns": [("custody_position", column) for column in self.graph.column_order.get("custody_position", [])],
                "filters": [
                    {
                        "table": "custody_position",
                        "column": "instrument_id",
                        "operator": "=",
                        "value": instrument_id or ":instrument_id",
                    }
                ],
                "sql": (
                    "SELECT *\n"
                    "FROM custody_position\n"
                    f"WHERE instrument_id = {self._custody_sql_value(instrument_id, 'instrument_id')};"
                ),
                "required": ["customer", "buy stock", "instrument_id"],
                "matched": ["customer", "buy stock", "instrument_id"],
                "complexity": "MODERATE",
            }

        if (
            has_buy_stock
            and "instrument" in q
            and "security_movement" in self.graph.tables
            and re.search(r"\b(specific|given|business\s+partner|bp\s+id|customer)\b", q)
        ):
            return {
                "name": "custody_bought_instruments_for_customer",
                "main_table": "security_movement",
                "selected_columns": [("security_movement", "instrument_id")],
                "filters": [
                    {
                        "table": "security_movement",
                        "column": "customer_reference",
                        "operator": "=",
                        "value": business_partner_id or ":business_partner_id",
                    },
                    {
                        "table": "security_movement",
                        "column": "credit_and_debit_flag",
                        "operator": "=",
                        "value": "1",
                    },
                ],
                "sql": (
                    "SELECT DISTINCT\n"
                    "  sm.instrument_id\n"
                    "FROM security_movement sm\n"
                    f"WHERE sm.customer_reference = {self._custody_sql_value(business_partner_id, 'business_partner_id')}\n"
                    "  AND sm.credit_and_debit_flag = 1;"
                ),
                "required": ["customer", "instrument_id", "credit_and_debit_flag"],
                "matched": ["customer", "instrument_id", "credit_and_debit_flag"],
                "complexity": "MODERATE",
            }

        if re.search(r"\b(detail|details|records?|profile|all)\b", q):
            return {
                "name": "custody_customer_details",
                "main_table": "custody_position",
                "selected_columns": [("custody_position", column) for column in self.graph.column_order.get("custody_position", [])],
                "filters": [],
                "sql": "SELECT *\nFROM custody_position;",
                "required": ["customer details", "custody_position"],
                "matched": ["customer details", "custody_position"],
                "complexity": "MODERATE",
            }

        return None

    def _custody_rule_provider_review(
        self,
        query: str,
        rule: dict[str, object],
        sql: str,
        plan: QueryPlan,
        validation: str,
    ) -> tuple[dict[str, object], float]:
        status = self._provider_status()
        trace: dict[str, object] = {
            "provider": status.get("provider", "local"),
            "model": status.get("model", "deterministic"),
            "active": False,
            "fallback_used": False,
            "fallback_reason": "",
            "retry_count": 0,
            "stages": [
                {
                    "stage": "business_logic_lookup",
                    "success": True,
                    "summary": "Matched TCS custody customer query rule and assembled schema-grounded SQL.",
                    "matched_rule": rule.get("name"),
                }
            ],
            "plan_validation": {"valid": True, "errors": []},
            "model_confidence": 0.0,
        }
        provider = self.llm_provider
        if provider is None or not getattr(provider, "available", False):
            return trace, 0.0

        trace["active"] = True
        prompt = (
            "Review this deterministic TCS custody SQL against the named business rule. "
            "Return only JSON with keys: approved, issues, missing_requirements, "
            "reasoning_summary, model_confidence. Do not rewrite SQL unless the "
            "rule is violated."
        )
        payload = {
            "user_request": query,
            "business_rule": {
                "name": rule.get("name"),
                "required": rule.get("required", []),
                "matched": rule.get("matched", []),
            },
            "validated_plan": self._plan_ir(
                Intent(filters=list(plan.filters), requires_join=False),
                EntityExtraction(_tokens(query), _tokens(query), [], [], [], list(plan.filters), []),
                plan,
                str(rule.get("complexity", "MODERATE")),
            ),
            "validator_result": validation,
            "sql": sql,
        }
        review = provider.generate_structured(prompt, payload)
        confidence = self._model_confidence(review.data) if review.success else 0.0
        if review.success and confidence <= 0:
            confidence = 94.0
        trace["stages"].append({
            "stage": "business_logic_review",
            "success": review.success,
            "latency_ms": review.latency_ms,
            "error_category": review.error_category,
            "error_message": getattr(review, "error_message", ""),
            "retry_count": review.retry_count,
            "summary": (review.data or {}).get("reasoning_summary") if review.data else "",
            "approved": (review.data or {}).get("approved") if review.data else None,
        })
        trace["model_confidence"] = confidence
        trace["retry_count"] = int(getattr(review, "retry_count", 0) or 0)
        if not review.success:
            reason = review.error_category or "business_logic_review_failed"
            trace.update({"fallback_used": True, "fallback_reason": reason})
            self._record_provider_fallback(reason)
        return trace, confidence

    def _run_custody_customer_logic(
        self,
        query: str,
        request_id: str,
        run_started_at: float,
        execution_trace: dict[str, object],
        *,
        allow_cache: bool,
    ) -> CopilotResult | None:
        rule = self._parse_custody_customer_rule(query)
        if rule is None:
            return None

        sql = str(rule["sql"])
        filters = list(rule.get("filters", []))
        selected_columns = list(rule.get("selected_columns", []))
        main_table = str(rule["main_table"])
        complexity = str(rule.get("complexity", "MODERATE"))
        plan = QueryPlan(
            main_table=main_table,
            selected_columns=selected_columns,
            joins=[],
            filters=filters,
            aggregations=[],
            group_by=[],
            order_by=None,
            limit=None,
            confidence=95,
        )
        terms = _tokens(query)
        intent = Intent(filters=filters, requires_join=False)
        entities = EntityExtraction(
            raw_terms=terms,
            canonical_terms=terms,
            tables=[main_table],
            columns=[column for _table, column in selected_columns],
            measures=[],
            filters=filters,
            unresolved_terms=[],
        )
        plan_validation_errors = self._validate_query_plan(plan)
        valid, validation = self.validation_agent.validate(sql, intent, entities, plan)
        alignment_report = {"missing_columns": [], "extra_columns": [], "critical_mismatches": []}
        if plan_validation_errors:
            valid = False
            validation = "Plan validation failed: " + ", ".join(plan_validation_errors)

        llm_trace, model_confidence = self._custody_rule_provider_review(
            query,
            rule,
            sql,
            plan,
            validation,
        )
        execution_trace.setdefault("events", []).extend([
            {
                "stage": "business_logic_lookup",
                "matched_rule": rule.get("name"),
                "required": rule.get("required", []),
                "matched": rule.get("matched", []),
            },
            {
                "stage": "plan_validation",
                "valid": not plan_validation_errors,
                "errors": plan_validation_errors,
            },
            {
                "stage": "sql_validation",
                "valid": valid,
                "validation": validation,
            },
        ])
        execution_trace["query_complexity"] = complexity

        components = {
            "intent": 96.0,
            "entity": 96.0,
            "column": 95.0,
            "join": 100.0,
            "aggregation": 100.0,
            "semantic": 95.0,
            "validation": 100.0 if valid else 0.0,
        }
        required = list(rule.get("required", []))
        matched = list(rule.get("matched", []))
        coverage = {
            "intent": {
                "score": components["intent"],
                "required": required,
                "matched": matched,
                "missing": [],
            },
            "entity": {
                "score": components["entity"],
                "required": required,
                "matched": matched,
                "missing": [],
            },
            "column": {
                "score": components["column"],
                "required": [f"{table}.{column}" for table, column in selected_columns],
                "matched": [f"{table}.{column}" for table, column in selected_columns],
                "missing": [],
            },
            "join": {
                "score": components["join"],
                "required_tables": [main_table],
                "joined_tables": [main_table],
                "missing": [],
            },
            "aggregation": {
                "score": components["aggregation"],
                "required": [],
                "matched": [],
                "missing": [],
            },
            "semantic": {
                "score": components["semantic"],
                "required": required,
                "matched": matched,
                "missing": [],
            },
            "validation": {
                "score": components["validation"],
                "valid": valid,
                "message": validation,
            },
            "plan_alignment": alignment_report,
            "plan_validation": {"valid": not plan_validation_errors, "errors": plan_validation_errors},
            "business_logic": {
                "matched_rule": rule.get("name"),
                "parameters": {
                    item["column"]: item.get("value")
                    for item in filters
                    if isinstance(item, dict)
                },
                "steps": [
                    "Resolve customer wording to TCS custody schema.",
                    "Use custody_position for customer/portfolio/position records.",
                    "Use security_movement for bought-instrument movement questions.",
                    "Keep demo clients table only for explicit client wording.",
                ],
            },
            "llm": llm_trace,
        }
        component_applicability = {
            "intent": True,
            "entity": True,
            "column": True,
            "join": False,
            "aggregation": False,
            "semantic": True,
        }
        coverage["confidence_applicability"] = component_applicability

        confidence_breakdown = self.confidence_coordinator.compute_from_components(
            components,
            valid,
            [],
            [],
        )
        planner_confidence = float(plan.confidence)
        validator_confidence = 100.0 if valid else 0.0
        applicable_scores = [
            components[key]
            for key, enabled in component_applicability.items()
            if enabled
        ]
        coverage_confidence = round(sum(applicable_scores) / len(applicable_scores), 2)
        confidence = min(96, int(round(confidence_breakdown.get("overall", 0.0))))
        confidence_breakdown.update({
            "overall": float(confidence),
            "planner_confidence": planner_confidence,
            "validator_confidence": validator_confidence,
            "coverage_confidence": coverage_confidence,
            "model_confidence": model_confidence,
            "system_confidence": float(confidence),
        })
        confidence_evidence = self._confidence_evidence(
            components,
            coverage,
            component_applicability,
            plan=plan,
            llm_trace=llm_trace,
            planner_confidence=planner_confidence,
            validator_confidence=validator_confidence,
            coverage_confidence=coverage_confidence,
            model_confidence=model_confidence,
        )
        confidence_band = self._confidence_band(confidence)
        selected_tables = sorted(self._plan_tables(plan))
        selected_column_names = [f"{table}.{column}" for table, column in selected_columns]
        runtime_metrics = {
            "request_id": request_id,
            "session_id": "local",
            "total_ms": round((time.perf_counter() - run_started_at) * 1000, 3),
            "events": len(execution_trace.get("events", [])),
            "cache_hit": False,
            "query_complexity": complexity,
            "llm_provider": llm_trace.get("provider"),
            "llm_model": llm_trace.get("model"),
            "workflow_engine": dict(execution_trace.get("workflow_run") or {}).get("engine", self.workflow.engine),
            "fallback_used": bool(llm_trace.get("fallback_used")),
            "fallback_reason": llm_trace.get("fallback_reason", ""),
            "repair_attempts": int(llm_trace.get("retry_count") or 0),
        }
        benchmark_record = {
            "query_id": request_id,
            "query": query,
            "generated_sql": sql,
            "candidate_sql": sql,
            "provider": llm_trace.get("provider"),
            "model": llm_trace.get("model"),
            "complexity": complexity,
            "planner_correct": not plan_validation_errors,
            "sql_correct": bool(valid),
            "validator_valid": bool(valid),
            "confidence": confidence,
            "confidence_band": confidence_band,
            "coverage": coverage,
            "confidence_breakdown": confidence_breakdown,
            "confidence_evidence": confidence_evidence,
            "retry_count": int(llm_trace.get("retry_count") or 0),
            "latency_ms": runtime_metrics["total_ms"],
            "fallback_used": bool(llm_trace.get("fallback_used")),
        }
        telemetry = self.telemetry_agent.record(
            query,
            valid,
            confidence_breakdown,
            coverage,
            provider_trace=llm_trace,
            complexity=complexity,
        )
        execution_trace["counters"] = dict(self.runtime_counters)
        execution_trace["cache_hit"] = False
        result = CopilotResult(
            sql=sql,
            confidence=confidence,
            valid=valid,
            validation=validation,
            clarification_required=not valid,
            clarification_options=[],
            intent=asdict(intent),
            entities=asdict(entities),
            selected_tables=selected_tables,
            selected_columns=selected_column_names,
            join_path=[],
            plan=asdict(plan),
            optimizations=self.optimization_agent.analyze(sql, plan),
            confidence_breakdown=confidence_breakdown,
            confidence_evidence=confidence_evidence,
            coverage_report=coverage,
            agent_telemetry=telemetry,
            execution_trace=execution_trace,
            runtime_metrics=runtime_metrics,
            benchmark_record=benchmark_record,
            missing_entities=[],
            missing_columns=[],
            missing_joins=[],
            missing_aggregations=[],
            query_complexity=complexity,
            confidence_band=confidence_band,
            provider_status=self._provider_status(),
            llm_trace=llm_trace,
            model_confidence=model_confidence,
            planner_confidence=planner_confidence,
            validator_confidence=validator_confidence,
            coverage_confidence=coverage_confidence,
            cache_hit=False,
        )
        self._write_runtime_logs(
            request_id,
            {
                "query": query,
                "sql": sql,
                "valid": result.valid,
                "plan": result.plan,
                "selected_tables": selected_tables,
                "selected_columns": selected_column_names,
                "join_path": [],
                "confidence_breakdown": confidence_breakdown,
                "confidence_evidence": confidence_evidence,
                "coverage_report": coverage,
                "execution_trace": execution_trace,
                "runtime_metrics": runtime_metrics,
                "benchmark_record": benchmark_record,
                "llm_trace": llm_trace,
            },
        )
        llm_failed_fallback = bool(llm_trace.get("active")) and bool(llm_trace.get("fallback_used"))
        if allow_cache and result.valid and result.confidence >= 70 and not llm_failed_fallback:
            self.cache.put(query, result)
        return result

    def _run_custody_balance_logic(
        self,
        query: str,
        request_id: str,
        run_started_at: float,
        execution_trace: dict[str, object],
        *,
        allow_cache: bool,
    ) -> CopilotResult | None:
        request = parse_balance_request(query)
        if request is None:
            return None
        required_tables = {"portfolio", "custody_position", "security_movement", "custody_block"}
        if not required_tables.issubset(self.graph.tables):
            return None

        missing_params = [
            label for label, value in (
                ("business_partner_id", request.business_partner_id),
                ("portfolio_id", request.portfolio_id),
                ("balance_date", request.balance_date),
            )
            if not value
        ]
        sql = build_available_balance_sql(request)
        filters = [
            {"table": "custody_position", "column": "business_partner_id", "operator": "=", "value": request.business_partner_id or ""},
            {"table": "custody_position", "column": "portfolio_id", "operator": "=", "value": request.portfolio_id or ""},
            {
                "table": "security_movement",
                "column": {1: "trade_date", 2: "value_date", 5: "transaction_date"}.get(request.balance_type, "trade_date"),
                "operator": "<=",
                "value": request.balance_date or "",
            },
            {"table": "custody_block", "column": "block_valid_from_date", "operator": "<=", "value": request.balance_date or ""},
            {"table": "custody_block", "column": "block_release_date", "operator": "as_of_active", "value": request.balance_date or ""},
            {"table": "custody_block", "column": "block_status", "operator": "=", "value": "ACTIVE"},
        ]
        intent = Intent(aggregations=["SUM"], filters=filters, requires_join=True)
        terms = _tokens(query)
        entities = EntityExtraction(
            raw_terms=terms,
            canonical_terms=terms,
            tables=sorted(required_tables),
            columns=[
                "business_partner_id",
                "portfolio_id",
                "balance_date",
                "amount_quantity",
                "block_quantity_amount",
                "available_balance",
            ],
            measures=["settled_balance", "blocked_balance", "available_balance"],
            filters=filters,
            unresolved_terms=[],
        )
        joins = self._custody_balance_relationships()
        plan = QueryPlan(
            main_table="custody_position",
            selected_columns=[
                ("custody_position", "business_partner_id"),
                ("custody_position", "portfolio_id"),
                ("custody_position", "position_number"),
                ("custody_position", "position_type"),
                ("custody_position", "instrument_id"),
                ("custody_position", "security_position_type"),
                ("custody_position", "custodian_id"),
                ("custody_position", "custodian_account_number"),
                ("custody_position", "currency"),
                ("custody_position", "stock_exchange"),
            ],
            joins=joins,
            filters=filters,
            aggregations=[
                {
                    "function": "SUM",
                    "table": "security_movement",
                    "column": "amount_quantity",
                    "alias": "settled_balance",
                },
                {
                    "function": "SUM",
                    "table": "custody_block",
                    "column": "block_quantity_amount",
                    "alias": "blocked_balance",
                },
            ],
            group_by=[],
            order_by=("custody_position.position_number", "ASC"),
            limit=None,
            confidence=96,
        )
        matches = self._custody_balance_matches()
        plan_validation_errors = self._validate_query_plan(plan)
        valid, validation = self.validation_agent.validate(sql, intent, entities, plan)
        alignment_report = self.sql_agent.audit_alignment(plan, sql)
        if plan_validation_errors:
            valid = False
            validation = "Plan validation failed: " + ", ".join(plan_validation_errors)
        if alignment_report.get("critical_mismatches"):
            valid = False
            validation = "Generated SQL does not match planner output: " + ", ".join(alignment_report.get("critical_mismatches", []))
        if missing_params:
            valid = False
            validation = "Missing required balance inputs: " + ", ".join(missing_params)

        llm_trace, model_confidence = self._custody_balance_provider_review(
            query,
            request,
            sql,
            plan,
            validation,
        )
        execution_trace.setdefault("events", []).extend([
            {
                "stage": "business_logic_lookup",
                "matched_rule": "custody_available_balance",
                "parameters": balance_request_summary(request),
            },
            {
                "stage": "plan_validation",
                "valid": not plan_validation_errors,
                "errors": plan_validation_errors,
            },
            {
                "stage": "sql_validation",
                "valid": valid,
                "validation": validation,
            },
        ])
        execution_trace["query_complexity"] = "ENTERPRISE"

        components = {
            "intent": 100.0,
            "entity": 82.0 if missing_params else 97.0,
            "column": 96.0,
            "join": 95.0,
            "aggregation": 100.0,
            "semantic": 97.0,
            "validation": 100.0 if valid else 0.0,
        }
        coverage = {
            "intent": {
                "score": components["intent"],
                "required": ["AVAILABLE_BALANCE", "SETTLED_BALANCE", "BLOCKED_BALANCE"],
                "matched": ["AVAILABLE_BALANCE", "SETTLED_BALANCE", "BLOCKED_BALANCE"],
                "missing": [],
            },
            "entity": {
                "score": components["entity"],
                "required": ["business_partner_id", "portfolio_id", "balance_date"],
                "matched": [
                    label for label in ["business_partner_id", "portfolio_id", "balance_date"]
                    if label not in missing_params
                ],
                "missing": missing_params,
            },
            "column": {
                "score": components["column"],
                "required": [
                    "custody_position.business_partner_id",
                    "custody_position.portfolio_id",
                    "security_movement.amount_quantity",
                    "security_movement.credit_and_debit_flag",
                    "custody_block.block_quantity_amount",
                    "custody_block.block_valid_from_date",
                    "custody_block.block_release_date",
                ],
                "matched": [
                    "custody_position.business_partner_id",
                    "custody_position.portfolio_id",
                    "security_movement.amount_quantity",
                    "security_movement.credit_and_debit_flag",
                    "custody_block.block_quantity_amount",
                    "custody_block.block_valid_from_date",
                    "custody_block.block_release_date",
                ],
                "missing": [],
            },
            "join": {
                "score": components["join"],
                "required_tables": sorted(required_tables),
                "joined_tables": sorted(required_tables),
                "missing": [],
            },
            "aggregation": {
                "score": components["aggregation"],
                "required": ["SUM", "AVAILABLE_BALANCE_FORMULA"],
                "matched": ["SUM", "AVAILABLE_BALANCE_FORMULA"],
                "missing": [],
            },
            "semantic": {
                "score": components["semantic"],
                "required": ["settled balance", "blocked balance", "available balance"],
                "matched": ["settled balance", "blocked balance", "available balance"],
                "missing": [],
            },
            "validation": {
                "score": components["validation"],
                "valid": valid,
                "message": validation,
            },
            "plan_alignment": alignment_report,
            "plan_validation": {"valid": not plan_validation_errors, "errors": plan_validation_errors},
            "business_logic": {
                "matched_rule": "custody_available_balance",
                "parameters": balance_request_summary(request),
                "steps": [
                    "Validate portfolio",
                    "Fetch custody position records from custody_position",
                    "Calculate settled balance from security_movement",
                    "Calculate active blocked balance from custody_block",
                    "available_balance = settled_balance - blocked_balance",
                ],
            },
            "llm": llm_trace,
        }
        component_applicability = {
            "intent": True,
            "entity": True,
            "column": True,
            "join": True,
            "aggregation": True,
            "semantic": True,
        }
        coverage["confidence_applicability"] = component_applicability

        confidence_breakdown = self.confidence_coordinator.compute_from_components(
            components,
            valid,
            missing_params,
            [],
        )
        planner_confidence = float(plan.confidence)
        validator_confidence = 100.0 if valid else 0.0
        applicable_scores = [
            components[key]
            for key, enabled in component_applicability.items()
            if enabled
        ]
        coverage_confidence = round(sum(applicable_scores) / len(applicable_scores), 2)
        confidence_breakdown.update({
            "planner_confidence": planner_confidence,
            "validator_confidence": validator_confidence,
            "coverage_confidence": coverage_confidence,
            "model_confidence": model_confidence,
            "system_confidence": confidence_breakdown.get("overall", 0.0),
        })
        confidence_evidence = self._confidence_evidence(
            components,
            coverage,
            component_applicability,
            plan=plan,
            llm_trace=llm_trace,
            planner_confidence=planner_confidence,
            validator_confidence=validator_confidence,
            coverage_confidence=coverage_confidence,
            model_confidence=model_confidence,
        )
        confidence = int(round(confidence_breakdown.get("overall", 0.0)))
        confidence_band = self._confidence_band(confidence)
        clarification_required = bool(missing_params) or not valid or confidence_band == "LOW"
        options = [f"Provide {item.replace('_', ' ')}." for item in missing_params]
        final_sql = sql if not clarification_required else (
            "I need the business partner id, portfolio id, and balance date before generating available-balance SQL."
        )
        selected_tables = sorted(required_tables)
        selected_columns = [f"{table}.{column}" for table, column in plan.selected_columns] + [
            "security_movement.amount_quantity",
            "security_movement.credit_and_debit_flag",
            "custody_block.block_quantity_amount",
        ]
        join_path = [
            f"{rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column}"
            for rel in joins
        ]
        runtime_metrics = {
            "request_id": request_id,
            "session_id": "local",
            "total_ms": round((time.perf_counter() - run_started_at) * 1000, 3),
            "events": len(execution_trace.get("events", [])),
            "cache_hit": False,
            "query_complexity": "ENTERPRISE",
            "llm_provider": llm_trace.get("provider"),
            "llm_model": llm_trace.get("model"),
            "workflow_engine": dict(execution_trace.get("workflow_run") or {}).get("engine", self.workflow.engine),
            "fallback_used": bool(llm_trace.get("fallback_used")),
            "fallback_reason": llm_trace.get("fallback_reason", ""),
            "repair_attempts": int(llm_trace.get("retry_count") or 0),
        }
        benchmark_record = {
            "query_id": request_id,
            "query": query,
            "generated_sql": final_sql,
            "candidate_sql": sql,
            "provider": llm_trace.get("provider"),
            "model": llm_trace.get("model"),
            "complexity": "ENTERPRISE",
            "planner_correct": not plan_validation_errors and not missing_params,
            "sql_correct": bool(valid and not clarification_required),
            "validator_valid": bool(valid),
            "confidence": confidence,
            "confidence_band": confidence_band,
            "coverage": coverage,
            "confidence_breakdown": confidence_breakdown,
            "confidence_evidence": confidence_evidence,
            "retry_count": int(llm_trace.get("retry_count") or 0),
            "latency_ms": runtime_metrics["total_ms"],
            "fallback_used": bool(llm_trace.get("fallback_used")),
        }
        telemetry = self.telemetry_agent.record(
            query,
            valid and not clarification_required,
            confidence_breakdown,
            coverage,
            provider_trace=llm_trace,
            complexity="ENTERPRISE",
        )
        execution_trace["counters"] = dict(self.runtime_counters)
        execution_trace["cache_hit"] = False

        result = CopilotResult(
            sql=final_sql,
            confidence=confidence,
            valid=valid and not clarification_required,
            validation=validation if not clarification_required else "Missing required balance inputs.",
            clarification_required=clarification_required,
            clarification_options=options,
            intent=asdict(intent),
            entities=asdict(entities),
            selected_tables=selected_tables,
            selected_columns=selected_columns,
            join_path=join_path,
            plan=asdict(plan),
            optimizations=self.optimization_agent.analyze(sql, plan),
            confidence_breakdown=confidence_breakdown,
            confidence_evidence=confidence_evidence,
            coverage_report=coverage,
            agent_telemetry=telemetry,
            execution_trace=execution_trace,
            runtime_metrics=runtime_metrics,
            benchmark_record=benchmark_record,
            missing_entities=missing_params,
            missing_columns=[],
            missing_joins=[],
            missing_aggregations=[],
            query_complexity="ENTERPRISE",
            confidence_band=confidence_band,
            provider_status=self._provider_status(),
            llm_trace=llm_trace,
            model_confidence=model_confidence,
            planner_confidence=planner_confidence,
            validator_confidence=validator_confidence,
            coverage_confidence=coverage_confidence,
            cache_hit=False,
        )
        self._write_runtime_logs(
            request_id,
            {
                "query": query,
                "sql": final_sql,
                "valid": result.valid,
                "plan": result.plan,
                "selected_tables": selected_tables,
                "selected_columns": selected_columns,
                "join_path": join_path,
                "confidence_breakdown": confidence_breakdown,
                "confidence_evidence": confidence_evidence,
                "coverage_report": coverage,
                "execution_trace": execution_trace,
                "runtime_metrics": runtime_metrics,
                "benchmark_record": benchmark_record,
                "llm_trace": llm_trace,
            },
        )
        llm_failed_fallback = bool(llm_trace.get("active")) and bool(llm_trace.get("fallback_used"))
        if allow_cache and result.valid and result.confidence >= 70 and not llm_failed_fallback:
            self.cache.put(query, result)
        return result

    def run(self, query: str, allow_cache: bool = True) -> CopilotResult:
        request_id = uuid.uuid4().hex[:12]
        run_started_at = time.perf_counter()
        workflow_run = self.workflow.invoke(query=query, request_id=request_id)
        execution_trace: dict[str, object] = {
            "request_id": request_id,
            "session_id": "local",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workflow": self.workflow.describe(),
            "workflow_run": workflow_run,
            "events": [],
            "counters": {},
        }
        custody_result = self._run_custody_balance_logic(
            query,
            request_id,
            run_started_at,
            execution_trace,
            allow_cache=allow_cache,
        )
        if custody_result is not None:
            return custody_result
        custody_customer_result = self._run_custody_customer_logic(
            query,
            request_id,
            run_started_at,
            execution_trace,
            allow_cache=allow_cache,
        )
        if custody_customer_result is not None:
            return custody_customer_result
        if allow_cache:
            cached = self.cache.get(query)
            if cached:
                cached.execution_trace = {
                    **execution_trace,
                    "cache_hit": True,
                    "events": [{"stage": "cache", "cache_hit": True}],
                    "counters": dict(self.runtime_counters),
                }
                cached.runtime_metrics = {
                    "request_id": request_id,
                    "total_ms": round((time.perf_counter() - run_started_at) * 1000, 3),
                    "cache_hit": True,
                    "workflow_engine": workflow_run.get("engine", self.workflow.engine),
                }
                return cached

        stage_started = time.perf_counter()
        intent = self.intent_agent.detect(query)
        self._trace_mark(execution_trace, "intent_agent_calls", "intent_detection", stage_started, {"operation": intent.operation, "aggregations": intent.aggregations})
        stage_started = time.perf_counter()
        entities = self.entity_agent.extract(query)
        self._trace_mark(execution_trace, "entity_agent_calls", "entity_extraction", stage_started, {"terms": entities.canonical_terms, "filters": entities.filters})
        # If user mentions measures (e.g., budget, amount) and requests grouping,
        # assume an aggregation (SUM) when no explicit aggregation was detected.
        if (
            entities.measures
            and (
                intent.group_by
                or intent.time_granularity
                or " by " in f" {query.lower()} "
            )
            and not intent.aggregations
        ):
            intent.aggregations = ["SUM"]
            intent.group_by = bool(intent.group_by or intent.time_granularity or " by " in f" {query.lower()} ")
        stage_started = time.perf_counter()
        matches, unresolved, ambiguities = self.linking_agent.link(query, entities)
        self._trace_mark(execution_trace, "schema_retrieval_calls", "schema_linking", stage_started, {"matches": len(matches), "unresolved": unresolved, "ambiguities": ambiguities})
        self._trace_mark(execution_trace, "resolver_calls", "semantic_resolution", stage_started, {"canonical_terms": entities.canonical_terms})
        stage_started = time.perf_counter()
        plan = self.planner_agent.plan(intent, entities, matches, unresolved, ambiguities, query)
        self._trace_mark(
            execution_trace,
            "planner_calls",
            "planner",
            stage_started,
            {
                "main_table": plan.main_table if plan else None,
                "selected_columns": [f"{table}.{column}" for table, column in plan.selected_columns] if plan else [],
                "joins": [f"{rel.from_table}.{rel.from_column}->{rel.to_table}.{rel.to_column}" for rel in plan.joins] if plan else [],
            },
        )
        query_complexity = self._query_complexity(intent, entities, matches, plan)
        plan_validation_errors = self._validate_query_plan(plan)
        execution_trace["query_complexity"] = query_complexity
        execution_trace.setdefault("events", []).append({
            "stage": "plan_validation",
            "valid": not plan_validation_errors,
            "errors": plan_validation_errors,
            "join_diagnostics": getattr(self.join_agent, "last_diagnostics", {}),
        })
        stage_started = time.perf_counter()
        deterministic_sql = self.sql_agent.generate(plan) if plan else "The schema does not have enough information to answer this query."
        deterministic_alignment = self.sql_agent.last_alignment if plan else {"aligned": False, "critical_mismatches": ["missing_plan"]}
        sql, alignment_report, llm_trace = self._generate_sql_with_optional_llm(
            query,
            intent,
            entities,
            matches,
            plan,
            query_complexity,
            deterministic_sql,
            deterministic_alignment,
            plan_validation_errors,
        )
        self._trace_mark(
            execution_trace,
            "sql_generator_calls",
            "sql_generation",
            stage_started,
            {
                "alignment": alignment_report,
                "llm": {
                    "provider": llm_trace.get("provider"),
                    "model": llm_trace.get("model"),
                    "active": llm_trace.get("active"),
                    "fallback_used": llm_trace.get("fallback_used"),
                    "fallback_reason": llm_trace.get("fallback_reason"),
                },
            },
        )
        stage_started = time.perf_counter()
        valid, validation = self.validation_agent.validate(sql, intent, entities, plan)
        if plan_validation_errors:
            valid = False
            validation = "Plan validation failed: " + ", ".join(plan_validation_errors)
        if alignment_report.get("critical_mismatches"):
            valid = False
            validation = "Generated SQL does not match planner output: " + ", ".join(alignment_report.get("critical_mismatches", []))
        self._trace_mark(execution_trace, "validator_calls", "sql_validation", stage_started, {"valid": valid, "validation": validation})
        # base semantic-style coverage for compatibility
        stage_started = time.perf_counter()
        coverage = self.semantic_agent.evaluate(
            query,
            sql,
            intent,
            entities,
            matches,
            plan,
            valid,
            unresolved,
            ambiguities,
        )

        # run lightweight modular coverage agents
        intent_comp = self.intent_coverage.evaluate(intent, plan)
        # pass the schema columns to entity coverage so it can infer readable display columns
        entity_comp = self.entity_coverage.evaluate(entities, matches, plan, query, schema_columns=self.graph.columns)
        column_comp = self.column_coverage.evaluate(entities, matches, plan)
        join_comp = self.join_coverage.evaluate(matches, plan, entities)
        agg_comp = self.agg_coverage.evaluate(intent, plan, sql)
        # semantic checks
        semantic_comp = None
        try:
            from .coverage_agents import SemanticCoverageAgent
            semantic_agent = SemanticCoverageAgent()
            semantic_comp = semantic_agent.evaluate(entities.canonical_terms, sql, matches, plan)
            # merge semantic findings into coverage for reporting
            coverage.setdefault("semantic", {}).update(semantic_comp)
        except Exception:
            semantic_comp = None

        # The modular agents are authoritative for both confidence and the
        # response payload. Keeping the legacy report here produced diagnostics
        # that contradicted the scores used by the coordinator.
        coverage.update({
            "intent": intent_comp,
            "entity": entity_comp,
            "column": column_comp,
            "join": join_comp,
            "aggregation": agg_comp,
            "validation": {
                "score": 100 if valid else 0,
                "valid": valid,
                "message": validation,
            },
        })

        # join path diagnostics (if available)
        try:
            if getattr(self, "join_path_coverage", None):
                join_path_report = self.join_path_coverage.evaluate(self.graph, plan, matches, sql)
                coverage["join_path"] = join_path_report
            else:
                join_path_report = {}
        except Exception:
            join_path_report = {}

        # compute adjusted join score using join path report
        adjusted_join_score = min(float(join_comp.get("score", 0.0)), float(join_path_report.get("join_coverage_score", join_comp.get("score", 0.0)))) if join_comp else float(join_path_report.get("join_coverage_score", 0.0) or 0.0)
        components = {
            "intent": float(intent_comp.get("score", 0.0)),
            "entity": float(entity_comp.get("score", 0.0)),
            "column": float(column_comp.get("score", 0.0)),
            "join": float(adjusted_join_score),
            "aggregation": float(agg_comp.get("score", 0.0)),
            "semantic": float((semantic_comp or coverage.get("semantic", {})).get("score", 0.0)),
            "validation": 100.0 if valid else 0.0,
        }
        coverage["plan_alignment"] = alignment_report
        coverage["plan_validation"] = {
            "valid": not plan_validation_errors,
            "errors": plan_validation_errors,
        }
        coverage["business_logic"] = (
            self.vocabulary.rules_for_terms(entities.canonical_terms)
            if self.experiment_flags.get("USE_BUSINESS_LOGIC", True)
            else {}
        )
        coverage["experiment_flags"] = dict(self.experiment_flags)
        coverage["join_graph"] = getattr(self.join_agent, "last_diagnostics", {})
        coverage["llm"] = llm_trace
        component_applicability = {
            "intent": True,
            "entity": self._coverage_applicable(entity_comp),
            "column": self._coverage_applicable(column_comp),
            "join": self._coverage_applicable(join_comp, join=True),
            "aggregation": self._coverage_applicable(agg_comp),
            "semantic": self._coverage_applicable((semantic_comp or coverage.get("semantic", {})) if isinstance((semantic_comp or coverage.get("semantic", {})), dict) else {}),
        }
        coverage["confidence_applicability"] = component_applicability
        self._trace_mark(
            execution_trace,
            "coverage_calls",
            "coverage",
            stage_started,
            {
                "intent_score": components["intent"],
                "entity_score": components["entity"],
                "column_score": components["column"],
                "join_score": components["join"],
                "aggregation_score": components["aggregation"],
                "semantic_score": components["semantic"],
            },
        )
        # expose expected display columns into the coverage report for diagnostics
        try:
            coverage.setdefault("entity", {})["expected_display"] = entity_comp.get("expected_display", {})
        except Exception:
            pass

        # include diagnostic counts for coordinator penalties
        expected_display = entity_comp.get("expected_display", {}) or {}
        missing_display = []
        sql_terms = set(_tokens(sql))
        selected_cols = [c for _, c in plan.selected_columns] if plan else []
        for table, col in expected_display.items():
            if col not in selected_cols and col not in sql_terms:
                missing_display.append((table, col))
        components["missing_display_count"] = len(missing_display)
        components["missing_joins_count"] = len((join_path_report or {}).get("missing_joins", []))
        components["incomplete_joins_count"] = len((join_path_report or {}).get("incomplete_joins", []))

        stage_started = time.perf_counter()
        confidence_breakdown = self.confidence_coordinator.compute_from_components(components, valid, unresolved, ambiguities)
        planner_confidence = float(plan.confidence if plan else 0.0)
        validator_confidence = 100.0 if valid else 0.0
        applicable_scores = [
            components[key]
            for key in ("intent", "entity", "column", "join", "aggregation", "semantic")
            if component_applicability.get(key)
        ]
        coverage_confidence = round(sum(applicable_scores) / len(applicable_scores), 2) if applicable_scores else 0.0
        model_confidence = float(llm_trace.get("model_confidence") or 0.0)
        confidence_breakdown.update({
            "planner_confidence": planner_confidence,
            "validator_confidence": validator_confidence,
            "coverage_confidence": coverage_confidence,
            "model_confidence": model_confidence,
            "system_confidence": confidence_breakdown.get("overall", 0.0),
        })
        confidence_evidence = self._confidence_evidence(
            components,
            coverage,
            component_applicability,
            plan=plan,
            llm_trace=llm_trace,
            planner_confidence=planner_confidence,
            validator_confidence=validator_confidence,
            coverage_confidence=coverage_confidence,
            model_confidence=model_confidence,
        )
        self._trace_mark(execution_trace, "confidence_calls", "confidence", stage_started, {"confidence": confidence_breakdown.get("overall", 0.0)})
        confidence = int(round(confidence_breakdown.get("overall", 0.0)))
        confidence_band = self._confidence_band(confidence)
        clarification_required = confidence_band == "LOW" or bool(ambiguities) or bool(unresolved)
        options = ambiguities[:5]
        if unresolved:
            options = [f"Map '{term}' to a real schema column first." for term in unresolved]
        if clarification_required and not options:
            missing = sorted(set(
                coverage["intent"].get("missing", [])
                + coverage["entity"].get("missing", [])
                + coverage["column"].get("missing", [])
                + coverage["aggregation"].get("missing", [])
                + coverage["join"].get("missing", [])
            ))
            options = [
                f"Confirm how '{term}' maps to the schema."
                for term in missing[:5]
            ] or ["Confirm the intended tables, columns, and aggregation before SQL generation."]
        telemetry = self.telemetry_agent.record(
            query,
            valid and not clarification_required,
            confidence_breakdown,
            coverage,
            provider_trace=llm_trace,
            complexity=query_complexity,
        )

        selected_tables = []
        selected_columns = []
        join_path = []
        if plan:
            selected_tables = sorted({plan.main_table, *[rel.from_table for rel in plan.joins], *[rel.to_table for rel in plan.joins]})
            selected_columns = [f"{table}.{column}" for table, column in plan.selected_columns]
            join_path = [
                f"{rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column}"
                for rel in plan.joins
            ]

        final_sql = sql if not clarification_required else self._clarification_message(unresolved, ambiguities)
        execution_trace["counters"] = dict(self.runtime_counters)
        execution_trace["cache_hit"] = False
        runtime_metrics = {
            "request_id": request_id,
            "session_id": "local",
            "total_ms": round((time.perf_counter() - run_started_at) * 1000, 3),
            "events": len(execution_trace.get("events", [])),
            "cache_hit": False,
            "query_complexity": query_complexity,
            "llm_provider": llm_trace.get("provider"),
            "llm_model": llm_trace.get("model"),
            "workflow_engine": workflow_run.get("engine", self.workflow.engine),
            "fallback_used": bool(llm_trace.get("fallback_used")),
            "fallback_reason": llm_trace.get("fallback_reason", ""),
            "repair_attempts": int(llm_trace.get("retry_count") or 0),
        }
        benchmark_record = {
            "query_id": request_id,
            "query": query,
            "generated_sql": final_sql,
            "candidate_sql": sql,
            "provider": llm_trace.get("provider"),
            "model": llm_trace.get("model"),
            "complexity": query_complexity,
            "planner_correct": bool(plan and not unresolved and not ambiguities and not alignment_report.get("critical_mismatches")),
            "sql_correct": bool(valid and alignment_report.get("aligned") and not clarification_required),
            "validator_valid": bool(valid),
            "confidence": confidence,
            "confidence_band": confidence_band,
            "coverage": coverage,
            "confidence_breakdown": confidence_breakdown,
            "confidence_evidence": confidence_evidence,
            "retry_count": int(llm_trace.get("retry_count") or 0),
            "latency_ms": runtime_metrics["total_ms"],
            "fallback_used": bool(llm_trace.get("fallback_used")),
        }

        result = CopilotResult(
            sql=final_sql,
            confidence=confidence,
            valid=valid and not clarification_required,
            validation=validation if not clarification_required else "Confidence below threshold; SQL was not approved for execution.",
            clarification_required=clarification_required,
            clarification_options=options,
            intent=asdict(intent),
            entities=asdict(entities),
            selected_tables=selected_tables,
            selected_columns=selected_columns,
            join_path=join_path,
            plan=asdict(plan) if plan else None,
            optimizations=self.optimization_agent.analyze(sql, plan),
            confidence_breakdown=confidence_breakdown,
            confidence_evidence=confidence_evidence,
            coverage_report=coverage,
            agent_telemetry=telemetry,
            execution_trace=execution_trace,
            runtime_metrics=runtime_metrics,
            benchmark_record=benchmark_record,
            missing_entities=coverage.get("entity", {}).get("missing", []),
            missing_columns=coverage.get("column", {}).get("missing", []),
            missing_joins=coverage.get("join", {}).get("missing", []),
            missing_aggregations=coverage.get("aggregation", {}).get("missing", []),
            query_complexity=query_complexity,
            confidence_band=confidence_band,
            provider_status=self._provider_status(),
            llm_trace=llm_trace,
            model_confidence=model_confidence,
            planner_confidence=planner_confidence,
            validator_confidence=validator_confidence,
            coverage_confidence=coverage_confidence,
            cache_hit=False,
        )
        self._write_runtime_logs(
            request_id,
            {
                "query": query,
                "sql": final_sql,
                "valid": result.valid,
                "plan": result.plan,
                "selected_tables": selected_tables,
                "selected_columns": selected_columns,
                "join_path": join_path,
                "confidence_breakdown": confidence_breakdown,
                "confidence_evidence": confidence_evidence,
                "coverage_report": coverage,
                "execution_trace": execution_trace,
                "runtime_metrics": runtime_metrics,
                "benchmark_record": benchmark_record,
                "llm_trace": llm_trace,
            },
        )
        llm_failed_fallback = bool(llm_trace.get("active")) and bool(llm_trace.get("fallback_used"))
        if result.valid and result.confidence >= 70 and not llm_failed_fallback:
            self.cache.put(query, result)
        return result

    def _clarification_message(self, unresolved: list[str], ambiguities: list[str]) -> str:
        if unresolved:
            return (
                "I cannot generate reliable SQL for this request because the schema does not contain "
                f"a mapped column for: {', '.join(unresolved)}. Add the column to the schema or save a learned mapping."
            )
        if ambiguities:
            return (
                "I need one clarification before generating SQL. The request matches multiple schema fields: "
                f"{', '.join(ambiguities[:5])}."
            )
        return "I cannot generate reliable SQL for this request with the current schema confidence."

    def relationship_map(self) -> dict[str, list[dict[str, str]]]:
        return self.graph.relationship_map()

    def er_diagram(self) -> str:
        return self.graph.er_diagram_mermaid()
