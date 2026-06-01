# README.md

````md
# SQL Copilot 🚀

SQL Copilot is an AI-powered Natural Language to SQL Generator built using Flask, LangChain, FAISS, BM25 Retrieval, and an optional Remote LLM integration.

It allows users to:
- Ask database questions in plain English
- Automatically generate SQL queries
- Validate SQL safely
- Use schema-aware retrieval
- Get explainable query insights
- Interact through a modern ChatGPT-style UI

---

# Features

## Backend Features
- Natural Language → SQL conversion
- Hybrid Retrieval:
  - FAISS vector search
  - BM25 keyword retrieval
- Schema-aware SQL generation
- Foreign key inference
- SQL validation
- Confidence scoring
- Query rewriting
- Conversation memory
- Join path inference
- Explainable AI insights
- SQLite execution validation
- Safe SQL-only generation

## Frontend Features
- ChatGPT-style interface
- Dark / Light theme
- Animated UI
- SQL syntax highlighting
- Copy SQL button
- Explainable AI panel
- Responsive layout
- Sidebar conversations

---

# Project Structure

```bash
project/
│
├── app.py                 # Flask backend
├── index.html             # Frontend UI
├── RAG_DOC.xlsx           # Database schema documentation
├── faiss_table_index/     # FAISS table embeddings
├── faiss_col_index/       # FAISS column embeddings
├── requirements.txt
└── README.md
````

---

# Technologies Used

## Backend

* Python
* Flask
* LangChain
* FAISS
* BM25Retriever
* SQLite
* sqlglot
* Pandas

## Frontend

* HTML
* CSS
* JavaScript
* Prism.js

---

# Installation

## 1. Clone Repository

```bash
git clone https://github.com/your-username/sql-copilot.git
cd sql-copilot
```

---

## 2. Create Virtual Environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Mac/Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Required Dependencies

Create a `requirements.txt` file:

```txt
flask
flask-cors
pandas
openpyxl
httpx
sqlglot
langchain
langchain-community
langchain-openai
faiss-cpu
rank-bm25
```

---

# Environment Variables

Optional Remote LLM support:

```bash
USE_REMOTE_LLM=true
GENAI_BASE_URL=https://genailab.tcs.in
GENAI_API_KEY=your_api_key
```

---

# Running the Project

```bash
uvicorn main:asgi_app --host 127.0.0.1 --port 5000
```

Server starts at:

```bash
http://127.0.0.1:5000
```

Open browser and start asking SQL questions.

---

# Example Queries

```text
Get all employees

Count employees by department

Show top 5 highest paid employees

Get employee name and department name

Show all active projects
```

---

# How It Works

## Step 1 — Schema Loading

Reads schema from `RAG_DOC.xlsx`

## Step 2 — Hybrid Retrieval

Uses:

* FAISS semantic search
* BM25 keyword retrieval

## Step 3 — Prompt Engineering

Builds SQL-focused prompts using:

* Schema
* Few-shot examples
* Join hints
* Conversation memory

## Step 4 — SQL Generation

Generates SQL using:

* Remote LLM OR
* Local rule-based fallback

## Step 5 — SQL Validation

Checks:

* Unknown tables
* Unknown columns
* Dangerous operations
* Ambiguous columns

## Step 6 — Query Insights

Returns:

* Confidence score
* Query type
* Tables used
* Columns used

---

# Security Features

The system blocks:

* DELETE
* DROP
* UPDATE
* INSERT
* ALTER
* TRUNCATE

Only SELECT queries are allowed.


---

# Future Improvements

* PostgreSQL/MySQL support
* Export query results
* User authentication
* Streaming responses
* Docker deployment
* Kubernetes support
* Fine-tuned SQL model

---

# RL-Enhanced Agentic SQL Layer

This project now includes an optional reinforcement-learning enhancement layer on top of the existing RAG Text-to-SQL pipeline. The original workflow remains intact; RL is used for feedback collection, explainability, policy-based optimization, and future PPO training.

## Added Structure

```bash
rl/
├── environment/sql_env.py      # SQLQueryOptimizationEnv and reward shaping
├── agent/ppo_agent.py          # Stable-Baselines3 PPO wrapper
├── training/train.py           # Training pipeline with checkpointing
├── evaluation/evaluate.py      # Evaluation script
└── models/                     # Saved models and checkpoints

agentic/
└── manager.py                  # Planner, retriever, generator, optimizer, validator, executor, explainer orchestration

docs/
└── rl_architecture.md          # Architecture diagram and RL workflow
```

## Feedback Storage

Every successful SQL generation stores execution feedback in SQLite table `agent_feedback`:

* `query`
* `generated_sql`
* `reward`
* `execution_time`
* `validation_status`
* `timestamp`

By default the feedback database is `sql_agent_feedback.sqlite`. Override it with:

```bash
AGENT_FEEDBACK_DB_PATH=path/to/feedback.sqlite
```

## Optional RL Dependencies

```bash
pip install -r requirements-rl.txt
```

## Train PPO

```bash
python -m rl.training.train --db-path path/to/app.sqlite --timesteps 10000
```

## Evaluate PPO

```bash
python -m rl.evaluation.evaluate --model-path rl/models/sql_ppo_agent.zip --db-path path/to/app.sqlite
```

## Dashboard

Run Flask and open:

```text
http://127.0.0.1:5000/dashboard
```

Metrics API:

```text
http://127.0.0.1:5000/metrics
```

---

# Final Run Steps Without API Key

These steps keep the existing fallback behavior. You do not need `GENAI_API_KEY` or any remote LLM setting.

## 1. Create and activate virtual environment

```bash
python -m venv venv
venv\Scripts\activate
```

## 2. Install normal app dependencies

```bash
pip install -r requirements.txt
```

## 3. Optional: install RL/dashboard dependencies

Use this only if you want PPO training, evaluation, or tests.

```bash
pip install -r requirements-rl.txt
```

## 4. Run the app with uvicorn in fallback mode

Do not set `USE_REMOTE_LLM` and do not set `GENAI_API_KEY`.

```bash
uvicorn main:asgi_app --host 127.0.0.1 --port 5000
```

Open:

```text
http://127.0.0.1:5000
```

## 5. Try schema questions

```text
Show all employees
Count tasks by status
Show active projects
List invoices by status
Show payments received by client
Show production deployments
List active sprints by project
Show departments and their managers
```

## 6. View RL feedback metrics

After running a few SQL questions, open:

```text
http://127.0.0.1:5000/dashboard
```

API version:

```text
http://127.0.0.1:5000/metrics
```

## 7. Run tests

```bash
python -m pytest tests
```

## 8. Optional PPO training

Only run this after installing `requirements-rl.txt`.

```bash
python -m rl.training.train --timesteps 10000
```
