import json,glob,random,os

REPORT='reports/validator_benchmark_120.json'
LOG_DIR='logs/validator'
OUT='reports/sample_diagnostics.json'

r=json.load(open(REPORT,'r',encoding='utf-8'))
d=r.get('details',[])
logs={}
for p in glob.glob(os.path.join(LOG_DIR,'*.json')):
    try:
        logs[p]=json.load(open(p,'r',encoding='utf-8'))
    except:
        pass

# normalize helper
def norm_list(lst):
    return sorted([ (x.split('.')[-1].lower() if isinstance(x,str) else str(x).lower()) for x in (lst or [])])

sample = random.sample(d, min(10,len(d)))
out=[]
for rec in sample:
    q=rec.get('query')
    required_cols = norm_list(rec.get('validator',{}).get('missing_columns') or rec.get('required_columns') or [])
    planned_cols = norm_list(rec.get('validator',{}).get('planned_columns') or rec.get('planned_columns') or [])
    found=None
    for p,obj in logs.items():
        o_planned = norm_list(obj.get('planned_columns') or [])
        o_required = norm_list(obj.get('required_columns') or obj.get('required') or [])
        # if both planned and required lists overlap sufficiently
        if o_planned==planned_cols and o_required==required_cols:
            found={'log_file':p,'diagnostics':obj.get('diagnostics'),'planned_columns':obj.get('planned_columns'),'required_columns':obj.get('required_columns')}
            break
        # fallback: if planned columns intersect
        if set(o_planned) & set(planned_cols):
            found={'log_file':p,'diagnostics':obj.get('diagnostics'),'planned_columns':obj.get('planned_columns'),'required_columns':obj.get('required_columns')}
            break
    out.append({'query':q,'sql_correct':rec.get('sql_correct'),'planner_correct':rec.get('planner_correct'),'validator_valid': (rec.get('validator') or {}).get('valid'), 'match': found})

json.dump(out, open(OUT,'w',encoding='utf-8'), indent=2)
print('Wrote',OUT)
