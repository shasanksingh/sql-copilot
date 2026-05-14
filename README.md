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
python app.py
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

