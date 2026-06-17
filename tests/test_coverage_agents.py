from agentic.coverage_agents import (
    IntentCoverageAgent,
    EntityCoverageAgent,
    ColumnCoverageAgent,
    JoinCoverageAgent,
    AggregationCoverageAgent,
    JoinPathCoverageAgent,
)
from agentic.enterprise_copilot import Intent, QueryPlan, SchemaRelationship, SchemaMatch, EntityExtraction


def make_plan_without_group():
    return QueryPlan(
        main_table="projects",
        selected_columns=[("projects", "budget")],
        joins=[],
        filters=[],
        aggregations=[],
        group_by=[],
        order_by=None,
        limit=None,
        confidence=50,
    )


def test_intent_coverage_group_missing():
    intent = Intent()
    intent.group_by = True
    intent.aggregations = []
    plan = make_plan_without_group()
    agent = IntentCoverageAgent()
    out = agent.evaluate(intent, plan)
    assert out["score"] < 50


def test_join_coverage_missing():
    matches = [SchemaMatch(kind="table", table="projects", column=None, score=90, reason="match") , SchemaMatch(kind="table", table="clients", column=None, score=80, reason="match")]
    plan = make_plan_without_group()
    agent = JoinCoverageAgent()
    out = agent.evaluate(matches, plan)
    assert out["score"] == 50 or out["score"] < 100


def test_column_coverage():
    matches = [SchemaMatch(kind="column", table="projects", column="budget", score=80, reason="col")] 
    plan = make_plan_without_group()
    agent = ColumnCoverageAgent()
    out = agent.evaluate(EntityExtraction([], [], [], [], [], [], []), matches, plan)
    assert out["score"] == 100


def test_column_coverage_does_not_require_inferred_identifier():
    matches = [
        SchemaMatch(kind="column", table="projects", column="project_id", score=90, reason="partial match"),
        SchemaMatch(kind="column", table="projects", column="project_name", score=90, reason="partial match"),
    ]
    entities = EntityExtraction(
        ["show", "all", "projects"],
        ["show", "all", "project"],
        [],
        [],
        [],
        [],
        [],
    )
    plan = QueryPlan(
        main_table="projects",
        selected_columns=[("projects", "project_name")],
        joins=[],
        filters=[],
        aggregations=[],
        group_by=[],
        order_by=None,
        limit=None,
        confidence=90,
    )

    out = ColumnCoverageAgent().evaluate(entities, matches, plan)

    assert out["score"] == 100
    assert out["required"] == []


def test_column_coverage_accepts_requested_aggregate_measure():
    matches = [
        SchemaMatch(kind="column", table="projects", column="budget", score=90, reason="explicit"),
    ]
    entities = EntityExtraction(
        ["project", "budget", "by", "client", "tier"],
        ["project", "budget", "by", "client", "tier"],
        [],
        [],
        ["budget"],
        [],
        [],
    )
    plan = QueryPlan(
        main_table="projects",
        selected_columns=[("clients", "tier")],
        joins=[SchemaRelationship("projects", "client_id", "clients", "client_id")],
        filters=[],
        aggregations=[{
            "function": "SUM",
            "table": "projects",
            "column": "budget",
            "alias": "total_budget",
        }],
        group_by=[("clients", "tier")],
        order_by=None,
        limit=None,
        confidence=95,
    )

    out = ColumnCoverageAgent().evaluate(entities, matches, plan)

    assert out["score"] == 100
    assert out["missing"] == []


def test_join_coverage_ignores_partial_bridge_table_match():
    matches = [
        SchemaMatch(kind="table", table="projects", column=None, score=100, reason="explicit"),
        SchemaMatch(kind="table", table="project_team", column=None, score=80, reason="partial match"),
    ]
    entities = EntityExtraction(
        ["show", "active", "projects"],
        ["show", "active", "project"],
        [],
        [],
        [],
        [],
        [],
    )
    plan = make_plan_without_group()

    out = JoinCoverageAgent().evaluate(matches, plan, entities)

    assert out["score"] == 100
    assert out["required_tables"] == ["projects"]
    assert out["missing"] == []


def test_join_path_coverage_audits_plan_not_retrieval_noise():
    matches = [
        SchemaMatch(kind="table", table="projects", column=None, score=100, reason="explicit"),
        SchemaMatch(kind="table", table="project_team", column=None, score=80, reason="partial match"),
    ]

    out = JoinPathCoverageAgent().evaluate(
        graph=None,
        plan=make_plan_without_group(),
        matches=matches,
        sql="SELECT p.budget FROM projects p;",
    )

    assert out["join_coverage_score"] == 100
    assert out["required_tables"] == ["projects"]
    assert out["missing_joins"] == []
