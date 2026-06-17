import json,csv
from pathlib import Path
IN=Path('reports/validator_benchmark_120.json')
OUT=Path('reports/confusion_matrix_audit.csv')
if not IN.exists():
    print('missing input')
    raise SystemExit(1)
j=json.loads(IN.read_text(encoding='utf-8'))
details=j.get('details',[])
rows=[]
for d in details:
    q=d.get('query')
    planner_correct=d.get('planner_correct')
    validator_valid=d.get('validator',{}).get('valid')
    # classification mapping
    if validator_valid is False and planner_correct is False:
        cls='TP'
    elif validator_valid is False and planner_correct is True:
        cls='FP'
    elif validator_valid is True and planner_correct is False:
        cls='FN'
    elif validator_valid is True and planner_correct is True:
        cls='TN'
    else:
        cls='UNKNOWN'
    rows.append([q, planner_correct, validator_valid, cls, d.get('generated_sql')])
with OUT.open('w',newline='',encoding='utf-8') as f:
    writer=csv.writer(f)
    writer.writerow(['query','planner_correct','validator_valid','classification','generated_sql'])
    writer.writerows(rows)
print('Wrote',OUT)
print('\nSample 20:')
for r in rows[:20]:
    print(r)
