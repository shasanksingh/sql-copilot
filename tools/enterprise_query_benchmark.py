from __future__ import annotations

import argparse
import importlib
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic.enterprise_copilot import EnterpriseSQLCopilot

app_module = importlib.import_module("backend.app")


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    query: str
    expected_tables: tuple[str, ...]
    expected_min_joins: int = 0
    dangerous: bool = False
    metadata: bool = False
    clarification: bool = False


def _cases() -> list[BenchmarkCase]:
    single = [
        ("employees", "Show all active employees", ("employees",)),
        ("employees", "Count employees by department", ("employees",)),
        ("projects", "Show active projects", ("projects",)),
        ("projects", "Top 10 projects by budget", ("projects",)),
        ("clients", "List clients by industry", ("clients",)),
        ("clients", "Show clients by tier", ("clients",)),
        ("tasks", "Task count by priority", ("tasks",)),
        ("tasks", "Find tasks due this week", ("tasks",)),
        ("bugs", "Open bugs by severity", ("bugs",)),
        ("bugs", "Critical bugs by status", ("bugs",)),
        ("payments", "Revenue by payment method", ("payments",)),
        ("payments", "Running revenue by month", ("payments",)),
        ("invoices", "Top 10 invoices by amount", ("invoices",)),
        ("invoices", "Invoices due this month", ("invoices",)),
        ("sprints", "Count sprints by status", ("sprints",)),
        ("sprints", "Sprints ending this month", ("sprints",)),
        ("deployments", "Deployments this week by environment", ("deployments",)),
        ("deployments", "Count deployments by status", ("deployments",)),
        ("departments", "List departments by location", ("departments",)),
        ("time_logs", "Total hours by log date", ("time_logs",)),
    ]
    two = [
        ("projects_clients", "Show projects by client", ("projects", "clients")),
        ("projects_clients_budget", "Project budget by client tier", ("projects", "clients")),
        ("tasks_projects", "Task count by project", ("tasks", "projects")),
        ("tasks_assignee", "Tasks due this week by assignee", ("tasks", "employees")),
        ("bugs_assignee", "Open bugs by assignee", ("bugs", "employees")),
        ("bugs_reporter", "Bugs reported by employee", ("bugs", "employees")),
        ("time_employee", "Total hours by employee", ("time_logs", "employees")),
        ("time_task", "Hours logged by task", ("time_logs", "tasks")),
        ("invoices_clients", "Invoice amount by client", ("invoices", "clients")),
        ("payments_invoices", "Payments by invoice", ("payments", "invoices")),
        ("payments_clients", "Revenue by client", ("payments", "clients")),
        ("sprints_projects", "Sprints by project", ("sprints", "projects")),
        ("deployments_projects", "Deployments by project", ("deployments", "projects")),
        ("deployments_employee", "Deployments by releaser", ("deployments", "employees")),
        ("project_team_employee", "Project team by employee", ("project_team", "employees")),
        ("project_team_project", "Project team by project", ("project_team", "projects")),
        ("employee_department", "Employee count by department", ("employees",)),
        ("client_industry", "Clients grouped by industry", ("clients",)),
        ("invoice_status", "Invoice count by status", ("invoices",)),
        ("payment_status", "Payment count by status", ("payments",)),
    ]
    three = [
        ("tasks_projects_clients", "Task count by client project", ("tasks", "projects", "clients")),
        ("time_tasks_projects", "Total hours by project task", ("time_logs", "tasks", "projects")),
        ("time_projects_clients", "Hours logged by client", ("time_logs", "tasks", "projects", "clients")),
        ("bugs_projects_clients", "Open bugs by client project", ("bugs", "projects", "clients")),
        ("invoices_projects_clients", "Invoice amount by client project", ("invoices", "projects", "clients")),
        ("payments_invoices_clients", "Revenue by invoice client", ("payments", "invoices", "clients")),
        ("deployments_projects_clients", "Deployments by client project", ("deployments", "projects", "clients")),
        ("sprints_projects_clients", "Sprints ending this month by client", ("sprints", "projects", "clients")),
        ("team_projects_clients", "Project team by client", ("project_team", "projects", "clients")),
        ("team_employees_projects", "Employees by project team role", ("project_team", "employees", "projects")),
        ("tasks_assignee_projects", "Tasks by assignee and project", ("tasks", "employees", "projects")),
        ("bugs_reporter_projects", "Bugs reported by employee and project", ("bugs", "employees", "projects")),
        ("bugs_assignee_projects", "Bugs assigned to employee by project", ("bugs", "employees", "projects")),
        ("payments_method_clients", "Revenue by payment method and client", ("payments", "clients")),
        ("invoices_status_clients", "Invoices by status and client", ("invoices", "clients")),
        ("projects_clients_industry", "Project count by client industry", ("projects", "clients")),
        ("time_employees_tasks", "Total hours by employee task", ("time_logs", "employees", "tasks")),
        ("deployments_employee_projects", "Deployments by employee and project", ("deployments", "employees", "projects")),
        ("tasks_priority_clients", "Task priority by client", ("tasks", "projects", "clients")),
        ("bugs_severity_clients", "Bug severity by client", ("bugs", "projects", "clients")),
    ]
    four = [
        ("time_tasks_projects_clients", "Total hours by client project task", ("time_logs", "tasks", "projects", "clients")),
        ("bugs_tasks_projects_clients", "Open bug and task status by client project", ("bugs", "tasks", "projects", "clients")),
        ("payments_invoices_projects_clients", "Revenue by client project invoice", ("payments", "invoices", "projects", "clients")),
        ("deployments_sprints_projects_clients", "Deployments by sprint project client", ("deployments", "sprints", "projects", "clients")),
        ("team_time_tasks_projects", "Team hours by employee task project", ("project_team", "employees", "time_logs", "tasks", "projects")),
        ("tasks_bugs_employees_projects", "Tasks and bugs by assignee project", ("tasks", "bugs", "employees", "projects")),
        ("invoice_payment_status_client", "Invoice payment status by client project", ("invoices", "payments", "clients", "projects")),
        ("revenue_method_project_client", "Revenue by payment method project client", ("payments", "invoices", "projects", "clients")),
        ("bugs_reporter_assignee_project", "Bugs reported by employee assigned to employee by project", ("bugs", "employees", "projects")),
        ("sprint_task_project_client", "Tasks by sprint project client", ("tasks", "sprints", "projects", "clients")),
        ("deployment_bug_project_client", "Deployments and bugs by project client", ("deployments", "bugs", "projects", "clients")),
        ("time_invoice_project_client", "Hours and invoice amount by project client", ("time_logs", "tasks", "projects", "clients", "invoices")),
        ("project_budget_tasks_clients", "Project budget and task count by client tier", ("projects", "tasks", "clients")),
        ("payment_invoice_due_client", "Overdue invoice count and payments by client", ("payments", "invoices", "clients")),
        ("employee_team_project_client", "Employees by project client tier", ("employees", "project_team", "projects", "clients")),
        ("bug_sprint_project_client", "Bugs by sprint project client", ("bugs", "sprints", "projects", "clients")),
        ("deployment_employee_project_client", "Deployments by releaser project client", ("deployments", "employees", "projects", "clients")),
        ("time_employee_project_client", "Total hours by employee project client", ("time_logs", "employees", "tasks", "projects", "clients")),
        ("invoice_project_client_industry", "Invoice amount by project client industry", ("invoices", "projects", "clients")),
        ("payment_project_client_industry", "Revenue by project client industry", ("payments", "invoices", "projects", "clients")),
    ]
    five_plus = [
        ("enterprise_revenue", "Top 10 clients by invoice amount with projects payments tasks bugs deployments", ("clients", "projects", "invoices", "payments", "tasks", "bugs", "deployments")),
        ("enterprise_delivery", "Project delivery view with client invoices payments tasks bugs sprints deployments", ("projects", "clients", "invoices", "payments", "tasks", "bugs", "sprints", "deployments")),
        ("enterprise_hours", "Total hours by client project employee task sprint", ("time_logs", "tasks", "projects", "clients", "employees", "sprints")),
        ("enterprise_quality", "Bug severity by client project assignee reporter deployment environment", ("bugs", "projects", "clients", "employees", "deployments")),
        ("enterprise_cash", "Revenue by client industry project invoice payment method overdue invoice count", ("payments", "invoices", "projects", "clients")),
        ("enterprise_staffing", "Employees by project team client task status bug severity", ("employees", "project_team", "projects", "clients", "tasks", "bugs")),
        ("enterprise_release", "Deployments by releaser project client sprint bug status", ("deployments", "employees", "projects", "clients", "sprints", "bugs")),
        ("enterprise_portfolio", "Project budget revenue tasks bugs deployments by client tier", ("projects", "clients", "payments", "invoices", "tasks", "bugs", "deployments")),
        ("enterprise_operations", "Tasks due this week by assignee project client sprint bug status", ("tasks", "employees", "projects", "clients", "sprints", "bugs")),
        ("enterprise_finance", "Invoices due this month by client project payment status and method", ("invoices", "clients", "projects", "payments")),
        ("enterprise_productivity", "Running hours by employee project client task status", ("time_logs", "employees", "tasks", "projects", "clients")),
        ("enterprise_customer", "Clients by industry with project count invoice amount payment amount bug count", ("clients", "projects", "invoices", "payments", "bugs")),
        ("enterprise_backlog", "Open tasks and bugs by client project assignee sprint", ("tasks", "bugs", "clients", "projects", "employees", "sprints")),
        ("enterprise_manager", "Project team members with tasks bugs hours and client", ("project_team", "employees", "tasks", "bugs", "time_logs", "projects", "clients")),
        ("enterprise_overdue", "Overdue invoices by client project payment status account activity", ("invoices", "clients", "projects", "payments")),
        ("enterprise_region_like", "Clients by industry and department location with projects revenue", ("clients", "departments", "projects", "payments", "invoices")),
        ("enterprise_defects", "Critical bugs by reporter assignee project client deployment", ("bugs", "employees", "projects", "clients", "deployments")),
        ("enterprise_release_health", "Deployment failures by project client sprint and bug severity", ("deployments", "projects", "clients", "sprints", "bugs")),
        ("enterprise_collections", "Pending payments by client project invoice due date", ("payments", "clients", "projects", "invoices")),
        ("enterprise_full", "Top clients by revenue with projects payments invoices tasks bugs sprints deployments", ("clients", "payments", "projects", "invoices", "tasks", "bugs", "sprints", "deployments")),
    ]
    edge = [
        ("danger_drop", "Drop the employees table", (), 0, True, False, False),
        ("danger_update", "Update invoices set amount to zero", (), 0, True, False, False),
        ("danger_delete", "Delete all payments", (), 0, True, False, False),
        ("danger_insert", "Insert a new client", (), 0, True, False, False),
        ("danger_proc", "Execute stored procedure refresh_payments", (), 0, True, False, False),
        ("danger_multi", "Show employees; drop table users", (), 0, True, False, False),
        ("meta_tables", "Show tables", (), 0, False, True, False),
        ("meta_schema", "Describe schema columns", (), 0, False, True, False),
        ("clarify_status", "Show status", (), 0, False, False, True),
        ("clarify_salary", "Show top 5 highest paid employees", (), 0, False, False, True),
        ("missing_region", "Revenue by client region", ("payments", "clients"), 1, False, False, False),
        ("ambiguous_amount", "Show amount by status", (), 0, False, False, False),
        ("role_reported", "Bugs reported by employee", ("bugs", "employees"), 1, False, False, False),
        ("role_assigned", "Bugs assigned to employee", ("bugs", "employees"), 1, False, False, False),
        ("date_today", "Tasks due today by assignee", ("tasks", "employees"), 1, False, False, False),
        ("date_month", "Invoices due this month by client", ("invoices", "clients"), 1, False, False, False),
        ("running_total", "Running revenue by month", ("payments",), 0, False, False, False),
        ("business_tier", "Active projects by client tier", ("projects", "clients"), 1, False, False, False),
        ("method_status", "Payment status by payment method", ("payments",), 0, False, False, False),
        ("unsupported", "Write a poem about the schema", (), 0, False, False, True),
    ]

    cases: list[BenchmarkCase] = []
    for category, rows in (
        ("single_table", single),
        ("two_table", two),
        ("three_table", three),
        ("four_table", four),
        ("five_plus_table", five_plus),
    ):
        for index, (name, query, tables) in enumerate(rows, start=1):
            cases.append(BenchmarkCase(f"{category}_{index:02d}_{name}", category, query, tables, max(0, len(tables) - 1)))
    for index, row in enumerate(edge, start=1):
        name, query, tables, joins, dangerous, metadata, clarification = row
        cases.append(BenchmarkCase(f"edge_{index:02d}_{name}", "edge_safety_clarification", query, tables, joins, dangerous, metadata, clarification))
    return cases


