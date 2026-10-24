"""Associate operations schema used by the business SQL copilot.

The schema deliberately models people and delivery work in business language.
It provides tables that are useful for staffing, project delivery, workload,
and availability queries.
"""

from __future__ import annotations


def _column(name: str, data_type: str, description: str, *, pk: bool = False, fk: bool = False) -> dict[str, object]:
    return {
        "name": name,
        "data_type": data_type,
        "description": description,
        "is_pk": pk,
        "is_fk": fk,
    }


ASSOCIATE_OPERATIONS_SCHEMA_TABLES: list[dict[str, object]] = [
    {
        "name": "associates",
        "domain": "Business Operations",
        "purpose": "Business associate directory with roles, reporting lines, and employment status.",
        "owner": "business-operations",
        "tags": ["associate", "workforce", "staffing", "business operations"],
        "aliases": ["associate", "associates", "staff member", "team member", "consultant"],
        "columns": [
            _column("associate_id", "INTEGER", "Unique identifier for a business associate.", pk=True),
            _column("associate_name", "VARCHAR(160)", "Associate display name."),
            _column("business_email", "VARCHAR(254)", "Associate business email address."),
            _column("role_title", "VARCHAR(120)", "Current role or job title."),
            _column("business_unit", "VARCHAR(120)", "Business unit or practice."),
            _column("manager_id", "INTEGER", "Manager associate identifier.", fk=True),
            _column("employment_status", "VARCHAR(40)", "Employment status such as active, leave, or inactive."),
            _column("start_date", "DATE", "Date the associate joined the business."),
        ],
        "indexes": ["associate_id", "business_unit", "employment_status", "manager_id"],
    },
    {
        "name": "associate_assignments",
        "domain": "Business Operations",
        "purpose": "Associate-to-project assignments, roles, allocation, and assignment status.",
        "owner": "business-operations",
        "tags": ["associate", "assignment", "project", "allocation"],
        "aliases": ["associate assignment", "staffing assignment", "project allocation", "project team"],
        "columns": [
            _column("assignment_id", "INTEGER", "Unique assignment identifier.", pk=True),
            _column("associate_id", "INTEGER", "Assigned associate.", fk=True),
            _column("project_id", "INTEGER", "Project receiving the assignment.", fk=True),
            _column("assignment_role", "VARCHAR(120)", "Delivery role on the project."),
            _column("allocation_percent", "DECIMAL(5,2)", "Percent of associate capacity allocated to the project."),
            _column("assignment_status", "VARCHAR(40)", "Assignment status such as active, planned, or completed."),
            _column("assigned_at", "DATE", "Assignment start date."),
            _column("release_date", "DATE", "Assignment release date when known."),
        ],
        "indexes": ["assignment_id", "associate_id", "project_id", "assignment_status"],
    },
    {
        "name": "associate_activity",
        "domain": "Business Operations",
        "purpose": "Business delivery activity logged by associates against projects.",
        "owner": "business-operations",
        "tags": ["associate", "activity", "delivery", "hours"],
        "aliases": ["associate activity", "delivery activity", "work log", "utilization"],
        "columns": [
            _column("activity_id", "INTEGER", "Unique associate activity identifier.", pk=True),
            _column("associate_id", "INTEGER", "Associate who completed the activity.", fk=True),
            _column("project_id", "INTEGER", "Related project.", fk=True),
            _column("activity_date", "DATE", "Date of the delivery activity."),
            _column("hours_logged", "DECIMAL(8,2)", "Delivery hours logged."),
            _column("activity_type", "VARCHAR(80)", "Business activity classification."),
            _column("outcome", "VARCHAR(255)", "Recorded delivery outcome."),
        ],
        "indexes": ["activity_id", "associate_id", "project_id", "activity_date"],
    },
    {
        "name": "associate_availability",
        "domain": "Business Operations",
        "purpose": "Planned associate capacity and availability periods for staffing decisions.",
        "owner": "business-operations",
        "tags": ["associate", "availability", "capacity", "staffing"],
        "aliases": ["associate availability", "available staff", "capacity", "bench"],
        "columns": [
            _column("availability_id", "INTEGER", "Unique availability record identifier.", pk=True),
            _column("associate_id", "INTEGER", "Associate whose capacity is recorded.", fk=True),
            _column("available_from", "DATE", "Start date for the availability period."),
            _column("available_to", "DATE", "End date for the availability period."),
            _column("capacity_percent", "DECIMAL(5,2)", "Available capacity percentage."),
            _column("availability_status", "VARCHAR(40)", "Availability status such as available, allocated, or leave."),
            _column("notes", "VARCHAR(255)", "Planning note for the availability period."),
        ],
        "indexes": ["availability_id", "associate_id", "availability_status", "available_from"],
    },
]


