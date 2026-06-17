import json
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from agentic.enterprise_copilot import EnterpriseSQLCopilot
from agentic.planner_agents import PlannerValidationAgent

# build copilot with same fixture as tests
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

def _validator(sql: str):
    return sql.lower().strip().startswith("select"), "Valid"

copilot = EnterpriseSQLCopilot(
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
    state_db_path=Path("state_test.sqlite"),
)

validator = PlannerValidationAgent()
queries = ["Show all active projects", "Get employee name and department name"]
report = []
for q in queries:
    res = copilot.run(q, allow_cache=False)
    coverage = res.coverage_report or {}
    required_tables = coverage.get("join", {}).get("required_tables", [])
    required_columns = coverage.get("column", {}).get("required", [])
    required_aggs = coverage.get("aggregation", {}).get("required", [])
    planned_tables = res.selected_tables
    planned_columns = res.selected_columns
    planned_columns_norm = [c.split('.',1)[1] if '.' in c else c for c in planned_columns]
    pv = validator.validate(required_tables, required_columns, required_aggs, planned_tables, planned_columns_norm, [])
    entry = {
        "query": q,
        "intent": res.intent,
        "entities": res.entities,
        "confidence": res.confidence,
        "coverage": res.coverage_report,
        "planned_tables": planned_tables,
        "planned_columns": planned_columns,
        "generated_sql": res.sql,
        "validation_result": pv,
        "missing_tables": pv.get("missing_tables"),
        "missing_columns": pv.get("missing_columns"),
        "missing_aggregations": pv.get("missing_aggregations"),
    }
    report.append(entry)

out = root / "reports" / "planner_validation_failed_tests.json"
out.write_text(json.dumps(report, indent=2))
print("Wrote", out)
