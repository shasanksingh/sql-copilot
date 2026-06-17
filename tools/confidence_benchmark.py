import csv
import json
import sys
from pathlib import Path
from typing import List, Dict

# ensure repository root is on path when executed directly
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic.enterprise_copilot import EnterpriseSQLCopilot


def build_copilot():
    # Larger test schema covering many cases
    tables = {"projects", "clients", "employees", "invoices", "payments", "orders", "customers", "products", "departments", "tasks", "tickets"}
    columns = {
        "projects": {"project_id", "client_id", "budget", "project_name"},
        "clients": {"client_id", "tier", "client_name"},
        "employees": {"employee_id", "name", "salary", "department_id"},
        "invoices": {"invoice_id", "customer_id", "amount", "created_at"},
        "payments": {"payment_id", "invoice_id", "amount", "paid_at"},
        "orders": {"order_id", "customer_id", "product_id", "quantity", "total"},
        "customers": {"customer_id", "customer_name", "region"},
        "products": {"product_id", "product_name", "price"},
        "departments": {"department_id", "department_name"},
        "tasks": {"task_id", "project_id", "status", "hours_spent"},
        "tickets": {"ticket_id", "project_id", "severity", "created_at"},
    }
    column_order = {t: sorted(list(cols)) for t, cols in columns.items()}
    column_types = {t: {} for t in tables}
    # simple relationships
    relationships = {
        "projects": [("client_id", "clients", "client_id"), ("project_id", "tasks", "project_id")],
        "clients": [("client_id", "projects", "client_id")],
        "invoices": [("customer_id", "customers", "customer_id")],
        "payments": [("invoice_id", "invoices", "invoice_id")],
        "orders": [("customer_id", "customers", "customer_id"), ("product_id", "products", "product_id")],
        "tasks": [("project_id", "projects", "project_id")],
        "tickets": [("project_id", "projects", "project_id")],
        "employees": [("department_id", "departments", "department_id")],
    }
    # convert to required format: relationships dict where key->list of tuples
    rels = {}
    for k, vals in relationships.items():
        rels[k] = [(col, to_table, to_col) for (col, to_table, to_col) in vals]

    table_hints = {}
    column_hints = {}
    value_filters = {}
    aliases = {t: t[:1] for t in tables}
    defaults = {t: list(columns[t])[:3] for t in tables}
    labels = {t: next(iter(sorted(columns[t]))) for t in tables}
    state_db_path = Path("state_benchmark.sqlite")
    return EnterpriseSQLCopilot(tables, columns, column_order, column_types, rels, table_hints, column_hints, value_filters, aliases, defaults, labels, lambda s: (s.strip().lower().startswith("select"), "Valid"), state_db_path)


def generate_queries() -> List[Dict]:
    templates = []
    # simple lookups
    templates += [
        {"q": "Show project_name for project_id 123", "type": "simple", "expected": {"columns": ["project_name"]}},
        {"q": "List all clients", "type": "simple", "expected": {"tables": ["clients"]}},
        {"q": "Get customer_name and region", "type": "simple", "expected": {"columns": ["customer_name", "region"]}},
    ]

    # aggregation templates
    templates += [{"q": f"Total revenue by region", "type": "agg", "expected": {"aggregation": ["SUM"], "group_by": ["region"]}}]

    # joins
    templates += [
        {"q": "Show project budget and client tier", "type": "join", "expected": {"tables": ["projects", "clients"]}},
        {"q": "Show orders total and customer name", "type": "join", "expected": {"tables": ["orders", "customers"]}},
    ]

    # ranking/window
    templates += [
        {"q": "Top 5 products by total sales", "type": "rank", "expected": {"order_by": "total", "limit": 5}},
        {"q": "Show customers with cumulative spend by region", "type": "window", "expected": {"window": True}},
    ]

    # multi-hop join
    templates += [
        {"q": "Show payments and client tier for invoices", "type": "multi-hop", "expected": {"tables": ["payments", "invoices", "customers", "clients"]}},
    ]

    # ambiguous and negative cases: wrong columns or missing columns
    templates += [
        {"q": "Show employee salary", "type": "negative", "expected": {"missing": ["salary"]}},
        {"q": "Show product price by unknown_dimension", "type": "ambiguous", "expected": {"missing": ["unknown_dimension"]}},
    ]

    # expand to 120 queries by variations
    queries = []
    base_templates = templates
    i = 0
    while len(queries) < 120:
        for t in base_templates:
            if len(queries) >= 120:
                break
            qtext = t["q"]
            # add minor variation
            if i % 5 == 0:
                q = qtext
            else:
                q = qtext.replace("Show", "Display").replace("Show", "Display")
            queries.append({"query": q, "expected": t.get("expected", {}), "type": t.get("type")})
            i += 1
    return queries


