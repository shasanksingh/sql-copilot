import csv
import json
from pathlib import Path
from typing import Dict, Any


def analyze_report(csv_path: Path) -> Dict[str, Any]:
    rows = []
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            r["expected"] = json.loads(r["expected"]) if r.get("expected") else {}
            r["coverage"] = json.loads(r["coverage"]) if r.get("coverage") else {}
            r["confidence"] = int(r.get("confidence", 0))
            rows.append(r)

    total = len(rows)
    false_high = []
    false_low = []
    missing_joins = []
    missing_aggs = []
    missing_entities = []
    missing_display_columns = []
    entity_coverage_scores = []
    join_coverage_scores = []
    confidence_buckets = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    failing = []

    for r in rows:
        expected = r["expected"]
        coverage = r["coverage"]
        conf = r["confidence"]

        # determine expected required elements
        expected_tables = set(expected.get("tables", []))
        expected_columns = set(expected.get("columns", []))
        expected_aggs = set(expected.get("aggregation", []))
        expected_group = bool(expected.get("group_by") or expected.get("group_by") is not None)

        # coverage missing lists
        cov = coverage
        cov_missing = []
        if isinstance(cov.get("join", {}), dict) and cov.get("join", {}).get("missing"):
            cov_missing.extend(cov.get("join", {}).get("missing", []))
        if isinstance(cov.get("column", {}), dict) and cov.get("column", {}).get("missing"):
            cov_missing.extend(cov.get("column", {}).get("missing", []))
        if isinstance(cov.get("aggregation", {}), dict) and cov.get("aggregation", {}).get("missing"):
            cov_missing.extend(cov.get("aggregation", {}).get("missing", []))

        # false high: high confidence but missing elements
        if conf >= 80 and cov_missing:
            false_high.append({"query": r["query"], "confidence": conf, "missing": cov_missing})

        # false low: low confidence but no missing elements
        if conf < 40:
            # consider coverage scores
            all_scores = [cov.get(k, {}).get("score", 100) for k in ("intent", "entity", "column", "join", "aggregation")]
            if all(s >= 80 for s in all_scores):
                false_low.append({"query": r["query"], "confidence": conf, "scores": all_scores})

        # missing joins detection
        if expected_tables and len(expected_tables) > 1:
            jm = cov.get("join", {}).get("missing", [])
            if jm:
                missing_joins.append({"query": r["query"], "missing_joins": jm})

        # missing aggregation detection
        if expected_aggs or expected.get("group_by"):
            agg_missing = cov.get("aggregation", {}).get("missing", [])
            if agg_missing:
                missing_aggs.append({"query": r["query"], "missing_aggregations": agg_missing})

        # missing entity detection
        if expected_columns:
            col_missing = cov.get("column", {}).get("missing", [])
            if col_missing:
                missing_entities.append({"query": r["query"], "missing_columns": col_missing})

        # detect missing readable/display columns reported by entity coverage
        entity_cov = cov.get("entity", {})
        expected_display = entity_cov.get("expected_display", {}) or {}
        if expected_display:
            missing_for_query = []
            for table, disp in expected_display.items():
                if disp in (cov.get("column", {}).get("missing", []) or []) or disp in (entity_cov.get("missing", []) or []):
                    missing_for_query.append({"table": table, "expected_display": disp})
            if missing_for_query:
                missing_display_columns.append({"query": r["query"], "missing_display": missing_for_query})

        # collect entity coverage score for accuracy measurement
        entity_coverage_scores.append(float(entity_cov.get("score", 0)))
        # collect join coverage score (prefer join_path if available)
        jp = cov.get("join_path") or {}
        if jp and jp.get("join_coverage_score") is not None:
            join_coverage_scores.append(float(jp.get("join_coverage_score", 0)))
        else:
            join_coverage_scores.append(float(cov.get("join", {}).get("score", 0)))

        # confidence distribution bucket
        if conf <= 20:
            confidence_buckets["0-20"] += 1
        elif conf <= 40:
            confidence_buckets["21-40"] += 1
        elif conf <= 60:
            confidence_buckets["41-60"] += 1
        elif conf <= 80:
            confidence_buckets["61-80"] += 1
        else:
            confidence_buckets["81-100"] += 1

        # collect failing rows (missing coverage or missing display/join)
        has_display_expected = bool(entity_cov.get("expected_display"))
        if cov_missing or (has_display_expected and any(True for _ in entity_cov.get("expected_display", {}).items() if True)) or (expected_tables and len(expected_tables) > 1 and cov.get("join", {}).get("missing")):
            failing.append({"query": r["query"], "confidence": conf, "missing": cov_missing or cov.get("column", {}).get("missing", []) or cov.get("join", {}).get("missing", [])})

    summary = {
        "total": total,
        "false_high_count": len(false_high),
        "false_low_count": len(false_low),
        "missing_joins_count": len(missing_joins),
        "missing_aggregations_count": len(missing_aggs),
        "missing_entities_count": len(missing_entities),
        "missing_display_columns_count": len(missing_display_columns),
        "entity_coverage_mean": (sum(entity_coverage_scores) / len(entity_coverage_scores)) if entity_coverage_scores else 0,
        "join_coverage_mean": (sum(join_coverage_scores) / len(join_coverage_scores)) if join_coverage_scores else 0,
        "confidence_distribution": confidence_buckets,
        "top_failing": failing[:20],
        "false_high": false_high[:10],
        "false_low": false_low[:10],
        "missing_joins": missing_joins[:10],
        "missing_aggregations": missing_aggs[:10],
        "missing_entities": missing_entities[:10],
        "missing_display_columns": missing_display_columns[:20],
    }
    return summary


if __name__ == "__main__":
    csv_path = Path("reports") / "confidence_benchmark.csv"
    if not csv_path.exists():
        print("Benchmark report not found. Run tools/confidence_benchmark.py first.")
    else:
        s = analyze_report(csv_path)
        print(json.dumps(s, indent=2))
