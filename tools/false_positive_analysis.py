import json, re
from collections import Counter, defaultdict

IN='reports/validator_benchmark_120.json'
OUT_MD='reports/top_false_positive_analysis.md'
OUT_CLUST='reports/false_positive_clusters.json'
OUT_EX='reports/false_positive_examples.json'

r=json.load(open(IN,'r',encoding='utf-8'))
details=r.get('details',[])

# Identify false positives: planner_correct == True and validator.valid == False
fps=[]
for d in details:
    planner_ok = bool(d.get('planner_correct') is True)
    v = d.get('validator') or {}
    valid = v.get('valid')
    if planner_ok and (valid is False):
        fps.append(d)

# clustering heuristics
DISPLAY_TOKENS = {'name','display','list','title','label'}
OPTIONAL_SUFFIXES = ('_id','id','_ts','timestamp','_at')

clusters = defaultdict(list)

for d in fps:
    v = d.get('validator') or {}
    missing_aggs = [x.lower() for x in (v.get('missing_aggregations') or [])]
    missing_cols = [x.lower() for x in (v.get('missing_columns') or [])]
    missing_tbls = [x.lower() for x in (v.get('missing_tables') or [])]
    gen_sql = (d.get('generated_sql') or '').lower()
    planned_cols = [c.split('.')[-1].lower() for c in (d.get('planned_columns') or [])]

    # heuristics
    assigned = False
    # Aggregation Equivalence Failure
    if missing_aggs:
        # look for common agg tokens
        agg_tokens = {'sum','avg','count','group_by','group','group_by','group_by'}
        if any(any(tok in ma for tok in agg_tokens) or re.search(r'sum\(|avg\(|count\(|group', ma) for ma in missing_aggs) or any('sum' in ma or 'avg' in ma or 'count' in ma or 'group' in ma for ma in missing_aggs):
            clusters['Aggregation Equivalence Failure'].append(d); assigned=True
    # Display Column Failure
    if (not assigned) and missing_cols:
        if any(any(tok in mc for tok in DISPLAY_TOKENS) or mc.endswith('name') for mc in missing_cols):
            clusters['Display Column Failure'].append(d); assigned=True
    # Join Equivalence Failure
    if (not assigned) and missing_tbls:
        clusters['Join Equivalence Failure'].append(d); assigned=True
    # Planner Metadata Failure (planner returned placeholder)
    if (not assigned) and (gen_sql.strip().startswith('i cannot generate') or gen_sql.strip().startswith('select\n  .*\nfrom  ;')):
        clusters['Planner Metadata Failure'].append(d); assigned=True
    # Missing Optional Column
    if (not assigned) and missing_cols:
        if any(mc.endswith(suf) for mc in missing_cols for suf in OPTIONAL_SUFFIXES):
            clusters['Missing Optional Column'].append(d); assigned=True
    # Alias Resolution Failure: planned columns contain similar tokens to missing
    if (not assigned) and missing_cols and planned_cols:
        for mc in missing_cols:
            for pc in planned_cols:
                if mc in pc or pc in mc or mc.replace('_','')==pc.replace('_',''):
                    clusters['Alias Resolution Failure'].append(d); assigned=True; break
            if assigned: break
    # Semantic Mapping Failure: fallback if missing columns look like entities
    if (not assigned) and missing_cols:
        # heuristic: missing cols longer than 4 and not agg-like
        if any(len(mc)>4 for mc in missing_cols):
            clusters['Semantic Mapping Failure'].append(d); assigned=True
    if not assigned:
        clusters['Validation Rule Too Strict'].append(d)

# summarize clusters
cluster_summary=[]
total_fp=len(fps)
for name, items in clusters.items():
    cnt=len(items)
    pct=cnt/total_fp*100 if total_fp else 0
    # average confidence not available; use None
    avg_conf=None
    examples=[items[i].get('query') for i in range(min(5,len(items)))]
    cluster_summary.append({'cluster':name,'count':cnt,'percentage':round(pct,2),'average_confidence':avg_conf,'examples':examples})

# Rank clusters
cluster_summary=sorted(cluster_summary, key=lambda x: x['count'], reverse=True)

# Identify largest cluster
largest=cluster_summary[0] if cluster_summary else None

