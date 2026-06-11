import type { SchemaRelationship } from "@/features/api/types";

export const schemaTables = [
  {
    name: "employees",
    rowCount: "12.4k",
    columns: ["employee_id", "employee_name", "department_id", "designation", "status", "hire_date"]
  },
  {
    name: "departments",
    rowCount: "48",
    columns: ["department_id", "department_name", "manager_id", "region"]
  },
  {
    name: "projects",
    rowCount: "1.8k",
    columns: ["project_id", "project_name", "client_id", "status", "budget", "start_date"]
  },
  {
    name: "clients",
    rowCount: "620",
    columns: ["client_id", "client_name", "industry", "country", "tier"]
  },
  {
    name: "tasks",
    rowCount: "86k",
    columns: ["task_id", "project_id", "assignee_id", "status", "hours_spent", "due_date"]
  },
  {
    name: "invoices",
    rowCount: "9.3k",
    columns: ["invoice_id", "client_id", "project_id", "amount", "status", "invoice_date"]
  }
];

export const fallbackRelationships: Record<string, SchemaRelationship[]> = {
  employees: [
    { from_table: "employees", from_column: "department_id", to_table: "departments", to_column: "department_id" },
    { from_table: "tasks", from_column: "assignee_id", to_table: "employees", to_column: "employee_id" }
  ],
  departments: [{ from_table: "employees", from_column: "department_id", to_table: "departments", to_column: "department_id" }],
  projects: [
    { from_table: "projects", from_column: "client_id", to_table: "clients", to_column: "client_id" },
    { from_table: "tasks", from_column: "project_id", to_table: "projects", to_column: "project_id" },
    { from_table: "invoices", from_column: "project_id", to_table: "projects", to_column: "project_id" }
  ],
  clients: [
    { from_table: "projects", from_column: "client_id", to_table: "clients", to_column: "client_id" },
    { from_table: "invoices", from_column: "client_id", to_table: "clients", to_column: "client_id" }
  ],
  tasks: [
    { from_table: "tasks", from_column: "project_id", to_table: "projects", to_column: "project_id" },
    { from_table: "tasks", from_column: "assignee_id", to_table: "employees", to_column: "employee_id" }
  ],
  invoices: [
    { from_table: "invoices", from_column: "client_id", to_table: "clients", to_column: "client_id" },
    { from_table: "invoices", from_column: "project_id", to_table: "projects", to_column: "project_id" }
  ]
};

export const suggestedPrompts = [
  "Count employees by department",
  "Show active projects with client names",
  "List invoices grouped by status",
  "Find tasks due this week by assignee",
  "Show project budget by client tier"
];

export const sampleRows = [
  { project_name: "Payment Gateway API", client: "Northwind Capital", status: "active", confidence: "94%" },
  { project_name: "Mobile App Revamp", client: "Aster Retail", status: "active", confidence: "91%" },
  { project_name: "Data Warehouse Sync", client: "Vertex Health", status: "review", confidence: "87%" }
];

export const plannerStages = [
  { title: "Table selection", detail: "projects, clients", metric: "2 tables" },
  { title: "Join chain", detail: "projects.client_id -> clients.client_id", metric: "1 hop" },
  { title: "Filters", detail: "LOWER(projects.status) = 'active'", metric: "1 filter" },
  { title: "Aggregations", detail: "No aggregation requested", metric: "0 aggs" }
];
