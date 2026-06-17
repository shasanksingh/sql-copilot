import json,glob
c=0
has=[]
no=[]
for p in sorted(glob.glob('logs/planner_diagnostics/*.json')):
    obj=json.load(open(p,'r',encoding='utf-8'))
    if 'audit_planner_correct' in obj:
        c+=1; has.append(p)
    else:
        no.append(p)
print('with audit_planner_correct:',c)
print('sample without field:', no[:5])
