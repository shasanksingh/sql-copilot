"""Business Operations semantic rules for the demo workforce and finance schema.

The physical tables remain the source of truth.  This module provides the
business vocabulary and approved read-only query patterns that sit on top of
those tables for business questions.
"""

from __future__ import annotations

import re
from typing import Iterable


BUSINESS_OPERATIONS_SCHEMA = {
    "name": "Business Operations",
    "purpose": "Workforce delivery, project delivery, client and receivables reporting.",
    "tables": (
        "employees", "clients", "projects", "project_team", "tasks", "time_logs", "invoices",
        "associates", "associate_assignments", "associate_activity", "associate_availability",
    ),
    "glossary": {
        "open work": "Tasks whose status is todo, in_progress, or blocked.",
        "assigned work": "Tasks linked to the responsible employee through tasks.assigned_to.",
        "active project": "Projects whose status is planning, active, or on_hold.",
        "outstanding invoice": "Invoices whose status is sent or overdue.",
        "available associate": "An associate with an available staffing period and remaining capacity.",
        "active assignment": "An associate-to-project assignment whose status is active.",
    },
}


def _normalise(query: str) -> str:
    return re.sub(r"\s+", " ", query.lower().replace("_", " ").replace("-", " ")).strip()


def parse_business_operations_rule(
    query: str,
    available_tables: Iterable[str],
) -> dict[str, object] | None:
    """Return a schema-grounded, read-only rule for recognised business prompts."""

    tables = set(available_tables)
    q = _normalise(query)
    if not q:
        return None

    wants_available = bool(re.search(r"\b(available|availability|capacity|bench|workload)\b", q))
    mentions_associate = bool(re.search(r"\b(associate|associates|staff|team member|consultant|workforce)\b", q))
    if wants_available and mentions_associate and {"associates", "associate_availability"}.issubset(tables):
        return {
            "name": "business_available_associates",
            "domain_label": "Business Operations",
            "main_table": "associate_availability",
            "selected_columns": [
                ("associates", "associate_name"),
                ("associates", "role_title"),
                ("associates", "business_unit"),
                ("associate_availability", "capacity_percent"),
                ("associate_availability", "available_from"),
                ("associate_availability", "available_to"),
            ],
            "joins": [("associate_availability", "associate_id", "associates", "associate_id")],
            "filters": [{"table": "associate_availability", "column": "availability_status", "operator": "available", "value": "available"}],
            "sql": (
                "SELECT\n"
                "  a.associate_name,\n"
                "  a.role_title,\n"
                "  a.business_unit,\n"
                "  av.capacity_percent,\n"
                "  av.available_from,\n"
                "  av.available_to\n"
                "FROM associate_availability av\n"
                "JOIN associates a ON av.associate_id = a.associate_id\n"
                "WHERE LOWER(av.availability_status) = 'available'\n"
                "ORDER BY av.capacity_percent DESC, a.associate_name ASC;"
            ),
            "required": ["available associate", "availability", "capacity"],
            "matched": ["available associate", "availability", "capacity"],
            "complexity": "MODERATE",
            "business_steps": [
                "Identify available associate capacity periods.",
                "Join capacity records to the associate directory.",
                "Prioritise associates with the most available capacity.",
            ],
        }

    mentions_assignment = bool(re.search(r"\b(assignment|assignments|allocation|staffing)\b", q))
    mentions_project = bool(re.search(r"\b(project|projects|delivery)\b", q))
    wants_active_assignment = bool(re.search(r"\b(active|current|ongoing|open)\b", q))
    if mentions_assignment and (mentions_associate or mentions_project) and {"associates", "associate_assignments", "projects"}.issubset(tables):
        status_filter = "WHERE LOWER(aa.assignment_status) = 'active'\n" if wants_active_assignment else ""
        return {
            "name": "business_associate_assignments_by_project",
            "domain_label": "Business Operations",
            "main_table": "associate_assignments",
            "selected_columns": [
                ("associates", "associate_name"),
                ("projects", "project_name"),
                ("associate_assignments", "assignment_role"),
                ("associate_assignments", "allocation_percent"),
                ("associate_assignments", "assignment_status"),
            ],
            "joins": [
                ("associate_assignments", "associate_id", "associates", "associate_id"),
                ("associate_assignments", "project_id", "projects", "project_id"),
            ],
            "filters": ([{"table": "associate_assignments", "column": "assignment_status", "operator": "active", "value": "active"}] if wants_active_assignment else []),
            "sql": (
                "SELECT\n"
                "  a.associate_name,\n"
                "  p.project_name,\n"
                "  aa.assignment_role,\n"
                "  aa.allocation_percent,\n"
                "  aa.assignment_status\n"
                "FROM associate_assignments aa\n"
                "JOIN associates a ON aa.associate_id = a.associate_id\n"
                "JOIN projects p ON aa.project_id = p.project_id\n"
                f"{status_filter}"
                "ORDER BY p.project_name ASC, a.associate_name ASC;"
            ),
            "required": ["associate", "assignment", "project"],
            "matched": ["associate", "assignment", "project"],
            "complexity": "MODERATE",
            "business_steps": [
                "Link each assignment to its associate and project.",
                "Apply the active-assignment filter when requested.",
            ],
        }

    wants_open_work = bool(re.search(r"\b(open|pending|in progress|blocked)\b", q))
    mentions_work = bool(re.search(r"\b(work|task|tasks|assignment|assignments)\b", q))
    mentions_employee = bool(re.search(r"\b(employee|employees|staff|worker|workers|assignee|assignees)\b", q))
    if wants_open_work and mentions_work and mentions_employee and {"tasks", "employees"}.issubset(tables):
        return {
            "name": "business_open_work_by_employee",
            "domain_label": "Business Operations",
            "main_table": "tasks",
            "selected_columns": [
                ("employees", "full_name"),
                ("tasks", "task_id"),
                ("tasks", "title"),
                ("tasks", "priority"),
                ("tasks", "status"),
                ("tasks", "due_date"),
            ],
            "joins": [("tasks", "assigned_to", "employees", "employee_id")],
            "filters": [{"table": "tasks", "column": "status", "operator": "open", "value": "todo,in_progress,blocked"}],
            "sql": (
                "SELECT\n"
                "  e.full_name,\n"
                "  t.task_id,\n"
                "  t.title,\n"
                "  t.priority,\n"
                "  t.status,\n"
                "  t.due_date\n"
                "FROM tasks t\n"
                "JOIN employees e ON t.assigned_to = e.employee_id\n"
                "WHERE LOWER(t.status) IN ('todo', 'in_progress', 'blocked')\n"
                "ORDER BY t.due_date ASC, e.full_name ASC;"
            ),
            "required": ["open work", "employee", "task assignment", "task status"],
            "matched": ["open work", "employee", "task assignment", "task status"],
            "complexity": "MODERATE",
            "business_steps": [
                "Resolve open work to todo, in-progress, and blocked task statuses.",
                "Join tasks to employees through the assigned_to relationship.",
                "Order the work queue by due date and responsible employee.",
            ],
        }

    mentions_project = bool(re.search(r"\b(project|projects|delivery)\b", q))
    mentions_client = bool(re.search(r"\b(client|clients|customer|customers)\b", q))
    wants_active = bool(re.search(r"\b(active|current|ongoing|open)\b", q))
    if wants_active and mentions_project and mentions_client and {"projects", "clients"}.issubset(tables):
        return {
            "name": "business_active_projects_by_client",
            "domain_label": "Business Operations",
            "main_table": "projects",
            "selected_columns": [
                ("clients", "client_name"),
                ("projects", "project_name"),
                ("projects", "status"),
                ("projects", "budget"),
                ("projects", "end_date"),
            ],
            "joins": [("projects", "client_id", "clients", "client_id")],
            "filters": [{"table": "projects", "column": "status", "operator": "active", "value": "planning,active,on_hold"}],
            "sql": (
                "SELECT\n"
                "  c.client_name,\n"
                "  p.project_name,\n"
                "  p.status,\n"
                "  p.budget,\n"
                "  p.end_date\n"
                "FROM projects p\n"
                "JOIN clients c ON p.client_id = c.client_id\n"
                "WHERE LOWER(p.status) IN ('planning', 'active', 'on_hold')\n"
                "ORDER BY c.client_name ASC, p.end_date ASC;"
            ),
            "required": ["active project", "client", "project status"],
            "matched": ["active project", "client", "project status"],
            "complexity": "MODERATE",
            "business_steps": [
                "Resolve active delivery work to planning, active, and on-hold projects.",
                "Join each project to its client record.",
            ],
        }

    mentions_invoice = bool(re.search(r"\b(invoice|invoices|receivable|receivables|billing)\b", q))
    wants_outstanding = bool(re.search(r"\b(outstanding|overdue|unpaid|open)\b", q))
    if wants_outstanding and mentions_invoice and {"invoices", "clients"}.issubset(tables):
        return {
            "name": "business_outstanding_invoices_by_client",
            "domain_label": "Business Operations",
            "main_table": "invoices",
            "selected_columns": [
                ("clients", "client_name"),
                ("invoices", "invoice_number"),
                ("invoices", "amount"),
                ("invoices", "status"),
                ("invoices", "due_date"),
            ],
            "joins": [("invoices", "client_id", "clients", "client_id")],
            "filters": [{"table": "invoices", "column": "status", "operator": "outstanding", "value": "sent,overdue"}],
            "sql": (
                "SELECT\n"
                "  c.client_name,\n"
                "  i.invoice_number,\n"
                "  i.amount,\n"
                "  i.status,\n"
                "  i.due_date\n"
                "FROM invoices i\n"
                "JOIN clients c ON i.client_id = c.client_id\n"
                "WHERE LOWER(i.status) IN ('sent', 'overdue')\n"
                "ORDER BY i.due_date ASC, c.client_name ASC;"
            ),
            "required": ["outstanding invoice", "client", "invoice status"],
            "matched": ["outstanding invoice", "client", "invoice status"],
            "complexity": "MODERATE",
            "business_steps": [
                "Resolve outstanding receivables to sent and overdue invoices.",
                "Join each invoice to its client record.",
            ],
        }

    return None
