import json
from pathlib import Path
p=Path('reports/planner_validation_false_negatives.json')
d=json.load(open(p,'r',encoding='utf-8'))
if isinstance(d,dict) and 'false_negatives' in d:
    print('len false_negatives list:', len(d['false_negatives']))
else:
    print('not dict/list or missing key')
