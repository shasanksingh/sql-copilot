import json
import sys
from pathlib import Path
# ensure repo root on path for direct script execution
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentic.planner_agents import PlannerValidationAgent

# paths
root = Path(__file__).resolve().parents[1]
logs_dir = root / "logs" / "planner_diagnostics"
sql_audit = root / "reports" / "sql_correctness_audit.csv"
out = root / "reports" / "planner_validation_false_negatives.json"

validator = PlannerValidationAgent()

# load sql audit mapping: query -> planner_correct, sql_correct
audit_map = {}
if sql_audit.exists():
    import csv
    with sql_audit.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            audit_map[r["query"]] = {
                "planner_correct": r.get("planner_correct", "False").lower() in ("true","1","yes"),
                "sql_correct": r.get("sql_correct", "False").lower() in ("true","1","yes"),
            }

# iterate diagnostics
entries = []
all_rows = []
for p in sorted(logs_dir.glob("*.json")):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    q = d.get("query")
    coverage = d.get("coverage", {}) or {}
    # required elements
    required_tables = coverage.get("join", {}).get("required_tables", [])
    required_columns = coverage.get("column", {}).get("required", [])
    required_aggs = coverage.get("aggregation", {}).get("required", [])

    planned_tables = d.get("planner_tables", []) or []
    planned_columns = d.get("planner_columns", []) or []
    # normalize planner column names to bare column name
    planned_columns_norm = [c.split('.',1)[1] if isinstance(c, str) and '.' in c else c for c in planned_columns]

    v = validator.validate(required_tables, required_columns, required_aggs, planned_tables, planned_columns_norm, [])
    audit = audit_map.get(q, {"planner_correct": None, "sql_correct": None})
    row = {
        "query": q,
        "intent": d.get("intent"),
        "entities": d.get("entities"),
        "planned_tables": planned_tables,
        "planned_columns": planned_columns,
        "generated_sql": d.get("generated_sql"),
        "validation_result": {"valid": v.get("valid"), "missing_tables": v.get("missing_tables"), "missing_columns": v.get("missing_columns"), "missing_aggregations": v.get("missing_aggregations")},
        "required_tables": required_tables,
        "required_columns": required_columns,
        "required_aggregations": required_aggs,
        "audit_planner_correct": audit.get("planner_correct"),
        "audit_sql_correct": audit.get("sql_correct"),
    }
    # root cause heuristics
    rc = []
    if not v.get("valid"):
        if v.get("missing_tables"):
            rc.append("missing_tables")
        if v.get("missing_columns"):
            rc.append("missing_columns")
        if v.get("missing_aggregations"):
            rc.append("missing_aggregations")
    else:
        if row["audit_planner_correct"] is True:
            rc.append("no_validation_issue")
    row["root_cause"] = rc or ["unknown"]

    entries.append(row)
    all_rows.append(row)

# find false negatives: validator says invalid but audit says planner_correct == True
false_negatives = [e for e in entries if (e["validation_result"]["valid"] is False) and (e["audit_planner_correct"] is True)]

report = {
    "total_analyzed": len(all_rows),
    "false_negatives_count": len(false_negatives),
    "false_negatives": false_negatives,
}

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2))
print("Wrote", out)
