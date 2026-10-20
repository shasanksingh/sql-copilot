# Multi-Agent SQL Copilot — Interview Questionnaire and Answer Guide

This guide is based on the implementation in `EnterpriseSQLCopilot`. It is designed for a system-design interview: explain the outcome first, then draw the pipeline and go deeper only when asked.

## 1. One-minute project pitch

"I built an enterprise text-to-SQL Copilot. A user asks a business question in natural language; the system grounds it in a governed schema, creates a structured query plan, optionally uses an LLM for complex cases, and returns SQL only after deterministic validation and confidence checks. The key design choice is planner-first: the LLM is an assistant inside the safety boundary, not the source of truth. The system is read-only, explainable, cached, and degrades to deterministic SQL if the provider fails."

## 2. Architecture at a glance

```text
Next.js client
  -> Flask ASGI API: authentication, CSRF, rate limits, telemetry
  -> Query cache
  -> Agentic SQL engine
       intent -> entities -> schema retrieval/linking -> semantic resolution
       -> join graph -> query plan -> optional LLM -> validator
       -> coverage -> confidence -> response/clarification
  -> Knowledge/data: schema workbook + dynamic schema + Spider examples + SQLite
  -> Optional model providers: NVIDIA GPT-OSS, OpenAI-compatible, Ollama, local fallback
```

The frontend is Next.js/React. The backend is Flask served through ASGI. The active enterprise schema is loaded from `backend/data/RAG_DOC.xlsx`, overlaid by approved live schema changes. The planner works with a relationship graph constructed from known foreign keys. SQLite holds local auth, sessions, telemetry, feedback, cache, and schema-governance data.

## 3. The seven interview stages

Use this grouped version when an interviewer asks for the “seven stages.” It is easier to communicate than the finer-grained code workflow.

| Stage | What happens | Why it comes here |
| --- | --- | --- |
| 1. Request gate | Authenticate request, normalize the question, check cache, classify SQL vs generic question vs clarification. | Reject/short-circuit cheaply before retrieval or LLM usage. |
| 2. Understand intent | Extract operation, metric, dimensions, filters, time range, grouping, ordering, and limit. | Later agents need a structured specification, not raw language. |
| 3. Ground in schema (RAG) | Resolve business vocabulary and retrieve/rank relevant tables, columns, descriptions, and examples. | Prevents invented tables/columns and sends small, relevant context downstream. |
| 4. Build a plan | Resolve business semantics, select tables/columns, find a safe multi-hop join path, and create query-plan IR. | SQL is generated from an inspectable plan rather than guessed directly. |
| 5. Generate or improve SQL | Deterministic renderer produces a candidate; for complex/enterprise queries, a bounded LLM may review, generate, critique, or repair it. | Model capability is used only where it adds value, with an allowed-schema payload. |
| 6. Verify | Parse and validate SQL, enforce one `SELECT`, verify tables/columns, run semantic coverage checks, and calculate evidence-based confidence. | A syntactically plausible answer is not enough; it must satisfy the requested meaning and policy. |
| 7. Decide and explain | Return accepted SQL with plan/trace/confidence, or ask a targeted clarification; cache eligible good results and emit telemetry. | Avoids hallucinating when uncertainty is material and makes decisions auditable. |

### Exact implementation view

The code exposes ten LangGraph/linear nodes: `intent_detection`, `entity_extraction`, `schema_linking`, `semantic_resolution`, `join_discovery`, `query_planning`, `sql_generation`, `sql_validation`, `coverage_audit`, and `confidence_scoring`. The seven-stage version above groups adjacent implementation nodes for an interview explanation; it does not replace them.

## 4. Why the agent order is deliberate

**Question: How does the system decide which agent runs first?**

**Answer:** It uses dependency ordering, not an LLM deciding freely at runtime. Each agent consumes evidence produced by prior agents. Intent detection must precede entity extraction because it tells us whether the request is a count, aggregate, detail list, or clarification. Entity/schema linking must precede join discovery because we cannot find a valid path until we know the relevant tables. Join discovery must precede planning because joins are part of the plan. Plan validation must precede an LLM call because the model is never allowed to reason over an ungrounded or invalid schema plan. Validation and coverage must follow generation because they evaluate the candidate SQL.

