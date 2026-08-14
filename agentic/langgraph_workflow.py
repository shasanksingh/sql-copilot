from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowNode:
    key: str
    label: str
    role: str


class SQLCopilotWorkflow:
    """Describes and optionally compiles the SQL Copilot multi-agent workflow."""

    nodes = [
        WorkflowNode("intent_detection", "Intent Detection", "classify requested operation, filters, grouping, and time intent"),
        WorkflowNode("entity_extraction", "Entity Extraction", "normalize business terms and value filters"),
        WorkflowNode("schema_linking", "Schema Linking", "ground terms to tables and columns"),
        WorkflowNode("semantic_resolution", "Semantic Resolution", "resolve business rules, measures, dates, and display columns"),
        WorkflowNode("join_discovery", "Join Discovery", "select safe schema graph paths"),
        WorkflowNode("query_planning", "Query Planning", "build the deterministic query plan"),
        WorkflowNode("sql_generation", "SQL Generation", "generate deterministic SQL or reviewed NVIDIA candidate SQL"),
        WorkflowNode("sql_validation", "SQL Validation", "enforce read-only policy and schema validation"),
        WorkflowNode("coverage_audit", "Coverage Audit", "check intent, entity, column, join, aggregation, and semantic coverage"),
        WorkflowNode("confidence_scoring", "Confidence Scoring", "coordinate planner, validator, coverage, and model confidence"),
    ]
    edges = [
        ("intent_detection", "entity_extraction"),
        ("entity_extraction", "schema_linking"),
        ("schema_linking", "semantic_resolution"),
        ("semantic_resolution", "join_discovery"),
        ("join_discovery", "query_planning"),
        ("query_planning", "sql_generation"),
        ("sql_generation", "sql_validation"),
        ("sql_validation", "coverage_audit"),
        ("coverage_audit", "confidence_scoring"),
    ]

    def __init__(self) -> None:
        self.engine = "linear"
        self.available = False
        self.reason = ""
        self.compiled_graph: Any | None = None
        self._compile_langgraph()

    def _compile_langgraph(self) -> None:
        try:
            from langgraph.graph import END, StateGraph  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional package
            self.reason = f"langgraph unavailable: {exc.__class__.__name__}"
            return

        try:
            graph = StateGraph(dict)
            for node in self.nodes:
                graph.add_node(node.key, self._node_runner(node.key))
            graph.set_entry_point(self.nodes[0].key)
            for source, target in self.edges:
                graph.add_edge(source, target)
            graph.add_edge(self.nodes[-1].key, END)
            self.compiled_graph = graph.compile()
            self.engine = "langgraph"
            self.available = True
            self.reason = ""
        except Exception as exc:  # pragma: no cover - version compatibility guard
            self.compiled_graph = None
            self.engine = "linear"
            self.available = False
            self.reason = f"langgraph compile failed: {exc.__class__.__name__}"

    @staticmethod
    def _node_runner(name: str):
        def run(state: dict[str, Any]) -> dict[str, Any]:
            visited = list(state.get("visited_agents") or [])
            visited.append(name)
            return {**state, "visited_agents": visited}

        return run

    def describe(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "requested_engine": "langgraph",
            "available": self.available,
            "reason": self.reason,
            "nodes": [
                {"key": node.key, "label": node.label, "role": node.role}
                for node in self.nodes
            ],
            "edges": [
                {"from": source, "to": target}
                for source, target in self.edges
            ],
        }

    def invoke(self, *, query: str, request_id: str) -> dict[str, object]:
        state = {
            "query": query,
            "request_id": request_id,
            "visited_agents": [],
        }
        if self.compiled_graph is not None:
            try:
                result = dict(self.compiled_graph.invoke(state))
                return {
                    "engine": self.engine,
                    "visited_agents": list(result.get("visited_agents") or []),
                    "node_count": len(result.get("visited_agents") or []),
                    "status": "executed",
                }
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                return {
                    "engine": "linear",
                    "visited_agents": [node.key for node in self.nodes],
                    "node_count": len(self.nodes),
                    "status": "fallback",
                    "reason": f"langgraph invoke failed: {exc.__class__.__name__}",
                }
        return {
            "engine": "linear",
            "visited_agents": [node.key for node in self.nodes],
            "node_count": len(self.nodes),
            "status": "fallback",
            "reason": self.reason,
        }


def build_sql_copilot_workflow() -> SQLCopilotWorkflow:
    return SQLCopilotWorkflow()
