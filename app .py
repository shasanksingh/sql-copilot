from __future__ import annotations

import os
import re
import sqlite3
import webbrowser
from collections import deque
from pathlib import Path
from threading import Timer

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

try:
    import httpx
except ImportError:
    httpx = None

try:
    import sqlglot
except ImportError:
    sqlglot = None

try:
    from langchain_core.documents import Document
except ImportError:
    class Document:
        def __init__(self, page_content: str, metadata: dict | None = None):
            self.page_content = page_content
            self.metadata = metadata or {}

try:
    from langchain_community.retrievers import BM25Retriever
except ImportError:
    BM25Retriever = None

try:
    from langchain_community.vectorstores import FAISS
except ImportError:
    FAISS = None

try:
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
except ImportError:
    ChatOpenAI = None
    OpenAIEmbeddings = None

try:
    from flask_cors import CORS
except ImportError:
    CORS = None


 
# 1. CONFIG
 

BASE_DIR = Path(__file__).resolve().parent

USE_REMOTE_LLM = os.getenv("USE_REMOTE_LLM", "").lower() in {"1", "true", "yes"}
BASE_URL = os.getenv("GENAI_BASE_URL", "https://genailab.tcs.in")
API_KEY = os.getenv("GENAI_API_KEY", "")

SCHEMA_FILE = BASE_DIR / "RAG_DOC.xlsx"
FAISS_TABLE_INDEX_PATH = str(BASE_DIR / "faiss_table_index")
FAISS_COL_INDEX_PATH = str(BASE_DIR / "faiss_col_index")

DB_PATH = None
MAX_RETRIES = 3
CONFIDENCE_THRESHOLD = 80

http_client = (
    httpx.Client(verify=False)
    if USE_REMOTE_LLM and API_KEY and httpx is not None
    else None
)

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
if CORS:
    CORS(app)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def log_step(message: str) -> None:
    print(message, flush=True)


 
# 2. MODELS
 

if USE_REMOTE_LLM and API_KEY and OpenAIEmbeddings and http_client:
    embeddings = OpenAIEmbeddings(
        base_url=BASE_URL,
        model="azure/genailab-maas-text-embedding-3-large",
        api_key=API_KEY,
        http_client=http_client,
    )
else:
    embeddings = None
    log_step("[local] Remote embeddings disabled; using keyword/BM25 retrieval")

if USE_REMOTE_LLM and API_KEY and ChatOpenAI and http_client:
    llm = ChatOpenAI(
        base_url=BASE_URL,
        model="genailab-maas-gpt-5.4",
        api_key=API_KEY,
        http_client=http_client,
    )
else:
    llm = None
    log_step("[local] Remote LLM disabled; using local rule-based SQL generation")


 
# 3. SCHEMA LOADING
 

log_step("[schema] Loading schema...")

try:
    df = pd.read_excel(SCHEMA_FILE, sheet_name=0).fillna("")
    log_step("[schema] Read schema as Excel file")
except Exception as exc:
    log_step(f"[schema] Excel read failed; trying tab-separated read: {exc}")
    df = pd.read_csv(SCHEMA_FILE, sep="\t").fillna("")
    log_step("[schema] Read schema as tab-separated file")

schema_tables: set[str] = set()
schema_columns: dict[str, set[str]] = {}
schema_column_order: dict[str, list[str]] = {}
schema_column_types: dict[str, dict] = {}
schema_graph: dict[str, list[tuple]] = {}

table_documents: list[Document] = []
column_documents: list[Document] = []
col_to_tables: dict[str, list[str]] = {}

for table_name, group in df.groupby("Table Name"):
    table_display = str(table_name).strip()
    t_lower = table_display.lower()
    schema_tables.add(t_lower)

    cols: set[str] = set()
    col_types: dict = {}
    col_lines = ""

    for _, row in group.iterrows():
        column_display = str(row["Column Name"]).strip()
        c_lower = column_display.lower()
        cols.add(c_lower)
        col_types[c_lower] = row["Data Type"]
        col_lines += (
            f"  - {column_display} ({row['Data Type']}): "
            f"{row['Description']}\n"
        )
        col_to_tables.setdefault(c_lower, []).append(t_lower)

        column_documents.append(Document(
            page_content=(
                f"Table: {table_display} | "
                f"Column: {column_display} ({row['Data Type']}) | "
                f"Meaning: {row['Description']}"
            ),
            metadata={"table": table_display, "column": column_display},
        ))

    schema_columns[t_lower] = cols
    schema_column_order[t_lower] = [str(col).strip().lower() for col in group["Column Name"]]
    schema_column_types[t_lower] = col_types

    table_documents.append(Document(
        page_content=(
            f"Table: {table_display}\n"
            f"Description: {group['What this table stores'].iloc[0]}\n\n"
            f"Columns:\n{col_lines}"
        ),
        metadata={"table": table_display},
    ))

try:
    xl = pd.ExcelFile(SCHEMA_FILE)
    if "foreign_keys" in xl.sheet_names:
        fk_df = pd.read_excel(SCHEMA_FILE, sheet_name="foreign_keys").fillna("")
        for _, row in fk_df.iterrows():
            ft = str(row["from_table"]).lower()
            schema_graph.setdefault(ft, []).append((
                str(row["from_column"]).lower(),
                str(row["to_table"]).lower(),
                str(row["to_column"]).lower(),
            ))
        log_step(f"[schema] FK relationships loaded for {len(schema_graph)} tables")
    else:
        log_step("[schema] No 'foreign_keys' sheet; join hints disabled")
except Exception:
    log_step("[schema] FK sheet unavailable; join hints disabled")


def _register_fk(
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
) -> bool:
    if from_table == to_table:
        return False
    if to_table not in schema_tables:
        return False
    if to_column not in schema_columns.get(to_table, set()):
        return False

    relation = (from_column, to_table, to_column)
    relations = schema_graph.setdefault(from_table, [])
    if relation in relations:
        return False
    relations.append(relation)
    return True


def infer_foreign_keys_from_schema() -> int:
    inferred = 0
    reference_pattern = re.compile(
        r"\breferences?\s+([a-zA-Z_][\w]*)\s*\(\s*([a-zA-Z_][\w]*)\s*\)",
        re.IGNORECASE,
    )
    column_targets = {
        "assigned_to": ("employees", "employee_id"),
        "reported_by": ("employees", "employee_id"),
        "employee_id": ("employees", "employee_id"),
        "project_id": ("projects", "project_id"),
        "client_id": ("clients", "client_id"),
        "task_id": ("tasks", "task_id"),
    }

    for _, row in df.iterrows():
        from_table = str(row["Table Name"]).strip().lower()
        from_column = str(row["Column Name"]).strip().lower()
        data_type = str(row["Data Type"]).lower()
        description = str(row["Description"])

        match = reference_pattern.search(description)
        if match:
            to_table = match.group(1).lower()
            to_column = match.group(2).lower()
        elif "fk" in data_type and from_column in column_targets:
            to_table, to_column = column_targets[from_column]
        else:
            continue

        if _register_fk(from_table, from_column, to_table, to_column):
            inferred += 1

    return inferred


inferred_fk_count = infer_foreign_keys_from_schema()
if inferred_fk_count:
    log_step(f"[schema] Inferred {inferred_fk_count} FK relationships from schema descriptions")

log_step(f"[schema] {len(schema_tables)} tables | {len(column_documents)} columns")


 
# 4. VECTOR STORES
 

