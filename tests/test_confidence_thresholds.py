from pathlib import Path
from agentic.enterprise_copilot import EnterpriseSQLCopilot


def simple_validator(sql: str):
    return (sql.strip().lower().startswith("select"), "Valid" if sql.strip().lower().startswith("select") else "Invalid")


def make_copilot():
    tables = {"projects", "clients", "employees"}
    columns = {
        "projects": {"project_id", "client_id", "budget"},
        "clients": {"client_id", "tier", "client_name"},
        "employees": {"employee_id", "name"},
    }
    column_order = {t: list(columns[t]) for t in columns}
    column_types = {t: {} for t in tables}
    relationships = {"projects": [("client_id", "clients", "client_id")]} 
    table_hints = {}
    column_hints = {}
    value_filters = {}
    aliases = {"projects": "p", "clients": "c", "employees": "e"}
    defaults = {"projects": ["project_id", "budget"]}
    labels = {"projects": "project_id"}
    state_db_path = Path("state_test.sqlite")
    return EnterpriseSQLCopilot(
        tables, columns, column_order, column_types, relationships,
        table_hints, column_hints, value_filters, aliases, defaults, labels,
        simple_validator, state_db_path
    )


def test_confidence_correct():
    copilot = make_copilot()
    q = "Show budget by client tier"
    res = copilot.run(q)
    assert isinstance(res.confidence, int)
    # correct query should be reasonably high (may be >=80)
    assert res.confidence >= 50


def test_confidence_cross_table_tier_query():
    copilot = make_copilot()
    q = "Show project budget by client tier"
    res = copilot.run(q)
    assert res.valid is True
    assert res.confidence >= 90
    assert "JOIN clients" in res.sql
    assert "c.tier" in res.sql


def test_confidence_wrong():
    copilot = make_copilot()
    q = "Show employee salary"
    res = copilot.run(q)
    # salary missing in schema, expect low confidence
    assert res.confidence < 50
