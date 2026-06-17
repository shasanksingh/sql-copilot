import json, glob, re, csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentic.planner_agents import PlannerValidationAgent

LOG_PATTERN = 'logs/planner_diagnostics/*.json'
OUT_JSON120 = 'reports/validator_benchmark_120.json'
OUT_CSV120 = 'reports/validator_benchmark_120.csv'
OUT_CONF120 = 'reports/validator_confusion_matrix_120.json'


def _extract_names_from_sql(sql):
    if not sql:
        return set(), set()
    low = sql.lower()
    cols = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*", low))
    cols.update(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", low))
    tables = set(re.findall(r"from\s+([a-zA-Z_][a-zA-Z0-9_]*)", low))
    tables.update(re.findall(r"join\s+([a-zA-Z_][a-zA-Z0-9_]*)", low))
    return cols, tables


def derive_audits(obj):
    cov = obj.get('coverage') or {}
    req_cols = set()
    req_tables = set()
    try:
        req_cols.update(cov.get('intent', {}).get('required', []) or [])
        req_cols.update(cov.get('entity', {}).get('required', []) or [])
        req_cols.update(cov.get('column', {}).get('required', []) or [])
        req_tables.update(cov.get('join', {}).get('required_tables', []) or [])
    except Exception:
        pass
    exp = obj.get('expected') or {}
    req_cols.update(exp.get('columns') or [])
    req_tables.update(exp.get('tables') or [])
    planner_cols = set([c.split('.')[-1] for c in (obj.get('planner_columns') or obj.get('planned_columns') or [])])
    planner_tables = set(obj.get('planner_tables') or obj.get('planned_tables') or obj.get('linked_tables') or [])
    gen_sql = obj.get('generated_sql') or ''
    sql_cols, sql_tables = _extract_names_from_sql(gen_sql)
    sql_cols_simple = set([c.split('.')[-1] for c in sql_cols])
    audit_planner = True
    if req_cols:
        if not req_cols.intersection(planner_cols) and not req_cols.intersection(sql_cols_simple):
            audit_planner = False
    if req_tables:
        if not req_tables.intersection(planner_tables) and not req_tables.intersection(sql_tables):
            audit_planner = False
    audit_sql = True
    if not gen_sql or 'i cannot generate' in gen_sql.lower() or 'select .*' in gen_sql.lower() or 'from  ;' in gen_sql.lower():
        audit_sql = False
    else:
        if req_cols and not req_cols.intersection(sql_cols_simple):
            audit_sql = False
        if req_tables and not req_tables.intersection(sql_tables):
            audit_sql = False
    obj['audit_planner_correct'] = audit_planner
    obj['audit_sql_correct'] = audit_sql
    return obj


def load_logs():
    items = []
    for p in sorted(glob.glob(LOG_PATTERN)):
        obj = json.load(open(p,'r',encoding='utf-8'))
        obj['_source_file'] = p
        obj = derive_audits(obj)
        items.append(obj)
    return items


def evaluate(dataset):
    agent = PlannerValidationAgent()
    TP = FP = FN = TN = 0
    details = []
    for d in dataset:
        q = d.get('query')
        intent = d.get('intent', {})
        cov = d.get('coverage') or {}
        required_tables = cov.get('join', {}).get('required_tables') or d.get('required_tables') or d.get('required_tables_derived') or []
        required_columns = cov.get('column', {}).get('required') or d.get('required_columns') or d.get('required_columns_derived') or []
        required_aggs = cov.get('intent', {}).get('required') or d.get('required_aggregations') or d.get('required_aggregations_derived') or []
        planned_tables = d.get('planned_tables') or d.get('planner_tables') or d.get('planned_tables') or []
        planned_columns = d.get('planned_columns') or d.get('planner_columns') or d.get('planned_columns') or []
        planned_aggs = d.get('planned_aggs') or []
        res = agent.validate(required_tables, required_columns, required_aggs, planned_tables, planned_columns, planned_aggs, intent=intent, entity_mappings=d.get('entities', {}).get('mappings') or d.get('entity_mappings'))
        validator_invalid = not res.get('valid')
        planner_incorrect = not bool(d.get('audit_planner_correct') is True)
        if validator_invalid and planner_incorrect:
            TP += 1
        elif validator_invalid and not planner_incorrect:
            FP += 1
        elif not validator_invalid and planner_incorrect:
            FN += 1
        else:
            TN += 1
        details.append({'query': q, 'validator': res, 'planner_correct': d.get('audit_planner_correct'), 'sql_correct': d.get('audit_sql_correct'), 'generated_sql': d.get('generated_sql')})
    total = TP + FP + FN + TN
    precision = TP / (TP + FP) if (TP + FP) else 0.0
    recall = TP / (TP + FN) if (TP + FN) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = FP / (FP + TN) if (FP + TN) else 0.0
    fnr = FN / (FN + TP) if (FN + TP) else 0.0
    out = {'summary': {'total_evaluated': total,'TP':TP,'FP':FP,'FN':FN,'TN':TN,'precision':precision,'recall':recall,'f1':f1,'false_positive_rate':fpr,'false_negative_rate':fnr}, 'details': details}
    json.dump(out, open(OUT_JSON120,'w',encoding='utf-8'), indent=2)
    with open(OUT_CSV120,'w',newline='',encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['metric','value'])
        for k,v in out['summary'].items():
            writer.writerow([k,v])
    json.dump({'confusion_matrix': {'TP':TP,'FP':FP,'FN':FN,'TN':TN}}, open(OUT_CONF120,'w',encoding='utf-8'), indent=2)
    print('Wrote', OUT_JSON120, OUT_CSV120, OUT_CONF120)


if __name__ == '__main__':
    logs = load_logs()
    print('Loaded', len(logs), 'logs')
    evaluate(logs)