**Question: Why not let a manager LLM dynamically choose agents?**

**Answer:** Dynamic routing is useful for open-ended work, but text-to-SQL has hard dependencies and high correctness/safety requirements. A deterministic state machine is cheaper, reproducible, observable, and easier to test. Conditional branches still exist: cache hit, out-of-schema guidance, early clarification, provider availability, and complexity-based LLM escalation.

**Question: What is the orchestrator?**

**Answer:** `EnterpriseSQLCopilot` coordinates the actual pipeline. `SQLCopilotWorkflow` declares the ordered LangGraph nodes and compiles to LangGraph when available; it has a linear fallback so the product remains usable if that optional dependency is unavailable.

**Question: Is this really multi-agent or just a pipeline?**

**Answer:** It is a specialized multi-agent pipeline. Each agent has a narrow responsibility and an explicit contract—intent, entity resolution, schema linking, join discovery, planning, validation, coverage, and confidence. The ordering is largely sequential because semantic dependencies make that correct. “Multi-agent” should not mean multiple autonomous LLMs talking to each other; specialization, explicit state, gates, and recoverability are the important properties.

## 5. RAG and LLM design questions

**Question: Why use RAG instead of an LLM alone?**

**Answer:** The enterprise schema and business definitions are external, changing knowledge. An LLM alone may know SQL but does not know that this organization’s `invoices.amount` represents booked revenue, how `clients` connect to `projects`, or which columns are approved. RAG retrieves the current, relevant schema descriptions, table/column metadata, relationships, and SQL patterns. That improves grounding, reduces hallucination, cuts prompt size, permits live updates without retraining, and gives evidence for the answer.

**Question: Why not fine-tune?**

**Answer:** Fine-tuning can help style or recurring domain patterns, but it is a poor primary source of schema truth: schemas change frequently, governance requires fast updates, and fine-tuned model weights are hard to audit. This design makes metadata retrieval and deterministic checks authoritative. Fine-tuning could be an additional optimization after enough curated feedback exists.

**Question: What does RAG retrieve in this project?**

**Answer:** The primary corpus is a workbook containing table names, columns, datatypes, table purpose, and descriptions. Dynamic schema overlay entries are incorporated after approval. The system uses BM25 immediately and FAISS when embeddings are configured. A Spider text-to-SQL corpus is used for generic, out-of-schema SQL guidance; it must not be presented as validated enterprise SQL.

**Question: Why BM25 plus FAISS?**

**Answer:** BM25 is fast, transparent, and strong for exact identifiers such as `invoice_date`. Vector search helps with semantic variants such as “customer segment” versus `client_tier`. Hybrid retrieval gives lexical precision and semantic recall. Retrieval only narrows candidates; validators remain authoritative.

**Question: How do you prevent RAG from retrieving the wrong schema?**

**Answer:** Retrieve and rank candidates, then schema-link terms to known objects, validate all plan references, verify graph connectivity, and use confidence/clarification for ambiguity. Retrieval is evidence, not permission. If “status” matches multiple tables without sufficient context, the system asks a question rather than selecting one silently.

**Question: What happens for an out-of-schema question?**

**Answer:** It is classified separately. The product can offer generic read-only SQL guidance based on Spider examples, clearly labeled as generic and not validated against the enterprise schema. For an in-schema request with weak mapping, it asks a clarification instead of pretending generic SQL is enterprise-ready.

## 6. Planner, graph, and SQL-generation questions

**Question: What is the query-plan IR?**

**Answer:** It is a structured intermediate representation containing the main table, selected columns, filters, aggregations, grouping, ordering, limit, required joins, unresolved concepts, ambiguities, and a planner confidence score. It decouples natural-language interpretation from SQL syntax and makes validation/explanation possible.

**Question: How are joins chosen?**

**Answer:** Tables are nodes and foreign-key relationships are edges. The join agent uses BFS-based candidate paths with configurable maximum depth. It scores candidates using path depth and role-specific relationship hints, while penalizing ambiguous parallel relationships when the user did not specify the role. It favors the smallest connected graph that satisfies the requested tables but does not hardcode a join-count limit.

**Question: Give an example.**

