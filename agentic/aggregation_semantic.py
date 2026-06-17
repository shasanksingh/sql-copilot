import re
from typing import List

class AggregationSemanticResolver:
    # small synonym groups
    SYNONYMS = [
        {'amount','invoice_amount','total_amount','payment_amount','payment','amount','revenue'},
        {'salary','employee_salary','annual_salary','wage'},
        {'budget','project_budget','allocated_budget'},
    ]

    @staticmethod
    def _tokenize_measure(col: str) -> List[str]:
        if not col:
            return []
        # strip aliases and parenthesis
        col = col.lower()
        col = re.sub(r"[^a-z0-9_]", '_', col)
        parts = [p for p in col.split('_') if p]
        return parts

    def extract_measure_tokens(self, agg_expr: str) -> List[str]:
        # agg_expr examples: 'SUM(amount)', 'COUNT(*)', 'AVG(employee_salary)'
        if not agg_expr:
            return []
        low = agg_expr.lower()
        if '(' in low and ')' in low:
            inner = low[low.find('(')+1:low.rfind(')')]
            inner = inner.strip()
            # handle *
            if inner == '*' or inner == '1':
                return ['count_star']
            return self._tokenize_measure(inner)
        # fallback
        return self._tokenize_measure(low)

    def aggregation_similarity(self, req: str, planned: str) -> float:
        # compute heuristic similarity between two aggregation expressions
        if not req or not planned:
            return 0.0
        rtok = self.extract_measure_tokens(req)
        ptok = self.extract_measure_tokens(planned)
        # if both are count variants
        if 'count_star' in rtok and 'count_star' in ptok:
            return 1.0
        if any('count' in tok for tok in rtok) and any('count' in tok for tok in ptok):
            return 1.0
        # simple token overlap score
        if not rtok or not ptok:
            return 0.0
        overlap = len(set(rtok) & set(ptok))
        denom = max(len(set(rtok)), len(set(ptok)))
        base_score = overlap/denom if denom else 0.0
        # synonyms bonus
        bonus = 0.0
        for synset in self.SYNONYMS:
            if (set(rtok) & synset) and (set(ptok) & synset):
                bonus = 0.6
                break
        score = min(1.0, base_score + bonus)
        return score

    def equivalent_measure(self, req: str, planned: str, threshold: float = 0.8) -> bool:
        return self.aggregation_similarity(req, planned) >= threshold


# quick manual test
if __name__ == '__main__':
    r = AggregationSemanticResolver()
    print(r.aggregation_similarity('SUM(amount)','SUM(invoice_amount)'))
    print(r.equivalent_measure('COUNT(*)','COUNT(client_id)'))
