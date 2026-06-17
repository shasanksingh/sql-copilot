import json
from collections import Counter
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

cnt=Counter()
for it in items:
    cnt[it.get('query')]+=1

print('total items:', len(items))
print('unique queries:', len(cnt))
most=cnt.most_common(30)
for q,c in most:
    print(c, q)

# list queries with singletons
singletons=[q for q,c in cnt.items() if c==1]
print('singletons count:', len(singletons))
# prepare audit summary
out={'total_items':len(items),'unique_queries':len(cnt),'top_duplicates': most}
open('reports/benchmark_audit.json','w',encoding='utf-8').write(json.dumps(out,indent=2))
print('Wrote reports/benchmark_audit.json')
