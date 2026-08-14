# Enterprise Query Planning

The production query path is planner-first:

```text
USER
-> intent gate
-> entity resolution
-> business vocabulary
-> schema retrieval and table ranking
-> schema graph
-> multi-hop join discovery
-> query plan IR
-> optional NVIDIA GPT-OSS-20B assist
-> SQL validator
-> coverage
-> confidence
-> clarification or response
```

The LLM never discovers the schema from scratch and cannot bypass the read-only policy.

## Join Graph

Tables are graph nodes and foreign keys are edges. `SchemaGraphEngine` supports BFS path candidates with configurable depth through `SQL_COPILOT_MAX_JOIN_DEPTH` and scores paths by:

- foreign-key path depth
- role-specific relationship matches such as `assigned_to`, `reported_by`, `created_by`, `approved_by`, `reviewed_by`, and `deployed_by`
- ambiguity penalties for parallel relationships when the query does not specify a role

The planner prefers the smallest graph that satisfies selected tables and dimensions, but does not hardcode a two-table or three-table limit.

## Plan Validation

Before optional LLM SQL generation, the plan is checked for:

- known tables
- known selected, grouped, filtered, and aggregated columns
- known relationships
- connected table graph

If validation fails, the model is skipped and the response is gated by deterministic validation and confidence.

## Dynamic Schema

Schema Studio changes rebuild metadata and reset the cached `EnterpriseSQLCopilot` instance. The refreshed graph, BM25/FAISS retrieval, table hints, default display columns, and relationship map become active without a backend restart.

