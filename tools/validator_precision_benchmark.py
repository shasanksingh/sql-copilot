import json
import glob
import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic.planner_agents import PlannerValidationAgent

# Inputs: logs + reports
LOG_PATTERN = 'logs/planner_diagnostics/*.json'
CONF_BENCH = 'reports/confidence_benchmark.csv'
FN_REPORT = 'reports/planner_validation_false_negatives.json'
FAILED_TESTS = 'reports/planner_validation_failed_tests.json'
OUT = 'reports/validator_precision_benchmark.json'
OUT_CSV = 'reports/validator_benchmark_results.csv'
OUT_JSON = 'reports/validator_benchmark_results.json'

OUT_JSON_FULL = 'reports/validator_benchmark_full.json'
OUT_CSV_FULL = 'reports/validator_benchmark_full.csv'
OUT_CONF_FULL = 'reports/validator_confusion_matrix_full.json'

INTEGRITY_REPORT = 'reports/benchmark_integrity_report.json'

SEGMENT_KEYS = [
    'Simple Select',
    'Join Queries',
    'Aggregation Queries',
    'Group By Queries',
    'Ranking Queries',
    'Window Function Queries',
    'Multi-Hop Join Queries',
    'Ambiguous Queries',
]


def load_logs():
    items = []
    for p in sorted(glob.glob(LOG_PATTERN)):
        with open(p, 'r', encoding='utf-8') as f:
            obj = json.load(f)
            obj['_source_file'] = p
            items.append(obj)
    return items