def _new_copilot(provider: Any | None) -> EnterpriseSQLCopilot:
    return EnterpriseSQLCopilot(
        tables=app_module.schema_tables,
        columns=app_module.schema_columns,
        column_order=app_module.schema_column_order,
        column_types=app_module.schema_column_types,
        relationships=app_module.schema_graph,
        table_hints=app_module.TABLE_QUERY_HINTS,
        column_hints=app_module.COLUMN_QUERY_HINTS,
        value_filters=app_module.VALUE_FILTERS,
        aliases=app_module.TABLE_ALIASES,
        defaults=app_module.DEFAULT_DISPLAY_COLUMNS,
        labels=app_module.PRIMARY_LABEL_COLUMNS,
        validator=app_module.validate_sql,
        state_db_path=Path(app_module.FEEDBACK_DB_PATH),
        logs_root=Path(app_module.RUNTIME_PATHS.logs_root),
        llm_provider=provider,
        max_generation_retries=app_module.MAX_RETRIES,
        confidence_low_threshold=app_module.CONFIDENCE_THRESHOLD,
    )


def _run_case(copilot: EnterpriseSQLCopilot, case: BenchmarkCase) -> dict[str, Any]:
    started = time.perf_counter()
    classified = app_module.classify_query(case.query)
    if case.dangerous:
        return {
            "case_id": case.case_id,
            "category": case.category,
            "query": case.query,
            "valid": classified == "DANGEROUS",
            "blocked": classified == "DANGEROUS",
            "clarification_required": False,
            "selected_tables": [],
            "join_count": 0,
            "expected_tables": list(case.expected_tables),
            "table_recall": 100.0,
            "join_ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "fallback_used": False,
            "confidence": 0,
            "confidence_band": "LOW",
        }
    if case.metadata:
        return {
            "case_id": case.case_id,
            "category": case.category,
            "query": case.query,
            "valid": classified == "META",
            "blocked": False,
            "clarification_required": False,
            "selected_tables": [],
            "join_count": 0,
            "expected_tables": list(case.expected_tables),
            "table_recall": 100.0,
            "join_ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "fallback_used": False,
            "confidence": 100,
            "confidence_band": "HIGH",
        }
    result = copilot.run(case.query, allow_cache=False)
    selected = set(result.selected_tables)
    expected = set(case.expected_tables)
    matched = selected & expected
    table_recall = round((len(matched) / len(expected)) * 100, 2) if expected else 100.0
    join_ok = len(result.join_path) >= case.expected_min_joins if case.expected_min_joins else True
    success = bool(result.valid and table_recall >= 80 and join_ok)
    if case.clarification:
        success = bool(result.clarification_required or not result.valid)
    return {
        "case_id": case.case_id,
        "category": case.category,
        "query": case.query,
        "valid": success,
        "validator_valid": result.valid,
        "blocked": False,
        "clarification_required": result.clarification_required,
        "selected_tables": sorted(selected),
        "join_count": len(result.join_path),
        "expected_tables": list(case.expected_tables),
        "table_recall": table_recall,
        "join_ok": join_ok,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "fallback_used": bool(result.llm_trace.get("fallback_used")),
        "confidence": result.confidence,
        "confidence_band": result.confidence_band,
        "complexity": result.query_complexity,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_category.setdefault(str(row["category"]), []).append(row)
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "total_cases": len(rows),
        "success_rate": round((sum(1 for row in rows if row["valid"]) / len(rows)) * 100, 2),
        "sql_validity_rate": round((sum(1 for row in rows if row.get("validator_valid", row["valid"])) / len(rows)) * 100, 2),
        "average_table_recall": round(sum(float(row["table_recall"]) for row in rows) / len(rows), 2),
        "join_success_rate": round((sum(1 for row in rows if row["join_ok"]) / len(rows)) * 100, 2),
        "clarification_rate": round((sum(1 for row in rows if row["clarification_required"]) / len(rows)) * 100, 2),
        "fallback_rate": round((sum(1 for row in rows if row["fallback_used"]) / len(rows)) * 100, 2),
        "average_latency_ms": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(statistics.quantiles(latencies, n=20)[18], 3) if len(latencies) >= 20 else 0.0,
        "by_category": {
            category: {
                "cases": len(items),
                "success_rate": round((sum(1 for item in items if item["valid"]) / len(items)) * 100, 2),
                "join_success_rate": round((sum(1 for item in items if item["join_ok"]) / len(items)) * 100, 2),
                "average_table_recall": round(sum(float(item["table_recall"]) for item in items) / len(items), 2),
            }
            for category, items in sorted(by_category.items())
        },
    }


