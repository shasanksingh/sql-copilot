import json
import csv
from pathlib import Path

IN = Path('reports/validator_benchmark_results.json')
OUT_CONF = Path('reports/validator_confusion_matrix.json')
OUT_QTYPE = Path('reports/validator_query_type_metrics.json')
OUT_FP = Path('reports/validator_false_positives.csv')
OUT_FN = Path('reports/validator_false_negatives.csv')
OUT_TRIAGE = Path('reports/validator_failure_triage.json')
OUT_RECO = Path('reports/validator_recommendation.json')

THRESHOLDS = {'precision': 0.9, 'recall': 0.9, 'fpr': 0.05, 'fnr': 0.05}

if not IN.exists():
    print('Missing input:', IN)
    raise SystemExit(1)

data = json.loads(IN.read_text(encoding='utf-8'))
summary = data.get('summary', {})
segments = data.get('segments', {})
confusion = data.get('confusion_matrix', {})
all_details = data.get('all_details', [])

# write confusion matrix
OUT_CONF.write_text(json.dumps(confusion, indent=2), encoding='utf-8')
print('Wrote', OUT_CONF)

# write query type metrics
OUT_QTYPE.write_text(json.dumps(segments, indent=2), encoding='utf-8')
print('Wrote', OUT_QTYPE)

# helper to normalize validator failure reason
def failure_reason(entry):
    v = entry.get('validator') or {}
    reasons = []
    if v.get('missing_tables'):
        reasons.append('missing_tables:'+','.join(v.get('missing_tables')))
    if v.get('missing_columns'):
        reasons.append('missing_columns:'+','.join(v.get('missing_columns')))
    if v.get('missing_aggregations'):
        reasons.append('missing_aggregations:'+','.join(v.get('missing_aggregations')))
    if v.get('invalid'):
        reasons.append('invalid')
    return ';'.join(reasons) if reasons else 'none'

# write false positives CSV (validator invalid but planner_correct True)
with OUT_FP.open('w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['user_query','generated_sql','confidence','planner_output','validation_failure_reason','expected_output','actual_output'])
    for e in all_details:
        v = e.get('validator') or {}
        validator_invalid = not v.get('valid')
        planner_correct = bool(e.get('planner_correct') is True)
        if validator_invalid and planner_correct:
            user_query = e.get('query')
            generated_sql = e.get('generated_sql')
            confidence = e.get('confidence')
            planner_output = e.get('validator', {})
            reason = failure_reason(e)
            expected = 'Valid (validator should have allowed)'
            actual = 'Invalid per validator: '+reason
            writer.writerow([user_query, generated_sql, confidence, json.dumps(planner_output), reason, expected, actual])
print('Wrote', OUT_FP)

# write false negatives CSV (validator passed but planner incorrect)
with OUT_FN.open('w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['user_query','generated_sql','confidence','planner_output','validation_failure_reason','expected_output','actual_output'])
    for e in all_details:
        v = e.get('validator') or {}
        validator_invalid = not v.get('valid')
        planner_correct = bool(e.get('planner_correct') is True)
        if (not validator_invalid) and (not planner_correct):
            user_query = e.get('query')
            generated_sql = e.get('generated_sql')
            confidence = e.get('confidence')
            planner_output = e.get('validator', {})
            reason = failure_reason(e)
            expected = 'Invalid (validator should have caught)'
            actual = 'Passed per validator'
            writer.writerow([user_query, generated_sql, confidence, json.dumps(planner_output), reason, expected, actual])
print('Wrote', OUT_FN)

# triage classification for every failure
triage = []
for e in all_details:
    v = e.get('validator') or {}
    validator_invalid = not v.get('valid')
    planner_correct = bool(e.get('planner_correct') is True)
    gen_sql = (e.get('generated_sql') or '')
    reason = failure_reason(e)
    classification = 'Other'
    # SQL generator apparent syntax errors
    if 'FROM ;' in gen_sql or gen_sql.strip() == '' or gen_sql.strip().startswith('SELECT .*'):
        classification = 'SQL Generator Error'
    elif not planner_correct:
        classification = 'Planner Error'
    elif planner_correct and validator_invalid:
        classification = 'Validator Error'
    # more granular checks
    if 'missing_aggregations' in reason:
        classification = 'Aggregation Equivalence Error'
    if 'missing_columns' in reason:
        # alias heuristic: if missing column names contain dot
        if any('.' in c for c in v.get('missing_columns') or []):
            classification = 'Alias Resolution Error'
        else:
            # display column heuristic
            if any(c.endswith('_id') or c.endswith('id') or 'date' in c or 'time' in c for c in v.get('missing_columns') or []):
                classification = 'Display Column Equivalence Error'
    triage.append({'query': e.get('query'), 'generated_sql': gen_sql, 'confidence': e.get('confidence'), 'planner_correct': planner_correct, 'validator_valid': v.get('valid'), 'validator_failure_reason': reason, 'classification': classification})

OUT_TRIAGE.write_text(json.dumps(triage, indent=2), encoding='utf-8')
print('Wrote', OUT_TRIAGE)

# recommendation
prec = summary.get('precision', 0.0)
rec = summary.get('recall', 0.0)
f1 = summary.get('f1', 0.0)
fpr = summary.get('false_positive_rate', 0.0)
fnr = summary.get('false_negative_rate', 0.0)

ready = (prec >= THRESHOLDS['precision'] and rec >= THRESHOLDS['recall'] and fpr <= THRESHOLDS['fpr'] and fnr <= THRESHOLDS['fnr'])

# find top root causes from triage
from collections import Counter
cnt = Counter([t['classification'] for t in triage])
most_common = [c for c,_ in cnt.most_common(5)]

recommendation = {'ready_for_advisory_mode': ready, 'precision': prec, 'recall': rec, 'f1_score': f1, 'false_positive_rate': fpr, 'false_negative_rate': fnr, 'top_root_causes': most_common, 'recommended_next_action': ''}

# construct recommended next action
if ready:
    recommendation['recommended_next_action'] = 'Enable advisory mode with logging; monitor production metrics.'
else:
    recommendation['recommended_next_action'] = 'Iteratively reduce top root causes (see top_root_causes); focus on Planner Error and Alias Resolution Error.'

OUT_RECO.write_text(json.dumps(recommendation, indent=2), encoding='utf-8')
print('Wrote', OUT_RECO)
