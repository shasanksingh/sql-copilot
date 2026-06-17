# typing and regex
from typing import List, Dict, Tuple, Any
import re
# Avoid importing enterprise_copilot here to prevent circular imports; use Any for types
Intent = Any
EntityExtraction = Any
SchemaMatch = Any
QueryPlan = Any

_NON_ENTITY_TERMS = {
    "a", "an", "and", "all", "as", "by", "for", "from", "get", "give", "group",
    "list", "me", "of", "on", "per", "show", "the", "to", "top", "with", "view",
    "display", "each", "every", "latest", "recent", "highest", "lowest", "active",
    "inactive", "open", "closed", "completed", "pending", "status", "number",
    "count", "total", "sum", "average", "avg", "min", "max",
    "find", "this", "week", "month", "quarter", "running", "cumulative",
}


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9_]*", (value or "").lower().replace("_", " ")))


def _entity_terms(entities: EntityExtraction | None) -> set[str]:
    if entities is None:
        return set()
    terms = set()
    for term in [
        *(getattr(entities, "raw_terms", []) or []),
        *(getattr(entities, "canonical_terms", []) or []),
    ]:
        terms.update(_terms(str(term)))
    terms.update(
        word[:-1] if word.endswith("s") and len(word) > 3 else word
        for word in list(terms)
    )
    return terms


def _table_is_explicit(table: str, query_terms: set[str]) -> bool:
    table_terms = {
        word[:-1] if word.endswith("s") and len(word) > 3 else word
        for word in _terms(table)
    }
    return bool(table_terms) and table_terms.issubset(query_terms)


def _column_is_explicit(table: str, column: str, query_terms: set[str]) -> bool:
    column_terms = _terms(column)
    if not column_terms:
        return False
    singular_terms = {
        word[:-1] if word.endswith("s") and len(word) > 3 else word
        for word in column_terms
    }
    if column == "id" or column.endswith("_id"):
        return "id" in query_terms and (singular_terms - {"id"}).issubset(query_terms)
    if singular_terms.issubset(query_terms):
        return True
    if column.endswith(("_name", "_title", "_label")):
        return bool({"name", "title", "label"} & query_terms) and _table_is_explicit(table, query_terms)
    return False


class IntentCoverageAgent:
    def evaluate(self, intent: Intent, plan: QueryPlan) -> Dict[str, object]:
        required = []
        if intent.aggregations:
            required.append(intent.aggregations[0])
        if intent.group_by:
            required.append("GROUP_BY")
        if intent.time_granularity:
            required.append(f"TIME_{intent.time_granularity.upper()}")
        if intent.time_range:
            required.append(f"RANGE_{intent.time_range.upper()}")
        if intent.running_total:
            required.append("RUNNING_TOTAL")
        score = 100
        matched = []
        if intent.aggregations:
            if plan and plan.aggregations:
                matched.append(intent.aggregations[0])
            else:
                score = 50
        if intent.group_by:
            if plan and plan.group_by:
                matched.append("GROUP_BY")
            else:
                score = min(score, 40)
        if intent.time_granularity:
            if plan and plan.time_granularity == intent.time_granularity:
                matched.append(f"TIME_{intent.time_granularity.upper()}")
            else:
                score = min(score, 40)
        if intent.time_range:
            has_range = bool(
                plan and any(
                    item.get("operator") == intent.time_range
                    for item in plan.filters
                )
            )
            if has_range:
                matched.append(f"RANGE_{intent.time_range.upper()}")
            else:
                score = min(score, 40)
        if intent.running_total:
            if plan and plan.running_total:
                matched.append("RUNNING_TOTAL")
            else:
                score = min(score, 40)
        return {"score": score, "required": required, "matched": matched, "missing": sorted(set(required) - set(matched))}


