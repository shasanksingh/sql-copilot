from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class EnterpriseColumn:
    name: str
    data_type: str
    description: str
    is_pk: bool = False
    is_fk: bool = False


@dataclass
class EnterpriseTable:
    name: str
    domain: str
    purpose: str
    row_count: int
    columns: list[EnterpriseColumn]
    indexes: list[str] = field(default_factory=list)
    last_updated: str = "2026-06-12"


@dataclass
class EnterpriseRelationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    relationship_type: str = "many_to_one"


DOMAIN_SEEDS: dict[str, list[str]] = {
    "Human Resources": [
        "employees", "departments", "positions", "salary_bands", "payroll",
        "attendance", "leave_requests", "performance_reviews", "training_records",
        "recruitment", "candidates", "employee_documents", "employee_benefits",
    ],
    "Finance": [
        "invoices", "payments", "transactions", "accounts", "ledgers", "budgets",
        "cost_centers", "expense_claims", "tax_records", "financial_forecasts",
        "revenue_streams", "audit_logs",
    ],
    "CRM": [
        "clients", "contacts", "opportunities", "contracts", "subscriptions",
        "renewals", "customer_feedback", "support_tickets", "service_requests",
        "account_segments", "customer_health_scores",
    ],
    "Project Management": [
        "projects", "milestones", "tasks", "sprints", "epics", "stories",
        "time_logs", "resource_allocations", "project_risks", "project_budgets",
        "deliverables", "programs",
    ],
    "Supply Chain": [
        "suppliers", "purchase_orders", "shipments", "inventory", "warehouses",
        "stock_movements", "procurement_requests", "vendor_contracts",
        "vendor_scorecards", "receiving_events",
    ],
    "IT Operations": [
        "incidents", "change_requests", "deployments", "systems", "servers",
        "applications", "monitoring_events", "alerts", "security_events",
        "access_logs", "service_catalog",
    ],
    "Healthcare": [
        "patients", "appointments", "doctors", "prescriptions", "medical_records",
        "insurance_claims", "hospital_departments", "care_plans", "lab_results",
    ],
    "Banking": [
        "customers", "bank_accounts", "bank_transactions", "loans", "credit_cards",
        "branches", "risk_profiles", "fraud_cases", "compliance_reviews",
        "kyc_documents",
    ],
    "Manufacturing": [
        "plants", "machines", "production_batches", "quality_checks",
        "maintenance_logs", "production_orders", "work_centers", "bom_items",
    ],
    "Insurance": [
        "policies", "claims", "claim_items", "policy_holders", "adjusters",
        "claim_payments", "claim_reviews", "fraud_investigations",
    ],
}


