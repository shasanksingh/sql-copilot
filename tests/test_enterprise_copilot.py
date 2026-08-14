from __future__ import annotations

from pathlib import Path

from agentic.enterprise_copilot import EnterpriseSQLCopilot, JoinDiscoveryAgent, SchemaGraphEngine


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


def _copilot(tmp_path: Path, llm_provider=None) -> EnterpriseSQLCopilot:
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
        llm_provider=llm_provider,
    )


def test_active_projects_generates_valid_sql(tmp_path: Path) -> None:
    result = _copilot(tmp_path).run("Show all active projects", allow_cache=False)

    assert result.valid is True
    assert result.confidence >= 70
    assert "FROM projects p" in result.sql
    assert "LOWER(p.status) = 'active'" in result.sql
    assert "p.project_name" in result.sql
    assert "p.budget" not in result.sql
    assert result.missing_columns == []
    assert result.missing_joins == []
    assert {item["table"] for item in result.plan["filters"]} == {"projects"}
    evidence = {item["key"]: item for item in result.confidence_evidence}
    assert evidence["join"]["applicable"] is False
    assert evidence["aggregation"]["applicable"] is False
    assert evidence["validation"]["score"] == 100
    workflow = result.execution_trace["workflow"]
    assert workflow["requested_engine"] == "langgraph"
    assert any(node["key"] == "query_planning" for node in workflow["nodes"])
    assert {"from": "query_planning", "to": "sql_generation"} in workflow["edges"]
    assert result.execution_trace["workflow_run"]["status"] in {"executed", "fallback"}
    assert "sql_generation" in result.execution_trace["workflow_run"]["visited_agents"]
    assert result.runtime_metrics["workflow_engine"] in {"langgraph", "linear"}


def test_employee_name_and_department_selects_only_requested_columns(tmp_path: Path) -> None:
    result = _copilot(tmp_path).run("Get employee name and department name", allow_cache=False)

    assert result.valid is True
    assert "e.full_name" in result.sql
    assert "e.department" in result.sql
    assert "e.email" not in result.sql
    assert "e.status" not in result.sql


def test_customer_details_selects_default_detail_columns(tmp_path: Path) -> None:
    copilot = EnterpriseSQLCopilot(
        tables={"clients"},
        columns={
            "clients": {"client_id", "client_name", "tier", "contact_email", "industry", "created_at"},
        },
        column_order={
            "clients": ["client_id", "client_name", "tier", "contact_email", "industry", "created_at"],
        },
        column_types={
            "clients": {
                "client_id": "INT",
                "client_name": "VARCHAR",
                "tier": "VARCHAR",
                "contact_email": "VARCHAR",
                "industry": "VARCHAR",
                "created_at": "TIMESTAMP",
            },
        },
        relationships={},
        table_hints={"clients": {"client", "clients", "customer", "customers"}},
        column_hints={"clients": {"client_name": {"name", "customer name"}}},
        value_filters={},
        aliases={"clients": "c"},
        defaults={"clients": ["client_id", "client_name", "tier", "contact_email", "industry", "created_at"]},
        labels={"clients": "client_name"},
        validator=_validator,
        state_db_path=tmp_path / "agent.sqlite",
    )

    result = copilot.run("Give details of all customer", allow_cache=False)

    assert result.valid is True
    assert "FROM clients c" in result.sql
    for column in ["client_id", "client_name", "tier", "contact_email", "industry", "created_at"]:
        assert f"c.{column}" in result.sql
    assert result.coverage_report["entity"]["missing"] == []
    assert result.coverage_report["semantic"]["missing"] == []


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


class _FakeGeneration:
    def __init__(
        self,
        data: dict[str, object],
        success: bool = True,
        error_category: str = "",
        error_message: str = "",
    ) -> None:
        self.data = data
        self.text = ""
        self.success = success
        self.provider = "nvidia"
        self.model = "openai/gpt-oss-20b"
        self.latency_ms = 4.0
        self.error_category = "" if success else error_category or "provider_error"
        self.error_message = error_message
        self.retry_count = 0


class _HallucinatingProvider:
    available = True

    def __init__(self) -> None:
        self.fallbacks: list[str] = []
        self.repair_attempts = 0

    def health_check(self, deep: bool = False) -> dict[str, object]:
        return {
            "provider": "nvidia",
            "model": "openai/gpt-oss-20b",
            "configured": True,
            "available": True,
            "status": "ready",
        }

    def metrics(self) -> dict[str, object]:
        return {"fallback_count": len(self.fallbacks), "repair_attempts": self.repair_attempts}

    def record_fallback(self, category: str) -> None:
        self.fallbacks.append(category)

    def generate_structured(self, *_args, **_kwargs):
        return _FakeGeneration({"sql": "SELECT x.fake_column FROM invented_table x;", "model_confidence": 99})