class EntityCoverageAgent:
    READABLE_PREFERENCES = [
        r".*_name$",
        r"^full_name$",
        r"^title$",
        r"^display_name$",
        r"^description$",
        r"^email$",
    ]

    ID_PATTERNS = [r".*_id$", r"^id$"]

    def _find_readable(self, table: str, schema_columns: Dict[str, set]) -> str | None:
        cols = schema_columns.get(table, set()) if schema_columns else set()
        # search in order of preference
        for pattern in self.READABLE_PREFERENCES:
            for c in cols:
                if re.match(pattern, c):
                    return c
        return None

    def _is_id_only(self, selected_columns: List[tuple[str, str]]) -> bool:
        if not selected_columns:
            return False
        # if every selected column looks like an id, consider id-only
        for _, col in selected_columns:
            if not any(re.match(p, col) for p in self.ID_PATTERNS):
                return False
        return True

    def evaluate(self, entities: EntityExtraction, matches: List[SchemaMatch], plan: QueryPlan, query: str = "", schema_columns: Dict[str, set] | None = None) -> Dict[str, object]:
        required = [
            t for t in entities.canonical_terms
            if t and len(t) > 2 and t not in _NON_ENTITY_TERMS
        ]
        schema_terms: set[str] = set()
        for m in matches:
            schema_terms.update(_terms(m.table))
            if getattr(m, "column", None):
                schema_terms.update(_terms(m.column))
        if plan:
            schema_terms.update(_terms(plan.main_table))
            for table, column in plan.selected_columns:
                schema_terms.update(_terms(table))
                schema_terms.update(_terms(column))
            for table, column in plan.group_by:
                schema_terms.update(_terms(table))
                schema_terms.update(_terms(column))
            for aggregation in plan.aggregations:
                schema_terms.update(_terms(str(aggregation.get("table", ""))))
                schema_terms.update(_terms(str(aggregation.get("column", ""))))
            for rel in plan.joins:
                schema_terms.update(_terms(rel.from_table))
                schema_terms.update(_terms(rel.to_table))
        for item in getattr(entities, "filters", []) or []:
            schema_terms.update(_terms(item.get("table", "")))
            schema_terms.update(_terms(item.get("column", "")))
            schema_terms.update(_terms(str(item.get("value", ""))))
        matched = [t for t in required if t in schema_terms or any(t in s for s in schema_terms)]

        # Heuristic: list/show queries likely expect a label/name column for the matched table
        q = (query or "").lower()
        expected_display: Dict[str, str] = {}
        selected_table_names = set()
        selected_columns = [col for _, col in plan.selected_columns] if plan else []
        if plan:
            selected_table_names.add(plan.main_table)
            selected_table_names.update(rel.from_table for rel in plan.joins)
            selected_table_names.update(rel.to_table for rel in plan.joins)
        if not (plan and plan.aggregations) and any(w in q for w in ["list", "all", "show", "display"]):
            for m in matches:
                table = m.table
                if selected_table_names and table not in selected_table_names:
                    continue
                readable = self._find_readable(table, schema_columns or {})
                if readable:
                    expected_display[table] = readable
                    if readable not in required:
                        required.append(readable)
                    if readable in selected_columns and readable not in matched:
                        matched.append(readable)

        score = int(round((len(matched) / len(required) * 100))) if required else 100

        # Penalize if expected readable columns exist in schema but only ids were selected
        if expected_display:
            for table, readable in expected_display.items():
                if readable in (schema_columns or {}).get(table, set()):
                    table_selected = [(t, c) for t, c in plan.selected_columns if t == table] if plan else []
                    if table_selected and all(any(re.match(p, c) for p in self.ID_PATTERNS) for _, c in table_selected):
                        score = max(0, score - 30)

        return {"score": score, "required": sorted(set(required)), "matched": sorted(set(matched)), "missing": sorted(set(required) - set(matched)), "expected_display": expected_display}


class ColumnCoverageAgent:
    def evaluate(self, entities: EntityExtraction, matches: List[SchemaMatch], plan: QueryPlan) -> Dict[str, object]:
        selected_tables = set()
        if plan:
            selected_tables.add(plan.main_table)
            selected_tables.update(rel.from_table for rel in plan.joins)
            selected_tables.update(rel.to_table for rel in plan.joins)
        query_terms = _entity_terms(entities)
        requested_columns = [
            m.column for m in matches
            if m.kind == "column"
            and m.column
            and (not selected_tables or m.table in selected_tables)
            and m.score >= 45
            and (not query_terms or _column_is_explicit(m.table, m.column, query_terms))
        ]
        selected_columns = [col for _, col in plan.selected_columns] if plan else []
        if plan:
            selected_columns.extend(
                str(aggregation.get("column", ""))
                for aggregation in plan.aggregations
            )
        matched = [c for c in requested_columns if c in selected_columns]
        score = int(round((len(matched) / len(requested_columns) * 100))) if requested_columns else 100
        return {"score": score, "required": sorted(set(requested_columns)), "matched": sorted(set(matched)), "missing": sorted(set(requested_columns) - set(matched))}


