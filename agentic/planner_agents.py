from __future__ import annotations

from typing import Any, List, Set, Tuple
from dataclasses import asdict
import json
import re
from agentic.aggregation_semantic import AggregationSemanticResolver
from agentic.display_resolver import DisplayColumnResolver


# --- Helper resolvers (high-impact relaxations) ---
class AggregationEquivalenceResolver:
    SYNONYM_MAP = {
        'total': {'amount', 'invoice_amount', 'sales_amount', 'revenue', 'record_count', 'sum'},
        'revenue': {'invoice_amount', 'amount'},
        'sales': {'sale', 'sales_amount', 'amount'},
        'salary': {'employee_salary', 'annual_salary', 'wage'},
        'budget': {'project_budget', 'allocated_budget'},
        'date': {'date', 'created_date', 'updated_date', 'created_at', 'updated_at'},
    }

    @staticmethod
    def _extract_col_in_agg(expr: str) -> str:
        if not expr:
            return ''
        low = expr.lower()
        if '(' in low and ')' in low:
            inner = low[low.find('(')+1:low.rfind(')')]
            return inner.strip()
        return low

    def normalize_aggregation(self, agg_expr: str) -> str:
        # produce normalized string like 'sum:amount' or 'count:*'
        if not agg_expr:
            return ''
        a = agg_expr.lower()
        inner = self._extract_col_in_agg(a)
        if '(' in a and ')' in a and inner == '':
            return ''
        if re.search(r"\bcount\s*\(", a):
            return 'count:*'
        if re.search(r"\bsum\s*\(", a):
            return 'sum:' + inner
        if re.search(r"\bavg\s*\(", a):
            return 'avg:' + inner
        if re.search(r"\bmin\s*\(", a):
            return 'min:' + inner
        if re.search(r"\bmax\s*\(", a):
            return 'max:' + inner
        return a

    def equivalent_aggregation(self, required: str, planned: str) -> bool:
        # permissive equivalence rules
        if not required or not planned:
            return False
        rnorm = self.normalize_aggregation(required)
        pnorm = self.normalize_aggregation(planned)
        if not rnorm or not pnorm:
            return False
        if rnorm == pnorm:
            return True
        # COUNT equivalence
        if rnorm.startswith('count') and pnorm.startswith('count'):
            return True
        # SUM/AVG/MIN/MAX token overlap or synonym match
        for func in ('sum','avg','min','max'):
            if rnorm.startswith(func) and pnorm.startswith(func):
                rcol = rnorm.split(':',1)[1] if ':' in rnorm else rnorm
                pcol = pnorm.split(':',1)[1] if ':' in pnorm else pnorm
                # direct token overlap
                if rcol and pcol and (rcol == pcol or rcol in pcol or pcol in rcol):
                    return True
                # synonym map
                for syn, variants in self.SYNONYM_MAP.items():
                    if rcol and (rcol == syn or rcol in variants) and pcol and (pcol == syn or pcol in variants):
                        return True
                rtokens = set(rcol.replace('_', ' ').split())
                ptokens = set(pcol.replace('_', ' ').split())
                if rtokens and ptokens:
                    for variants in self.SYNONYM_MAP.values():
                        if (rtokens & variants) and (ptokens & variants):
                            return True
        return False


class CanonicalColumnResolver:
    SYNONYMS = {
        'client': {'client','customer','client_name','customer_name','client_id','customer_id'},
        'project': {'project','project_name','project_id'},
        'employee': {'employee','staff','employee_name','full_name','employee_id','staff_id'},
        'department': {'department','division','department_name','division_name','department_id','division_id'},
        'vendor': {'vendor','supplier','vendor_name','supplier_name','vendor_id','supplier_id'},
        'product': {'product','item','product_name','item_name','product_id','item_id'},
        'amount': {'amount','total','revenue','invoice_amount','sales_amount','total_amount'},
        'salary': {'salary','employee_salary','annual_salary','wage'},
        'budget': {'budget','project_budget','allocated_budget'},
    }

    @staticmethod
    def strip_alias(col: str) -> str:
        if not col:
            return ''
        if '.' in col:
            return col.split('.')[-1]
        return col

    @staticmethod
    def strip_table_prefix(col: str) -> str:
        return CanonicalColumnResolver.strip_alias(col)

    def canonical_name(self, col: str) -> str:
        if not col:
            return ''
        c = self.strip_table_prefix(col).lower()
        # remove common punctuation
        c = ''.join([ch if ch.isalnum() or ch=='_' else '_' for ch in c])
        c = re.sub(r"_+", "_", c).strip("_")
        # singularize simple plurals
        if c.endswith('s') and len(c) > 3:
            c = c[:-1]
        # map synonyms
        for key, variants in self.SYNONYMS.items():
            if c == key or c in variants:
                return key
        for suffix in ('_name', '_title', '_label', '_id'):
            if c.endswith(suffix) and len(c) > len(suffix):
                base = c[:-len(suffix)]
                if base.endswith('s') and len(base) > 3:
                    base = base[:-1]
                for key, variants in self.SYNONYMS.items():
                    if base == key or base in variants:
                        return key
        return c


