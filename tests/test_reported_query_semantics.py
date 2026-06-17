from __future__ import annotations

import importlib

import pytest

from backend.synthetic_enterprise_data import SyntheticEnterpriseDataEngine


@pytest.mark.parametrize(
    ("query", "required_sql"),
    [
        (
            "Top performers by department",
            [
                "SUM(tl.hours_spent) AS total_hours",
                "GROUP BY e.department, e.full_name",
                "ORDER BY total_hours DESC",
            ],
        ),
        (
            "Revenue by quarter",
            [
                "DATE_TRUNC('quarter', pay.payment_date)",
                "SUM(pay.amount_paid) AS revenue",
            ],
        ),
        (
            "Find tasks due this week by assignee",
            [
                "JOIN employees e ON t.assigned_to = e.employee_id",
                "DATE_TRUNC('week', CURRENT_DATE)",
                "e.full_name",
            ],
        ),
        (
            "Active projects by client tier",
            [
                "c.tier",
                "JOIN clients c ON p.client_id = c.client_id",
                "LOWER(p.status) = 'active'",
            ],
        ),
        (
            "Running revenue by month",
            [
                "DATE_TRUNC('month', pay.payment_date)",
                "SUM(SUM(pay.amount_paid)) OVER",
                "AS running_revenue",
            ],
        ),
    ],
)
def test_reported_queries_generate_semantically_aligned_sql(
    query: str,
    required_sql: list[str],
) -> None:
    app_module = importlib.import_module("backend.app")

    result = app_module.get_enterprise_copilot().run(query, allow_cache=False)

    assert result.valid is True
    assert result.confidence >= 80
    assert result.clarification_required is False
    for fragment in required_sql:
        assert fragment in result.sql


def test_client_tier_is_visible_in_active_and_synthetic_schema() -> None:
    app_module = importlib.import_module("backend.app")
    assert "tier" in app_module.schema_columns["clients"]
    assert ("clients", "tier") in app_module.virtual_schema_columns
    synthetic = SyntheticEnterpriseDataEngine(180).generate_catalog()
    synthetic_clients = next(
        table for table in synthetic["tables"]
        if table["name"] == "clients"
    )
    assert "tier" in {column["name"] for column in synthetic_clients["columns"]}


@pytest.mark.parametrize(
    ("query", "required_sql", "forbidden_sql"),
    [
        (
            "Invoice amount by month",
            ["DATE_TRUNC('month', i.issued_date)", "SUM(i.amount) AS total_invoice_amount"],
            [],
        ),
        (
            "Running hours by employee each month",
            [
                "JOIN employees e ON tl.employee_id = e.employee_id",
                "PARTITION BY e.full_name",
                "SUM(SUM(tl.hours_spent))",
            ],
            [],
        ),
        (
            "Show project budget by client tier",
            ["c.tier", "SUM(p.budget) AS total_budget", "GROUP BY c.tier"],
            [],
        ),
        (
            "Critical bugs by assignee",
            ["JOIN employees e ON b.assigned_to = e.employee_id", "GROUP BY e.full_name"],
            ["b.reported_by = e.employee_id"],
        ),
        (
            "Invoices due this week by client",
            ["c.client_name", "i.due_date", "DATE_TRUNC('week', CURRENT_DATE)"],
            [],
        ),
        (
            "Top 10 clients by invoice amount",
            ["c.client_name", "SUM(i.amount) AS total_invoice_amount", "LIMIT 10"],
            [],
        ),
        (
            "Deployments this week by environment",
            ["dep.environment", "dep.deployed_at", "DATE_TRUNC('week', CURRENT_DATE)"],
            [],
        ),
        (
            "Sprints ending this month by project",
            ["p.project_name", "s.end_date", "DATE_TRUNC('month', CURRENT_DATE)"],
            [],
        ),
    ],
)
def test_generalized_semantic_rules_cover_other_tables(
    query: str,
    required_sql: list[str],
    forbidden_sql: list[str],
) -> None:
    app_module = importlib.import_module("backend.app")

    result = app_module.get_enterprise_copilot().run(query, allow_cache=False)

    assert result.valid is True
    assert result.confidence >= 80
    for fragment in required_sql:
        assert fragment in result.sql
    for fragment in forbidden_sql:
        assert fragment not in result.sql