def _load_or_build(index_path: str, docs: list[Document], label: str) -> FAISS:
    if FAISS is None or embeddings is None:
        raise RuntimeError("FAISS or embeddings unavailable")
    if os.path.exists(index_path):
        log_step(f"[vector] Loading {label} FAISS from disk...")
        return FAISS.load_local(
            index_path,
            embeddings,
            allow_dangerous_deserialization=True,
        )

    log_step(f"[vector] Building {label} FAISS first run...")
    vs = FAISS.from_documents(docs, embeddings)
    vs.save_local(index_path)
    log_step(f"[vector] Saved {index_path}")
    return vs


log_step("[vector] Initialising vector stores...")
try:
    table_vs = _load_or_build(FAISS_TABLE_INDEX_PATH, table_documents, "table-level")
    column_vs = _load_or_build(FAISS_COL_INDEX_PATH, column_documents, "column-level")
    faiss_table_ret = table_vs.as_retriever(search_kwargs={"k": 3})
    faiss_col_ret = column_vs.as_retriever(search_kwargs={"k": 5})
except Exception as exc:
    table_vs = None
    column_vs = None
    faiss_table_ret = None
    faiss_col_ret = None
    log_step(f"[vector] FAISS unavailable; using local schema retrieval: {exc}")

if BM25Retriever:
    bm25_ret = BM25Retriever.from_documents(table_documents)
    bm25_ret.k = 3
else:
    bm25_ret = None
    log_step("[deps] BM25Retriever unavailable; BM25 disabled")


 
# 5. SCHEMA GRAPH - JOIN PATH INFERENCE
 

def find_join_path(a: str, b: str) -> str | None:
    for col, rel_table, rel_col in schema_graph.get(a, []):
        if rel_table == b:
            return f"JOIN {b} ON {a}.{col} = {b}.{rel_col}"
    for col, rel_table, rel_col in schema_graph.get(b, []):
        if rel_table == a:
            return f"JOIN {a} ON {b}.{col} = {a}.{rel_col}"
    return None


def build_join_hints(table_names: list[str]) -> str:
    hints: list[str] = []
    for i, t1 in enumerate(table_names):
        for t2 in table_names[i + 1:]:
            path = find_join_path(t1, t2)
            if path:
                hints.append(f"  {t1} <-> {t2}: {path}")
    return "\n".join(hints)


 
# 6. HYBRID RETRIEVAL
 

def hybrid_retrieve(query: str) -> tuple[list[Document], list[str]]:
    query_terms = set(re.findall(r"[a-z_]{3,}", query.lower()))

    if faiss_table_ret:
        table_docs = faiss_table_ret.invoke(query)
    else:
        scored_docs: list[tuple[int, Document]] = []
        for doc in table_documents:
            text = doc.page_content.lower().replace("_", " ")
            score = sum(1 for term in query_terms if term in text)
            if doc.metadata["table"].lower() in query.lower():
                score += 5
            scored_docs.append((score, doc))
        table_docs = [
            doc for score, doc in sorted(scored_docs, key=lambda item: item[0], reverse=True)
            if score > 0
        ][:3] or table_documents[:3]

    if faiss_col_ret:
        col_docs = faiss_col_ret.invoke(query)
    else:
        col_docs = [
            doc for doc in column_documents
            if any(term in doc.page_content.lower().replace("_", " ") for term in query_terms)
        ][:5]
    bm25_docs = bm25_ret.invoke(query) if bm25_ret else []

    col_hit_tables = {d.metadata["table"] for d in col_docs}

    top_col_hints: list[str] = []
    for d in col_docs:
        hint = f"{d.metadata['table']}.{d.metadata['column']}"
        if hint not in top_col_hints:
            top_col_hints.append(hint)

    seen: set[str] = set()
    final: list[Document] = []

    for doc in table_docs:
        table = doc.metadata["table"]
        if table not in seen:
            seen.add(table)
            final.append(doc)

    for doc in table_documents:
        table = doc.metadata["table"]
        if table in col_hit_tables and table not in seen:
            seen.add(table)
            final.append(doc)

    for doc in bm25_docs:
        table = doc.metadata["table"]
        if table not in seen:
            seen.add(table)
            final.append(doc)

    return final[:5], top_col_hints[:8]


 
# 7. QUERY REWRITING
 

_REWRITE_SYSTEM = (
    "You are a query normalizer for a SQL generation system.\n"
    "Rewrite the user's natural language query using standard business terminology.\n"
    "- Expand abbreviations: 'emp'->'employee', 'dept'->'department', 'mgr'->'manager'\n"
    "- Normalise synonyms: 'workers'->'employees', 'mail'->'email', 'headcount'->'count of employees'\n"
    "- Remove filler words and make the intent explicit\n"
    "- Do NOT change the meaning or add assumptions\n"
    "Return ONLY the rewritten query, nothing else."
)

_REWRITE_TRIGGERS = re.compile(
    r"\b(emp|dept|mgr|sal|headcount|workers|staff|mail|folks|"
    r"peeps|num|no\.|qty|amt|rec|ref|cos|grp)\b",
    re.IGNORECASE,
)

_LOCAL_REWRITE_REPLACEMENTS = [
    (r"\bemps?\b", "employees"),
    (r"\bworkers?\b|\bstaff\b|\bfolks\b|\bpeeps\b", "employees"),
    (r"\bdept\b", "department"),
    (r"\bmgr\b", "manager"),
    (r"\bmail\b", "email"),
    (r"\bheadcount\b", "count of employees"),
    (r"\bnum\b|\bno\.?\b|\bqty\b", "number of"),
    (r"\bamt\b", "amount"),
    (r"\brec\b", "record"),
    (r"\bref\b", "reference"),
    (r"\bgrp\b", "group"),
    (r"\bdefects?\b|\bissues?\b", "bugs"),
]


def _needs_rewrite(query: str) -> bool:
    if len(query.split()) <= 3:
        return False
    return bool(_REWRITE_TRIGGERS.search(query))


