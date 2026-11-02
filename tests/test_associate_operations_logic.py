from __future__ import annotations

from agentic.associate_operations_domain import (
    ASSOCIATE_OPERATIONS_ALIASES,
    ASSOCIATE_OPERATIONS_COLUMN_HINTS,
    ASSOCIATE_OPERATIONS_DEFAULT_DISPLAY_COLUMNS,
    ASSOCIATE_OPERATIONS_LABEL_COLUMNS,
    ASSOCIATE_OPERATIONS_RELATIONSHIPS,
    ASSOCIATE_OPERATIONS_SCHEMA_TABLES,
    ASSOCIATE_OPERATIONS_TABLE_HINTS,
)
from agentic.business_operations_domain import parse_business_operations_rule
from agentic.enterprise_copilot import EnterpriseSQLCopilot
from pathlib import Path


ALL_TABLES = {
    "associates",
    "associate_assignments",
    "associate_activity",
    "associate_availability",
    "projects",
}


def test_associate_schema_has_business_ready_relationships() -> None:
    names = {str(table["name"]) for table in ASSOCIATE_OPERATIONS_SCHEMA_TABLES}

    assert names == ALL_TABLES - {"projects"}
    assert {tuple(item.values()) for item in ASSOCIATE_OPERATIONS_RELATIONSHIPS} >= {
        ("associate_assignments", "associate_id", "associates", "associate_id"),
        ("associate_assignments", "project_id", "projects", "project_id"),
        ("associate_availability", "associate_id", "associates", "associate_id"),
    }


def test_available_associates_are_routed_to_dynamic_planning() -> None:
    rule = parse_business_operations_rule("Show available associates by business unit", ALL_TABLES)

    assert rule is None


def test_time_bounded_availability_uses_the_general_time_planner() -> None:
    rule = parse_business_operations_rule(
        "Show associate availability from this month",
        ALL_TABLES,
    )

    assert rule is None


def test_active_assignment_rule_links_associates_to_projects() -> None:
    rule = parse_business_operations_rule("Show active associate assignments by project", ALL_TABLES)

    assert rule is not None
    assert rule["name"] == "business_associate_assignments_by_project"
    assert "FROM associate_assignments aa" in str(rule["sql"])
    assert "JOIN projects p ON aa.project_id = p.project_id" in str(rule["sql"])
    assert "LOWER(aa.assignment_status) = 'active'" in str(rule["sql"])


def _associate_copilot(tmp_path: Path) -> EnterpriseSQLCopilot:
    table_payloads = {str(item["name"]): item for item in ASSOCIATE_OPERATIONS_SCHEMA_TABLES}
    table_payloads["projects"] = {
        "columns": [
            {"name": "project_id", "data_type": "INTEGER"},
            {"name": "project_name", "data_type": "VARCHAR"},
        ],
    }
    columns = {
        table: {str(column["name"]) for column in payload["columns"]}
        for table, payload in table_payloads.items()
    }
    order = {
        table: [str(column["name"]) for column in payload["columns"]]
        for table, payload in table_payloads.items()
    }
    types = {
        table: {str(column["name"]): str(column["data_type"]) for column in payload["columns"]}
        for table, payload in table_payloads.items()
    }
    relationships: dict[str, list[tuple[str, str, str]]] = {}
    for item in ASSOCIATE_OPERATIONS_RELATIONSHIPS:
        relationships.setdefault(str(item["from_table"]), []).append(
            (str(item["from_column"]), str(item["to_table"]), str(item["to_column"]))
        )

    return EnterpriseSQLCopilot(
        tables=set(table_payloads),
        columns=columns,
        column_order=order,
        column_types=types,
        relationships=relationships,
        table_hints=ASSOCIATE_OPERATIONS_TABLE_HINTS,
        column_hints=ASSOCIATE_OPERATIONS_COLUMN_HINTS,
        value_filters={},
        aliases=ASSOCIATE_OPERATIONS_ALIASES | {"projects": "p"},
        defaults=ASSOCIATE_OPERATIONS_DEFAULT_DISPLAY_COLUMNS,
        labels=ASSOCIATE_OPERATIONS_LABEL_COLUMNS | {"projects": "project_name"},
        validator=lambda sql: (sql.lower().strip().startswith("select"), "Valid"),
        state_db_path=tmp_path / "associate.sqlite",
    )


def test_associate_requests_produce_distinct_schema_grounded_sql(tmp_path: Path) -> None:
    copilot = _associate_copilot(tmp_path)

    availability = copilot.run("Show available associates by business unit", allow_cache=False)
    activity = copilot.run("List associate activity", allow_cache=False)
    delivery = copilot.run("Delivery hours by project this month", allow_cache=False)
    trend = copilot.run("Trend associate availability by month", allow_cache=False)

    assert availability.valid is True
    assert "FROM associate_availability av" in availability.sql
    assert "LOWER(av.availability_status) = 'available'" in availability.sql
    assert "a.business_unit" in availability.sql

    assert activity.valid is True
    assert activity.sql == "SELECT *\nFROM associate_activity;"
    assert activity.sql != availability.sql

    assert delivery.valid is True
    assert "SUM(act.hours_logged) AS delivery_hours" in delivery.sql
    assert "JOIN projects p" in delivery.sql
    assert delivery.sql != activity.sql

    assert trend.valid is True
    assert "COUNT(av.availability_id) AS availability_count" in trend.sql
    assert "DATE_TRUNC('month', av.available_from)" in trend.sql
    assert trend.sql != availability.sql