class DisplayColumnValidator:
    DISPLAY_TOKENS = {'name','display','list','title','label'}
    def __init__(self):
        self._last_display_required = False

    def requires_display_column(self, intent: dict | None, entities: dict | None, required_columns: list) -> bool:
        explicit = False
        # intent check
        if intent:
            # intent may include explicit tokens
            for t in (intent.get('terms') or []) + (intent.get('canonical_terms') or []):
                if t and any(tok in t.lower() for tok in self.DISPLAY_TOKENS):
                    explicit = True
                    break
        # check entities or required_columns for explicit display requests
        if not explicit and entities:
            for term in (entities.get('canonical_terms') or []):
                if term and any(tok in term.lower() for tok in self.DISPLAY_TOKENS):
                    explicit = True
                    break
        self._last_display_required = explicit
        return explicit

    def display_column_equivalent(self, required_col: str, planned_cols: list, explicit_display: bool | None = None) -> bool:
        # accept id if no explicit display required (handled at caller)
        req = required_col.lower()
        planned_canon = [self.strip(pl).lower() for pl in (planned_cols or [])]
        display_required = self._last_display_required if explicit_display is None else explicit_display
        self._last_display_required = False
        if display_required:
            if req.endswith('_id') or req == 'id':
                return any(pc == req or pc.endswith('_id') or pc == 'id' for pc in planned_canon)
            return any(
                pc == req
                or 'name' in pc
                or 'title' in pc
                or 'label' in pc
                or 'display' in pc
                for pc in planned_canon
            )
        # if required is a name but planned has id, consider equivalent in non-explicit-display mode
        if req.endswith('_id') or req.endswith('id'):
            # id satisfies itself
            return any(self.strip(pl).lower().endswith('id') for pl in (planned_cols or []))
        if any(pc == req for pc in planned_canon):
            return True
        # id alternative
        if any(pc.endswith('id') for pc in planned_canon):
            return True
        return False

    @staticmethod
    def strip(col: str) -> str:
        if not col:
            return ''
        if '.' in col:
            return col.split('.')[-1]
        return col

# --- end helpers ---

class TableSelectionAgent:
    def select_tables(self, intent: Any, entities: Any, matches: list, graph: Any) -> dict:
        # select any table matched explicitly or with moderate score
        selected = set()
        reasons = {}
        for m in matches:
            try:
                if getattr(m, 'kind', '') == 'table' or getattr(m, 'score', 0) >= 50:
                    selected.add(m.table)
                    reasons.setdefault(m.table, []).append(f'match:{getattr(m,"score",0)}')
                elif getattr(m, 'kind', '') == 'column' and getattr(m, 'score', 0) >= 70:
                    selected.add(m.table)
                    reasons.setdefault(m.table, []).append('column_high_score')
            except Exception:
                continue

        # include entity-derived tables (best-effort)
        try:
            for term in getattr(entities, 'canonical_terms', []) or []:
                for m in matches:
                    if m.table and term in m.table:
                        selected.add(m.table)
                        reasons.setdefault(m.table, []).append('entity_term')
        except Exception:
            pass

        return {'selected_tables': sorted(selected), 'confidence': 90.0, 'reason': reasons}


class JoinPlanningAgent:
    def plan_joins(self, main_table: str, selected_tables: Set[str], graph: Any) -> list:
        joins = []
        added = set([main_table])
        for tbl in sorted(selected_tables):
            if tbl in added:
                continue
            path = graph.shortest_join_path(main_table, tbl)
            for rel in path:
                # avoid duplicates by (from,to)
                key = (rel.from_table, rel.to_table, rel.from_column, rel.to_column)
                if rel.to_table not in added or rel.from_table not in added:
                    joins.append(rel)
                    added.add(rel.from_table)
                    added.add(rel.to_table)
        return joins


class AggregationPlanningAgent:
    def plan_aggregations(self, intent: Any, graph: Any, main_table: str, matches: list) -> dict:
        aggs = []
        group_by = []
        order_by = None
        limit = intent.limit if getattr(intent, 'limit', None) else None
        if getattr(intent, 'aggregations', None):
            for a in intent.aggregations:
                aggs.append(a)
        if intent.group_by:
            # pick a sensible group column on main_table
            for candidate in ('region','department','project_name','customer_name'):
                if candidate in getattr(graph, 'columns', {}).get(main_table, set()):
                    group_by.append((main_table, candidate))
                    break
        return {'aggregations': aggs, 'group_by': group_by, 'order_by': order_by, 'limit': limit}