ASSOCIATE_OPERATIONS_RELATIONSHIPS: list[dict[str, str]] = [
    {"from_table": "associates", "from_column": "manager_id", "to_table": "associates", "to_column": "associate_id"},
    {"from_table": "associate_assignments", "from_column": "associate_id", "to_table": "associates", "to_column": "associate_id"},
    {"from_table": "associate_assignments", "from_column": "project_id", "to_table": "projects", "to_column": "project_id"},
    {"from_table": "associate_activity", "from_column": "associate_id", "to_table": "associates", "to_column": "associate_id"},
    {"from_table": "associate_activity", "from_column": "project_id", "to_table": "projects", "to_column": "project_id"},
    {"from_table": "associate_availability", "from_column": "associate_id", "to_table": "associates", "to_column": "associate_id"},
]


ASSOCIATE_OPERATIONS_TABLE_HINTS: dict[str, set[str]] = {
    "associates": {"associate", "associates", "staff", "team member", "consultant", "workforce", "business unit"},
    "associate_assignments": {"assignment", "assignments", "staffing", "project allocation", "allocated associate", "project team"},
    "associate_activity": {"activity", "activities", "work log", "delivery hours", "utilization", "hours logged"},
    "associate_availability": {"availability", "available associate", "available staff", "capacity", "bench", "workload"},
}

ASSOCIATE_OPERATIONS_COLUMN_HINTS: dict[str, dict[str, set[str]]] = {
    "associates": {
        "associate_id": {"associate id", "staff id"},
        "associate_name": {"associate name", "staff name", "team member name", "names"},
        "role_title": {"role", "title", "designation"},
        "business_unit": {"business unit", "practice", "division", "team"},
        "employment_status": {"status", "active", "leave", "inactive"},
    },
    "associate_assignments": {
        "assignment_role": {"assignment role", "delivery role", "project role"},
        "allocation_percent": {"allocation", "capacity allocated", "allocation percent"},
        "assignment_status": {"assignment status", "active assignment"},
        "assigned_at": {"assignment date", "assigned"},
        "release_date": {"release date", "end assignment"},
    },
    "associate_activity": {
        "activity_date": {"activity date", "date"},
        "hours_logged": {"hours", "hours logged", "utilization"},
        "activity_type": {"activity type", "work type"},
        "outcome": {"outcome", "result"},
    },
    "associate_availability": {
        "available_from": {"available from", "availability start"},
        "available_to": {"available to", "availability end"},
        "capacity_percent": {"capacity", "availability percentage", "available capacity"},
        "availability_status": {"availability status", "available", "allocated", "leave"},
    },
}

ASSOCIATE_OPERATIONS_DEFAULT_DISPLAY_COLUMNS = {
    "associates": ["associate_id", "associate_name", "role_title", "business_unit", "employment_status"],
    "associate_assignments": ["assignment_id", "associate_id", "project_id", "assignment_role", "allocation_percent", "assignment_status"],
    "associate_activity": ["activity_id", "associate_id", "project_id", "activity_date", "hours_logged", "activity_type"],
    "associate_availability": ["availability_id", "associate_id", "available_from", "available_to", "capacity_percent", "availability_status"],
}

ASSOCIATE_OPERATIONS_LABEL_COLUMNS = {
    "associates": "associate_name",
    "associate_assignments": "assignment_id",
    "associate_activity": "activity_id",
    "associate_availability": "availability_id",
}

ASSOCIATE_OPERATIONS_ALIASES = {
    "associates": "a",
    "associate_assignments": "aa",
    "associate_activity": "act",
    "associate_availability": "av",
}
