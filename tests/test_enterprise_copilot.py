from __future__ import annotations

from pathlib import Path

from agentic.enterprise_copilot import EnterpriseSQLCopilot


TABLES = {"employees", "projects", "project_team"}
COLUMNS = {
    "employees": {"employee_id", "full_name", "department", "status"},
    "projects": {"project_id", "project_name", "status", "budget"},
    "project_team": {"id", "project_id", "employee_id"},
}
COLUMN_ORDER = {
    "employees": ["employee_id", "full_name", "department", "status"],
    "projects": ["project_id", "project_name", "status", "budget"],
    "project_team": ["id", "project_id", "employee_id"],
}
COLUMN_TYPES = {
    "employees": {"employee_id": "INT", "full_name": "VARCHAR", "department": "VARCHAR", "status": "ENUM"},
    "projects": {"project_id": "INT", "project_name": "VARCHAR", "status": "ENUM", "budget": "DECIMAL"},
    "project_team": {"id": "INT", "project_id": "INT", "employee_id": "INT"},
}
RELATIONSHIPS = {
    "project_team": [
        ("project_id", "projects", "project_id"),
        ("employee_id", "employees", "employee_id"),
    ]
}
TABLE_HINTS = {
    "employees": {"employee", "employees", "staff"},
    "projects": {"project", "projects", "active"},
    "project_team": {"team", "assignment"},
}
COLUMN_HINTS = {
    "employees": {
        "full_name": {"name"},
        "department": {"department", "team"},
        "status": {"status", "active"},
    },
    "projects": {
        "project_name": {"name"},
        "status": {"status", "active"},
        "budget": {"budget"},
    },
}
VALUE_FILTERS = {
    "employees": {"status": {"active": "active"}},
    "projects": {"status": {"active": "active"}},
}


def _validator(sql: str) -> tuple[bool, str]:
    return sql.lower().strip().startswith("select"), "Valid"


def _copilot(tmp_path: Path) -> EnterpriseSQLCopilot:
    return EnterpriseSQLCopilot(
        tables=TABLES,
        columns=COLUMNS,
        column_order=COLUMN_ORDER,
        column_types=COLUMN_TYPES,
        relationships=RELATIONSHIPS,
        table_hints=TABLE_HINTS,
        column_hints=COLUMN_HINTS,
        value_filters=VALUE_FILTERS,
        aliases={"employees": "e", "projects": "p", "project_team": "pt"},
        defaults={
            "employees": ["employee_id", "full_name", "department", "status"],
            "projects": ["project_id", "project_name", "status", "budget"],
        },
        labels={"employees": "full_name", "projects": "project_name"},
        validator=_validator,
        state_db_path=tmp_path / "agent.sqlite",
    )


def test_active_projects_generates_valid_sql(tmp_path: Path) -> None:
    result = _copilot(tmp_path).run("Show all active projects", allow_cache=False)

    assert result.valid is True
    assert result.confidence >= 70
    assert "FROM projects p" in result.sql
    assert "LOWER(p.status) = 'active'" in result.sql
    assert "p.project_name" in result.sql
    assert "p.budget" not in result.sql


def test_employee_name_and_department_selects_only_requested_columns(tmp_path: Path) -> None:
    result = _copilot(tmp_path).run("Get employee name and department name", allow_cache=False)

    assert result.valid is True
    assert "e.full_name" in result.sql
    assert "e.department" in result.sql
    assert "e.email" not in result.sql
    assert "e.status" not in result.sql


def test_salary_without_schema_column_requires_clarification(tmp_path: Path) -> None:
    result = _copilot(tmp_path).run("Show top 5 highest paid employees", allow_cache=False)

    assert result.valid is False
    assert result.clarification_required is True
    assert result.sql.startswith("I cannot generate reliable SQL")
    assert result.clarification_options == ["Map 'salary/pay/compensation' to a real schema column first."]


def test_status_only_query_returns_ambiguity_options(tmp_path: Path) -> None:
    result = _copilot(tmp_path).run("show status", allow_cache=False)

    assert result.valid is False
    assert result.clarification_required is True
    assert "employees.status" in result.clarification_options
    assert "projects.status" in result.clarification_options
