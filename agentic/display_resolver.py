import re
from typing import List

class DisplayColumnResolver:
    DISPLAY_TOKENS = {'name','title','label','display','display name','client name','customer name','project name'}
    ID_SUFFIXES = ('_id','id')

    def requires_display(self, query_text: str, intent: dict | None = None) -> bool:
        if intent and intent.get('aggregations'):
            # aggregation queries typically need measures, not display names
            return False
        if not query_text:
            return False
        q = query_text.lower()
        for tok in self.DISPLAY_TOKENS:
            if tok in q:
                return True
        return False

    def display_equivalent(self, required_col: str, planned_cols: List[str], query_text: str = '') -> dict:
        # Return dict with whether equivalent, and which substitution applied
        res = {'equivalent': False, 'accepted_id_substitution': False, 'reason': ''}
        req = (required_col or '').lower()
        planned = [(c or '').lower() for c in (planned_cols or [])]
        if not req:
            res['equivalent'] = True
            return res
        # if explicit display required, require a name-like column
        if self.requires_display(query_text):
            # look for any planned column that contains 'name' or tokens
            for p in planned:
                if 'name' in p or 'title' in p or 'label' in p:
                    res['equivalent'] = True
                    res['reason'] = 'explicit_display_present'
                    return res
            res['reason'] = 'explicit_display_missing'
            return res
        # otherwise accept id substitutions
        for p in planned:
            if p.endswith(self.ID_SUFFIXES) or p == req:
                res['equivalent'] = True
                if p.endswith(self.ID_SUFFIXES) and p != req:
                    res['accepted_id_substitution'] = True
                    res['reason'] = 'id_substitution'
                else:
                    res['reason'] = 'direct_match'
                return res
        # fallback: token overlap
        req_tokens = re.sub(r'[^a-z0-9_]', '_', req).split('_')
        for p in planned:
            p_tokens = re.sub(r'[^a-z0-9_]', '_', p).split('_')
            if set(req_tokens) & set(p_tokens):
                res['equivalent'] = True
                res['reason'] = 'token_overlap'
                return res
        res['reason'] = 'no_match'
        return res

if __name__ == '__main__':
    d = DisplayColumnResolver()
    print(d.display_equivalent('client_name',['client_id'],'list clients'))
    print(d.display_equivalent('client_name',['client_id'],'display client name'))
