import json, glob, random, os

IN = 'reports/validator_benchmark_120.json'
LOG_DIR = 'logs/validator'
OUT_AUDIT_MD = 'reports/validator_execution_audit.md'
OUT_FIELD_VER = 'reports/benchmark_field_verification.json'
OUT_CONSIST = 'reports/benchmark_consistency_report.md'

c = json.load(open(IN,'r',encoding='utf-8'))
details = c.get('details', [])

total = len(details)
valid_true = valid_false = valid_missing = 0
sql_true = sql_false = sql_missing = 0
planner_true = planner_false = planner_missing = 0

for d in details:
    v = d.get('validator')
    if v is None:
        valid_missing += 1
    else:
        if 'valid' in v:
            if v.get('valid'):
                valid_true += 1
            else:
                valid_false += 1
        else:
            valid_missing += 1
    # sql_correct
    if 'sql_correct' in d:
        if d.get('sql_correct') is True:
            sql_true += 1
        elif d.get('sql_correct') is False:
            sql_false += 1
    else:
        sql_missing += 1
    # planner_correct
    if 'planner_correct' in d:
        if d.get('planner_correct') is True:
            planner_true += 1
        elif d.get('planner_correct') is False:
            planner_false += 1
    else:
        planner_missing += 1

field_counts = {
    'total_records': total,
    'validator_valid_true_count': valid_true,
    'validator_valid_false_count': valid_false,
    'validator_missing_count': valid_missing,
    'sql_correct_true_count': sql_true,
    'sql_correct_false_count': sql_false,
    'sql_correct_missing_count': sql_missing,
    'planner_correct_true_count': planner_true,
    'planner_correct_false_count': planner_false,
    'planner_correct_missing_count': planner_missing,
}
json.dump(field_counts, open(OUT_FIELD_VER,'w',encoding='utf-8'), indent=2)

# Field existence counts for every record
exist_counts = {'validator.valid':0,'sql_correct':0,'planner_correct':0,'generated_sql':0,'query':0}
for d in details:
    if d.get('query') is not None:
        exist_counts['query'] += 1
    if d.get('generated_sql') is not None:
        exist_counts['generated_sql'] += 1
    if 'sql_correct' in d:
        exist_counts['sql_correct'] += 1
    if 'planner_correct' in d:
        exist_counts['planner_correct'] += 1
    v = d.get('validator')
    if v and ('valid' in v):
        exist_counts['validator.valid'] += 1

# Random sample verification (10)
sample = random.sample(details, min(10, total))
sample_out = []
# load logs map
logs = {}
for p in glob.glob(os.path.join(LOG_DIR,'*.json')):
    try:
        obj = json.load(open(p,'r',encoding='utf-8'))
        key = (obj.get('query') or obj.get('planned_columns') or str(p))
        logs[p] = obj
    except Exception:
        continue

for d in sample:
    q = d.get('query')
    sqlc = d.get('sql_correct')
    planc = d.get('planner_correct')
    v = d.get('validator')
    valid = None
    if v and ('valid' in v):
        valid = v.get('valid')
    # try find an exact log match by query or generated_sql
    diag = None
    for p,obj in logs.items():
        if obj.get('query') and obj.get('query') == q:
            diag = obj.get('diagnostics')
            break
        # sometimes logs include planned_columns; match generated_sql
        if obj.get('generated_sql') and obj.get('generated_sql') == d.get('generated_sql'):
            diag = obj.get('diagnostics')
            break
    sample_out.append({
        'query': q,
        'sql_correct': sqlc,
        'planner_correct': planc,
        'validator.valid': valid,
        'diagnostics': diag
    })

# Cross-check other reports
other_reports = ['reports/manual_confusion_matrix.json','reports/validator_distribution.json','reports/system_bottleneck_analysis.json']
other = {}
for r in other_reports:
    try:
        other[r] = json.load(open(r,'r',encoding='utf-8'))
    except Exception as e:
        other[r] = {'error': str(e)}

# Decide canonical: prefer reports/validator_benchmark_120.json as authoritative because it's produced by evaluator and contains per-query validator results; other reports are downstream derivations and in earlier audits were found to read raw logs lacking validator fields.
canonical = 'reports/validator_benchmark_120.json'

consistency_lines = []
consistency_lines.append('Canonical report: '+canonical)
for r in other_reports:
    status = 'present'
    if isinstance(other.get(r), dict) and other.get(r).get('error'):
        status = 'error'
    else:
        # check whether this report includes validator fields
        text = json.dumps(other.get(r))
        if 'validator' in text or 'validator.valid' in text or 'planner_correct' in text:
            status = 'contains_validator'
        else:
            status = 'missing_validator_fields'
    consistency_lines.append(f'- {r}: {status}')

# Write audit md
with open(OUT_AUDIT_MD,'w',encoding='utf-8') as f:
    f.write('# Validator Execution Audit\n\n')
    f.write('## Task 3: Field counts\n')
    for k,v in field_counts.items():
        f.write(f'- {k}: {v}\n')
    f.write('\n## Task 4: Field existence counts\n')
    for k,v in exist_counts.items():
        f.write(f'- {k}: {v}\n')
    f.write('\n## Task 5: Random sample (10)\n')
    for s in sample_out:
        f.write(json.dumps(s,indent=2))
        f.write('\n')
    f.write('\n## Task 6: Cross-check other reports\n')
    for line in consistency_lines:
        f.write(line+'\n')

# write consistency report
with open(OUT_CONSIST,'w',encoding='utf-8') as f:
    f.write('# Benchmark Consistency Report\n\n')
    f.write('Canonical: reports/validator_benchmark_120.json\n\n')
    for r in other_reports:
        f.write(f'- {r}: ')
        if isinstance(other.get(r), dict) and other.get(r).get('error'):
            f.write('ERROR loading\n')
        else:
            text = json.dumps(other.get(r))
            if 'validator' in text or 'planner_correct' in text:
                f.write('Contains validator/planner fields\n')
            else:
                f.write('Missing validator/planner fields — likely reads raw planner logs\n')

print('Wrote', OUT_AUDIT_MD, OUT_FIELD_VER, OUT_CONSIST)