**Answer:** For “monthly invoice revenue by client tier for paid invoices,” the planner resolves revenue to `SUM(invoices.amount)`, month to `invoices.invoice_date`, tier to `clients.tier`, and paid to `invoices.status = 'paid'`. It derives `clients -> projects -> invoices` from the schema graph, then produces a grouped, dated aggregate query.

**Question: Why not generate SQL directly from retrieved context?**

**Answer:** Direct generation collapses interpretation, join selection, and SQL syntax into one untestable step. The plan provides a contract: a candidate can be rejected if it introduces an unknown table, misses a requested grouping, or violates the selected join path. It also enables a deterministic SQL fallback.

**Question: How do business terms get resolved?**

**Answer:** A vocabulary layer canonicalizes user language and planner hints map terms to sanctioned tables/columns. Specialized semantic resolvers handle measures, date ranges, display columns, aggregations, and domain rules. An unresolved term—such as compensation when no salary field exists—reduces confidence and produces a clarification rather than an invented column.

**Question: How do you handle ambiguity?**

**Answer:** Ambiguity is a first-class result. The schema linker records ambiguous matches and unresolved concepts. The confidence coordinator applies penalties; below the configured threshold the system asks a targeted clarification, for example, which table’s `status` the user means. This is safer than choosing the most common match.

## 7. Why the LLM is optional and bounded

**Question: Where does the LLM fit?**

**Answer:** It is optional after deterministic intent detection, schema linking, join discovery, plan construction, and plan validation. For complex or enterprise queries it may review the plan, generate a candidate SQL/JSON response, critique an accepted candidate, or repair a failed candidate. It sees bounded payload: user request, validated plan, allowed schema, deterministic candidate, and validation feedback.

**Question: Why is LLM output not trusted directly?**

**Answer:** Model output is probabilistic. A confident-looking query can use a nonexistent column, wrong join cardinality, or unsafe statement. The system requires structured JSON, parses it, checks plan alignment, runs read-only/schema validation, audits semantic coverage, and applies a non-model confidence gate. The model’s self-reported confidence is advisory only.

**Question: How is a malformed LLM answer handled?**

**Answer:** The provider attempts JSON extraction and has a bounded structured-JSON repair path. If it still fails—or the provider times out, rate-limits, returns unavailable, or returns invalid SQL—the system records the error category and falls back to deterministic generation rather than failing the request.

**Question: How does the system avoid infinite repair loops?**

**Answer:** Retries are explicitly bounded by `MAX_GENERATION_RETRIES`. Each repair receives the exact validator and planner-alignment failures so it is targeted. After the budget is exhausted, deterministic fallback or clarification is used.

**Question: When would you skip the LLM?**

**Answer:** On cache hits; early clarification; invalid plans; simple patterns that deterministic rendering handles well; absent/unhealthy provider; and cases where the LLM feature flag is off. Complex and enterprise queries are the primary escalation path because that is where plan review/critique has the best quality-to-cost trade-off.

## 8. Cost optimization questions

**Question: How are you optimizing LLM API cost?**

**Answer:** First, we avoid calls rather than merely making calls cheaper:

- Query cache checks occur before expensive stages; cache keys are normalized and namespaced by cache version/provider/model state.
- Deterministic intent, linking, planning, and SQL rendering resolve many requests without an LLM.
- The remote call occurs only after a valid plan exists and primarily for `COMPLEX`/`ENTERPRISE` queries.
- Hybrid retrieval sends only ranked, relevant schema context—not the full database workbook.
- Structured JSON reduces conversational back-and-forth and limits parsing ambiguity.
- Model temperature, top-p, output-token cap, timeout, and retry budget are configurable.
- Failures are not cached as successful LLM responses; fallback results are kept separate from healthy provider results.
- Failure cooldown can temporarily stop calls to an unhealthy provider, avoiding repeated paid/time-consuming failures.
- The frontend shares the active copilot result across Planner, Optimizer, Explainability, and Execution views instead of generating again.

**Question: How would you measure cost savings?**