def run_benchmark(out_dir: Path = Path("reports")) -> Dict:
    copilot = build_copilot()
    queries = generate_queries()
    out_dir.mkdir(parents=True, exist_ok=True)
    # planner diagnostics logs
    logs_dir = Path("logs") / "planner_diagnostics"
    logs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "confidence_benchmark.csv"
    rows = []
    diag_rows = []
    for item in queries:
        q = item["query"]
        expected = item["expected"]
        res = copilot.run(q)
        row = {
            "query": q,
            "expected": json.dumps(expected),
            "generated_sql": res.sql,
            "coverage": json.dumps(res.coverage_report),
            "confidence": res.confidence,
        }
        rows.append(row)

        # Build planner diagnostics per user request
        coverage = res.coverage_report or {}
        linked_tables = coverage.get("join", {}).get("required_tables", [])
        linked_columns = coverage.get("column", {}).get("required", [])

        # Planner tables/columns/join path from result
        planner_tables = []
        planner_columns = []
        planner_join_path = []
        plan = res.plan if hasattr(res, "plan") else None
        if plan:
            try:
                # plan may be a dict (asdict) or object
                if isinstance(plan, dict):
                    main = plan.get("main_table")
                    if main:
                        planner_tables.append(main)
                    joins = plan.get("joins", []) or []
                    for j in joins:
                        # join dicts may include from_table/to_table
                        ft = j.get("from_table") if isinstance(j, dict) else getattr(j, "from_table", None)
                        tt = j.get("to_table") if isinstance(j, dict) else getattr(j, "to_table", None)
                        if ft and ft not in planner_tables:
                            planner_tables.append(ft)
                        if tt and tt not in planner_tables:
                            planner_tables.append(tt)
                    # selected columns present as list of [table, col] or as strings elsewhere
                    sel = plan.get("selected_columns", [])
                    for sc in sel:
                        if isinstance(sc, (list, tuple)) and len(sc) == 2:
                            planner_columns.append(f"{sc[0]}.{sc[1]}")
                        elif isinstance(sc, str):
                            planner_columns.append(sc)
                else:
                    # fallback for object-like plan
                    planner_tables = [plan.main_table]
                    for rel in getattr(plan, "joins", []):
                        planner_tables.extend([rel.from_table, rel.to_table])
                    planner_columns = [f"{t}.{c}" for t, c in getattr(plan, "selected_columns", [])]
            except Exception:
                planner_tables = planner_tables or []
        # CopilotResult also exposes selected_columns and join_path as human-friendly lists
        if hasattr(res, "selected_columns") and res.selected_columns:
            # prefer the explicitly rendered selected_columns (e.g., "table.col")
            planner_columns = res.selected_columns
        if hasattr(res, "join_path") and res.join_path:
            planner_join_path = res.join_path

        diag = {
            "query": q,
            "intent": getattr(res, "intent", {}),
            "entities": getattr(res, "entities", {}),
            "linked_tables": linked_tables,
            "linked_columns": linked_columns,
            "planner_tables": planner_tables,
            "planner_columns": planner_columns,
            "planner_join_path": planner_join_path,
            "generated_sql": res.sql,
            "confidence": res.confidence,
            "coverage": res.coverage_report,
            "expected": expected,
        }

        # write individual diagnostic file (indexed for uniqueness)
        idx = len(diag_rows) + 1
        safe_name = f"{idx:04d}.json"
        with (logs_dir / safe_name).open("w", encoding="utf-8") as fh:
            json.dump(diag, fh, indent=2)
        diag_rows.append(diag)

    # write CSV
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["query", "expected", "generated_sql", "coverage", "confidence"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    summary = {
        "total": len(rows),
        "csv": str(csv_path),
    }
    (out_dir / "confidence_benchmark.json").write_text(json.dumps(summary))

    # Write planner failures/summary CSV for observability
    failures_path = out_dir / "planner_failures.csv"
    with failures_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "query",
            "expected_tables",
            "planner_tables",
            "expected_columns",
            "planner_columns",
            "expected_joins",
            "planner_joins",
            "confidence",
            "failure_reason",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for d in diag_rows:
            expected = d.get("expected", {}) or {}
            exp_tables = expected.get("tables", [])
            exp_cols = expected.get("columns", [])
            # expected_joins not explicitly present in templates; use tables
            exp_joins = exp_tables
            plan_tables = d.get("planner_tables", [])
            plan_cols = d.get("planner_columns", [])
            plan_joins = d.get("planner_join_path", [])

            # determine failure reasons conservatively
            reasons = []
            if exp_tables:
                missing_tables = sorted(set(exp_tables) - set(plan_tables))
                if missing_tables:
                    reasons.append(f"missing_table:{'|'.join(missing_tables)}")
            if exp_cols:
                # normalize planner columns to column names
                planner_col_names = [c.split('.', 1)[1] if isinstance(c, str) and '.' in c else c for c in plan_cols]
                missing_cols = sorted(set(exp_cols) - set(planner_col_names))
                if missing_cols:
                    reasons.append(f"missing_column:{'|'.join(missing_cols)}")
            if exp_joins and len(exp_joins) > 1:
                # if not all expected tables are present in planner_tables, consider missing_joins
                missing_join_tables = sorted(set(exp_joins) - set(plan_tables))
                if missing_join_tables:
                    reasons.append(f"missing_join:{'|'.join(missing_join_tables)}")

            failure_reason = ";".join(reasons)

            writer.writerow({
                "query": d.get("query", ""),
                "expected_tables": json.dumps(exp_tables),
                "planner_tables": json.dumps(plan_tables),
                "expected_columns": json.dumps(exp_cols),
                "planner_columns": json.dumps(plan_cols),
                "expected_joins": json.dumps(exp_joins),
                "planner_joins": json.dumps(plan_joins),
                "confidence": d.get("confidence", 0),
                "failure_reason": failure_reason,
            })
    return summary


if __name__ == "__main__":
    print(run_benchmark())