# Top 20 high impact cases: select first 20 fps and provide details
top20=[]
for d in fps[:20]:
    rec={'query':d.get('query'),'generated_sql':d.get('generated_sql'),'planned_columns':d.get('planned_columns'),'required_columns':d.get('required_columns') or d.get('validator',{}).get('missing_columns'),'validator':d.get('validator')}
    # failure reason heuristic
    reason='Unknown'
    for name, items in clusters.items():
        if d in items:
            reason=name; break
    rec['failure_cluster']=reason
    # expected behaviour: planner columns satisfy required
    rec['expected_behaviour']='Planner-provided columns/aggregations should satisfy required fields'
    rec['actual_behaviour']='Validator marked as invalid; missing fields listed above'
    # potential fix suggestion per cluster
    if 'Aggregation' in reason:
        rec['potential_fix']='Relax aggregation equivalence: accept COUNT(*) vs COUNT(col) and map SUM(amount)<->SUM(invoice_amount)'
    elif 'Display' in reason:
        rec['potential_fix']='Allow id/name substitutions when display not explicitly requested'
    elif 'Alias' in reason:
        rec['potential_fix']='Improve canonicalization of aliased columns and table prefixes'
    else:
        rec['potential_fix']='Investigate specific case; add unit test and refine resolver rules'
    top20.append(rec)

# compute hypothetical precision gain if we fixed largest cluster entirely
current_TP = r.get('summary',{}).get('TP',0)
current_FP = r.get('summary',{}).get('FP',0)
current_total_eval = r.get('summary',{}).get('total_evaluated', total_fp)
largest_count = largest['count'] if largest else 0
potential_FP = current_FP - largest_count
potential_TP = current_TP
potential_precision = potential_TP / (potential_TP + potential_FP) if (potential_TP + potential_FP)>0 else None

out_clusters={'summary':cluster_summary,'total_fp':total_fp}
json.dump(out_clusters, open(OUT_CLUST,'w',encoding='utf-8'), indent=2)

# write examples (all fps up to 500)
examples=[{'query':d.get('query'),'planner_correct':d.get('planner_correct'),'sql_correct':d.get('sql_correct'),'validator':d.get('validator'),'generated_sql':d.get('generated_sql')} for d in fps]
json.dump(examples, open(OUT_EX,'w',encoding='utf-8'), indent=2)

# write markdown
with open(OUT_MD,'w',encoding='utf-8') as f:
    f.write('# Top False Positive Analysis\n\n')
    f.write(f'Total queries evaluated: {r.get("summary",{}).get("total_evaluated",len(details))}\n')
    f.write(f'False positives (planner_correct && validator.invalid): {total_fp}\n\n')
    f.write('## Cluster summary (ranked)\n')
    for c in cluster_summary:
        f.write(f'- {c["cluster"]}: {c["count"]} ({c["percentage"]}%) avg_confidence={c["average_confidence"]}\n')
        f.write(f'  - examples: {c["examples"]}\n')
    f.write('\n')
    if largest:
        f.write('## Largest cluster\n')
        f.write(f'- {largest["cluster"]} — {largest["count"]} ({largest["percentage"]}%)\n')
        f.write('\n')
        f.write('### Example queries\n')
        for q in largest['examples']:
            f.write(f'- {q}\n')
        f.write('\n')
        f.write('### Suggested fix\n')
        f.write('- See cluster-specific suggestions above; recommended to add unit tests and relax equivalence rules for this class.\n')
        f.write('\n')
        f.write(f'### Estimated precision if fixed fully: {round(potential_precision*100,2) if potential_precision is not None else "N/A"}%\n')
    f.write('\n## Top 20 high-impact cases\n')
    for rec in top20:
        f.write('---\n')
        f.write(f"Query: {rec['query']}\n")
        f.write(f"Generated SQL: {rec['generated_sql']}\n")
        f.write(f"Planner output (planned_columns): {rec.get('planned_columns')}\n")
        f.write(f"Validator failure reason: {rec['failure_cluster']}\n")
        f.write(f"Expected behaviour: {rec['expected_behaviour']}\n")
        f.write(f"Actual behaviour: {rec['actual_behaviour']}\n")
        f.write(f"Potential fix: {rec['potential_fix']}\n")

print('Wrote', OUT_MD, OUT_CLUST, OUT_EX)