**Answer:** Track request count, provider-invocation rate, input/output tokens, cost per provider/model, cache-hit rate, repair rate, fallback rate, and cost per accepted high-confidence query. Compare a baseline “LLM on every request with full schema” with the gated system in an A/B or offline benchmark. Monitor quality simultaneously: valid SQL rate, semantic coverage, clarification rate, user acceptance, p95 latency, and false acceptance rate.

**Question: What is a good cache key?**

**Answer:** This implementation normalizes exact natural-language input and namespaces it by cache version and provider identity/state. In a production upgrade, include schema version, tenant/user authorization scope, SQL dialect, business-rule version, model/provider version, and prompt/template version. Do not share cached SQL across tenants or permissions without a guaranteed identical data-access policy.

**Question: What is a cache risk?**

**Answer:** Stale or unauthorized answers. Invalidate/bust on schema, vocabulary, policy, or prompt changes; give entries TTLs; namespace by tenant/role; cache only validated high-confidence responses; and never cache an answer produced during a failed remote-provider fallback as if it were a provider success.

**Question: Why not call a small model for every routing task?**

**Answer:** Regex/rules, retrieval scores, graph traversal, and deterministic classifiers are faster, cheaper, testable, and more reliable for known structured tasks. Use an LLM for ambiguity and semantic reasoning where it materially improves outcomes, not for tasks software already performs well.

## 9. Safety, validation, and confidence questions

**Question: What does validation enforce?**

**Answer:** The API accepts one read-only `SELECT` statement only. It rejects empty SQL, non-`SELECT` starts, multiple statements, write/DDL/privilege operations such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `GRANT`, and `REVOKE`, unknown tables, unknown columns, wildcard `SELECT *`, ambiguous unqualified columns, and parse errors when `sqlglot` is available.

**Question: Is validation enough to make execution safe?**

**Answer:** No. Syntax/read-only validation is necessary but not sufficient. Production should use a database account with least privilege, a read-only replica or governed warehouse, query timeout/cost limits, row-level security, allowlisted datasets, result-size caps, query logging, and human approval for sensitive data. This project intentionally provides preview/export rather than arbitrary database execution.

**Question: How is confidence calculated?**

**Answer:** It is evidence-based weighted scoring, not model self-confidence. Default weights are intent 25%, entity 20%, column 15%, join 15%, aggregation 10%, semantic coverage 10%, and validation 5%. Invalid SQL, unresolved concepts, ambiguities, low entity/column/join/semantic scores, missing display columns, and incomplete join paths apply penalties. The configuration supports weight overrides.

**Question: What happens at each confidence band?**

**Answer:** Defaults are HIGH 90–100: return normally; MEDIUM 75–89: return with visible context; LOW 0–74: ask for clarification or refuse unsafe output. Thresholds are configurable with `CONFIDENCE_LOW_THRESHOLD` and `CONFIDENCE_HIGH_THRESHOLD`.

**Question: Why do coverage checks exist after SQL validation?**

**Answer:** A query can be legal and schema-valid but semantically incomplete. Example: “revenue by client tier for paid invoices” might omit the `paid` filter or the client-tier grouping. Coverage verifies requested entities, display columns, filters, groups, aggregates, join needs, and semantics survive from plan to SQL.

## 10. Reliability, scaling, and operational questions

**Question: What if NVIDIA/OpenAI/Ollama is down?**

**Answer:** Provider errors are categorized (for example rate limit, configuration, network, timeout, invalid JSON). The system falls back to deterministic SQL where safe, reports provider/fallback status, and may apply cooldown before retrying the provider. The product does not fail startup just because an optional remote provider is unavailable.

**Question: How do you make this horizontally scalable?**

**Answer:** Keep API workers stateless, move SQLite state to a shared transactional store such as PostgreSQL, replace process-local rate limiting with Redis or a gateway, use distributed cache (Redis), store schema/index artifacts in shared object storage or a versioned registry, run embedding/index refresh in background workers, add queues for evaluation/audit, and propagate schema/config versions across instances. Session/JWT revocation and telemetry must use shared storage.

**Question: Is SQLite production-ready?**

**Answer:** It is appropriate for this local/single-node implementation and developer workflow. It is a known boundary: multi-worker or horizontally scaled production needs a shared transactional database and shared rate limiter.

**Question: How do dynamic schema updates work?**