class SyntheticEnterpriseDataEngine:
    """Builds a stable enterprise-scale virtual schema for planning and UI demos."""

    def __init__(self, target_tables: int = 180) -> None:
        self.target_tables = max(100, target_tables)

    def generate_catalog(self) -> dict[str, object]:
        tables = self._tables()
        relationships = self._relationships(tables)
        return {
            "summary": {
                "tables_count": len(tables),
                "relationships_count": len(relationships),
                "domains_count": len(DOMAIN_SEEDS),
                "supported_scales": ["10K", "50K", "100K", "500K", "1M+"],
            },
            "domains": sorted(DOMAIN_SEEDS),
            "tables": [asdict(table) for table in tables],
            "relationships": [asdict(rel) for rel in relationships],
        }

    def _tables(self) -> list[EnterpriseTable]:
        names: list[tuple[str, str]] = []
        for domain, seeds in DOMAIN_SEEDS.items():
            names.extend((domain, seed) for seed in seeds)

        domain_names = list(DOMAIN_SEEDS)
        counter = 1
        while len(names) < self.target_tables:
            domain = domain_names[(counter - 1) % len(domain_names)]
            names.append((domain, f"{self._domain_slug(domain)}_extension_{counter:03d}"))
            counter += 1

        tables = []
        for index, (domain, name) in enumerate(names[: self.target_tables], start=1):
            singular = name[:-1] if name.endswith("s") else name
            pk = f"{singular}_id"
            columns = [
                EnterpriseColumn(pk, "INTEGER", f"Primary key for {name}", is_pk=True),
                EnterpriseColumn("name", "TEXT", f"Business label for {name}"),
                EnterpriseColumn("status", "TEXT", "Lifecycle status"),
                EnterpriseColumn("created_at", "TIMESTAMP", "Creation timestamp"),
                EnterpriseColumn("updated_at", "TIMESTAMP", "Last update timestamp"),
                EnterpriseColumn("effective_date", "DATE", "Business effective date"),
                EnterpriseColumn("owner_employee_id", "INTEGER", "References employees.employee_id", is_fk=True),
                EnterpriseColumn("amount", "DECIMAL(18,2)", "Financial or quantitative measure"),
            ]
            if name == "clients":
                columns.append(
                    EnterpriseColumn(
                        "tier",
                        "TEXT",
                        "Synthetic client service tier",
                    )
                )
            tables.append(
                EnterpriseTable(
                    name=name,
                    domain=domain,
                    purpose=f"{domain} records for {name.replace('_', ' ')}",
                    row_count=10_000 + index * 137,
                    columns=columns,
                    indexes=[pk, "status", "created_at", "owner_employee_id"],
                )
            )
        return tables

    def _relationships(self, tables: list[EnterpriseTable]) -> list[EnterpriseRelationship]:
        by_name = {table.name: table for table in tables}
        relationships: list[EnterpriseRelationship] = []

        def add(from_table: str, from_column: str, to_table: str, to_column: str) -> None:
            if from_table in by_name and to_table in by_name:
                relationships.append(EnterpriseRelationship(from_table, from_column, to_table, to_column))

        for table in tables:
            if table.name != "employees" and "employees" in by_name:
                add(table.name, "owner_employee_id", "employees", "employee_id")

        cross_domain = [
            ("employees", "department_id", "departments", "department_id"),
            ("projects", "client_id", "clients", "client_id"),
            ("invoices", "project_id", "projects", "project_id"),
            ("payments", "invoice_id", "invoices", "invoice_id"),
            ("tasks", "project_id", "projects", "project_id"),
            ("time_logs", "task_id", "tasks", "task_id"),
            ("purchase_orders", "supplier_id", "suppliers", "supplier_id"),
            ("shipments", "warehouse_id", "warehouses", "warehouse_id"),
            ("inventory", "warehouse_id", "warehouses", "warehouse_id"),
            ("appointments", "patient_id", "patients", "patient_id"),
            ("prescriptions", "appointment_id", "appointments", "appointment_id"),
            ("bank_transactions", "bank_account_id", "bank_accounts", "bank_account_id"),
            ("fraud_cases", "customer_id", "customers", "customer_id"),
            ("production_batches", "plant_id", "plants", "plant_id"),
            ("quality_checks", "production_batche_id", "production_batches", "production_batche_id"),
            ("claims", "policy_id", "policies", "policie_id"),
        ]
        for relation in cross_domain:
            add(*relation)

        ordered = tables
        for index, table in enumerate(ordered):
            for hop in (1, 3):
                target = ordered[(index + hop) % len(ordered)]
                if table.name != target.name:
                    add(table.name, f"{target.name[:-1] if target.name.endswith('s') else target.name}_id", target.name, f"{target.name[:-1] if target.name.endswith('s') else target.name}_id")

        return relationships[: max(300, len(tables) * 2)]

    def _domain_slug(self, domain: str) -> str:
        return domain.lower().replace(" ", "_")


class SchemaRequestRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._ensure()

    def _ensure(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_requests (
                    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_notes TEXT NOT NULL,
                    requested_tables TEXT NOT NULL,
                    requested_columns TEXT NOT NULL,
                    business_context TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    generated_schema TEXT NOT NULL DEFAULT '{}',
                    requested_by_user_id INTEGER,
                    request_kind TEXT NOT NULL DEFAULT 'table_request',
                    attachment_name TEXT NOT NULL DEFAULT '',
                    attachment_content TEXT NOT NULL DEFAULT ''
                )
                """
            )
            existing = {
                row[1] for row in conn.execute("PRAGMA table_info(schema_requests)").fetchall()
            }
            migrations = {
                "requested_by_user_id": "INTEGER",
                "request_kind": "TEXT NOT NULL DEFAULT 'table_request'",
                "attachment_name": "TEXT NOT NULL DEFAULT ''",
                "attachment_content": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in migrations.items():
                if column not in existing:
                    conn.execute(
                        f"ALTER TABLE schema_requests ADD COLUMN {column} {definition}"
                    )

    def create(self, payload: dict[str, object]) -> dict[str, object]:
        generated_schema = SchemaDesignAgent().design(payload)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO schema_requests (
                    user_notes, requested_tables, requested_columns, business_context,
                    status, generated_schema, requested_by_user_id, request_kind,
                    attachment_name, attachment_content
                )
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("user_notes") or payload.get("business_purpose") or ""),
                    json.dumps(payload.get("requested_tables") or payload.get("table_name") or ""),
                    json.dumps(payload.get("requested_columns") or payload.get("columns") or []),
                    str(payload.get("business_context") or payload.get("business_rules") or ""),
                    json.dumps(generated_schema),
                    payload.get("requested_by_user_id"),
                    str(payload.get("request_kind") or "table_request")[:80],
                    str(payload.get("attachment_name") or "")[:255],
                    str(payload.get("attachment_content") or "")[:1_000_000],
                ),
            )
            request_id = cursor.lastrowid
        result = self.get(request_id)
        return result or {"request_id": request_id, "status": "pending", "generated_schema": generated_schema}

    def list(
        self,
        status: str | None = None,
        user_id: int | None = None,
    ) -> list[dict[str, object]]:
        sql = (
            "SELECT request_id, timestamp, user_notes, requested_tables, requested_columns, "
            "business_context, status, generated_schema, requested_by_user_id, "
            "request_kind, attachment_name, attachment_content FROM schema_requests"
        )
        conditions = []
        params: list[object] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if user_id is not None:
            conditions.append("requested_by_user_id = ?")
            params.append(user_id)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY timestamp DESC"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def update_status(self, request_id: int, status: str) -> dict[str, object] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE schema_requests SET status = ? WHERE request_id = ?",
                (status, request_id),
            )
        return self.get(request_id)

    def get(self, request_id: int) -> dict[str, object] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT request_id, timestamp, user_notes, requested_tables, requested_columns,
                       business_context, status, generated_schema, requested_by_user_id,
                       request_kind, attachment_name, attachment_content
                FROM schema_requests
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def analytics(self, user_id: int | None = None) -> dict[str, object]:
        rows = self.list(user_id=user_id)
        status_counts: dict[str, int] = {}
        domain_counts: dict[str, int] = {}
        for row in rows:
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
            schema = row.get("generated_schema") or {}
            domain = str(schema.get("domain", "General"))
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        return {
            "total_requests": len(rows),
            "status_counts": status_counts,
            "most_requested_domains": sorted(domain_counts.items(), key=lambda item: item[1], reverse=True)[:6],
            "pending_requests": status_counts.get("pending", 0),
        }

    def _row_to_dict(self, row: Iterable[object]) -> dict[str, object]:
        values = list(row)
        return {
            "request_id": values[0],
            "timestamp": values[1],
            "user_notes": values[2],
            "requested_tables": json.loads(values[3]),
            "requested_columns": json.loads(values[4]),
            "business_context": values[5],
            "status": values[6],
            "generated_schema": json.loads(values[7] or "{}"),
            "requested_by_user_id": values[8],
            "request_kind": values[9],
            "attachment_name": values[10],
            "has_attachment": bool(values[11]),
        }


class SchemaDesignAgent:
    def design(self, payload: dict[str, object]) -> dict[str, object]:
        text = " ".join(str(value) for value in payload.values()).lower()
        domain = self._detect_domain(text)
        module = self._module_name(payload, domain)
        tables = self._tables_for_domain(module, domain)
        return {
            "domain": domain,
            "module": module,
            "tables": tables,
            "relationships": [
                {
                    "from_table": tables[index]["name"],
                    "from_column": f"{tables[index + 1]['name'][:-1]}_id",
                    "to_table": tables[index + 1]["name"],
                    "to_column": f"{tables[index + 1]['name'][:-1]}_id",
                }
                for index in range(len(tables) - 1)
            ],
            "indexes": [f"{table['name']}.{table['columns'][0]['name']}" for table in tables],
        }

    def _detect_domain(self, text: str) -> str:
        for domain in DOMAIN_SEEDS:
            if domain.lower().split()[0] in text:
                return domain
        if "claim" in text or "policy" in text:
            return "Insurance"
        if "subscription" in text or "renewal" in text:
            return "CRM"
        if "vendor" in text or "supplier" in text:
            return "Supply Chain"
        return "General"

    def _module_name(self, payload: dict[str, object], domain: str) -> str:
        explicit = payload.get("table_name") or payload.get("requested_tables")
        if isinstance(explicit, list) and explicit:
            return str(explicit[0]).lower().replace(" ", "_")
        if explicit:
            return str(explicit).lower().replace(" ", "_")
        return f"{domain.lower().replace(' ', '_')}_module"

    def _tables_for_domain(self, module: str, domain: str) -> list[dict[str, object]]:
        seeds = DOMAIN_SEEDS.get(domain, [module, f"{module}_items", f"{module}_events"])
        selected = seeds[:5] if len(seeds) >= 5 else seeds
        return [
            {
                "name": table,
                "purpose": f"Generated {domain} table for {table.replace('_', ' ')}",
                "columns": [
                    {"name": f"{table[:-1] if table.endswith('s') else table}_id", "data_type": "INTEGER", "is_pk": True},
                    {"name": "name", "data_type": "TEXT"},
                    {"name": "status", "data_type": "TEXT"},
                    {"name": "effective_date", "data_type": "DATE"},
                    {"name": "amount", "data_type": "DECIMAL(18,2)"},
                ],
            }
            for table in selected
        ]
