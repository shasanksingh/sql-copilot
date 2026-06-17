import json
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from agentic.planner_agents import PlannerValidationAgent

logs_dir = root / "logs" / "planner_diagnostics"
sql_audit = root / "reports" / "sql_correctness_audit.csv"
out = root / "reports" / "validation_metrics.json"
per_test_out = root / "reports" / "planner_validation_tests_analysis.json"

# load audit map
import csv
audit_map = {}
if sql_audit.exists():
    with sql_audit.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            audit_map[r["query"]] = {
                "planner_correct": r.get("planner_correct", "False").lower() in ("true","1","yes"),
                "sql_correct": r.get("sql_correct", "False").lower() in ("true","1","yes"),
            }

validator = PlannerValidationAgent()
TP = FP = FN = TN = 0
entries = []
for p in sorted(logs_dir.glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    q = d.get("query")
    cov = d.get("coverage", {}) or {}
    required_tables = cov.get("join", {}).get("required_tables", [])
    required_columns = cov.get("column", {}).get("required", [])
    required_aggs = cov.get("aggregation", {}).get("required", [])
    planned_tables = d.get("planner_tables", []) or []
    planned_columns = d.get("planner_columns", []) or []
    planned_columns_norm = [c.split('.',1)[1] if isinstance(c, str) and '.' in c else c for c in planned_columns]
    v = validator.validate(required_tables, required_columns, required_aggs, planned_tables, planned_columns_norm, [])
    predicted_invalid = not v.get("valid")
    audit = audit_map.get(q, {"planner_correct": None})
    planner_correct = audit.get("planner_correct")
    # Interpret ground truth: planner_correct True -> planner ok (so validation should say valid)
    if planner_correct is True:
        if predicted_invalid:
            FN += 1  # false negative: validation labeled invalid but planner was correct
        else:
            TN += 1  # true negative? interpreted as correct & predicted valid -> true negative in 'invalid' detection
    elif planner_correct is False:
        if predicted_invalid:
            TP += 1
        else:
            FP += 1
    else:
        # unknown ground truth; skip
        continue
    entries.append({"query": q, "planner_correct": planner_correct, "predicted_invalid": predicted_invalid, "missing": v})

precision = TP / (TP + FP) if (TP + FP) else None
recall = TP / (TP + FN) if (TP + FN) else None
false_negative_rate = FN / (FN + TP) if (FN + TP) else None

metrics = {
    "total_evaluated": TP+FP+FN+TN,
    "TP": TP,
    "FP": FP,
    "FN": FN,
    "TN": TN,
    "precision": precision,
    "recall": recall,
    "false_negative_rate": false_negative_rate,
}

out.write_text(json.dumps(metrics, indent=2))

# extract the two failing test queries details
tests = ["Show all active projects", "Get employee name and department name"]
selected = []
for e in entries:
    if e["query"] in tests:
        selected.append(e)
per_test_out.write_text(json.dumps(selected, indent=2))
print("Wrote metrics to", out)
print("Wrote per-test analysis to", per_test_out)
