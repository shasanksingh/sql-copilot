# RL-Enhanced SQL Copilot Architecture

```mermaid
flowchart LR
    U[User Query] --> P[Planner Agent]
    P --> R[Retriever Agent]
    R --> G[SQL Generation Agent]
    G --> O[RL Optimization Agent]
    O --> V[Validator Agent]
    V --> E[Execution Agent]
    E --> X[Explanation Agent]
    X --> U
    E --> F[(agent_feedback)]
    F --> T[PPO Training Pipeline]
    T --> M[(rl/models)]
    M --> O
```

## Workflow

1. The existing RAG pipeline retrieves schema context and generates candidate SQL.
2. `SQLQueryOptimizationEnv` wraps query state, actions, execution metadata, validation, and reward shaping.
3. PPO can learn which optimization action to apply: regenerate SQL, modify joins, modify filters, modify aggregation, or keep the query.
4. Every execution can write feedback into the `agent_feedback` SQLite table.
5. The dashboard reads that feedback table to show reward, success rate, latency, and trends.

## Commands

Install optional RL dependencies:

```bash
pip install -r backend/requirements-rl.txt
```

Train:

```bash
python -m rl.training.train --db-path your.sqlite --timesteps 10000
```

Evaluate:

```bash
python -m rl.evaluation.evaluate --model-path rl/models/sql_ppo_agent.zip --db-path your.sqlite
```

## Frontend Integration

The redesigned Next.js dashboard consumes `GET /metrics` to show:

- total validated query feedback rows
- average reward
- query success rate
- SQL accuracy
- average latency
- recent reward/latency trend in Recharts

The metrics database defaults to `backend/sql_agent_feedback.sqlite` and can still be overridden:

```bash
AGENT_FEEDBACK_DB_PATH=path/to/feedback.sqlite
```