def rewrite_query_locally(query: str) -> str:
    rewritten = query
    for pattern, replacement in _LOCAL_REWRITE_REPLACEMENTS:
        rewritten = re.sub(pattern, replacement, rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(r"\s+", " ", rewritten).strip()
    if rewritten and rewritten.lower() != query.lower():
        log_step(f"[rewrite-local] '{query}' -> '{rewritten}'")
    return rewritten or query


def rewrite_query(query: str) -> str:
    if not _needs_rewrite(query):
        return query
    if llm is None:
        return rewrite_query_locally(query)
    try:
        resp = llm.invoke([
            {"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user", "content": query},
        ])
        rewritten = resp.content.strip()
        if rewritten and rewritten.lower() != query.lower():
            log_step(f"[rewrite] '{query}' -> '{rewritten}'")
        return rewritten or query
    except Exception as exc:
        log_step(f"[rewrite] skipped: {exc}")
        return query


 
# 8. INTENT CLASSIFIER
 

_DANGEROUS = {
    "delete", "drop", "remove", "update", "truncate",
    "alter", "grant", "revoke", "exec", "execute",
}
_META = {
    "schema", "tables", "columns", "describe",
    "list tables", "show tables", "what tables",
}


def classify_query(query: str) -> str:
    q = query.lower()
    if any(w in q for w in _DANGEROUS):
        return "DANGEROUS"
    if any(w in q for w in _META):
        return "META"
    return "SQL"


 
# 9. FEW SHOTS
 

FEW_SHOTS: list[dict] = [
    {"query": "Get all employees", "sql": "SELECT * FROM employees;"},
    {"query": "Get employee names and emails", "sql": "SELECT full_name, email FROM employees;"},
    {"query": "Count all employees", "sql": "SELECT COUNT(*) FROM employees;"},
    {"query": "Get employees with Gmail addresses", "sql": "SELECT * FROM employees WHERE email LIKE '%gmail%';"},
    {"query": "Count employees by department", "sql": "SELECT department, COUNT(*) AS headcount FROM employees GROUP BY department;"},
    {"query": "Top 5 highest paid employees", "sql": "SELECT full_name, salary FROM employees ORDER BY salary DESC LIMIT 5;"},
    {
        "query": "Get employee name and their department name",
        "sql": (
            "SELECT e.full_name, d.department_name "
            "FROM employees e "
            "JOIN departments d ON e.department_id = d.id;"
        ),
    },
]


def _fmt_shots(examples: list[dict]) -> str:
    return "\n\n".join(
        f"User: {example['query']}\nSQL: {example['sql']}"
        for example in examples
    )


 
# 10. PROMPT BUILDER
 

def build_prompt(
    schema_context: str,
    user_query: str,
    join_hints: str = "",
    col_hints: list[str] | None = None,
    history_context: str = "",
) -> str:
    col_hints = col_hints or []

    join_block = ""
    if join_hints:
        join_block = (
            "\nJOIN CONDITIONS (MANDATORY):\n"
            "- If your query involves more than one table, you MUST use one of the\n"
            "  JOIN conditions listed below exactly as written.\n"
            "- Do NOT invent or guess join conditions.\n"
            "- If no JOIN condition is listed for the tables you need, return NOT_POSSIBLE.\n"
            f"{join_hints}\n"
        )

    col_block = ""
    if col_hints:
        formatted = "\n".join(f"  - {hint}" for hint in col_hints)
        col_block = (
            "\nTOP RELEVANT COLUMNS (use these where appropriate):\n"
            f"{formatted}\n"
        )

    hist_block = ""
    if history_context:
        hist_block = (
            "\nCONVERSATION HISTORY (context only - do not blindly reuse past SQL):\n"
            f"{history_context}\n"
        )

    return (
        "You are an expert SQL generator.\n\n"
        "STRICT RULES:\n"
        "- ONLY generate SELECT queries.\n"
        "- NEVER generate DELETE, DROP, UPDATE, INSERT, ALTER, TRUNCATE or any DDL/DML.\n"
        "- Use ONLY the tables and columns listed in the SCHEMA section.\n"
        "- Always qualify ambiguous column names with their table alias "
        "(e.g. e.full_name, d.department_name).\n"
        "- If the query cannot be answered from the schema, return exactly: NOT_POSSIBLE\n"
        "- Do NOT wrap SQL in markdown fences or add any explanation.\n"
        "- Output ONLY raw SQL ending with a semicolon.\n"
        f"{join_block}"
        f"{col_block}"
        f"{hist_block}"
        f"\nFEW-SHOT EXAMPLES:\n{_fmt_shots(FEW_SHOTS)}\n\n"
        f"SCHEMA:\n{schema_context}\n\n"
        f"USER QUERY:\n{user_query}\n\n"
        "SQL:"
    )


 
# 11. ALIAS-AWARE TABLE EXTRACTION
 

def extract_tables_and_aliases(sql: str) -> tuple[set[str], dict[str, str]]:
    used_tables: set[str] = set()
    alias_map: dict[str, str] = {}

    if sqlglot is not None:
        try:
            parsed = sqlglot.parse_one(sql)
            for tbl in parsed.find_all(sqlglot.exp.Table):
                real_name = tbl.name.lower()
                used_tables.add(real_name)
                if tbl.alias:
                    alias_map[tbl.alias.lower()] = real_name
            return used_tables, alias_map
        except sqlglot.errors.ParseError:
            pass

    for match in re.finditer(
        r"\b(?:from|join)\s+(\w+)(?:\s+(?:as\s+)?(\w+))?",
        sql,
        re.IGNORECASE,
    ):
        real = match.group(1).lower()
        used_tables.add(real)
        if match.group(2):
            alias_map[match.group(2).lower()] = real

    return used_tables, alias_map


 
# 12. VALIDATOR
 

_FORBIDDEN_OPS = [
    "delete", "drop", "update", "insert",
    "alter", "truncate", "grant", "revoke",
]


def validate_sql(sql: str) -> tuple[bool, str]:
    sql_lower = sql.lower().strip()

    for word in _FORBIDDEN_OPS:
        if re.search(rf"\b{word}\b", sql_lower):
            return False, f"Forbidden operation: '{word}'"

    if not sql_lower.startswith("select"):
        return False, "Query must begin with SELECT"

    used_tables, alias_map = extract_tables_and_aliases(sql)

    for table in used_tables:
        if table not in schema_tables:
            return False, f"Unknown table: '{table}'"

    if sqlglot is not None:
        try:
            parsed = sqlglot.parse_one(sql)
            for col_expr in parsed.find_all(sqlglot.exp.Column):
                col_name = col_expr.name.lower()
                table_ref = col_expr.table.lower() if col_expr.table else None

                if col_name == "*":
                    continue

                if table_ref:
                    real_table = alias_map.get(table_ref, table_ref)
                    if real_table in schema_columns:
                        if col_name not in schema_columns[real_table]:
                            alias_note = (
                                f" (via alias '{table_ref}')"
                                if table_ref != real_table else ""
                            )
                            return False, (
                                f"Unknown column '{col_name}' in table '{real_table}'"
                                f"{alias_note}"
                            )
                else:
                    matches = [
                        table for table in used_tables
                        if col_name in schema_columns.get(table, set())
                    ]
                    if len(matches) > 1:
                        return False, (
                            f"Ambiguous column '{col_name}' exists in multiple tables {matches}. "
                            "Qualify it with a table alias."
                        )
                    if len(matches) == 0 and used_tables:
                        return False, (
                            f"Unknown column '{col_name}' - not found in any retrieved table"
                        )
        except sqlglot.errors.ParseError as exc:
            return False, f"SQL parse error: {exc}"
    else:
        log_step("[deps] sqlglot missing; using table-only SQL validation")

    return True, "Valid"


 
# 13. CONFIDENCE SCORING
 

def confidence_score(sql: str, is_valid: bool, original_query: str) -> int:
    if not is_valid:
        return 0

    score = 80
    q = original_query.lower()
    s = sql.lower()

    if any(w in q for w in ["count", "total", "how many"]) and "count(" in s:
        score += 5
    if any(w in q for w in ["group", "per", "each", "by department", "by category"]) and "group by" in s:
        score += 5
    if any(w in q for w in ["sort", "order", "top", "latest", "recent", "highest", "lowest"]) and "order by" in s:
        score += 5
    if any(w in q for w in ["join", "and their", "along with", "with its"]) and "join" in s:
        score += 5

    if "select *" in s and len(original_query.split()) > 5:
        score -= 5
    if len(sql.strip()) < 15:
        score -= 30

    return max(0, min(score, 100))


 
# 14. EXECUTION FEEDBACK
 

def execution_validate(sql: str) -> tuple[bool, str]:
    if DB_PATH is None:
        return True, ""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute(f"EXPLAIN QUERY PLAN {sql}")
        conn.close()
        return True, ""
    except Exception as exc:
        return False, str(exc)


 
# 15. CONVERSATION MEMORY
 

class SQLChatSession:
    def __init__(self, max_history: int = 5):
        self.history = deque(maxlen=max_history)

    def add(self, query: str, sql: str) -> None:
        self.history.append({"query": query, "sql": sql})

    def get_context(self) -> str:
        if not self.history:
            return ""
        return "\n\n".join(
            f"User: {item['query']}\nSQL: {item['sql']}"
            for item in self.history
        )

    def clear(self) -> None:
        self.history.clear()


session = SQLChatSession()


 
# 16. XAI / UI INSIGHTS
 

def detect_query_type(sql: str) -> str:
    sql_lower = sql.lower()
    if "count(" in sql_lower:
        return "Count"
    if "group by" in sql_lower:
        return "Aggregation"
    if "join" in sql_lower:
        return "Join"
    if "order by" in sql_lower:
        return "Ranking"
    return "Lookup"


def extract_selected_columns(sql: str) -> list[str]:
    match = re.search(r"\bselect\s+(.*?)\s+\bfrom\b", sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    select_part = re.sub(r"\s+", " ", match.group(1).strip())
    if select_part == "*":
        return ["*"]
    return [part.strip() for part in select_part.split(",")[:6] if part.strip()]


def build_query_insights(
    sql: str,
    query: str,
    source: str,
    attempts: int,
    validation_note: str = "",
) -> dict[str, object]:
    is_valid, validation_message = validate_sql(sql)
    score = confidence_score(sql, is_valid, query)
    tables = sorted(extract_tables_and_aliases(sql)[0], key=str.lower)
    selected_columns = extract_selected_columns(sql)
    has_limit = bool(re.search(r"\blimit\s+\d+", sql, re.IGNORECASE))
    query_type = detect_query_type(sql)

    return {
        "confidence": score,
        "threshold": CONFIDENCE_THRESHOLD,
        "valid": is_valid,
        "validation": validation_note or validation_message,
        "source": source,
        "attempts": attempts,
        "max_attempts": MAX_RETRIES,
        "tables": tables,
        "columns": selected_columns,
        "query_type": query_type,
        "has_limit": has_limit,
        "summary": (
            f"{query_type} query using "
            f"{', '.join(tables) if tables else 'the available schema'}"
        ),
    }


 
# 17. LOCAL FALLBACK
 
TABLE_ALIASES = {
    "employees": "e",
    "clients": "c",
    "projects": "p",
    "project_team": "pt",
    "tasks": "t",
    "time_logs": "tl",
    "bugs": "b",
}

TABLE_QUERY_HINTS = {
    "employees": {
        "employee", "employees", "staff", "worker", "workers", "developer",
        "developers", "qa", "manager", "managers", "devops", "department",
        "role", "email",
    },
    "clients": {
        "client", "clients", "customer", "customers", "industry",
        "organization", "contact",
    },
    "projects": {
        "project", "projects", "budget", "start date", "end date",
        "planning", "on hold",
    },
    "project_team": {
        "project team", "team", "assignment", "assigned", "member",
        "members", "role in project",
    },
    "tasks": {
        "task", "tasks", "todo", "in progress", "blocked", "priority",
        "deadline", "due", "assignee", "assigned",
    },
    "time_logs": {
        "time", "time log", "time logs", "hours", "hours spent", "logged",
        "productivity", "billing",
    },
    "bugs": {
        "bug", "bugs", "defect", "defects", "issue", "issues", "severity",
        "reported", "reporter", "resolved", "closed", "blocker",
    },
}

DEFAULT_DISPLAY_COLUMNS = {
    "employees": ["employee_id", "full_name", "email", "role", "department", "status"],
    "clients": ["client_id", "client_name", "contact_email", "industry", "created_at"],
    "projects": ["project_id", "project_name", "client_id", "status", "budget", "start_date", "end_date"],
    "project_team": ["id", "project_id", "employee_id", "role_in_project", "assigned_at"],
    "tasks": ["task_id", "title", "project_id", "assigned_to", "priority", "status", "due_date"],
    "time_logs": ["log_id", "task_id", "employee_id", "hours_spent", "log_date", "remarks"],
    "bugs": ["bug_id", "project_id", "reported_by", "assigned_to", "severity", "status", "created_at"],
}

PRIMARY_LABEL_COLUMNS = {
    "employees": "full_name",
    "clients": "client_name",
    "projects": "project_name",
    "tasks": "title",
    "time_logs": "log_id",
    "bugs": "bug_id",
    "project_team": "id",
}

COLUMN_QUERY_HINTS = {
    "employees": {
        "employee_id": {"id", "employee id"},
        "full_name": {"name", "names", "full name", "employee name", "employee names"},
        "email": {"email", "mail", "emails"},
        "role": {"role", "job role", "designation"},
        "department": {"department", "dept"},
        "joining_date": {"joining date", "joined", "join date"},
        "status": {"status", "active", "inactive", "on leave"},
    },
    "clients": {
        "client_id": {"id", "client id"},
        "client_name": {"name", "names", "client name", "client names"},
        "contact_email": {"contact email", "email", "mail"},
        "industry": {"industry", "domain"},
        "created_at": {"created", "onboarded", "created at"},
    },
    "projects": {
        "project_id": {"id", "project id"},
        "project_name": {"name", "names", "project name", "project names"},
        "client_id": {"client", "client id"},
        "start_date": {"start", "start date", "started"},
        "end_date": {"end", "end date", "completion"},
        "status": {"status", "planning", "active", "completed", "on hold"},
        "budget": {"budget", "cost", "amount"},
    },
    "project_team": {
        "project_id": {"project", "project id"},
        "employee_id": {"employee", "employee id"},
        "role_in_project": {"role", "project role", "role in project"},
        "assigned_at": {"assigned", "assigned at"},
    },
    "tasks": {
        "task_id": {"id", "task id"},
        "title": {"title", "task", "task title"},
        "description": {"description", "details"},
        "assigned_to": {"assignee", "assigned", "assigned to", "employee"},
        "priority": {"priority"},
        "status": {"status", "todo", "in progress", "completed", "blocked"},
        "created_at": {"created", "created at"},
        "due_date": {"due", "due date", "deadline"},
    },
    "time_logs": {
        "task_id": {"task", "task id"},
        "employee_id": {"employee", "employee id"},
        "hours_spent": {"hours", "hours spent", "time spent", "time"},
        "log_date": {"date", "log date", "logged"},
        "remarks": {"remarks", "notes"},
    },
    "bugs": {
        "bug_id": {"id", "bug id"},
        "project_id": {"project", "project id"},
        "reported_by": {"reported by", "reporter", "found by"},
        "assigned_to": {"assigned", "assigned to", "assignee", "developer"},
        "severity": {"severity", "minor", "major", "critical", "blocker"},
        "status": {"status", "open", "in progress", "resolved", "closed"},
        "description": {"description", "details"},
        "created_at": {"created", "reported", "created at"},
    },
}

VALUE_FILTERS = {
    "employees": {
        "status": {
            "active": "active",
            "inactive": "inactive",
            "on leave": "on_leave",
            "on_leave": "on_leave",
        },
        "role": {
            "developer": "developer",
            "developers": "developer",
            "manager": "manager",
            "managers": "manager",
        },
        "department": {
            "engineering": "engineering",
            "product": "product",
        },
    },
    "clients": {
        "industry": {
            "fintech": "fintech",
            "healthtech": "healthtech",
            "e-commerce": "e-commerce",
            "ecommerce": "e-commerce",
        },
    },
    "projects": {
        "status": {
            "planning": "planning",
            "active": "active",
            "completed": "completed",
            "complete": "completed",
            "on hold": "on_hold",
            "on_hold": "on_hold",
        },
    },
    "tasks": {
        "priority": {
            "low": "low",
            "medium": "medium",
            "high": "high",
            "critical": "critical",
        },
        "status": {
            "todo": "todo",
            "to do": "todo",
            "in progress": "in_progress",
            "in_progress": "in_progress",
            "completed": "completed",
            "complete": "completed",
            "blocked": "blocked",
        },
    },
    "bugs": {
        "severity": {
            "minor": "minor",
            "major": "major",
            "critical": "critical",
            "blocker": "blocker",
        },
        "status": {
            "open": "open",
            "in progress": "in_progress",
            "in_progress": "in_progress",
            "resolved": "resolved",
            "closed": "closed",
        },
    },
}

DATE_ORDER_COLUMNS = {
    "employees": "joining_date",
    "clients": "created_at",
    "projects": "start_date",
    "tasks": "created_at",
    "time_logs": "log_date",
    "bugs": "created_at",
    "project_team": "assigned_at",
}


def _normalise_query_text(query: str) -> str:
    rewritten = rewrite_query_locally(query)
    rewritten = rewritten.lower().replace("-", " ")
    return re.sub(r"\s+", " ", rewritten).strip()


def _phrase_in_query(query: str, phrase: str) -> bool:
    parts = re.split(r"[\s_]+", phrase.lower().strip())
    if not parts:
        return False
    pattern = r"(?<!\w)" + r"[\s_]+".join(re.escape(part) for part in parts) + r"(?!\w)"
    return bool(re.search(pattern, query))


def _has_any(query: str, phrases: set[str] | list[str] | tuple[str, ...]) -> bool:
    return any(_phrase_in_query(query, phrase) for phrase in phrases)


def _is_count_request(query: str) -> bool:
    return _has_any(query, ["count", "how many", "number of"])


def _is_group_request(query: str) -> bool:
    return bool(re.search(r"\b(by|per|each|grouped|group)\b", query))


def _is_total_request(query: str) -> bool:
    return _has_any(query, ["total", "sum"])


def _is_average_request(query: str) -> bool:
    return _has_any(query, ["average", "avg", "mean"])


def _limit_value(query: str) -> int | None:
    match = re.search(
        r"\b(?:top|first|last|latest|recent|newest|oldest|earliest|limit)\s+(\d{1,4})\b",
        query,
    )
    if not match:
        match = re.search(r"\b(\d{1,4})\s+(?:rows|records|results)\b", query)
    if match:
        return min(max(int(match.group(1)), 1), 1000)
    if _has_any(query, ["top", "first", "last"]):
        return 10
    return None


def _limit_clause(query: str) -> str:
    limit = _limit_value(query)
    return f"LIMIT {limit}" if limit is not None else ""


def _wants_order(query: str) -> bool:
    return _has_any(query, [
        "order", "sort", "rank", "top", "highest", "lowest", "most",
        "least", "largest", "smallest", "maximum", "minimum", "max",
        "min", "latest", "recent", "newest", "last", "oldest",
        "earliest", "first",
    ])


def _alias(table: str) -> str:
    return TABLE_ALIASES.get(table, table[:1] or "t")


def _table_score(query: str, table: str) -> int:
    singular = table[:-1] if table.endswith("s") else table
    score = 0
    if _phrase_in_query(query, table) or _phrase_in_query(query, singular):
        score += 12
    for hint in TABLE_QUERY_HINTS.get(table, set()):
        if _phrase_in_query(query, hint):
            score += 4
    for column in schema_columns.get(table, set()):
        if _phrase_in_query(query, column) or _phrase_in_query(query, column.replace("_", " ")):
            score += 3
    return score


def _pick_primary_table(query: str, docs: list[Document]) -> str:
    scores = {table: _table_score(query, table) for table in schema_tables}
    for idx, doc in enumerate(docs[:5]):
        table = doc.metadata["table"].lower()
        scores[table] = scores.get(table, 0) + max(1, 5 - idx)
    best_table, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0 and docs:
        return docs[0].metadata["table"].lower()
    return best_table


def _requested_columns(query: str, table: str) -> list[str]:
    if _has_any(query, ["all columns", "everything", "all fields"]):
        return ["*"]

    selected: list[str] = []
    for column in schema_column_order.get(table, []):
        column_text = column.replace("_", " ")
        hints = COLUMN_QUERY_HINTS.get(table, {}).get(column, set())
        if (
            _phrase_in_query(query, column)
            or _phrase_in_query(query, column_text)
            or _has_any(query, hints)
        ):
            selected.append(column)

    label_column = PRIMARY_LABEL_COLUMNS.get(table)
    if selected and label_column and label_column not in selected:
        selected.insert(0, label_column)
    if selected:
        return selected

    defaults = [
        column for column in DEFAULT_DISPLAY_COLUMNS.get(table, [])
        if column in schema_columns.get(table, set())
    ]
    return defaults or schema_column_order.get(table, [])[:6] or ["*"]


def _select_columns(table: str, columns: list[str], alias: str | None = None) -> str:
    if columns == ["*"]:
        return f"{alias}.*" if alias else "*"
    if alias:
        return ", ".join(f"{alias}.{column}" for column in columns)
    return ", ".join(columns)


def _filters_for_table(query: str, table: str, alias: str) -> list[str]:
    filters: list[str] = []

    if table == "employees":
        if _phrase_in_query(query, "gmail"):
            filters.append(f"LOWER({alias}.email) LIKE '%gmail%'")
        if _phrase_in_query(query, "qa"):
            filters.append(f"(LOWER({alias}.role) = 'qa' OR LOWER({alias}.department) = 'qa')")
        if _phrase_in_query(query, "devops"):
            filters.append(f"(LOWER({alias}.role) = 'devops' OR LOWER({alias}.department) = 'devops')")

    if table == "tasks" and _phrase_in_query(query, "overdue"):
        filters.append(f"{alias}.due_date < CURRENT_DATE")
        filters.append(f"LOWER({alias}.status) <> 'completed'")

    for column, values in VALUE_FILTERS.get(table, {}).items():
        for phrase, value in values.items():
            if table == "employees" and phrase in {"qa", "devops"}:
                continue
            if _phrase_in_query(query, phrase):
                filters.append(f"LOWER({alias}.{column}) = '{value.lower()}'")

    unique_filters: list[str] = []
    for item in filters:
        if item not in unique_filters:
            unique_filters.append(item)
    return unique_filters


def _where_clause(query: str, aliases: dict[str, str]) -> str:
    filters: list[str] = []
    for table, alias in aliases.items():
        filters.extend(_filters_for_table(query, table, alias))
    if not filters:
        return ""
    return "WHERE " + " AND ".join(filters)


def _aggregate_for_query(query: str, table: str, alias: str) -> tuple[str, str]:
    if table == "time_logs" and _has_any(query, ["hours", "time spent", "time"]):
        if _is_average_request(query):
            return f"AVG({alias}.hours_spent) AS average_hours", "average_hours"
        return f"SUM({alias}.hours_spent) AS total_hours", "total_hours"

    if table == "projects" and _phrase_in_query(query, "budget"):
        if _is_average_request(query):
            return f"AVG({alias}.budget) AS average_budget", "average_budget"
        if _has_any(query, ["maximum", "max"]):
            return f"MAX({alias}.budget) AS highest_budget", "highest_budget"
        if _has_any(query, ["minimum", "min"]):
            return f"MIN({alias}.budget) AS lowest_budget", "lowest_budget"
        if _is_total_request(query):
            return f"SUM({alias}.budget) AS total_budget", "total_budget"

    id_columns = [column for column in schema_column_order.get(table, []) if column.endswith("_id")]
    count_column = id_columns[0] if id_columns else "*"
    target = f"{alias}.{count_column}" if count_column != "*" else "*"
    return f"COUNT({target}) AS record_count", "record_count"


def _group_column(query: str, table: str) -> str | None:
    for column in schema_column_order.get(table, []):
        if column.endswith("_id") and not _phrase_in_query(query, column.replace("_", " ")):
            continue
        hints = COLUMN_QUERY_HINTS.get(table, {}).get(column, set())
        if (
            _phrase_in_query(query, column)
            or _phrase_in_query(query, column.replace("_", " "))
            or _has_any(query, hints)
        ):
            return column

    common_groups = {
        "employees": ["department", "role", "status"],
        "clients": ["industry"],
        "projects": ["status", "client_id"],
        "project_team": ["project_id", "employee_id", "role_in_project"],
        "tasks": ["status", "priority", "assigned_to", "project_id"],
        "time_logs": ["employee_id", "task_id", "log_date"],
        "bugs": ["severity", "status", "assigned_to", "reported_by", "project_id"],
    }
    for column in common_groups.get(table, []):
        if column in schema_columns.get(table, set()) and _phrase_in_query(query, column.replace("_", " ")):
            return column
    return None


def _order_clause(
    query: str,
    table: str,
    alias: str,
    aggregate_alias: str | None = None,
) -> str:
    if aggregate_alias and _wants_order(query):
        if _has_any(query, ["lowest", "least", "minimum", "min", "smallest"]):
            return f"ORDER BY {aggregate_alias} ASC"
        return f"ORDER BY {aggregate_alias} DESC"

    if table == "projects" and _phrase_in_query(query, "budget"):
        if _has_any(query, ["lowest", "least", "minimum", "min", "smallest"]):
            return f"ORDER BY {alias}.budget ASC"
        if _has_any(query, ["top", "highest", "most", "largest", "maximum", "max"]):
            return f"ORDER BY {alias}.budget DESC"

    if table == "time_logs" and _has_any(query, ["hours", "time spent"]):
        if _has_any(query, ["lowest", "least", "minimum", "min"]):
            return f"ORDER BY {alias}.hours_spent ASC"
        if _has_any(query, ["top", "highest", "most", "largest", "maximum", "max"]):
            return f"ORDER BY {alias}.hours_spent DESC"

    date_column = "due_date" if table == "tasks" and _has_any(query, ["due", "deadline"]) else DATE_ORDER_COLUMNS.get(table)
    if date_column:
        if _has_any(query, ["oldest", "earliest", "first"]):
            return f"ORDER BY {alias}.{date_column} ASC"
        if _has_any(query, ["latest", "recent", "newest", "last"]):
            return f"ORDER BY {alias}.{date_column} DESC"

    return ""


def _assemble_sql(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line).rstrip(";") + ";"


def _employee_project_sql(query: str) -> str:
    limit_clause = _limit_clause(query)
    where = _where_clause(query, {"employees": "e"})
    wants_projects_per_employee = (
        _has_any(query, ["by employee", "per employee", "each employee"])
        or (
            _has_any(query, ["employee", "employees"])
            and _has_any(query, ["project count", "number of projects", "count of projects"])
        )
    )
    if _is_count_request(query) and wants_projects_per_employee:
        return _assemble_sql([
            "SELECT",
            "  e.full_name,",
            "  COUNT(DISTINCT p.project_id) AS project_count",
            "FROM employees e",
            "JOIN project_team pt ON e.employee_id = pt.employee_id",
            "JOIN projects p ON pt.project_id = p.project_id",
            where,
            "GROUP BY e.full_name",
            _order_clause(query, "project_team", "pt", "project_count"),
            limit_clause,
        ])

    if _is_count_request(query) and _has_any(query, ["by project", "per project", "each project"]):
        return _assemble_sql([
            "SELECT",
            "  p.project_name,",
            "  COUNT(DISTINCT e.employee_id) AS employee_count",
            "FROM projects p",
            "JOIN project_team pt ON p.project_id = pt.project_id",
            "JOIN employees e ON pt.employee_id = e.employee_id",
            where,
            "GROUP BY p.project_name",
            _order_clause(query, "project_team", "pt", "employee_count"),
            limit_clause,
        ])

    return _assemble_sql([
        "SELECT",
        "  e.full_name,",
        "  p.project_name,",
        "  pt.role_in_project,",
        "  pt.assigned_at",
        "FROM project_team pt",
        "JOIN employees e ON pt.employee_id = e.employee_id",
        "JOIN projects p ON pt.project_id = p.project_id",
        where,
        _order_clause(query, "project_team", "pt"),
        limit_clause,
    ])


def _project_client_sql(query: str) -> str:
    limit_clause = _limit_clause(query)
    where = _where_clause(query, {"projects": "p", "clients": "c"})
    if _is_count_request(query) or _is_group_request(query):
        return _assemble_sql([
            "SELECT",
            "  c.client_name,",
            "  COUNT(p.project_id) AS project_count",
            "FROM clients c",
            "LEFT JOIN projects p ON p.client_id = c.client_id",
            where,
            "GROUP BY c.client_name",
            _order_clause(query, "projects", "p", "project_count"),
            limit_clause,
        ])

    return _assemble_sql([
        "SELECT",
        "  p.project_name,",
        "  c.client_name,",
        "  p.status,",
        "  p.start_date,",
        "  p.end_date,",
        "  p.budget",
        "FROM projects p",
        "JOIN clients c ON p.client_id = c.client_id",
        where,
        _order_clause(query, "projects", "p"),
        limit_clause,
    ])


def _task_sql(query: str) -> str:
    limit_clause = _limit_clause(query)
    where = _where_clause(query, {"tasks": "t"})

    if _is_count_request(query) and _has_any(query, ["by project", "per project", "each project"]):
        return _assemble_sql([
            "SELECT",
            "  p.project_name,",
            "  COUNT(t.task_id) AS task_count",
            "FROM projects p",
            "LEFT JOIN tasks t ON t.project_id = p.project_id",
            where,
            "GROUP BY p.project_name",
            _order_clause(query, "tasks", "t", "task_count"),
            limit_clause,
        ])

    if _is_count_request(query) and _has_any(query, ["by employee", "per employee", "each employee", "by assignee"]):
        return _assemble_sql([
            "SELECT",
            "  e.full_name,",
            "  COUNT(t.task_id) AS task_count",
            "FROM employees e",
            "LEFT JOIN tasks t ON t.assigned_to = e.employee_id",
            where,
            "GROUP BY e.full_name",
            _order_clause(query, "tasks", "t", "task_count"),
            limit_clause,
        ])

    group_column = _group_column(query, "tasks")
    if _is_count_request(query) and group_column in {"status", "priority"}:
        return _assemble_sql([
            "SELECT",
            f"  t.{group_column},",
            "  COUNT(t.task_id) AS task_count",
            "FROM tasks t",
            where,
            f"GROUP BY t.{group_column}",
            _order_clause(query, "tasks", "t", "task_count"),
            limit_clause,
        ])

    return _assemble_sql([
        "SELECT",
        "  t.title,",
        "  p.project_name,",
        "  e.full_name AS assigned_employee,",
        "  t.priority,",
        "  t.status,",
        "  t.due_date",
        "FROM tasks t",
        "JOIN projects p ON t.project_id = p.project_id",
        "JOIN employees e ON t.assigned_to = e.employee_id",
        where,
        _order_clause(query, "tasks", "t"),
        limit_clause,
    ])


def _bug_sql(query: str) -> str:
    limit_clause = _limit_clause(query)
    where = _where_clause(query, {"bugs": "b"})

    if _is_count_request(query) and _has_any(query, ["by project", "per project", "each project"]):
        return _assemble_sql([
            "SELECT",
            "  p.project_name,",
            "  COUNT(b.bug_id) AS bug_count",
            "FROM projects p",
            "LEFT JOIN bugs b ON b.project_id = p.project_id",
            where,
            "GROUP BY p.project_name",
            _order_clause(query, "bugs", "b", "bug_count"),
            limit_clause,
        ])

    if _is_count_request(query) and _has_any(query, ["by severity", "per severity", "each severity"]):
        return _assemble_sql([
            "SELECT",
            "  b.severity,",
            "  COUNT(b.bug_id) AS bug_count",
            "FROM bugs b",
            where,
            "GROUP BY b.severity",
            _order_clause(query, "bugs", "b", "bug_count"),
            limit_clause,
        ])

    if _is_count_request(query) and _has_any(query, ["by status", "per status", "each status"]):
        return _assemble_sql([
            "SELECT",
            "  b.status,",
            "  COUNT(b.bug_id) AS bug_count",
            "FROM bugs b",
            where,
            "GROUP BY b.status",
            _order_clause(query, "bugs", "b", "bug_count"),
            limit_clause,
        ])

    return _assemble_sql([
        "SELECT",
        "  b.bug_id,",
        "  p.project_name,",
        "  assignee.full_name AS assigned_employee,",
        "  reporter.full_name AS reported_by_employee,",
        "  b.severity,",
        "  b.status,",
        "  b.created_at",
        "FROM bugs b",
        "JOIN projects p ON b.project_id = p.project_id",
        "LEFT JOIN employees assignee ON b.assigned_to = assignee.employee_id",
        "LEFT JOIN employees reporter ON b.reported_by = reporter.employee_id",
        where,
        _order_clause(query, "bugs", "b"),
        limit_clause,
    ])


def _time_log_sql(query: str) -> str:
    limit_clause = _limit_clause(query)
    if _has_any(query, ["by project", "per project", "each project", "project"]):
        where = _where_clause(query, {"time_logs": "tl"})
        return _assemble_sql([
            "SELECT",
            "  p.project_name,",
            "  SUM(tl.hours_spent) AS total_hours",
            "FROM time_logs tl",
            "JOIN tasks t ON tl.task_id = t.task_id",
            "JOIN projects p ON t.project_id = p.project_id",
            where,
            "GROUP BY p.project_name",
            _order_clause(query, "time_logs", "tl", "total_hours"),
            limit_clause,
        ])

    if _has_any(query, ["by task", "per task", "each task", "task"]):
        where = _where_clause(query, {"time_logs": "tl"})
        return _assemble_sql([
            "SELECT",
            "  t.title,",
            "  SUM(tl.hours_spent) AS total_hours",
            "FROM time_logs tl",
            "JOIN tasks t ON tl.task_id = t.task_id",
            where,
            "GROUP BY t.title",
            _order_clause(query, "time_logs", "tl", "total_hours"),
            limit_clause,
        ])

    if _has_any(query, ["by employee", "per employee", "each employee", "employee"]):
        where = _where_clause(query, {"time_logs": "tl", "employees": "e"})
        return _assemble_sql([
            "SELECT",
            "  e.full_name,",
            "  SUM(tl.hours_spent) AS total_hours",
            "FROM time_logs tl",
            "JOIN employees e ON tl.employee_id = e.employee_id",
            where,
            "GROUP BY e.full_name",
            _order_clause(query, "time_logs", "tl", "total_hours"),
            limit_clause,
        ])

    where = _where_clause(query, {"time_logs": "tl"})
    return _assemble_sql([
        "SELECT",
        "  tl.log_id,",
        "  e.full_name,",
        "  t.title,",
        "  tl.hours_spent,",
        "  tl.log_date,",
        "  tl.remarks",
        "FROM time_logs tl",
        "JOIN employees e ON tl.employee_id = e.employee_id",
        "JOIN tasks t ON tl.task_id = t.task_id",
        where,
        _order_clause(query, "time_logs", "tl"),
        limit_clause,
    ])


def _single_table_sql(query: str, table: str) -> str:
    alias = _alias(table)
    limit_clause = _limit_clause(query)
    where = _where_clause(query, {table: alias})

    if _is_group_request(query):
        group_column = _group_column(query, table)
        if group_column:
            aggregate_expr, aggregate_alias = _aggregate_for_query(query, table, alias)
            return _assemble_sql([
                "SELECT",
                f"  {alias}.{group_column},",
                f"  {aggregate_expr}",
                f"FROM {table} {alias}",
                where,
                f"GROUP BY {alias}.{group_column}",
                _order_clause(query, table, alias, aggregate_alias),
                limit_clause,
            ])

    if _is_count_request(query):
        return _assemble_sql([
            "SELECT",
            "  COUNT(*) AS total_count",
            f"FROM {table} {alias}",
            where,
            limit_clause,
        ])

    aggregate_expr, _ = _aggregate_for_query(query, table, alias)
    uses_numeric_aggregate = (
        table == "time_logs"
        and _has_any(query, ["hours", "time spent", "total time", "average time"])
    ) or (
        table == "projects"
        and _phrase_in_query(query, "budget")
        and (
            _is_total_request(query)
            or _is_average_request(query)
            or _has_any(query, ["maximum", "minimum"])
        )
    )
    if uses_numeric_aggregate:
        return _assemble_sql([
            "SELECT",
            f"  {aggregate_expr}",
            f"FROM {table} {alias}",
            where,
            limit_clause,
        ])

    columns = _requested_columns(query, table)
    return _assemble_sql([
        "SELECT",
        f"  {_select_columns(table, columns, alias)}",
        f"FROM {table} {alias}",
        where,
        _order_clause(query, table, alias),
        limit_clause,
    ])


def generate_sql_fallback(query: str, docs: list[Document] | None = None) -> str:
    docs = docs or table_documents
    if not docs and not schema_tables:
        return "SELECT 1;"

    query_text = _normalise_query_text(query)

    if _has_any(query_text, ["salary", "paid", "payroll", "wage", "compensation"]):
        return "The schema does not have enough information to answer this query."

    mentions_employee = _table_score(query_text, "employees") > 0
    mentions_project = _table_score(query_text, "projects") > 0
    mentions_client = _table_score(query_text, "clients") > 0
    mentions_task = _table_score(query_text, "tasks") > 0
    mentions_bug = _table_score(query_text, "bugs") > 0
    mentions_time = _table_score(query_text, "time_logs") > 0

    if mentions_time:
        return _time_log_sql(query_text)
    if mentions_task:
        return _task_sql(query_text)
    if mentions_bug:
        return _bug_sql(query_text)
    if mentions_employee and mentions_project and {"employees", "project_team", "projects"}.issubset(schema_tables):
        return _employee_project_sql(query_text)
    if mentions_project and mentions_client and {"projects", "clients"}.issubset(schema_tables):
        return _project_client_sql(query_text)

    primary_table = _pick_primary_table(query_text, docs)
    return _single_table_sql(query_text, primary_table)


 
# 18. MAIN PIPELINE
 

def generate_sql(
    user_query: str,
    chat_session: SQLChatSession,
    max_retries: int = MAX_RETRIES,
) -> dict[str, object]:
    intent = classify_query(user_query)
    if intent == "DANGEROUS":
        sql = "Only SELECT queries are supported. Write/delete operations are blocked."
        return {
            "sql": sql,
            "insights": {
                "confidence": 0,
                "threshold": CONFIDENCE_THRESHOLD,
                "valid": False,
                "validation": "Blocked dangerous intent",
                "source": "Policy guard",
                "attempts": 0,
                "max_attempts": max_retries,
                "tables": [],
                "columns": [],
                "query_type": "Blocked",
                "has_limit": False,
                "summary": "Write/delete operation blocked",
            },
        }
    if intent == "META":
        sql = f"Available tables: {', '.join(sorted(schema_tables))}"
        return {
            "sql": sql,
            "insights": {
                "confidence": 100,
                "threshold": CONFIDENCE_THRESHOLD,
                "valid": True,
                "validation": "Schema metadata response",
                "source": "Schema metadata",
                "attempts": 0,
                "max_attempts": max_retries,
                "tables": sorted(schema_tables),
                "columns": [],
                "query_type": "Metadata",
                "has_limit": False,
                "summary": "Schema metadata response",
            },
        }

    normalised = rewrite_query(user_query)

    docs, col_hints = hybrid_retrieve(normalised)
    retrieved_tables = [d.metadata["table"].lower() for d in docs]
    log_step(f"\n[retrieve] Retrieved tables: {retrieved_tables}")
    if col_hints:
        log_step(f"[retrieve] Column hints: {col_hints}")

    schema_context = "\n\n---\n\n".join(doc.page_content for doc in docs)
    join_hints = build_join_hints(retrieved_tables)
    if join_hints:
        log_step(f"[retrieve] Join hints:\n{join_hints}")

    history_context = chat_session.get_context()

    if llm is None:
        sql = generate_sql_fallback(user_query, docs)
        log_step("[local] Generated SQL without an LLM or API key")
        log_step(f"[fallback] SQL: {sql}")
        chat_session.add(user_query, sql)
        return {
            "sql": sql,
            "insights": build_query_insights(
                sql,
                user_query,
                source="Local rule-based engine",
                attempts=0,
                validation_note="Generated locally without an LLM or API key",
            ),
        }

    for attempt in range(1, max_retries + 1):
        prompt = build_prompt(
            schema_context,
            normalised,
            join_hints,
            col_hints,
            history_context,
        )
        try:
            response = llm.invoke(prompt)
        except Exception as exc:
            log_step(f"[llm] Attempt {attempt}/{max_retries} failed: {exc}")
            sql = generate_sql_fallback(user_query, docs)
            chat_session.add(user_query, sql)
            return {
                "sql": sql,
                "insights": build_query_insights(
                    sql,
                    user_query,
                    source="Local rule-based engine",
                    attempts=attempt - 1,
                    validation_note=f"LLM unavailable: {exc}",
                ),
            }

        sql = response.content.strip()
        sql = re.sub(r"^```[a-zA-Z]*\n?", "", sql).rstrip("`").strip()

        if sql.upper().strip() == "NOT_POSSIBLE":
            sql = "The schema does not have enough information to answer this query."
            return {
                "sql": sql,
                "insights": {
                    "confidence": 0,
                    "threshold": CONFIDENCE_THRESHOLD,
                    "valid": False,
                    "validation": "Schema does not contain enough information",
                    "source": "LLM validated",
                    "attempts": attempt,
                    "max_attempts": max_retries,
                    "tables": retrieved_tables,
                    "columns": col_hints,
                    "query_type": "Not possible",
                    "has_limit": False,
                    "summary": "Not possible from current schema",
                },
            }

        is_valid, val_msg = validate_sql(sql)

        if is_valid and DB_PATH:
            exec_ok, exec_msg = execution_validate(sql)
            if not exec_ok:
                is_valid, val_msg = False, f"DB execution error: {exec_msg}"

        score = confidence_score(sql, is_valid, user_query)

        log_step(
            f"\n[llm] Attempt {attempt}/{max_retries} | "
            f"Valid: {is_valid} | Score: {score}/100 | {val_msg}"
        )
        log_step(f"[llm] SQL: {sql}")

        if is_valid and score >= CONFIDENCE_THRESHOLD:
            chat_session.add(user_query, sql)
            return {
                "sql": sql,
                "insights": build_query_insights(
                    sql,
                    user_query,
                    source="LLM validated",
                    attempts=attempt,
                    validation_note=val_msg,
                ),
            }

        if attempt < max_retries:
            history_context += (
                f"\n\n[ATTEMPT {attempt} FAILED - Reason: {val_msg}. "
                "Fix this mistake before generating again.]\n"
                f"Bad SQL was: {sql}"
            )

    sql = "Could not generate a reliable SQL query after maximum retries."
    return {
        "sql": sql,
        "insights": {
            "confidence": 0,
            "threshold": CONFIDENCE_THRESHOLD,
            "valid": False,
            "validation": "Maximum retries exhausted",
            "source": "LLM retries",
            "attempts": max_retries,
            "max_attempts": max_retries,
            "tables": retrieved_tables,
            "columns": col_hints,
            "query_type": "Retry failure",
            "has_limit": False,
            "summary": "Generation did not pass validation",
        },
    }


 
# 18. ROUTES
 

@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "schema_tables": sorted(schema_tables),
        "columns": len(column_documents),
    })


