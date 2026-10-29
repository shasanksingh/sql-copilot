from __future__ import annotations

from agentic.associate_operations_domain import (
    ASSOCIATE_OPERATIONS_RELATIONSHIPS,
    ASSOCIATE_OPERATIONS_SCHEMA_TABLES,
)
from agentic.business_operations_domain import parse_business_operations_rule


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


def test_available_associates_rule_is_schema_grounded() -> None:
    rule = parse_business_operations_rule("Show available associates by business unit", ALL_TABLES)

    assert rule is not None
    assert rule["name"] == "business_available_associates"
    assert "FROM associate_availability av" in str(rule["sql"])
    assert "JOIN associates a ON av.associate_id = a.associate_id" in str(rule["sql"])
    assert "LOWER(av.availability_status) = 'available'" in str(rule["sql"])


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