def _extract_names_from_sql(sql):
    if not sql:
        return set(), set()
    low = sql.lower()
    # crude column extract: words with dot or alphanumeric sequences in select list
    cols = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*", low))
    # add unqualified tokens that look like column names
    cols.update(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", low))
    tables = set(re.findall(r"from\s+([a-zA-Z_][a-zA-Z0-9_]*)", low))
    tables.update(re.findall(r"join\s+([a-zA-Z_][a-zA-Z0-9_]*)", low))
    return cols, tables


def derive_audits(obj):
    # derive required tables/columns/aggs from coverage/expected
    cov = obj.get('coverage') or {}
    req_cols = set()
    req_tables = set()
    req_aggs = set()
    # intent/entity/column blocks
    try:
        req_cols.update(cov.get('intent', {}).get('required', []) or [])
        req_cols.update(cov.get('entity', {}).get('required', []) or [])
        req_cols.update(cov.get('column', {}).get('required', []) or [])
        req_aggs.update(cov.get('intent', {}).get('required', []) or [])
        req_tables.update(cov.get('join', {}).get('required_tables', []) or [])
    except Exception:
        pass
    # expected block
    exp = obj.get('expected') or {}
    req_cols.update(exp.get('columns') or [])
    req_tables.update(exp.get('tables') or [])

    # planner outputs
    planner_cols = set([c.split('.')[-1] for c in (obj.get('planner_columns') or obj.get('planned_columns') or [])])
    planner_tables = set(obj.get('planner_tables') or obj.get('planned_tables') or obj.get('linked_tables') or [])

    gen_sql = obj.get('generated_sql') or ''
    sql_cols, sql_tables = _extract_names_from_sql(gen_sql)
    # normalize: strip table prefixes from cols
    sql_cols_simple = set([c.split('.')[-1] for c in sql_cols])

    # audit_planner_correct: planner produced required cols/tables or SQL contains them
    audit_planner = True
    if req_cols:
        if not req_cols.intersection(planner_cols) and not req_cols.intersection(sql_cols_simple):
            audit_planner = False
    if req_tables:
        if not req_tables.intersection(planner_tables) and not req_tables.intersection(sql_tables):
            audit_planner = False

    # audit_sql_correct: SQL syntactically present and references required cols/tables
    audit_sql = True
    if not gen_sql or 'i cannot generate' in gen_sql.lower() or 'select .*' in gen_sql.lower() or 'from  ;' in gen_sql.lower():
        audit_sql = False
    else:
        if req_cols and not req_cols.intersection(sql_cols_simple):
            audit_sql = False
        if req_tables and not req_tables.intersection(sql_tables):
            audit_sql = False

    obj['required_columns_derived'] = list(req_cols)
    obj['required_tables_derived'] = list(req_tables)
    obj['required_aggregations_derived'] = list(req_aggs)
    obj['audit_planner_correct'] = audit_planner
    obj['audit_sql_correct'] = audit_sql
    return obj


def load_false_negatives():
    items = []
    try:
        with open(FN_REPORT, 'r', encoding='utf-8') as f:
            d = json.load(f)
            if isinstance(d, dict) and 'false_negatives' in d:
                items = d['false_negatives']
            elif isinstance(d, list):
                items = d
    except FileNotFoundError:
        items = []
    return items


def load_failed_tests():
    items = []
    try:
        with open(FAILED_TESTS, 'r', encoding='utf-8') as f:
            d = json.load(f)
            if isinstance(d, dict) and 'failures' in d:
                items = d['failures']
            elif isinstance(d, list):
                items = d
    except FileNotFoundError:
        items = []
    return items


def build_dataset():
    logs = load_logs()
    items = []
    for obj in logs:
        obj = derive_audits(obj)
        items.append(obj)
    # include any supplementary reports (but keep full logs as primary)
    items.extend(load_false_negatives())
    items.extend(load_failed_tests())
    # derive audits for any supplemental items if missing
    for i, it in enumerate(items):
        if 'audit_planner_correct' not in it:
            items[i] = derive_audits(it)
    return items


def evaluate(dataset):
    agent = PlannerValidationAgent()
    TP = FP = FN = TN = 0
    details = []
    per_segment = {k: {'TP':0,'FP':0,'FN':0,'TN':0,'total':0} for k in SEGMENT_KEYS}
    fp_list = []
    fn_list = []
    for d in dataset:
        q = d.get('query')
        intent = d.get('intent', {})
        cov = d.get('coverage') or {}
        # determine required and planned lists
        required_tables = cov.get('join', {}).get('required_tables') or d.get('required_tables') or []
        required_columns = cov.get('column', {}).get('required') or d.get('required_columns') or []
        required_aggs = cov.get('intent', {}).get('required') or d.get('required_aggregations') or []
        planned_tables = d.get('planned_tables') or d.get('planner_tables') or []
        planned_columns = d.get('planned_columns') or d.get('planner_columns') or []
        planned_aggs = d.get('planned_aggs') or []

        res = agent.validate(required_tables, required_columns, required_aggs, planned_tables, planned_columns, planned_aggs, intent=intent, entity_mappings=d.get('entities', {}).get('mappings') or d.get('entity_mappings'))
        validator_invalid = not res.get('valid')
        planner_incorrect = not bool(d.get('audit_planner_correct') is True)
        # note: audit_planner_correct True => planner correct
        if validator_invalid and planner_incorrect:
            TP += 1
        elif validator_invalid and not planner_incorrect:
            FP += 1
        elif not validator_invalid and planner_incorrect:
            FN += 1
        else:
            TN += 1
        details.append({'query': q, 'validator': res, 'planner_correct': d.get('audit_planner_correct'), 'confidence': d.get('confidence'), 'generated_sql': d.get('generated_sql')})

        # classify into a segment
        def seg_key(intent, cov):
            score = intent.get('score', 100) if isinstance(intent, dict) else 100
            if isinstance(intent, dict) and intent.get('aggregations'):
                return 'Aggregation Queries'
            if isinstance(intent, dict) and intent.get('group_by'):
                return 'Group By Queries'
            if isinstance(intent, dict) and intent.get('order_by'):
                return 'Ranking Queries'
            if cov and cov.get('window') or (isinstance(intent, dict) and intent.get('window')):
                return 'Window Function Queries'
            # multi-hop if required_tables length >1
            req_tables = cov.get('join', {}).get('required_tables') or required_tables or []
            if len(req_tables) > 1:
                return 'Multi-Hop Join Queries'
            if intent.get('requires_join') or (cov.get('join', {}).get('required_tables')):
                return 'Join Queries'
            if score < 50:
                return 'Ambiguous Queries'
            return 'Simple Select'

        sk = seg_key(intent or {}, cov or {})
        if sk not in per_segment:
            sk = 'Simple Select'
        per_segment[sk]['total'] += 1
        if validator_invalid and planner_incorrect:
            per_segment[sk]['TP'] += 1
        elif validator_invalid and not planner_incorrect:
            per_segment[sk]['FP'] += 1
        elif not validator_invalid and planner_incorrect:
            per_segment[sk]['FN'] += 1
        else:
            per_segment[sk]['TN'] += 1

        if validator_invalid and not planner_incorrect:
            fp_list.append({'query': q, 'generated_sql': d.get('generated_sql'), 'confidence': d.get('confidence'), 'planner_output': {'planned_tables': planned_tables, 'planned_columns': planned_columns}, 'validation': res})
        if not validator_invalid and planner_incorrect:
            fn_list.append({'query': q, 'generated_sql': d.get('generated_sql'), 'confidence': d.get('confidence'), 'planner_output': {'planned_tables': planned_tables, 'planned_columns': planned_columns}, 'validation': res})
    total = TP + FP + FN + TN
    precision = TP / (TP + FP) if (TP + FP) else 0.0
    recall = TP / (TP + FN) if (TP + FN) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = FP / (FP + TN) if (FP + TN) else 0.0
    fnr = FN / (FN + TP) if (FN + TP) else 0.0

    results = {
        'total_evaluated': total,
        'TP': TP, 'FP': FP, 'FN': FN, 'TN': TN,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'false_positive_rate': fpr,
        'false_negative_rate': fnr,
    }

    # per-segment metrics
    seg_metrics = {}
    for k, v in per_segment.items():
        tp = v['TP']; fp = v['FP']; fn = v['FN']; tn = v['TN']
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1s = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        seg_metrics[k] = {'total': v['total'], 'TP':tp,'FP':fp,'FN':fn,'TN':tn,'precision':prec,'recall':rec,'f1':f1s}

    # confusion matrix formatting
    confusion = {
        'Valid SQL + Validator Pass': TN,  # Valid SQL and validator passes -> TN (validator not invalid)
        'Valid SQL + Validator Fail': FP,
        'Invalid SQL + Validator Pass': FN,
        'Invalid SQL + Validator Fail': TP,
    }

    # top lists
    top_fp = sorted(fp_list, key=lambda x: (x.get('confidence') or 0))[:20]
    top_fn = sorted(fn_list, key=lambda x: (x.get('confidence') or 0), reverse=True)[:20]

    out_all = {'summary': results, 'segments': seg_metrics, 'confusion_matrix': confusion, 'top_false_positives': top_fp, 'top_false_negatives': top_fn, 'details_sample': details[:50], 'all_details': details}

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out_all, f, indent=2)

    # also write CSV summary
    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['metric','value'])
        writer.writerow(['total_evaluated', total])
        writer.writerow(['TP', TP])
        writer.writerow(['FP', FP])
        writer.writerow(['FN', FN])
        writer.writerow(['TN', TN])
        writer.writerow(['precision', precision])
        writer.writerow(['recall', recall])
        writer.writerow(['f1', f1])
        writer.writerow(['false_positive_rate', fpr])
        writer.writerow(['false_negative_rate', fnr])

    print('Wrote', OUT_JSON, 'and', OUT_CSV)


