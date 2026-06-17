from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable
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

try:
    import networkx as nx
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    nx = None

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


TokenSet = set[str]
QUERY_CACHE_VERSION = "enterprise-v6"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9_]*", text.lower().replace("-", " "))


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
    coverage_report: dict[str, object] = field(default_factory=dict)
    agent_telemetry: dict[str, object] = field(default_factory=dict)
    execution_trace: dict[str, object] = field(default_factory=dict)
    runtime_metrics: dict[str, object] = field(default_factory=dict)
    benchmark_record: dict[str, object] = field(default_factory=dict)
    missing_entities: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    missing_joins: list[str] = field(default_factory=list)
    missing_aggregations: list[str] = field(default_factory=list)
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


class QueryCacheLayer:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
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
        data.setdefault("coverage_report", {})
        data.setdefault("agent_telemetry", {})
        data.setdefault("execution_trace", {})
        data.setdefault("runtime_metrics", {})
        data.setdefault("benchmark_record", {})
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
        return f"{QUERY_CACHE_VERSION}:{query.strip().lower()}"


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

    def shortest_join_path(self, source: str, target: str) -> list[SchemaRelationship]:
        if source == target:
            return []
        queue = deque([(source, [])])
        seen = {source}
        while queue:
            table, path = queue.popleft()
            for rel in self._adjacency.get(table, []):
                if rel.to_table in seen:
                    continue
                next_path = path + [rel]
                if rel.to_table == target:
                    return next_path
                seen.add(rel.to_table)
                queue.append((rel.to_table, next_path))
        return []

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
        query_terms = set(entities.canonical_terms) | {_singular(term) for term in entities.raw_terms}
        matches: list[SchemaMatch] = []
        for table in self.graph.tables:
            text = " ".join([table, table.replace("_", " "), *self.table_hints.get(table, set())])
            score = _score_text(query_terms, text)
            if score >= 30:
                matches.append(SchemaMatch("table", table, None, score, "table/hint match"))
            for column in self.graph.column_order.get(table, []):
                hints = self.column_hints.get(table, {}).get(column, set())
                column_text = " ".join([column, column.replace("_", " "), *hints])
                col_score = _score_text(query_terms, column_text)
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
    def __init__(self, graph: SchemaGraphEngine) -> None:
        self.graph = graph

    def discover(self, main_table: str, tables: Iterable[str]) -> list[SchemaRelationship]:
        join_chain: list[SchemaRelationship] = []
        joined = {main_table}
        for table in tables:
            if table in joined:
                continue
            best_path = self.graph.shortest_join_path(main_table, table)
            for rel in best_path:
                if rel.to_table not in joined:
                    join_chain.append(rel)
                    joined.add(rel.to_table)
                joined.add(rel.from_table)
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
        query_terms = set(entities.canonical_terms) | {_singular(term) for term in entities.raw_terms}
        for table in list(table_scores):
            table_terms = set(_tokens(table.replace("_", " ")))
            table_terms |= {_singular(term) for term in table_terms}
            if query_terms & table_terms:
                table_scores[table] += 60
        main_table = max(table_scores.items(), key=lambda item: item[1])[0]
        selected_tables = {main_table}
        for match in matches:
            if not getattr(match, "table", None) or match.table == main_table:
                continue
            table_terms = set(_tokens(match.table.replace("_", " ")))
            table_terms |= {_singular(term) for term in table_terms}
            column_terms = set(_tokens((match.column or "").replace("_", " ")))
            explicit_table = bool(query_terms & table_terms)
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
            if match.kind == "table" and (match.score >= 75 or explicit_table):
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
        canonical = set(entities.canonical_terms)
        candidates: list[tuple[int, int, str]] = []
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
            text_terms = set(_tokens(text))
            ignored = {
                "id", "name", "date", "month", "quarter", "week", "year",
                "amount", "budget", "hours", "revenue", "total", "running",
            }
            for column in self.graph.column_order.get(base_table, []):
                column_terms = set(_tokens(column.replace("_", " "))) - ignored
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
            path = [direct] if direct else self.graph.shortest_join_path(base_table, target_table)
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
            role,
            "assigned_to" if "assignee" in query else "",
            "reported_by" if re.search(r"\breporter\b|\breported\s+by\b", query) else "",
            "deployed_by" if "deployed" in query else "",
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
        critical = missing_tables + missing_aggs + missing_group_by
        return {
            "aligned": not critical and not missing_columns,
            "planned_tables": sorted(planned_tables),
            "sql_tables": sorted(sql_tables),
            "selected_columns": sorted(selected_columns),
            "missing_tables": missing_tables,
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

    def record(
        self,
        query: str,
        valid: bool,
        breakdown: dict[str, float],
        coverage: dict[str, object],
    ) -> dict[str, object]:
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
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agent_telemetry (
                    query, confidence, valid, intent_score, entity_score, join_score,
                    column_score, aggregation_score, semantic_score, missing_concepts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    ) -> None:
        self.graph = SchemaGraphEngine(tables, columns, column_order, column_types, relationships)
        self.vocabulary = BusinessVocabularyEngine(state_db_path)
        self.cache = QueryCacheLayer(state_db_path)
        self.intent_agent = IntentDetectionAgent()
        self.entity_agent = EntityExtractionAgent(self.vocabulary, value_filters)
        self.linking_agent = SchemaLinkingEngine(self.graph, table_hints, column_hints, self.vocabulary)
        self.join_agent = JoinDiscoveryAgent(self.graph)
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
        self.logs_root = Path("logs")
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
            "confidence": ("query", "confidence_breakdown", "coverage_report"),
            "benchmark": ("benchmark_record",),
        }.items():
            try:
                target = self.logs_root / name / f"{request_id}.json"
                data = {key: payload.get(key) for key in keys}
                target.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            except OSError:
                continue

    def run(self, query: str, allow_cache: bool = True) -> CopilotResult:
        request_id = uuid.uuid4().hex[:12]
        run_started_at = time.perf_counter()
        execution_trace: dict[str, object] = {
            "request_id": request_id,
            "session_id": "local",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "events": [],
            "counters": {},
        }
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
        stage_started = time.perf_counter()
        sql = self.sql_agent.generate(plan) if plan else "The schema does not have enough information to answer this query."
        alignment_report = self.sql_agent.last_alignment if plan else {"aligned": False, "critical_mismatches": ["missing_plan"]}
        self._trace_mark(execution_trace, "sql_generator_calls", "sql_generation", stage_started, {"alignment": alignment_report})
        stage_started = time.perf_counter()
        valid, validation = self.validation_agent.validate(sql, intent, entities, plan)
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
        self._trace_mark(execution_trace, "confidence_calls", "confidence", stage_started, {"confidence": confidence_breakdown.get("overall", 0.0)})
        confidence = int(round(confidence_breakdown.get("overall", 0.0)))
        clarification_required = confidence < 70 or bool(ambiguities) or bool(unresolved)
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
        }
        benchmark_record = {
            "query": query,
            "generated_sql": final_sql,
            "candidate_sql": sql,
            "planner_correct": bool(plan and not unresolved and not ambiguities and not alignment_report.get("critical_mismatches")),
            "sql_correct": bool(valid and alignment_report.get("aligned") and not clarification_required),
            "validator_valid": bool(valid),
            "confidence": confidence,
            "coverage": coverage,
            "confidence_breakdown": confidence_breakdown,
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
            coverage_report=coverage,
            agent_telemetry=telemetry,
            execution_trace=execution_trace,
            runtime_metrics=runtime_metrics,
            benchmark_record=benchmark_record,
            missing_entities=coverage.get("entity", {}).get("missing", []),
            missing_columns=coverage.get("column", {}).get("missing", []),
            missing_joins=coverage.get("join", {}).get("missing", []),
            missing_aggregations=coverage.get("aggregation", {}).get("missing", []),
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
                "coverage_report": coverage,
                "execution_trace": execution_trace,
                "runtime_metrics": runtime_metrics,
                "benchmark_record": benchmark_record,
            },
        )
        if result.valid and result.confidence >= 70:
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