def test_llm_hallucinated_schema_falls_back_to_deterministic_sql(tmp_path: Path) -> None:
    provider = _HallucinatingProvider()

    result = _copilot(tmp_path, provider).run("Count projects by employee department", allow_cache=False)

    assert result.valid is True
    assert "invented_table" not in result.sql
    assert "FROM projects p" in result.sql
    assert result.llm_trace["fallback_used"] is True
    assert result.llm_trace["fallback_reason"] == "candidate_failed_validation"
    assert provider.fallbacks


class _ConnectionFailingProvider(_HallucinatingProvider):
    def generate_structured(self, *_args, **_kwargs):
        return _FakeGeneration(
            {},
            success=False,
            error_category="provider_error",
            error_message="Connection error.",
        )


def test_llm_provider_error_does_not_report_missing_sql_assist(tmp_path: Path) -> None:
    result = _copilot(tmp_path, _ConnectionFailingProvider()).run("Count projects by employee department", allow_cache=False)

    evidence = {item["key"]: item for item in result.confidence_evidence}
    assert result.llm_trace["fallback_used"] is True
    assert result.llm_trace["fallback_reason"] == "provider_error"
    assert evidence["model_confidence"]["applicable"] is False
    assert evidence["model_confidence"]["missing"] == []
    assert evidence["model_confidence"]["note"] == "NVIDIA assist could not connect; deterministic SQL was used."


def test_join_discovery_supports_five_plus_table_paths() -> None:
    tables = {"t1", "t2", "t3", "t4", "t5", "t6"}
    columns = {
        "t1": {"id"},
        "t2": {"id", "t1_id"},
        "t3": {"id", "t2_id"},
        "t4": {"id", "t3_id"},
        "t5": {"id", "t4_id"},
        "t6": {"id", "t5_id"},
    }
    column_order = {table: sorted(cols) for table, cols in columns.items()}
    column_types = {table: {column: "INTEGER" for column in cols} for table, cols in columns.items()}
    relationships = {
        "t2": [("t1_id", "t1", "id")],
        "t3": [("t2_id", "t2", "id")],
        "t4": [("t3_id", "t3", "id")],
        "t5": [("t4_id", "t4", "id")],
        "t6": [("t5_id", "t5", "id")],
    }
    graph = SchemaGraphEngine(tables, columns, column_order, column_types, relationships)
    joiner = JoinDiscoveryAgent(graph, max_depth=8)

    joins = joiner.discover("t1", {"t6"})

    assert len(joins) == 5
    assert joiner.last_diagnostics["paths"][0]["selected_depth"] == 5


def test_role_aware_join_prefers_reported_by_over_assigned_to(tmp_path: Path) -> None:
    copilot = EnterpriseSQLCopilot(
        tables={"employees", "bugs"},
        columns={
            "employees": {"employee_id", "full_name"},
            "bugs": {"bug_id", "reported_by", "assigned_to", "status"},
        },
        column_order={
            "employees": ["employee_id", "full_name"],
            "bugs": ["bug_id", "reported_by", "assigned_to", "status"],
        },
        column_types={
            "employees": {"employee_id": "INT", "full_name": "VARCHAR"},
            "bugs": {"bug_id": "INT", "reported_by": "INT", "assigned_to": "INT", "status": "TEXT"},
        },
        relationships={
            "bugs": [
                ("assigned_to", "employees", "employee_id"),
                ("reported_by", "employees", "employee_id"),
            ],
        },
        table_hints={
            "employees": {"employee", "employees", "reporter", "assignee"},
            "bugs": {"bug", "bugs", "reported", "assigned"},
        },
        column_hints={
            "employees": {"full_name": {"name", "employee"}},
            "bugs": {
                "reported_by": {"reported by", "reporter"},
                "assigned_to": {"assigned to", "assignee"},
                "status": {"status"},
            },
        },
        value_filters={},
        aliases={"employees": "e", "bugs": "b"},
        defaults={"bugs": ["bug_id", "status"], "employees": ["full_name"]},
        labels={"employees": "full_name", "bugs": "bug_id"},
        validator=_validator,
        state_db_path=tmp_path / "role.sqlite",
    )

    result = copilot.run("Show bugs reported by employee", allow_cache=False)

    assert result.valid is True
    assert result.plan["joins"][0]["from_column"] == "reported_by"