class JoinCoverageAgent:
    def evaluate(self, matches: List[SchemaMatch], plan: QueryPlan, entities: EntityExtraction | None = None) -> Dict[str, object]:
        selected_tables = []
        if plan:
            selected_tables = sorted({plan.main_table, *[rel.from_table for rel in plan.joins], *[rel.to_table for rel in plan.joins]})
        query_terms = _entity_terms(entities)
        selected_column_terms = set()
        if plan:
            for _, column in plan.selected_columns:
                selected_column_terms.update(_terms(column))
        if query_terms:
            required_tables = sorted({
                *selected_tables,
                *[
                    m.table for m in matches
                    if (
                        m.kind == "table"
                        and _table_is_explicit(m.table, query_terms)
                        and not (
                            {
                                word[:-1] if word.endswith("s") and len(word) > 3 else word
                                for word in _terms(m.table)
                            }
                            & selected_column_terms
                        )
                    )
                ],
            })
        else:
            required_tables = sorted({
                m.table for m in matches
                if m.kind == "table" or (m.score >= 70 and (not selected_tables or m.table in selected_tables))
            })
        if not required_tables:
            return {"score": 100, "required_tables": required_tables, "joined_tables": selected_tables, "missing": []}
        matched = sorted(set(required_tables) & set(selected_tables))
        score = int(round((len(matched) / len(required_tables) * 100)))
        missing = sorted(set(required_tables) - set(matched))
        return {"score": score, "required_tables": required_tables, "joined_tables": matched, "missing": missing}


class AggregationCoverageAgent:
    def evaluate(self, intent: Intent, plan: QueryPlan, sql: str) -> Dict[str, object]:
        required = intent.aggregations[:] if intent.aggregations else []
        if intent.group_by:
            required.append("GROUP_BY")
        if intent.running_total:
            required.append("RUNNING_TOTAL")
        matched = []
        for agg in intent.aggregations:
            if agg and agg.lower() in (sql or "").lower():
                matched.append(agg)
        if intent.group_by and plan and plan.group_by:
            matched.append("GROUP_BY")
        if intent.running_total and plan and plan.running_total and " over " in (sql or "").lower():
            matched.append("RUNNING_TOTAL")
        score = int(round((len(matched) / len(required) * 100))) if required else 100
        return {"score": score, "required": required, "matched": matched, "missing": sorted(set(required) - set(matched))}


class SemanticCoverageAgent:
    """Lightweight semantic coverage checks comparing requested concepts against SQL.

    Detects missing business concepts and incorrect substitutions (e.g., id used instead of name).
    """
    def evaluate(self, query_terms: list[str], sql: str, matches: List[SchemaMatch], plan: QueryPlan) -> Dict[str, object]:
        sql_terms = set([t for t in re.findall(r"[a-z0-9_]+", (sql or "").lower())])
        required = [t for t in query_terms if t and len(t) > 2 and t not in _NON_ENTITY_TERMS]
        matched = [t for t in required if any(t in s for s in sql_terms) or any(t == m.table or t == m.column for m in matches)]
        # detect incorrect substitution: e.g., 'name' requested but only 'id' present
        incorrect = []
        for term in required:
            if term.endswith("name"):
                # if only id present for same entity
                id_token = term.replace("name", "id")
                if id_token in sql_terms and term not in sql_terms:
                    incorrect.append({"requested": term, "found": id_token})
        score = int(round((len(matched) / len(required) * 100))) if required else 100
        return {"score": score, "required": sorted(set(required)), "matched": sorted(set(matched)), "missing": sorted(set(required) - set(matched)), "incorrect_substitutions": incorrect}