**Answer:** Schema Studio changes go through governed requests. Once approved/applied, the metadata layer reloads the dynamic overlay, relationship graph, table/column retrieval documents, BM25/FAISS indexes, planner hints, ER output, and cached copilot instance without a backend restart. Excel-backed source tables are protected from live overwrite/delete.

**Question: How would you make schema refresh race-safe?**

**Answer:** Version schema snapshots immutably, build indexes off-path, validate them, atomically switch the active version, attach schema version to each request/cache entry, and keep old snapshots until in-flight requests finish. Never mutate the graph being used by a request.

**Question: What should be monitored?**

**Answer:** p50/p95 latency per stage; cache hit rate; provider calls/tokens/cost; provider error/fallback/cooldown rates; JSON repair rate; validation reject reasons; confidence distribution; clarification rate; coverage failures; schema-refresh success/time; auth/rate-limit events; and user feedback/acceptance. The existing metrics expose planner accuracy, SQL accuracy, validator precision, confidence reliability, confidence, join/intent signals, provider/model/fallback/repair details, and execution time.

## 11. Security and governance questions

**Question: How is the API secured?**

**Answer:** Browser clients use HTTP-only authenticated cookies plus CSRF protection. The backend validates the active JWT session in SQLite; unsafe methods require the stored token, cookie, and header to match. Credentialed CORS is restricted to configured origins. Admin routes enforce `role=admin` server-side. Provider secrets stay server-side and are not returned to the frontend.

**Question: How do you handle prompt injection?**

**Answer:** Treat user text as untrusted data, not instructions. The LLM receives a fixed system prompt and a constrained structured payload. The authoritative controls are outside the model: allowed schema, validated plan, one-statement read-only validator, coverage and confidence gates, least-privilege database credentials, logging, and no arbitrary execution route. A prompt cannot grant itself tables or operations that the deterministic layer rejects.

**Question: How is PII handled?**

**Answer:** The current project has governance/auth foundations, but production should add metadata classification (PII/sensitive), RBAC/ABAC-aware retrieval and validation, column/table allowlists, masking or aggregation policies, audit events containing actor and policy version, encryption, retention limits, and tenant isolation. Do not send sensitive row values to the LLM unless a reviewed data-processing policy permits it.

**Question: How do you audit a generated answer?**

**Answer:** Return/store the request ID, normalized prompt, selected tables/columns, join path, plan, validation result, coverage report, confidence breakdown/evidence, provider/model state, fallback/repair details, cache status, and timestamps. The UI exposes explainability rather than only SQL text.

## 12. Evaluation and testing questions

**Question: How do you evaluate quality?**

**Answer:** Use a labeled enterprise benchmark covering simple select, filters, aggregation, grouping, time ranges, direct joins, multi-hop joins, ambiguity, missing schema concepts, and malicious/unsafe prompts. Score separate dimensions: parse/validator success, execution correctness against a fixture database, semantic equivalence, coverage, correct clarification, false acceptance, latency, and cost. This project includes a 120-case enterprise benchmark and tests for agent semantics, confidence thresholds, joins, aggregation equivalence, aliases, displayed columns, auth, and provider behavior.

**Question: Why is exact SQL string match insufficient?**

**Answer:** Equivalent SQL can differ in aliases, join order, whitespace, or legal aggregate expression. Evaluate result equivalence and intent/coverage where possible, plus safety. Exact match is useful for regression snapshots but should not be the only metric.

**Question: What is an ablation study here?**

**Answer:** Disable one component at a time and measure the change. Supported experiment flags include schema graph, business logic, hybrid retrieval, LLM planner, LLM critic, and validator (validator safety is locked on in production). For example, compare join accuracy with and without graph-based join discovery, or token cost/quality with and without LLM review.

**Question: How do you incorporate feedback safely?**

**Answer:** Store feedback and telemetry, triage recurring failures, add test cases first, update vocabulary/business rules/schema mappings under review, benchmark before release, and version all artifacts. Do not automatically treat user corrections as schema truth or let them change prompts/policies without governance.

## 13. Likely interviewer follow-ups and concise answers

**What is the hardest problem?** Correct semantic grounding—not SQL syntax. A syntactically valid query can still join the wrong relationship or calculate the wrong business metric.

