import json
from pathlib import Path

before_metrics = Path('reports/validator_benchmark_120_metrics.json')
after = Path('reports/validator_benchmark_120.json')
out_before = Path('reports/validator_benchmark_before.json')
out_after = Path('reports/validator_benchmark_after.json')
out_imp = Path('reports/validator_improvement_report.json')

if not before_metrics.exists() or not after.exists():
    print('Missing inputs')
    raise SystemExit(1)

before = json.loads(before_metrics.read_text(encoding='utf-8'))
after_data = json.loads(after.read_text(encoding='utf-8'))
after_summary = after_data.get('summary', {})

out_before.write_text(json.dumps(before, indent=2), encoding='utf-8')
out_after.write_text(json.dumps(after_summary, indent=2), encoding='utf-8')

# analyze top remaining errors: false positives
fps = []
for d in after_data.get('details', []):
    validator = d.get('validator', {})
    planner_correct = d.get('planner_correct')
    # false positive: validator invalid but planner_correct True
    if (not validator.get('valid')) and (planner_correct is True):
        fps.append(d)

# categorize fps
cats = {'Alias Resolution Errors':[], 'Aggregation Equivalence Errors':[], 'Display Column Equivalence Errors':[], 'Join Path Equivalence Errors':[], 'Planner Metadata Errors':[], 'Other':[]}
for e in fps:
    v = e.get('validator',{})
    gen = (e.get('generated_sql') or '').lower()
    missing_cols = set(v.get('missing_columns') or [])
    missing_aggs = set([m.lower() for m in (v.get('missing_aggregations') or [])])
    placed = False
    # alias: missing columns contain dots or planner columns include alias
    if any('.' in mc for mc in missing_cols):
        cats['Alias Resolution Errors'].append(e)
        placed = True
    # aggregation
    if not placed and any(a in ('group_by','sum','count','avg','min','max') or 'sum' in a or 'count' in a for a in missing_aggs):
        cats['Aggregation Equivalence Errors'].append(e); placed=True
    # display column
    if not placed:
        # if missing columns are id-like
        if any(mc.lower().endswith('_id') or mc.lower().endswith('id') for mc in missing_cols):
            cats['Display Column Equivalence Errors'].append(e); placed=True
    # join path
    if not placed:
        if v.get('missing_tables'):
            cats['Join Path Equivalence Errors'].append(e); placed=True
    if not placed:
        # planner metadata: expected requirement not present in planner outputs
        if not e.get('generated_sql') or 'i cannot generate' in (e.get('generated_sql') or '').lower():
            cats['Planner Metadata Errors'].append(e); placed=True
    if not placed:
        cats['Other'].append(e)

# build report
report = {
    'before': before,
    'after': after_summary,
    'counts': {k: len(v) for k,v in cats.items()},
    'top_remaining_errors_sample': {k: [ {'query': x.get('query'), 'generated_sql': x.get('generated_sql'), 'missing': x.get('validator')} for x in v[:10]] for k,v in cats.items()}
}

out_imp.write_text(json.dumps(report, indent=2), encoding='utf-8')
print('Wrote', out_before, out_after, out_imp)