if __name__ == '__main__':
    ds = build_dataset()
    total_logs = len(sorted(glob.glob(LOG_PATTERN)))
    total_records = len(ds)
    # duplicates by query
    queries = [d.get('query') for d in ds if d.get('query')]
    dup_counts = Counter(queries)
    duplicate_records = sum(1 for q,c in dup_counts.items() if c>1)
    skipped = sum(1 for d in ds if not d.get('generated_sql') or d.get('generated_sql')=='')
    integrity = {'total_log_files': total_logs, 'total_records_loaded': total_records, 'skipped_records': skipped, 'duplicate_query_count': duplicate_records}
    with open(INTEGRITY_REPORT, 'w', encoding='utf-8') as f:
        json.dump(integrity, f, indent=2)
    print('Wrote', INTEGRITY_REPORT)
    # run full evaluation
    evaluate(ds)
    # copy primary outputs produced by evaluate to _full variants
    try:
        data = json.load(open(OUT_JSON,'r',encoding='utf-8'))
        json.dump(data, open(OUT_JSON_FULL,'w',encoding='utf-8'), indent=2)
        # write confusion matrix full
        json.dump(data.get('confusion_matrix',{}), open(OUT_CONF_FULL,'w',encoding='utf-8'), indent=2)
        # CSV summary
        with open(OUT_CSV_FULL,'w',newline='',encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            s = data.get('summary',{})
            writer.writerow(['metric','value'])
            for k,v in s.items():
                writer.writerow([k,v])
        print('Wrote full benchmark outputs')
    except Exception as e:
        print('Could not write full outputs:', e)
