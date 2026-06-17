import json
from collections import defaultdict

REPORT_IN = "reports/planner_validation_false_negatives.json"
FAILED_TESTS = "reports/planner_validation_failed_tests.json"
OUT = "reports/planner_validation_root_causes.json"

CATEGORIES = [
    "Missing Table False Positive",
    "Missing Column False Positive",
    "Missing Aggregation False Positive",
    "Alias Resolution Error",
    "Display Column Mismatch",
    "Planner Metadata Error",
    "Entity Resolution Error",
]


def classify(entry):
    reasons = set()
    vr = entry.get('validation_result', {})
    intent = entry.get('intent', {})
    entities = entry.get('entities', {})
    planned_columns = entry.get('planned_columns') or []
    required_columns = entry.get('required_columns') or []

    if vr.get('missing_tables'):
        reasons.add('Missing Table False Positive')

    if vr.get('missing_columns'):
        # detect display-only misses: if required columns are ids or optional
        missing = vr.get('missing_columns')
        id_like = [c for c in missing if c.endswith('_id') or c.endswith('id') or c.startswith('meta')]
        if id_like and len(missing) == len(id_like):
            reasons.add('Display Column Mismatch')
        else:
            reasons.add('Missing Column False Positive')

    if vr.get('missing_aggregations'):
        reasons.add('Missing Aggregation False Positive')

    # Alias resolution heuristic: required unprefixed but planned contains prefixed variant
    for rc in required_columns:
        rnorm = rc.split('.')[-1]
        if rnorm and any(p.endswith('.' + rnorm) for p in planned_columns):
            # if validator reported missing rc but planning has x.rnorm
            if rc in vr.get('missing_columns', []) or rnorm in vr.get('missing_columns', []):
                reasons.add('Alias Resolution Error')

    # Entity resolution: unresolved terms in entities
    if entities and entities.get('unresolved_terms'):
        reasons.add('Entity Resolution Error')

    # Planner metadata / generator errors: no planner_columns and SQL missing
    if not planned_columns and (entry.get('generated_sql', '').strip().lower().startswith('i cannot') or entry.get('generated_sql','').strip().endswith('FROM  ;')):
        reasons.add('Planner Metadata Error')

    if not reasons:
        reasons.add('Other')

    return list(sorted(reasons))


def gather_examples(items):
    by_cat = defaultdict(list)
    for e in items:
        cats = classify(e)
        for c in cats:
            if len(by_cat[c]) < 5:
                by_cat[c].append({
                    'query': e.get('query'),
                    'planned_tables': e.get('planned_tables'),
                    'planned_columns': e.get('planned_columns'),
                    'generated_sql': e.get('generated_sql'),
                    'validation_result': e.get('validation_result'),
                })
    return by_cat


def main():
    items = []
    try:
        with open(REPORT_IN, 'r', encoding='utf-8') as f:
            d = json.load(f)
            # support both list under key or root list
            if isinstance(d, dict) and 'false_negatives' in d:
                items.extend(d['false_negatives'])
            elif isinstance(d, list):
                items.extend(d)
    except FileNotFoundError:
        pass

    try:
        with open(FAILED_TESTS, 'r', encoding='utf-8') as f:
            d = json.load(f)
            if isinstance(d, dict) and 'failures' in d:
                items.extend(d['failures'])
            elif isinstance(d, list):
                items.extend(d)
    except FileNotFoundError:
        pass

    by_cat = gather_examples(items)
    summary = {c: {'count': len(by_cat.get(c, [])), 'examples': by_cat.get(c, [])} for c in (CATEGORIES + ['Other'])}

    out = {
        'total_analyzed': len(items),
        'categories': summary,
    }

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)

    print('Wrote', OUT)


if __name__ == '__main__':
    main()
