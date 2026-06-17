import json
from pathlib import Path

old = Path('reports/validator_benchmark_results.json')
new120 = Path('reports/validator_benchmark_120.json')
comp_out = Path('reports/validator_benchmark_comparison.json')
metrics120_out = Path('reports/validator_benchmark_120_metrics.json')

if not old.exists() or not new120.exists():
    print('Missing benchmark files')
    raise SystemExit(1)

old_data = json.loads(old.read_text(encoding='utf-8'))
new_data = json.loads(new120.read_text(encoding='utf-8'))
old_summary = old_data.get('summary', {})
new_summary = new_data.get('summary', {})

diff = {}
for k in ['total_evaluated','TP','FP','FN','TN','precision','recall','f1','false_positive_rate','false_negative_rate']:
    diff[k] = {'old': old_summary.get(k), 'new120': new_summary.get(k)}

comp = {'comparison': diff}
comp_out.write_text(json.dumps(comp, indent=2), encoding='utf-8')
metrics120_out.write_text(json.dumps(new_summary, indent=2), encoding='utf-8')
print('Wrote', comp_out, 'and', metrics120_out)
