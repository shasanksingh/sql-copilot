import json
import csv
from pathlib import Path
from collections import Counter

BENCH_IN = Path('reports/validator_benchmark_results.json')
FN = Path('reports/planner_validation_false_negatives.json')
FT = Path('reports/planner_validation_failed_tests.json')
OUT_AUDIT = Path('reports/benchmark_audit.json')
OUT_CONF_AUDIT = Path('reports/confusion_matrix_audit.csv')
OUT_EQ = Path('reports/benchmark_equivalence_errors.json')
OUT_NORM = Path('reports/validator_metrics_normalized.json')
OUT_ROOT = Path('reports/validator_root_cause_analysis.json')

# load data
bench = json.loads(BENCH_IN.read_text(encoding='utf-8')) if BENCH_IN.exists() else {}
all_details = bench.get('all_details', [])

# build lookup from reports
items = []
if FN.exists():
    d=json.loads(FN.read_text(encoding='utf-8'))
    if isinstance(d,dict) and 'false_negatives' in d:
        items.extend(d['false_negatives'])
    elif isinstance(d,list): items.extend(d)
if FT.exists():
    d=json.loads(FT.read_text(encoding='utf-8'))
    if isinstance(d,dict) and 'failures' in d:
        items.extend(d['failures'])
    elif isinstance(d,list): items.extend(d)

lookup = {it.get('query'): it for it in items}

# 2. confusion matrix audit csv
rows = []
for d in all_details:
    q = d.get('query')
    validator_res = d.get('validator', {})
    validator_valid = validator_res.get('valid')
    # find audit
    rep = lookup.get(q)
    planner_correct = rep.get('audit_planner_correct') if rep else None
    sql_correct = rep.get('audit_sql_correct') if rep else None
    # expected: if sql_correct is True -> validator should pass (valid==True)
    expected_valid = True if sql_correct is True else False if sql_correct is False else None
    # classification
    if expected_valid is None:
        classification = 'unknown'
    else:
        if expected_valid and validator_valid:
            classification = 'TN'
        elif expected_valid and not validator_valid:
            classification = 'FP'
        elif (not expected_valid) and (not validator_valid):
            classification = 'TP'
        elif (not expected_valid) and validator_valid:
            classification = 'FN'
        else:
            classification = 'unknown'
    rows.append([q, planner_correct, sql_correct, validator_valid, expected_valid, classification])