class EntityResolutionAgent:
    def resolve(self, entities: Any, matches: list, graph: Any, labels: dict, column_order: dict) -> list:
        mappings = []
        for term in getattr(entities, 'canonical_terms', []) or []:
            mapped = None
            for m in matches:
                if getattr(m, 'column', None) and term in (m.column or ''):
                    mapped = (m.table, m.column, 95.0)
                    break
            if not mapped:
                # fallback: prefer readable label on matched table
                for m in matches:
                    t = m.table
                    label = labels.get(t)
                    if label and label in (graph.columns.get(t, set())):
                        mapped = (t, label, 70.0)
                        break
            if mapped:
                mappings.append({'entity': term, 'mapped_column': f"{mapped[0]}.{mapped[1]}", 'confidence': mapped[2]})
        return mappings


class PlannerValidationAgent:
    """Validate planner outputs with intent- and alias-aware rules.

    Backwards compatible: previous callers may pass only the original positional
    arguments. Newer callers can provide `intent`, `entity_mappings` and
    `alias_map` to improve matching.
    """
    CRITICAL_COLUMNS = {'client_name', 'project_name', 'department_name'}
    IMPORTANT_COLUMNS = {'budget', 'revenue', 'salary'}
    OPTIONAL_COLUMN_SUFFIXES = ('_id', 'id', '_ts', 'timestamp', '_at')

    def __init__(self):
        self.aggregation_resolver = AggregationSemanticResolver()
        self.display_resolver = DisplayColumnResolver()

    def _normalize(self, col: str) -> str:
        # strip table aliases/tags, lower-case
        if not col:
            return ''
        if '.' in col:
            col = col.split('.')[-1]
        return col.lower()

    def _canonical(self, col: str) -> str:
        # stronger canonicalization: strip table/alias, snake->words, drop plural 's'
        n = self._normalize(col)
        # remove trailing plural s for simple normalization (clients -> client)
        if n.endswith('s') and len(n) > 3:
            n = n[:-1]
        return n

    def _is_optional(self, col: str) -> bool:
        n = col.lower()
        for s in self.OPTIONAL_COLUMN_SUFFIXES:
            if n.endswith(s):
                return True
        return n.startswith('meta') or n in ('created', 'updated')

    def _agg_equivalent(self, required: str, planned: str) -> bool:
        # Use AggregationEquivalenceResolver for permissive equivalence
        try:
            resolver = AggregationEquivalenceResolver()
            return resolver.equivalent_aggregation(required, planned)
        except Exception:
            # fallback to previous behavior
            r = required.lower() if required else ''
            p = planned.lower() if planned else ''
            if 'count' in r and 'count' in p:
                return True
            if r.startswith('sum') and p.startswith('sum'):
                rcol = r[r.find('(')+1:r.rfind(')')]
                pcol = p[p.find('(')+1:p.rfind(')')]
                rtok = set(rcol.replace('_',' ').split())
                ptok = set(pcol.replace('_',' ').split())
                return len(rtok & ptok) > 0
            if r.startswith('avg') and p.startswith('avg'):
                rcol = r[r.find('(')+1:r.rfind(')')]
                pcol = p[p.find('(')+1:p.rfind(')')]
                rtok = set(rcol.replace('_',' ').split())
                ptok = set(pcol.replace('_',' ').split())
                return len(rtok & ptok) > 0
            return self._canonical(required) == self._canonical(planned)

    def validate(self, required_tables: list, required_columns: list, required_aggs: list, planned_tables: list, planned_columns: list, planned_aggs: list, intent: dict | None = None, alias_map: dict | None = None, entity_mappings: list | None = None) -> dict:
        # Normalize sets
        planned_tables = planned_tables or []
        planned_columns = planned_columns or []
        planned_aggs = planned_aggs or []
        required_tables = required_tables or []
        required_columns = required_columns or []
        required_aggs = required_aggs or []

        # alias-aware mapping: create canonical set of planned columns
        planned_plain = {self._canonical(c): c for c in planned_columns}
        planned_norm_set = set(planned_plain.keys())

        # resolvers
        agg_resolver = AggregationEquivalenceResolver()
        col_resolver = CanonicalColumnResolver()
        display_validator = DisplayColumnValidator()

        diagnostics = {
            'rule_triggered': [],
            'equivalent_matches': [],
            'ignored_requirements': [],
            'validation_reason': ''
        }

        missing_tables = sorted(set(required_tables) - set(planned_tables)) if required_tables else []

        # Column matching with importance scoring and alias-awareness
        missing_columns = []
        for rc in required_columns:
            rnorm = col_resolver.canonical_name(rc)
            matched = False
            # direct match
            if rnorm in planned_norm_set:
                matched = True
            else:
                # try alias_map if provided (map unprefixed -> existing)
                if alias_map:
                    # rc may be 'c.client_name' or 'client_name'
                    if rc in alias_map and col_resolver.canonical_name(alias_map[rc]) in planned_norm_set:
                        matched = True
                # try entity mappings (synonyms)
                if not matched and entity_mappings:
                    for m in entity_mappings:
                        mapped = m.get('mapped_column') if isinstance(m, dict) else None
                        if mapped and col_resolver.canonical_name(mapped) == rnorm and col_resolver.canonical_name(mapped) in planned_norm_set:
                            matched = True
                            break
                # try fuzzy token overlap
                if not matched:
                    for pcanon in planned_norm_set:
                        if rnorm == pcanon:
                            matched = True
                            break
                        if rnorm in pcanon or pcanon in rnorm:
                            matched = True
                            break
            if not matched:
                # if column is optional, do not count as missing
                if self._is_optional(rc):
                    diagnostics['ignored_requirements'].append(rc)
                    continue
                # if this is a display query and rc is an id/optional, skip
                if intent and (not intent.get('aggregations')) and self._is_optional(rc):
                    continue
                # if display requested, allow id substitution
                if display_validator.requires_display_column(intent, {'mappings': entity_mappings} if entity_mappings else None, required_columns):
                    # require explicit non-id; do not mark as ignored
                    missing_columns.append(rc)
                else:
                    # allow id/name substitutions: if planned has id for required name, treat as matched
                    planned_names = planned_columns or []
                    if display_validator.display_column_equivalent(rc, planned_names):
                        diagnostics['equivalent_matches'].append({'rule': 'display_equiv', 'required': rc, 'planned': planned_names})
                    else:
                        missing_columns.append(rc)

        # Aggregation matching: use semantic resolver for permissive equivalence
        missing_aggs = []
        agg_equiv_count = 0
        for ra in required_aggs:
            matched = False
            for pa in planned_aggs:
                if self.aggregation_resolver.equivalent_measure(ra, pa):
                    matched = True
                    agg_equiv_count += 1
                    diagnostics['equivalent_matches'].append({'rule': 'agg_equiv', 'required': ra, 'planned': pa})
                    break
            if not matched:
                missing_aggs.append(ra)

        # intent-aware relaxations: make display columns optional unless explicitly requested
        if intent:
            if not intent.get('aggregations'):
                # if user explicitly requested readable column names (e.g., 'show client names') then require them
                explicit_display = False
                # simple heuristic: intent object may include a 'display' flag or canonical terms exist on caller side; fallback check on required_columns
                for rc in required_columns:
                    if self._canonical(rc) in self.CRITICAL_COLUMNS:
                        explicit_display = True
                        break
                if not explicit_display:
                    # drop id/optional columns from missing set and record them as ignored
                    new_missing = []
                    for c in missing_columns:
                        if self._is_optional(c):
                            diagnostics['ignored_requirements'].append(c)
                        else:
                            new_missing.append(c)
                    missing_columns = new_missing

        # Planner-aware validation: do not invent extra requirements. If required_* is empty, validate only planner outputs (pass).
        if not required_tables and not required_columns and not required_aggs:
            valid = True
        else:
            valid = not (missing_tables or missing_columns or missing_aggs)

        # Diagnostics: write per-query validator log (enhanced)
        try:
            import os, hashlib
            os.makedirs('logs/validator', exist_ok=True)
            # create short filename by hashing planned columns + query signature if available
            sig = '|'.join(sorted(planned_columns or [])) + '::' + '|'.join(sorted(planned_tables or []))
            h = hashlib.sha1(sig.encode('utf-8')).hexdigest()[:10]
            fname = os.path.join('logs/validator', f'validator_{h}.json')
            with open(fname, 'w', encoding='utf-8') as vf:
                log_obj = {
                    'planned_tables': planned_tables,
                    'planned_columns': planned_columns,
                    'required_tables': required_tables,
                    'required_columns': required_columns,
                    'planned_aggs': planned_aggs,
                    'required_aggs': required_aggs,
                    'validation': {
                        'valid': valid,
                        'missing_tables': missing_tables,
                        'missing_columns': missing_columns,
                        'missing_aggregations': missing_aggs
                    },
                    'diagnostics': diagnostics,
                    'equivalence_applied': {'agg_equiv': True},
                    'intent': intent,
                }
                json.dump(log_obj, vf, indent=2)
        except Exception:
            pass

        return {
            'valid': valid,
            'missing_tables': sorted(missing_tables),
            'missing_columns': sorted(missing_columns),
            'missing_aggregations': sorted(missing_aggs),
        }
