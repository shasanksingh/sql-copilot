import json
from collections import Counter

before = json.load(open('reports/validator_benchmark_120.json','r',encoding='utf-8'))
after = json.load(open('reports/validator_after_refactor.json','r',encoding='utf-8'))

def summarize(dataset):
    s = dataset.get('summary',{})
    return s

b = summarize(before)
a = summarize(after)

# compute top 20 FP/FN for after
FP = []
FN = []
root_causes = Counter()
for d in after.get('details',[]):
    validator = d.get('validator',{})
    planner_correct = d.get('planner_correct')
    valid = validator.get('valid')
    if (not valid) and planner_correct:
        FP.append(d)
        if validator.get('missing_aggregations'):
            root_causes['aggregation'] += 1
        elif validator.get('missing_columns'):
            root_causes['column'] += 1
        else:
            root_causes['other'] += 1
    if valid and (not planner_correct):
        FN.append(d)

FP_top20 = FP[:20]
FN_top20 = FN[:20]

with open('reports/refactor_impact_report.md','w',encoding='utf-8') as f:
    f.write('# Refactor Impact Report\n\n')
    f.write('**Before**:\n')
    for k in ['total_evaluated','TP','FP','FN','TN','precision','recall','f1','false_positive_rate','false_negative_rate']:
        f.write(f'- **{k}**: {b.get(k)}\n')
    f.write('\n**After**:\n')
    for k in ['total_evaluated','TP','FP','FN','TN','precision','recall','f1','false_positive_rate','false_negative_rate']:
        f.write(f'- **{k}**: {a.get(k)}\n')
    # improvement
    def pct(old, new):
        try:
            return (new-old)/old*100.0
        except Exception:
            return None
    if b.get('precision') is not None and a.get('precision') is not None:
        f.write('\n**Improvement %**:\n')
        f.write(f'- Precision: {pct(b.get("precision"), a.get("precision"))}\n')
        f.write(f'- Recall: {pct(b.get("recall"), a.get("recall"))}\n')
        f.write(f'- F1: {pct(b.get("f1"), a.get("f1"))}\n')
        f.write(f'- FPR: {pct(b.get("false_positive_rate"), a.get("false_positive_rate"))}\n')
        f.write(f'- FNR: {pct(b.get("false_negative_rate"), a.get("false_negative_rate"))}\n')
    f.write('\n**Top 20 remaining false positives**:\n')
    for d in FP_top20:
        f.write(f'- {d.get("query")} -- missing_columns={d.get("validator",{}).get("missing_columns")} missing_aggs={d.get("validator",{}).get("missing_aggregations")}\n')
    f.write('\n**Top 20 remaining false negatives**:\n')
    for d in FN_top20:
        f.write(f'- {d.get("query")} -- missing_columns={d.get("validator",{}).get("missing_columns")} missing_aggs={d.get("validator",{}).get("missing_aggregations")}\n')
    f.write('\n**Root cause distribution**:\n')
    for k,v in root_causes.most_common():
        f.write(f'- {k}: {v}\n')

print('Wrote reports/refactor_impact_report.md')
