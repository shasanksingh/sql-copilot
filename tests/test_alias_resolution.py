import pytest
from agentic.planner_agents import CanonicalColumnResolver

resolver = CanonicalColumnResolver()

@pytest.mark.parametrize('inp,expected', [
    ('c.client_name','client'),
    ('client_name','client'),
    ('clients.client_name','client'),
    ('p.project_name','project'),
    ('project_name','project'),
    ('projects.project_name','project'),
    ('invoice_amount','amount'),
    ('total','amount'),
    ('revenue','amount'),
    ('sales_amount','amount'),
])
def test_canonical_basic(inp, expected):
    assert resolver.canonical_name(inp) == expected


def test_strip_alias():
    assert resolver.strip_alias('tbl.col') == 'col'
    assert resolver.strip_alias('col') == 'col'


def test_plural_singular():
    assert resolver.canonical_name('clients') == 'client'
    assert resolver.canonical_name('projects') == 'project'


def test_punctuation_and_case():
    assert resolver.canonical_name('Clients.Client-Name') == 'client'


def test_unknown_column():
    assert resolver.canonical_name('weird_field') == 'weird_field'


def test_various():
    assert resolver.canonical_name('Invoice_Amount') == 'amount'
    assert resolver.canonical_name('sales') == 'sale'

# additional sanity checks
def test_many():
    inputs = ['a.b','A_B','customer_id','customer_name','Customer']
    for i in inputs:
        _ = resolver.canonical_name(i)
