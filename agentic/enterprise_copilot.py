from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable

try:
    import networkx as nx
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    nx = None

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


TokenSet = set[str]
QUERY_CACHE_VERSION = "enterprise-v2"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9_]*", text.lower().replace("-", " "))


def _singular(word: str) -> str:
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
            "status": {"status", "state"},
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
        intent.group_by = bool(re.search(r"\b(by|per|each|grouped by|group by)\b", q))
        if re.search(r"\b(lowest|least|min|minimum|oldest|earliest)\b", q):
            intent.order_by = "requested"
            intent.order_direction = "ASC"
        elif re.search(r"\b(top|highest|most|max|maximum|largest|latest|recent|newest)\b", q):
            intent.order_by = "requested"
            intent.order_direction = "DESC"
        match = re.search(r"\b(?:top|first|limit|last)\s+(\d{1,4})\b", q)
        intent.limit = min(int(match.group(1)), 1000) if match else None
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
        measures = [term for term in canonical if term in {"salary", "amount", "budget", "hours"}]
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
    ) -> QueryPlan | None:
        if unresolved or ambiguities or not matches:
            main = matches[0].table if matches else ""
            return QueryPlan(main, [], [], entities.filters, [], [], None, intent.limit, 20, unresolved, ambiguities)

        table_scores: dict[str, int] = defaultdict(int)
        for match in matches:
            table_scores[match.table] += match.score if match.kind == "table" else int(match.score * 0.65)
        main_table = max(table_scores.items(), key=lambda item: item[1])[0]
        selected_tables = {main_table}
        for match in matches:
            if match.kind == "column" and match.score >= 70:
                selected_tables.add(match.table)
        joins = self.joiner.discover(main_table, selected_tables)

        selected_columns = self._explicit_requested_columns(main_table, entities)
        if not selected_columns:
            selected_columns = self._concise_display_columns(main_table, entities)

        aggregations: list[dict[str, str]] = []
        group_by: list[tuple[str, str]] = []
        if intent.aggregations:
            agg = intent.aggregations[0]
            id_cols = [col for col in self.graph.column_order.get(main_table, []) if col.endswith("_id")]
            target = id_cols[0] if id_cols else "*"
            aggregations.append({"function": agg, "table": main_table, "column": target, "alias": "record_count"})
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
                order_by = ("record_count", intent.order_direction or "DESC")
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
            entities.filters,
            aggregations,
            group_by,
            order_by,
            intent.limit,
            confidence,
        )

    def _default_group_column(self, table: str) -> str | None:
        for candidate in ("department", "status", "role", "priority", "severity", "industry"):
            if candidate in self.graph.columns.get(table, set()):
                return candidate
        return None

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

    def generate(self, plan: QueryPlan) -> str:
        if plan.unresolved_terms:
            return "The schema does not have enough information to answer this query."
        if plan.ambiguity_options:
            return "Clarification required before SQL generation."

        aliases = {plan.main_table: self.aliases.get(plan.main_table, plan.main_table[:1])}
        for rel in plan.joins:
            aliases.setdefault(rel.from_table, self.aliases.get(rel.from_table, rel.from_table[:1]))
            aliases.setdefault(rel.to_table, self.aliases.get(rel.to_table, rel.to_table[:1]))

        select_parts: list[str] = []
        for table, column in plan.selected_columns:
            select_parts.append(f"{aliases[table]}.{column}")
        for agg in plan.aggregations:
            table = agg["table"]
            column = agg["column"]
            target = "*" if column == "*" else f"{aliases[table]}.{column}"
            select_parts.append(f"{agg['function']}({target}) AS {agg['alias']}")
        if not select_parts:
            select_parts = [f"{aliases[plan.main_table]}.*"]

        lines = ["SELECT", "  " + ",\n  ".join(select_parts), f"FROM {plan.main_table} {aliases[plan.main_table]}"]
        emitted = {plan.main_table}
        for rel in plan.joins:
            left_alias = aliases[rel.from_table]
            right_alias = aliases[rel.to_table]
            if rel.to_table in emitted:
                continue
            lines.append(
                f"JOIN {rel.to_table} {right_alias} ON {left_alias}.{rel.from_column} = {right_alias}.{rel.to_column}"
            )
            emitted.add(rel.to_table)

        filters = [
            f"LOWER({aliases[item['table']]}.{item['column']}) {item.get('operator', '=')} '{item['value'].lower()}'"
            for item in plan.filters
            if item["table"] in aliases
        ]
        if filters:
            lines.append("WHERE " + " AND ".join(filters))
        if plan.group_by:
            lines.append("GROUP BY " + ", ".join(f"{aliases[t]}.{c}" for t, c in plan.group_by))
        if plan.order_by:
            expr, direction = plan.order_by
            if "." in expr:
                table, col = expr.split(".", 1)
                expr = f"{aliases.get(table, table)}.{col}"
            lines.append(f"ORDER BY {expr} {direction}")
        if plan.limit:
            lines.append(f"LIMIT {plan.limit}")
        return "\n".join(lines) + ";"


class SQLValidationAgent:
    def __init__(self, validator: Callable[[str], tuple[bool, str]]) -> None:
        self.validator = validator

    def validate(self, sql: str, intent: Intent, entities: EntityExtraction, plan: QueryPlan | None) -> tuple[bool, str]:
        if not sql.lower().strip().startswith("select"):
            return False, "SQL generation was rejected before SELECT validation"
        valid, message = self.validator(sql)
        if not valid:
            return valid, message
        if plan and intent.limit and f"limit {intent.limit}" not in sql.lower():
            return False, "Requested LIMIT is missing"
        for term in plan.unresolved_terms if plan else []:
            return False, f"Unresolved business term: {term}"
        return True, "Valid"


class ConfidenceScoringAgent:
    def score(self, plan: QueryPlan | None, valid: bool, unresolved: list[str], ambiguities: list[str]) -> int:
        if unresolved or ambiguities or plan is None:
            return 25
        score = plan.confidence
        if valid:
            score += 8
        else:
            score -= 30
        if plan.joins:
            score -= max(0, len(plan.joins) - 1) * 5
        return max(0, min(100, score))


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
        self.sql_agent = SQLGenerationAgent(aliases)
        self.validation_agent = SQLValidationAgent(validator)
        self.confidence_agent = ConfidenceScoringAgent()
        self.optimization_agent = SQLOptimizationEngine()

    def run(self, query: str, allow_cache: bool = True) -> CopilotResult:
        if allow_cache:
            cached = self.cache.get(query)
            if cached:
                return cached

        intent = self.intent_agent.detect(query)
        entities = self.entity_agent.extract(query)
        matches, unresolved, ambiguities = self.linking_agent.link(query, entities)
        plan = self.planner_agent.plan(intent, entities, matches, unresolved, ambiguities)
        sql = self.sql_agent.generate(plan) if plan else "The schema does not have enough information to answer this query."
        valid, validation = self.validation_agent.validate(sql, intent, entities, plan)
        confidence = self.confidence_agent.score(plan, valid, unresolved, ambiguities)
        clarification_required = confidence < 70 or bool(ambiguities) or bool(unresolved)
        options = ambiguities[:5]
        if unresolved:
            options = [f"Map '{term}' to a real schema column first." for term in unresolved]

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

        result = CopilotResult(
            sql=sql if not clarification_required else self._clarification_message(unresolved, ambiguities),
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
