import pytest
from agentic.planner_agents import AggregationEquivalenceResolver

resolver = AggregationEquivalenceResolver()

@pytest.mark.parametrize("req,pl,expected", [
    ("COUNT(*)","COUNT(id)", True),
    ("COUNT(user_id)","COUNT(*)", True),
    ("SUM(amount)","SUM(invoice_amount)", True),
    ("SUM(revenue)","SUM(invoice_amount)", True),
    ("AVG(salary)","AVG(employee_salary)", True),
    ("MIN(date)","MIN(created_date)", True),
    ("MAX(date)","MAX(updated_date)", True),
    ("SUM(amount)","SUM(tax)", False),
    ("AVG(salary)","SUM(salary)", False),
    ("COUNT(*)","SUM(amount)", False),
])
def test_agg_equiv_basic(req, pl, expected):
    assert resolver.equivalent_aggregation(req, pl) == expected

# additional focused tests
def test_count_variants():
    assert resolver.equivalent_aggregation('COUNT(*)', 'COUNT( id )')
    assert resolver.equivalent_aggregation('COUNT(1)', 'COUNT(user_id)')

def test_sum_token_overlap_true():
    assert resolver.equivalent_aggregation('SUM(invoice_amount)', 'SUM(amount)')

def test_sum_token_overlap_false():
    assert not resolver.equivalent_aggregation('SUM(price)', 'SUM(quantity)')

def test_avg_equiv():
    assert resolver.equivalent_aggregation('AVG(salary)', 'AVG(employee_salary)')

def test_min_max_equiv():
    assert resolver.equivalent_aggregation('MIN(created_date)', 'MIN(date)')
    assert resolver.equivalent_aggregation('MAX(updated_at)', 'MAX(updated_date)')

def test_empty_strings():
    assert not resolver.equivalent_aggregation('', 'SUM(amount)')
    assert not resolver.equivalent_aggregation(None, None)

def test_synonym_map():
    assert resolver.equivalent_aggregation('SUM(revenue)', 'SUM(invoice_amount)')

def test_non_agg():
    assert not resolver.equivalent_aggregation('client_name', 'client_id')

def test_case_insensitivity():
    assert resolver.equivalent_aggregation('Sum(Amount)', 'sum(invoice_amount)')

def test_whitespace_tolerance():
    assert resolver.equivalent_aggregation('SUM( amount )', 'SUM(invoice_amount)')

def test_unusual_input():
    assert not resolver.equivalent_aggregation('AVG()', 'AVG()')

def test_partial_match():
    assert resolver.equivalent_aggregation('SUM(total_amount)', 'SUM(amount)')

def test_number_of_cases():
    # sanity: ensure many combinations do not crash
    cases = [
        ('SUM(a)','SUM(b)'),
        ('AVG(x)','AVG(y)'),
        ('COUNT(*)','COUNT(id)'),
        ('MIN(d1)','MIN(d2)'),
    ]
    for r,p in cases:
        _ = resolver.equivalent_aggregation(r,p)

# ensure at least 20 asserts via parametrization above plus these
