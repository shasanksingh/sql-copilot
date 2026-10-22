from agentic.business_operations_domain import (
    BUSINESS_OPERATIONS_SCHEMA,
    parse_business_operations_rule,
)


ALL_TABLES = set(BUSINESS_OPERATIONS_SCHEMA["tables"])


def test_open_work_maps_to_assigned_tasks_and_employees() -> None:
    rule = parse_business_operations_rule("Open work assigned to employees", ALL_TABLES)

    assert rule is not None
    assert rule["name"] == "business_open_work_by_employee"
    assert "FROM tasks t" in str(rule["sql"])
    assert "JOIN employees e ON t.assigned_to = e.employee_id" in str(rule["sql"])
    assert "LOWER(t.status) IN ('todo', 'in_progress', 'blocked')" in str(rule["sql"])


def test_active_projects_and_outstanding_invoices_are_grounded() -> None:
    projects = parse_business_operations_rule("Show active projects by client", ALL_TABLES)
    invoices = parse_business_operations_rule("List outstanding invoices by client", ALL_TABLES)

    assert projects is not None
    assert "JOIN clients c ON p.client_id = c.client_id" in str(projects["sql"])
    assert invoices is not None
    assert "JOIN clients c ON i.client_id = c.client_id" in str(invoices["sql"])
    assert "LOWER(i.status) IN ('sent', 'overdue')" in str(invoices["sql"])


def test_business_rules_require_their_source_tables() -> None:
    assert parse_business_operations_rule("Open work assigned to employees", {"tasks"}) is None