**What is the single source of truth?** Governed schema metadata plus approved business rules; the model is not the source of truth.

**What are the main failure modes?** Unresolved/ambiguous terms, wrong retrieval, disconnected/ambiguous joins, invalid provider JSON, hallucinated schema, provider outage, and stale schema/cache. Each has an explicit gate, fallback, or clarification path.

**How do you reduce latency?** Cache first, keep graph/index in memory, use hybrid retrieval to narrow context, use deterministic agents for routine cases, conditionally call the LLM, limit output/retries, parallelize independent retrieval/metadata work in a production upgrade, and show stage timings.

**Could you parallelize agents?** Yes, only where dependencies permit. Retrieval of table documents and business-vocabulary lookup can run in parallel after normalization. Join selection depends on schema linking; validation/coverage depend on SQL, so those remain ordered. Parallelism should not destroy explainability or deterministic replay.

**Why use LangGraph?** It makes states, nodes, edges, traces, and conditional routing explicit, improving observability and future extensibility. The project retains a linear fallback to avoid making a framework dependency a single point of failure.

**How would you support multiple SQL dialects?** Add dialect as a request/tenant configuration, use dialect-aware deterministic rendering and parser/validator settings, include it in RAG examples, test each dialect, and namespace cache/schema policies by dialect.

**How would you support tenant isolation?** Store tenant ID on metadata, indexes, cache keys, sessions, audit logs, and policy evaluation; retrieve only authorized tenant schema; use isolated database credentials/datasets; never cross-tenant cache or prompt context.

**Why not execute every SQL query for validation?** Execution may be expensive, leak data, create load, or be unavailable. First use static safety/schema/semantic validation. If execution is enabled, run explain/limited dry runs in an isolated read-only environment with quotas and timeouts.

**Where would you add human approval?** For low confidence, sensitive/PII data, expensive scans, new business metrics, schema edits, and actions beyond preview. The approval payload should include plan, SQL, estimated cost, policy reason, and audit metadata.

**What would you improve next?** Add a robust SQL AST policy engine with dialect-specific limits, authorization-aware semantic layer, schema/versioned distributed caching, asynchronous index refresh, result-based execution evaluation in a safe sandbox, automatic question reformulation for low-confidence cases, and a production-grade shared datastore/rate limiter.

## 14. A whiteboard answer you can memorize

"My system is a planner-first, multi-agent text-to-SQL architecture. The request is authenticated and checked in cache. Deterministic agents then extract intent and entities, retrieve only relevant schema/business context, resolve joins over a foreign-key graph, and create a validated plan IR. Only then, for complex cases, I call the LLM with a bounded schema and plan. Its output is never trusted directly: I enforce a one-statement read-only policy, validate table/column references, audit semantic coverage, calculate evidence-based confidence, and either return an explainable query or ask a clarification. This order reduces hallucinations, latency, and API cost while making the system safe to operate and easy to debug."

## 15. Facts to avoid overstating in the interview

- Say “optional NVIDIA GPT-OSS assistance,” not “the LLM always generates SQL.”
- Say “generic Spider SQL guidance is not enterprise-schema validated.”
- Say “SQLite is for local/single-node mode; scale-out needs shared state.”
- Say “the current execution UI is preview/export, not arbitrary database execution.”
- Say “confidence is evidence-based; model confidence is advisory.”
- Say “seven stages is the interview grouping; the implementation exposes ten workflow nodes.”

## 16. File/code map for live demonstration

| What to show | File |
| --- | --- |
| Workflow nodes/edges and LangGraph fallback | `agentic/langgraph_workflow.py` |
| End-to-end coordinator, cache, LLM boundary | `agentic/enterprise_copilot.py` |
| Intent, schema linking, join graph, planning | `agentic/planner_agents.py` |
| Confidence weights and penalties | `agentic/confidence_coordinator.py` |
| SQL policy validation | `backend/app.py` (`validate_sql`) |
| Provider, structured JSON, repair/fallback telemetry | `backend/llm_providers.py` |
| Architecture and quality docs | `docs/enterprise_sql_copilot.md`, `docs/enterprise_query_planning.md`, `docs/confidence_and_evaluation.md` |