with OUT_CONF_AUDIT.open('w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['query','planner_correct','sql_correct','validator_result','expected_result','classification'])
    writer.writerows(rows)
print('Wrote', OUT_CONF_AUDIT)

# 3. benchmark equivalence errors
# heuristics: if validator failure lists missing_columns or missing_aggregations but generated_sql contains equivalent forms
eq = []
for d in all_details:
    q = d.get('query')
    v = d.get('validator', {})
    gen = (d.get('generated_sql') or '').lower()
    reasons = []
    if v.get('missing_aggregations'):
        # if missing SUM but gen contains sum of a different column or count(*) etc
        if 'count(' in gen or 'sum(' in gen:
            reasons.append('aggregation_equivalence')
    if v.get('missing_columns'):
        for mc in v.get('missing_columns'):
            mc_low = mc.lower()
            # alias removal
            if '.' in mc_low:
                if mc_low.split('.')[-1] in gen:
                    reasons.append('alias_equivalence')
            else:
                if mc_low in gen:
                    reasons.append('name_present_in_sql')
                # check common id vs name mismatch
                if mc_low.endswith('_id') and mc_low.replace('_id','') in gen:
                    reasons.append('display_vs_id')
    if reasons:
        eq.append({'query':q,'generated_sql':d.get('generated_sql'),'validator':v,'reasons':list(set(reasons))})

OUT_EQ.write_text(json.dumps(eq,indent=2),encoding='utf-8')
print('Wrote', OUT_EQ)

# 4. compute normalized metrics applying alias, aggregation, display equivalence
# normalization functions

def normalize_validator(v,d):
    # v is validator result dict
    # d is detail entry
    new_v = dict(v)
    missing_cols = set(new_v.get('missing_columns') or [])
    missing_aggs = set(new_v.get('missing_aggregations') or [])
    gen = (d.get('generated_sql') or '').lower()
    # alias normalization: if missing column 'client_name' but gen contains 'c.client_name' or 'client_name'
    to_remove_cols = set()
    for mc in list(missing_cols):
        mc_low = mc.lower()
        if '.' in mc_low:
            if mc_low.split('.')[-1] in gen:
                to_remove_cols.add(mc)
        else:
            if mc_low in gen:
                to_remove_cols.add(mc)
            # id vs display
            if mc_low.endswith('_id'):
                if mc_low.replace('_id','') in gen:
                    to_remove_cols.add(mc)
    missing_cols -= to_remove_cols
    # aggregation equivalence: if missing SUM but gen has sum of other column, accept
    to_remove_aggs = set()
    for ma in list(missing_aggs):
        ma_low = ma.lower()
        if ma_low in ('sum','group_by','count'):
            if 'sum(' in gen or 'count(' in gen or 'group by' in gen:
                to_remove_aggs.add(ma)
    missing_aggs -= to_remove_aggs
    new_v['missing_columns'] = list(missing_cols)
    new_v['missing_aggregations'] = list(missing_aggs)
    new_v['valid'] = (not new_v['missing_columns']) and (not new_v['missing_aggregations']) and (not new_v.get('missing_tables'))
    return new_v

TP=FP=FN=TN=0
norm_details=[]
for d in all_details:
    q=d.get('query')
    v=d.get('validator',{})
    norm = normalize_validator(v,d)
    norm_details.append({'query':q,'orig_validator':v,'norm_validator':norm,'generated_sql':d.get('generated_sql')})
    # expected from audit_sql_correct
    rep=lookup.get(q)
    expected_invalid = None
    if rep and 'audit_sql_correct' in rep:
        expected_invalid = not bool(rep.get('audit_sql_correct'))
    # if expected_invalid is None, skip counting
    if expected_invalid is None:
        continue
    validator_invalid = not norm.get('valid')
    if validator_invalid and expected_invalid:
        TP+=1
    elif validator_invalid and not expected_invalid:
        FP+=1
    elif (not validator_invalid) and expected_invalid:
        FN+=1
    elif (not validator_invalid) and not expected_invalid:
        TN+=1

results_norm={'TP':TP,'FP':FP,'FN':FN,'TN':TN}
OUT_NORM.write_text(json.dumps({'results':results_norm,'details_sample':norm_details[:50]},indent=2),encoding='utf-8')
print('Wrote', OUT_NORM)

# 5. root cause analysis
counts=Counter()
root_list=[]
for d in all_details:
    q=d.get('query')
    v=d.get('validator',{})
    rep=lookup.get(q)
    gen=(d.get('generated_sql') or '')
    classification='Unknown'
    if rep and rep.get('audit_sql_correct') is False:
        classification='SQL Generator Error'
    elif rep and rep.get('audit_planner_correct') is False:
        classification='Planner Error'
    else:
        # if validator missing columns/agg -> Validator Error or Benchmark Error
        if v.get('missing_aggregations') or v.get('missing_columns'):
            # if generated_sql contains equivalent tokens treat as Benchmark Expectation Error
            treated=False
            low=gen.lower()
            for mc in (v.get('missing_columns') or []):
                if mc.lower() in low or ('.'+mc.lower() in low) or (mc.lower().replace('_id','') in low):
                    classification='Benchmark Expectation Error'
                    treated=True
                    break
            if not treated:
                classification='Validator Error'
    counts[classification]+=1
    root_list.append({'query':q,'classification':classification,'validator':v,'generated_sql':gen,'audit':rep})
OUT_ROOT.write_text(json.dumps({'counts':counts,'items':root_list},default=lambda o:dict(o),indent=2),encoding='utf-8')
print('Wrote', OUT_ROOT)

# 6. recommendation logic
# choose A-D based on dominant root cause
most=counts.most_common()
decision='Fix Validator'
if most:
    top=most[0][0]
    if top=='SQL Generator Error': decision='Fix SQL Generator'
    elif top=='Planner Error': decision='Fix Planner'
    elif top=='Benchmark Expectation Error' or top=='Benchmark Error' or top=='Labeling Error': decision='Fix Benchmark'
    elif top=='Validator Error': decision='Fix Validator'
OUT_DEC=Path('reports/validator_audit_recommendation.json')
OUT_DEC.write_text(json.dumps({'decision':decision,'top_root_cause':most[0] if most else None},indent=2),encoding='utf-8')
print('Wrote', OUT_DEC)