@app.route("/sql", methods=["GET", "POST", "OPTIONS"])
@app.route("/sql/", methods=["GET", "POST", "OPTIONS"])
def sql_api():
    if request.method == "OPTIONS":
        return ("", 204)

    if request.method == "GET":
        return jsonify({
            "status": "ok",
            "message": "Send POST JSON to this endpoint: {'query': 'your request'}",
        })

    try:
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or "").strip()
        reset = data.get("reset", False)

        if reset or query.lower() == "reset":
            session.clear()
            log_step("[session] Chat session reset")
            return jsonify({
                "query": query,
                "sql": "-- Chat session reset.",
                "message": "Session reset.",
                "insights": {
                    "confidence": 100,
                    "threshold": CONFIDENCE_THRESHOLD,
                    "valid": True,
                    "validation": "Session reset",
                    "source": "Session",
                    "attempts": 0,
                    "max_attempts": MAX_RETRIES,
                    "tables": [],
                    "columns": [],
                    "query_type": "Session",
                    "has_limit": False,
                    "summary": "Chat memory cleared",
                },
            })

        if not query:
            return jsonify({"error": "query is required"}), 400

        log_step("")
        log_step(f"[request] User query: {query}")
        result = generate_sql(query, session)

        return jsonify({
            "query": query,
            "sql": result["sql"],
            "message": "Generated using RAG schema retrieval.",
            "insights": result["insights"],
        })

    except Exception as exc:
        log_step(f"[error] {exc}")
        return jsonify({"error": str(exc)}), 500


 
# 19. RUN
 

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    Timer(1, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="0.0.0.0", port=port, debug=True)