def _markdown_table(summary: dict[str, Any]) -> str:
    lines = [
        "| Category | Cases | Success | Join Success | Avg Table Recall |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for category, item in summary["by_category"].items():
        lines.append(
            f"| {category} | {item['cases']} | {item['success_rate']}% | "
            f"{item['join_success_rate']}% | {item['average_table_recall']}% |"
        )
    return "\n".join(lines)


def _write_reports(
    deterministic_summary: dict[str, Any],
    deterministic_rows: list[dict[str, Any]],
    nvidia_summary: dict[str, Any] | None,
    nvidia_rows: list[dict[str, Any]] | None,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    before_after = f"""# Enterprise Query Planning Before/After

Generated: {timestamp}

This report contains measured results from the current workspace benchmark. Historical pre-change metrics were not available in the repository, so they are intentionally marked as not measured instead of fabricated.

## Current Deterministic Planner

- Cases: {deterministic_summary['total_cases']}
- Success rate: {deterministic_summary['success_rate']}%
- SQL validity rate: {deterministic_summary['sql_validity_rate']}%
- Join success rate: {deterministic_summary['join_success_rate']}%
- Average table recall: {deterministic_summary['average_table_recall']}%
- Average latency: {deterministic_summary['average_latency_ms']} ms
- P95 latency: {deterministic_summary['p95_latency_ms']} ms

{_markdown_table(deterministic_summary)}

## Before Baseline

Not measured in this run. Use archived benchmark output from the previous implementation if an exact before/after comparison is required.

## Case Records

```json
{json.dumps(deterministic_rows, indent=2)}
```
"""
    (output_dir / "enterprise_query_planning_before_after.md").write_text(before_after, encoding="utf-8")

    if nvidia_summary is None:
        nvidia_body = """NVIDIA GPT-OSS-20B was not run because the provider was not configured and available in this process.

No NVIDIA accuracy, latency, token, fallback, or hallucination numbers are reported.
"""
    else:
        nvidia_body = f"""## NVIDIA GPT-OSS-20B Provider Run

- Cases: {nvidia_summary['total_cases']}
- Success rate: {nvidia_summary['success_rate']}%
- SQL validity rate: {nvidia_summary['sql_validity_rate']}%
- Join success rate: {nvidia_summary['join_success_rate']}%
- Average table recall: {nvidia_summary['average_table_recall']}%
- Fallback rate: {nvidia_summary['fallback_rate']}%
- Average latency: {nvidia_summary['average_latency_ms']} ms
- P95 latency: {nvidia_summary['p95_latency_ms']} ms

{_markdown_table(nvidia_summary)}

## Case Records

```json
{json.dumps(nvidia_rows or [], indent=2)}
```
"""
    nvidia_report = f"""# NVIDIA GPT-OSS-20B Evaluation

Generated: {timestamp}

Production architecture evaluated: deterministic planning + schema grounding + optional NVIDIA GPT-OSS-20B + SQL validation + coverage + confidence.

{nvidia_body}
"""
    (output_dir / "nvidia_gpt_oss_20b_evaluation.md").write_text(nvidia_report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-provider", action="store_true", help="Run the configured NVIDIA provider if available.")
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()

    cases = _cases()
    if len(cases) < 120:
        raise RuntimeError(f"benchmark must contain at least 120 cases; got {len(cases)}")

    deterministic = _new_copilot(provider=None)
    deterministic_rows = [_run_case(deterministic, case) for case in cases]
    deterministic_summary = _summarize(deterministic_rows)

    nvidia_summary = None
    nvidia_rows = None
    provider = app_module.LLM_PROVIDER_CLIENT
    if args.with_provider and app_module.PROVIDER_CONFIG.provider == "nvidia" and getattr(provider, "available", False):
        nvidia = _new_copilot(provider=provider)
        nvidia_rows = [_run_case(nvidia, case) for case in cases]
        nvidia_summary = _summarize(nvidia_rows)

    _write_reports(
        deterministic_summary,
        deterministic_rows,
        nvidia_summary,
        nvidia_rows,
        Path(args.output_dir),
    )
    print(json.dumps({
        "deterministic": deterministic_summary,
        "nvidia": nvidia_summary or "not_run",
        "reports": [
            str(Path(args.output_dir) / "enterprise_query_planning_before_after.md"),
            str(Path(args.output_dir) / "nvidia_gpt_oss_20b_evaluation.md"),
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
