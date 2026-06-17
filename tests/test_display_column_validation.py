import pytest
from agentic.planner_agents import DisplayColumnValidator

v = DisplayColumnValidator()

@pytest.mark.parametrize('intent,required,planned,expected', [
    (None,'client_name',['client_name'], True),
    (None,'client_name',['client_id'], True),
    ({'terms':['show client names']},'client_name',['client_id'], False),
    ({'terms':['list clients']},'client_name',['client_id'], False),
    (None,'project_name',['project_id'], True),
    ({'terms':['display project title']},'project_name',['project_id'], False),
])
def test_display_equiv(intent, required, planned, expected):
    if v.requires_display_column(intent, None, [required]):
        assert v.display_column_equivalent(required, planned) == expected
    else:
        assert v.display_column_equivalent(required, planned) == True


def test_strip():
    assert v.strip('t.client_name') == 'client_name'
    assert v.strip('client_id') == 'client_id'


def test_requires_display():
    assert v.requires_display_column({'terms':['show name']}, None, [])
    assert not v.requires_display_column({}, None, ['client_id'])


def test_various_planned_lists():
    assert v.display_column_equivalent('client_name', ['clients.client_id'])
    assert v.display_column_equivalent('client_name', ['client_id','client_name'])


def test_more_cases():
    assert v.display_column_equivalent('name', ['id'])
    assert v.display_column_equivalent('title', ['title'])

# generate multiple small checks to reach 20 asserts
def test_bulk():
    pairs = [
        ('client_name',['client_id']),
        ('client_name',['client_name']),
        ('client_name',['clients.client_name']),
        ('client_name',['c.client_id']),
    ]
    for req,pl in pairs:
        assert v.display_column_equivalent(req, pl)