class DisplayColumnSelectionAgent:
    """Select human-readable/display columns for a table given schema information and query intent."""
    READABLE_PREFERENCES = [
        r".*_name$",
        r"^full_name$",
        r"^title$",
        r"^display_name$",
        r"^description$",
        r"^email$",
    ]
    ID_PATTERNS = [r".*_id$", r"^id$"]

    def select(self, table: str, schema_columns: Dict[str, set], column_order: Dict[str, list], defaults: Dict[str, list], labels: Dict[str, str], explicit_requested: list[str] | None = None) -> list[str]:
        cols = schema_columns.get(table, set()) if schema_columns else set()
        selected: list[str] = []
        explicit = set(explicit_requested or [])

        # If user explicitly requested columns, respect them (but still prefer readable labels first)
        if explicit:
            for c in column_order.get(table, []):
                if c in explicit:
                    selected.append(c)
            # fill remaining readable if explicit didn't include them

        # preferred readable patterns (prefer these over schema label hints)
        for pattern in self.READABLE_PREFERENCES:
            for c in column_order.get(table, []):
                if c in cols and re.match(pattern, c) and c not in selected:
                    selected.append(c)

        # prefer label configured in labels (used as fallback if no readable found)
        label = labels.get(table)
        if label and label in cols and label not in selected:
            selected.append(label)

        # include defaults excluding id-like columns
        for c in (defaults.get(table, []) + column_order.get(table, [])):
            if c in cols and c not in selected and not any(re.match(p, c) for p in self.ID_PATTERNS):
                selected.append(c)

        # finally, if nothing selected, include first non-id or fallback to first column
        if not selected:
            for c in column_order.get(table, []):
                if c in cols and not any(re.match(p, c) for p in self.ID_PATTERNS):
                    selected.append(c)
            if not selected and column_order.get(table):
                selected.append(column_order.get(table)[0])

        # limit to first 4 for display
        return selected[:4]


class JoinPathCoverageAgent:
    """Compare planned join path with SQL-generated join path and report missing/incomplete joins."""
    def evaluate(self, graph: Any, plan: Any, matches: List[SchemaMatch], sql: str) -> Dict[str, object]:
        planned_tables = set()
        if plan:
            planned_tables.add(plan.main_table)
            planned_tables.update({rel.from_table for rel in plan.joins})
            planned_tables.update({rel.to_table for rel in plan.joins})
        # This agent audits planner-to-SQL alignment. Raw retrieval matches are
        # intentionally excluded because they may contain high-scoring bridge
        # tables that the planner correctly determined were unnecessary.
        required_tables = sorted(planned_tables)

        # extract tables present in SQL via FROM and JOIN clauses
        sql_tables = set()
        if sql:
            for m in re.findall(r"from\s+([a-z0-9_]+)\b", sql, re.IGNORECASE):
                sql_tables.add(m)
            for m in re.findall(r"join\s+([a-z0-9_]+)\b", sql, re.IGNORECASE):
                sql_tables.add(m)

        missing = sorted(set(required_tables) - sql_tables)

        # detect incomplete multi-hop joins: for each required table not in sql, compute shortest path
        incomplete = []
        if graph is not None and plan is not None:
            for t in required_tables:
                if t in sql_tables:
                    continue
                path = graph.shortest_join_path(plan.main_table, t)
                # if path exists but none of its intermediate tables are in sql_tables, mark incomplete
                if path:
                    path_tables = {rel.to_table for rel in path} | {rel.from_table for rel in path}
                    if path_tables & sql_tables:
                        # some part present, but incomplete
                        incomplete.append({"table": t, "path": [f"{r.from_table}.{r.from_column}->{r.to_table}.{r.to_column}" for r in path]})

        join_coverage_score = int(round((len(sql_tables & set(required_tables)) / len(required_tables) * 100))) if required_tables else 100

        report = {
            "join_coverage_score": join_coverage_score,
            "required_tables": required_tables,
            "planned_tables": sorted(planned_tables),
            "sql_tables": sorted(sql_tables),
            "missing_joins": missing,
            "incomplete_joins": incomplete,
        }
        return report
