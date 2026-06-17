import json
from pathlib import Path
fn='reports/planner_validation_false_negatives.json'
ft='reports/planner_validation_failed_tests.json'
items=[]
if Path(fn).exists():
    d=json.load(open(fn,'r',encoding='utf-8'))
    if isinstance(d,dict) and 'false_negatives' in d:
        items.extend(d['false_negatives'])
    elif isinstance(d,list): items.extend(d)
if Path(ft).exists():
    d=json.load(open(ft,'r',encoding='utf-8'))
    if isinstance(d,dict) and 'failures' in d:
        items.extend(d['failures'])
    elif isinstance(d,list): items.extend(d)
print('total items from reports:', len(items))
unique=set()
for it in items:
    q=it.get('query')
    unique.add(q)
print('unique queries:', len(unique))
from glob import glob
logs=glob('logs/planner_diagnostics/*.json')
print('log files count:', len(logs))
c=0
for p in logs:
    obj=json.load(open(p,'r',encoding='utf-8'))
    if 'audit_planner_correct' in obj:
        c+=1
print('logs with audit_planner_correct:',c)
