from __future__ import annotations

import os
import re
import io
import json
import sqlite3
import time
import webbrowser
from collections import deque
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from threading import Timer

import pandas as pd
from flask import Flask, g, jsonify, make_response, request, send_from_directory
from agentic.custody_balance_domain import (
    CUSTODY_BALANCE_ALIASES,
    CUSTODY_BALANCE_COLUMN_HINTS,
    CUSTODY_BALANCE_DEFAULT_DISPLAY_COLUMNS,
    CUSTODY_BALANCE_LABEL_COLUMNS,
    CUSTODY_BALANCE_RELATIONSHIPS,
    CUSTODY_BALANCE_SCHEMA_TABLES,
    CUSTODY_BALANCE_TABLE_HINTS,
)
from agentic.enterprise_copilot import EnterpriseSQLCopilot
try:
    from backend.auth import AuthStore, SlidingWindowRateLimiter
    from backend.email_delivery import load_email_config, password_reset_url, send_password_reset_email, send_test_email
    from backend.llm_providers import SUPPORTED_PROVIDERS, create_llm_provider, load_provider_config
    from backend.runtime_config import configure_runtime_paths, env_path, load_dotenv_file, resolve_path
    from backend.spider_rag import SpiderTextSqlRag
    from backend.synthetic_enterprise_data import SchemaRequestRepository, SyntheticEnterpriseDataEngine
except ImportError:  # pragma: no cover - supports direct python backend/app.py execution
    from auth import AuthStore, SlidingWindowRateLimiter
    from email_delivery import load_email_config, password_reset_url, send_password_reset_email, send_test_email
    from llm_providers import SUPPORTED_PROVIDERS, create_llm_provider, load_provider_config
    from runtime_config import configure_runtime_paths, env_path, load_dotenv_file, resolve_path
    from spider_rag import SpiderTextSqlRag
    from synthetic_enterprise_data import SchemaRequestRepository, SyntheticEnterpriseDataEngine

from rl.environment.sql_env import (
    ACTION_NAMES,
    SQLQueryOptimizationEnv,
    SQLState,
    compute_reward,
    ensure_feedback_table,
    execute_sql_for_stats,
    store_experience,
)

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

try:
    from asgiref.wsgi import WsgiToAsgi
except ImportError:
    WsgiToAsgi = None


 
# 1. CONFIG
 

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


load_dotenv_file(ROOT_DIR / ".env")
RUNTIME_PATHS = configure_runtime_paths(ROOT_DIR)
RUNTIME_PROVIDER_ENV_FILE = RUNTIME_PATHS.runtime_root / "secrets" / "provider.env"
RUNTIME_EMAIL_ENV_FILE = RUNTIME_PATHS.runtime_root / "secrets" / "email.env"
if not _env_truthy("SQL_COPILOT_DISABLE_RUNTIME_SECRETS"):
    load_dotenv_file(RUNTIME_PROVIDER_ENV_FILE, override=True)
    load_dotenv_file(RUNTIME_EMAIL_ENV_FILE, override=True)
DATA_DIR = env_path("SQL_COPILOT_DATA_DIR", BASE_DIR / "data", RUNTIME_PATHS.project_root)
STATIC_DIR = BASE_DIR / "static"

PROVIDER_CONFIG = load_provider_config(RUNTIME_PATHS.model_root)
USE_REMOTE_LLM = PROVIDER_CONFIG.chat_enabled
BASE_URL = PROVIDER_CONFIG.base_url
API_KEY = PROVIDER_CONFIG.api_key or ("ollama" if PROVIDER_CONFIG.provider == "ollama" else "")

SCHEMA_FILE = env_path("SCHEMA_FILE", DATA_DIR / "RAG_DOC.xlsx", RUNTIME_PATHS.project_root)
if not SCHEMA_FILE.exists() and (ROOT_DIR / "RAG_DOC .xlsx").exists():
    SCHEMA_FILE = ROOT_DIR / "RAG_DOC .xlsx"
SPIDER_TEXT_SQL_FILE = env_path(
    "SPIDER_TEXT_SQL_FILE",
    ROOT_DIR / "spider_text_sql.csv",
    RUNTIME_PATHS.project_root,
)
FAISS_TABLE_INDEX_PATH = str(env_path("FAISS_TABLE_INDEX_PATH", RUNTIME_PATHS.faiss_root / "table_index", RUNTIME_PATHS.project_root))
FAISS_COL_INDEX_PATH = str(env_path("FAISS_COL_INDEX_PATH", RUNTIME_PATHS.faiss_root / "column_index", RUNTIME_PATHS.project_root))
DYNAMIC_SCHEMA_FILE = env_path(
    "DYNAMIC_SCHEMA_FILE",
    RUNTIME_PATHS.runtime_root / "dynamic_schema.json",
    RUNTIME_PATHS.project_root,
)

DB_PATH = (
    str(env_path("SQL_COPILOT_EXECUTION_DB_PATH", RUNTIME_PATHS.sqlite_root / "execution.sqlite", RUNTIME_PATHS.project_root))
    if os.getenv("SQL_COPILOT_EXECUTION_DB_PATH")
    else None
)
FEEDBACK_DB_PATH = str(env_path("AGENT_FEEDBACK_DB_PATH", RUNTIME_PATHS.sqlite_root / "sql_agent_feedback.sqlite", RUNTIME_PATHS.project_root))
AUTH_DB_PATH = str(env_path("AUTH_DB_PATH", RUNTIME_PATHS.sqlite_root / "sql_copilot.db", RUNTIME_PATHS.project_root))
AUTH_JWT_SECRET = os.getenv("AUTH_JWT_SECRET", "")
SCHEMA_REQUEST_DB_PATH = str(resolve_path(os.getenv("SCHEMA_REQUEST_DB_PATH"), Path(AUTH_DB_PATH), RUNTIME_PATHS.project_root))
LEGACY_RL_MODEL_PATH = ROOT_DIR / "rl" / "models" / "sql_ppo_agent.zip"
DEFAULT_RL_MODEL_PATH = RUNTIME_PATHS.model_root / "rl" / "sql_ppo_agent.zip"
if not os.getenv("RL_MODEL_PATH") and LEGACY_RL_MODEL_PATH.exists():
    DEFAULT_RL_MODEL_PATH = LEGACY_RL_MODEL_PATH
RL_MODEL_PATH = str(env_path("RL_MODEL_PATH", DEFAULT_RL_MODEL_PATH, RUNTIME_PATHS.project_root))
RL_ENABLED = os.getenv("RL_ENABLED", "1").lower() in {"1", "true", "yes"}
APP_ENV = os.getenv("APP_ENV", "development").lower()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:4000").rstrip("/")
FRONTEND_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_ORIGINS", FRONTEND_ORIGIN).split(",")
    if origin.strip()
}
if APP_ENV != "production":
    FRONTEND_ORIGINS.update({
        "http://127.0.0.1:4000",
        "http://localhost:4000",
    })
COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "1" if APP_ENV == "production" else "0").lower() in {"1", "true", "yes"}
ACCESS_COOKIE = "sql_copilot_access"
CSRF_COOKIE = "sql_copilot_csrf"
MAX_RETRIES = PROVIDER_CONFIG.max_generation_retries
CONFIDENCE_THRESHOLD = int(os.getenv("CONFIDENCE_LOW_THRESHOLD", "75"))

http_client = (
    httpx.Client(verify=False)
    if USE_REMOTE_LLM and httpx is not None
    else None
)

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
if CORS:
    CORS(
        app,
        origins=sorted(FRONTEND_ORIGINS),
        supports_credentials=True,
        allow_headers=["Content-Type", "X-CSRF-Token"],
        methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    )

asgi_app = WsgiToAsgi(app) if WsgiToAsgi else None


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in FRONTEND_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers.add("Vary", "Origin")
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


def log_step(message: str) -> None:
    print(message, flush=True)


ensure_feedback_table(FEEDBACK_DB_PATH)
auth_store = AuthStore(Path(AUTH_DB_PATH), signing_secret=AUTH_JWT_SECRET)
schema_request_repo = SchemaRequestRepository(Path(SCHEMA_REQUEST_DB_PATH))
synthetic_enterprise_engine = SyntheticEnterpriseDataEngine(
    int(os.getenv("ENTERPRISE_SYNTHETIC_TABLES", "180"))
)
EMAIL_CONFIG = load_email_config(RUNTIME_PATHS.runtime_root, FRONTEND_ORIGIN)
rate_limiter = SlidingWindowRateLimiter()

if os.getenv("BOOTSTRAP_ADMIN_EMAIL") and os.getenv("BOOTSTRAP_ADMIN_PASSWORD"):
    auth_store.bootstrap_admin(
        os.getenv("BOOTSTRAP_ADMIN_NAME", "SQL Copilot Admin"),
        os.getenv("BOOTSTRAP_ADMIN_EMAIL", ""),
        os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""),
    )


PUBLIC_PATHS = {
    "/",
    "/health",
    "/favicon.ico",
    "/legacy",
    "/auth/login",
    "/auth/signup",
    "/auth/forgot-password",
    "/auth/reset-password",
}


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",", 1)[0].strip() or request.remote_addr or "")[:128]


def _rate_limit(scope: str, limit: int, window_seconds: int):
    key = f"{scope}:{_client_ip()}"
    if rate_limiter.allow(key, limit, window_seconds, time.monotonic()):
        return None
    return jsonify({"error": "Too many requests. Please try again later."}), 429


def _set_auth_cookies(response, session_data: dict[str, object]) -> None:
    max_age = max(
        0,
        int((session_data["expires_at"] - datetime.now(timezone.utc)).total_seconds()),
    )
    response.set_cookie(
        ACCESS_COOKIE,
        str(session_data["token"]),
        max_age=max_age,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="Lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        str(session_data["csrf_token"]),
        max_age=max_age,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite="Lax",
        path="/",
    )


def _clear_auth_cookies(response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/", secure=COOKIE_SECURE, samesite="Lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=COOKIE_SECURE, samesite="Lax")


@app.before_request
def authenticate_request():
    if request.method == "OPTIONS" or request.path in PUBLIC_PATHS:
        return None
    token = request.cookies.get(ACCESS_COOKIE, "")
    authorization = request.headers.get("Authorization", "")
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    validated = auth_store.validate_session(token) if token else None
    if not validated:
        response = jsonify({"error": "Authentication required.", "code": "AUTH_REQUIRED"})
        response.status_code = 401
        _clear_auth_cookies(response)
        return response
    g.current_user, g.auth_session = validated
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        header_token = request.headers.get("X-CSRF-Token", "")
        cookie_token = request.cookies.get(CSRF_COOKIE, "")
        expected = str(g.auth_session["csrf_token"])
        if not header_token or header_token != cookie_token or header_token != expected:
            return jsonify({"error": "CSRF validation failed.", "code": "CSRF_FAILED"}), 403
    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "current_user", {}).get("role") != "admin":
            return jsonify({"error": "Administrator access required."}), 403
        return view(*args, **kwargs)

    return wrapped


def provider_config_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if APP_ENV == "production" and getattr(g, "current_user", {}).get("role") != "admin":
            return jsonify({"error": "Administrator access required."}), 403
        return view(*args, **kwargs)

    return wrapped

try:
    from rl.agent.ppo_agent import PPOAgent
except ImportError:
    PPOAgent = None

ppo_agent = None
enterprise_copilot = None
spider_text_sql_rag = None


 
# 2. MODELS
 

def _create_http_client(provider_config):
    if provider_config.chat_enabled and httpx is not None:
        return httpx.Client(verify=False)
    return None


def _create_embeddings(provider_config, provider_http_client):
    if provider_config.embeddings_enabled and OpenAIEmbeddings and provider_http_client:
        try:
            return OpenAIEmbeddings(
                base_url=provider_config.base_url,
                model=provider_config.embedding_model,
                api_key=provider_config.api_key,
                http_client=provider_http_client,
            )
        except Exception:
            log_step("[local] Remote embeddings initialization failed; using keyword/BM25 retrieval")
    else:
        log_step(
            f"[local] Remote embeddings disabled for provider '{provider_config.provider}'; "
            "using keyword/BM25 retrieval"
        )
    return None


def _log_llm_status(provider_config, provider_client) -> None:
    if provider_client.available:
        log_step(
            f"[llm] {provider_config.provider} provider ready with model "
            f"{provider_config.chat_model}"
        )
        return
    if provider_config.needs_sdk:
        log_step(
            f"[local] Provider '{provider_config.provider}' selected but no SDK adapter is configured; "
            "using deterministic SQL generation"
        )
    elif provider_config.provider == "nvidia" and not provider_config.api_key:
        log_step("[local] NVIDIA provider not configured; using deterministic fallback")
    else:
        log_step("[local] Remote LLM disabled; using deterministic SQL generation")


def reload_llm_provider(*, reset_copilot: bool = True) -> dict[str, object]:
    global PROVIDER_CONFIG, USE_REMOTE_LLM, BASE_URL, API_KEY, MAX_RETRIES
    global http_client, embeddings, LLM_PROVIDER_CLIENT, llm, enterprise_copilot

    old_http_client = globals().get("http_client")
    if old_http_client is not None:
        try:
            old_http_client.close()
        except Exception:
            pass

    PROVIDER_CONFIG = load_provider_config(RUNTIME_PATHS.model_root)
    USE_REMOTE_LLM = PROVIDER_CONFIG.chat_enabled
    BASE_URL = PROVIDER_CONFIG.base_url
    API_KEY = PROVIDER_CONFIG.api_key or ("ollama" if PROVIDER_CONFIG.provider == "ollama" else "")
    MAX_RETRIES = PROVIDER_CONFIG.max_generation_retries
    http_client = _create_http_client(PROVIDER_CONFIG)
    embeddings = _create_embeddings(PROVIDER_CONFIG, http_client)
    LLM_PROVIDER_CLIENT = create_llm_provider(
        PROVIDER_CONFIG,
        chat_client_factory=ChatOpenAI,
        http_client=http_client,
    )
    llm = LLM_PROVIDER_CLIENT.chat_client if LLM_PROVIDER_CLIENT.available else None
    if reset_copilot and "enterprise_copilot" in globals():
        enterprise_copilot = None
    _log_llm_status(PROVIDER_CONFIG, LLM_PROVIDER_CLIENT)
    return LLM_PROVIDER_CLIENT.health_check(deep=False)


http_client = None
embeddings = None
LLM_PROVIDER_CLIENT = None
llm = None
reload_llm_provider(reset_copilot=False)


PROVIDER_ENV_WRITE_ORDER = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_API_BASE",
    "NVIDIA_API_KEY",
    "LLM_API_KEY",
    "SQL_COPILOT_REMOTE_LLM",
    "LLM_TEMPERATURE",
    "LLM_TOP_P",
    "LLM_MAX_TOKENS",
    "LLM_MAX_RETRIES",
    "LLM_TIMEOUT_SECONDS",
    "LLM_PROVIDER_FAILURE_COOLDOWN_SECONDS",
)

EMAIL_ENV_WRITE_ORDER = (
    "EMAIL_BACKEND",
    "EMAIL_OUTBOX_DIR",
    "PASSWORD_RESET_BASE_URL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_USE_TLS",
    "SMTP_USE_SSL",
    "SMTP_TIMEOUT_SECONDS",
)


def _provider_default_settings(provider: str) -> dict[str, str]:
    if provider == "nvidia":
        return {
            "model": "openai/gpt-oss-20b",
            "base_url": "https://integrate.api.nvidia.com/v1",
        }
    if provider == "openai":
        return {"model": "", "base_url": "https://api.openai.com/v1"}
    if provider == "ollama":
        return {"model": "llama3.1", "base_url": "http://127.0.0.1:11434/v1"}
    if provider == "local":
        return {"model": "deterministic", "base_url": ""}
    return {"model": PROVIDER_CONFIG.chat_model, "base_url": PROVIDER_CONFIG.base_url}


def _provider_api_key_name(provider: str) -> str:
    if provider == "nvidia":
        return "NVIDIA_API_KEY"
    return "LLM_API_KEY"


def _read_runtime_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def _read_provider_env_file() -> dict[str, str]:
    return _read_runtime_env_file(RUNTIME_PROVIDER_ENV_FILE)


def _clean_provider_env_value(value: object, *, name: str) -> str:
    text = "" if value is None else str(value).strip()
    if "\n" in text or "\r" in text:
        raise ValueError(f"{name} cannot contain line breaks.")
    return text


def _write_runtime_env_file(path: Path, values: dict[str, str], order: tuple[str, ...], header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        header,
        "# This file is generated by the Settings page and is ignored by git.",
    ]
    for name in order:
        value = values.get(name)
        if value is not None and value != "":
            lines.append(f"{name}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_provider_env_file(values: dict[str, str]) -> None:
    _write_runtime_env_file(
        RUNTIME_PROVIDER_ENV_FILE,
        values,
        PROVIDER_ENV_WRITE_ORDER,
        "# SQL Copilot local LLM provider settings.",
    )


def _current_provider_payload(*, deep: bool = False) -> dict[str, object]:
    status = LLM_PROVIDER_CLIENT.health_check(deep=deep)
    runtime_values = _read_provider_env_file()
    return {
        "selected": PROVIDER_CONFIG.provider,
        "adapter": PROVIDER_CONFIG.adapter,
        "remote_enabled": bool(LLM_PROVIDER_CLIENT.available),
        "api_key_present": bool(PROVIDER_CONFIG.api_key),
        "embeddings_enabled": bool(embeddings),
        "chat_model": PROVIDER_CONFIG.chat_model,
        "embedding_model": PROVIDER_CONFIG.embedding_model,
        "local_model": PROVIDER_CONFIG.local_model,
        "supported": list(SUPPORTED_PROVIDERS),
        "status": status,
        "timeout_seconds": PROVIDER_CONFIG.timeout_seconds,
        "max_retries": PROVIDER_CONFIG.max_retries,
        "temperature": PROVIDER_CONFIG.temperature,
        "top_p": PROVIDER_CONFIG.top_p,
        "max_tokens": PROVIDER_CONFIG.max_tokens,
        "max_generation_retries": PROVIDER_CONFIG.max_generation_retries,
        "runtime_configured": RUNTIME_PROVIDER_ENV_FILE.exists(),
        "runtime_config_path": str(RUNTIME_PROVIDER_ENV_FILE),
        "runtime_config_provider": runtime_values.get("LLM_PROVIDER", ""),
    }


def _apply_runtime_provider_config(payload: dict[str, object]) -> dict[str, object]:
    provider = _clean_provider_env_value(
        payload.get("provider") or PROVIDER_CONFIG.provider or "nvidia",
        name="provider",
    ).lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider '{provider}'.")

    defaults = _provider_default_settings(provider)
    current_runtime_values = _read_provider_env_file()
    model = _clean_provider_env_value(
        payload.get("model") or defaults["model"],
        name="model",
    )
    base_url = _clean_provider_env_value(
        payload.get("base_url") or defaults["base_url"],
        name="base_url",
    ).rstrip("/")
    if provider == "local":
        model = defaults["model"]
        base_url = defaults["base_url"]
    elif provider == "nvidia":
        if model in {"", "deterministic"}:
            model = defaults["model"]
        if not base_url:
            base_url = defaults["base_url"]
    elif provider not in {"ollama"} and not model:
        raise ValueError(f"{provider} model is required.")
    api_key = _clean_provider_env_value(payload.get("api_key"), name="api_key")
    api_key_name = _provider_api_key_name(provider)
    runtime_api_key = "" if provider == "local" else (
        current_runtime_values.get(api_key_name)
        or current_runtime_values.get("LLM_API_KEY", "")
    )
    environment_api_key = "" if provider == "local" else (
        (
            os.getenv("NVIDIA_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("SQL_COPILOT_LLM_API_KEY")
            or ""
        )
        if provider == "nvidia"
        else (
            os.getenv(f"{provider.upper()}_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("SQL_COPILOT_LLM_API_KEY")
            or ""
        )
    )
    effective_api_key = api_key or runtime_api_key or environment_api_key
    if provider not in {"local", "ollama"} and not effective_api_key:
        raise ValueError(f"{provider} API key is required.")

    values: dict[str, str] = {
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model,
        "LLM_API_BASE": base_url,
        "SQL_COPILOT_REMOTE_LLM": "0" if provider == "local" else "1",
        "LLM_TEMPERATURE": _clean_provider_env_value(
            payload.get("temperature") if payload.get("temperature") is not None else PROVIDER_CONFIG.temperature,
            name="temperature",
        ),
        "LLM_TOP_P": _clean_provider_env_value(
            payload.get("top_p") if payload.get("top_p") is not None else PROVIDER_CONFIG.top_p,
            name="top_p",
        ),
        "LLM_MAX_TOKENS": _clean_provider_env_value(
            payload.get("max_tokens") if payload.get("max_tokens") is not None else PROVIDER_CONFIG.max_tokens,
            name="max_tokens",
        ),
        "LLM_MAX_RETRIES": _clean_provider_env_value(
            payload.get("max_retries") if payload.get("max_retries") is not None else PROVIDER_CONFIG.max_retries,
            name="max_retries",
        ),
        "LLM_TIMEOUT_SECONDS": _clean_provider_env_value(
            payload.get("timeout_seconds") if payload.get("timeout_seconds") is not None else PROVIDER_CONFIG.timeout_seconds,
            name="timeout_seconds",
        ),
        "LLM_PROVIDER_FAILURE_COOLDOWN_SECONDS": _clean_provider_env_value(
            payload.get("provider_failure_cooldown_seconds")
            if payload.get("provider_failure_cooldown_seconds") is not None
            else os.getenv("LLM_PROVIDER_FAILURE_COOLDOWN_SECONDS", "0"),
            name="provider_failure_cooldown_seconds",
        ),
    }
    if provider != "local" and (api_key or runtime_api_key):
        values[api_key_name] = effective_api_key

    _write_provider_env_file(values)
    if provider == "local":
        for name in ("LLM_API_KEY", "NVIDIA_API_KEY", "SQL_COPILOT_LLM_API_KEY", "OPENAI_API_KEY"):
            os.environ.pop(name, None)
    else:
        stale_key_names = {"LLM_API_KEY", "NVIDIA_API_KEY", "SQL_COPILOT_LLM_API_KEY", "OPENAI_API_KEY"}
        stale_key_names.discard(api_key_name)
        for name in stale_key_names:
            os.environ.pop(name, None)
    for name, value in values.items():
        os.environ[name] = value
    if provider != "local" and effective_api_key:
        os.environ[api_key_name] = effective_api_key

    status = reload_llm_provider(reset_copilot=True)
    return {
        "provider": _current_provider_payload(deep=bool(payload.get("verify"))),
        "status": status,
    }


def reload_email_config() -> dict[str, object]:
    global EMAIL_CONFIG
    EMAIL_CONFIG = load_email_config(RUNTIME_PATHS.runtime_root, FRONTEND_ORIGIN)
    return _current_email_payload()


def _read_email_env_file() -> dict[str, str]:
    return _read_runtime_env_file(RUNTIME_EMAIL_ENV_FILE)


def _write_email_env_file(values: dict[str, str]) -> None:
    _write_runtime_env_file(
        RUNTIME_EMAIL_ENV_FILE,
        values,
        EMAIL_ENV_WRITE_ORDER,
        "# SQL Copilot local email delivery settings.",
    )


def _current_email_payload() -> dict[str, object]:
    runtime_values = _read_email_env_file()
    return {
        "backend": EMAIL_CONFIG.backend,
        "smtp_configured": EMAIL_CONFIG.smtp_configured,
        "host": EMAIL_CONFIG.host,
        "port": EMAIL_CONFIG.port,
        "username_present": bool(EMAIL_CONFIG.username),
        "password_present": bool(EMAIL_CONFIG.password),
        "sender": EMAIL_CONFIG.sender,
        "use_tls": EMAIL_CONFIG.use_tls,
        "use_ssl": EMAIL_CONFIG.use_ssl,
        "timeout_seconds": EMAIL_CONFIG.timeout_seconds,
        "outbox_dir": str(EMAIL_CONFIG.outbox_dir),
        "frontend_origin": EMAIL_CONFIG.frontend_origin,
        "runtime_configured": RUNTIME_EMAIL_ENV_FILE.exists(),
        "runtime_config_path": str(RUNTIME_EMAIL_ENV_FILE),
        "runtime_config_backend": runtime_values.get("EMAIL_BACKEND", ""),
    }


def _apply_runtime_email_config(payload: dict[str, object]) -> dict[str, object]:
    backend = _clean_provider_env_value(payload.get("backend") or EMAIL_CONFIG.backend or "smtp", name="backend").lower()
    if backend not in {"smtp", "file", "disabled"}:
        raise ValueError("Email backend must be smtp, file, or disabled.")

    current_runtime_values = _read_email_env_file()
    host = _clean_provider_env_value(payload.get("host") or EMAIL_CONFIG.host, name="host")
    port = _clean_provider_env_value(payload.get("port") or EMAIL_CONFIG.port or 587, name="port")
    username = _clean_provider_env_value(payload.get("username") or EMAIL_CONFIG.username, name="username")
    password = _clean_provider_env_value(payload.get("password"), name="password")
    sender = _clean_provider_env_value(payload.get("sender") or EMAIL_CONFIG.sender or username, name="sender")
    outbox_dir = _clean_provider_env_value(payload.get("outbox_dir") or EMAIL_CONFIG.outbox_dir, name="outbox_dir")
    frontend_origin = _clean_provider_env_value(
        payload.get("frontend_origin") or EMAIL_CONFIG.frontend_origin or FRONTEND_ORIGIN,
        name="frontend_origin",
    ).rstrip("/")
    timeout = _clean_provider_env_value(payload.get("timeout_seconds") or EMAIL_CONFIG.timeout_seconds, name="timeout_seconds")
    use_tls = "1" if bool(payload.get("use_tls", EMAIL_CONFIG.use_tls)) else "0"
    use_ssl = "1" if bool(payload.get("use_ssl", EMAIL_CONFIG.use_ssl)) else "0"

    try:
        int(port)
    except ValueError as exc:
        raise ValueError("SMTP port must be a number.") from exc
    try:
        float(timeout)
    except ValueError as exc:
        raise ValueError("SMTP timeout must be a number.") from exc

    effective_password = password or current_runtime_values.get("SMTP_PASSWORD", "") or os.getenv("SMTP_PASSWORD", "")
    if backend == "smtp" and not host:
        raise ValueError("SMTP host is required for real password reset email.")
    if backend == "smtp" and not sender:
        raise ValueError("SMTP from address is required for real password reset email.")

    values = {
        "EMAIL_BACKEND": backend,
        "EMAIL_OUTBOX_DIR": outbox_dir,
        "PASSWORD_RESET_BASE_URL": frontend_origin,
        "SMTP_HOST": host,
        "SMTP_PORT": port,
        "SMTP_USERNAME": username,
        "SMTP_FROM": sender,
        "SMTP_USE_TLS": use_tls,
        "SMTP_USE_SSL": use_ssl,
        "SMTP_TIMEOUT_SECONDS": timeout,
    }
    if password or current_runtime_values.get("SMTP_PASSWORD"):
        values["SMTP_PASSWORD"] = effective_password

    _write_email_env_file(values)
    for name, value in values.items():
        os.environ[name] = value
    if effective_password:
        os.environ["SMTP_PASSWORD"] = effective_password
    email_status = reload_email_config()
    delivery = None
    test_recipient = _clean_provider_env_value(payload.get("test_recipient"), name="test_recipient")
    if bool(payload.get("verify")) and test_recipient:
        delivery = send_test_email(EMAIL_CONFIG, test_recipient)
    return {
        "email": email_status,
        "delivery": delivery,
    }


 
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
schema_column_descriptions: dict[str, dict[str, str]] = {}
schema_table_metadata: dict[str, dict[str, object]] = {}
schema_graph: dict[str, list[tuple]] = {}
virtual_schema_columns: set[tuple[str, str]] = set()
dynamic_schema_tables: set[str] = set()

table_documents: list[Document] = []
column_documents: list[Document] = []
col_to_tables: dict[str, list[str]] = {}

for table_name, group in df.groupby("Table Name"):
    table_display = str(table_name).strip()
    t_lower = table_display.lower()
    schema_tables.add(t_lower)

    cols: set[str] = set()
    col_types: dict = {}
    col_descriptions: dict[str, str] = {}
    col_lines = ""

    for _, row in group.iterrows():
        column_display = str(row["Column Name"]).strip()
        c_lower = column_display.lower()
        description = str(row["Description"])
        cols.add(c_lower)
        col_types[c_lower] = row["Data Type"]
        col_descriptions[c_lower] = description
        col_lines += (
            f"  - {column_display} ({row['Data Type']}): "
            f"{description}\n"
        )
        col_to_tables.setdefault(c_lower, []).append(t_lower)

        column_documents.append(Document(
            page_content=(
                f"Table: {table_display} | "
                f"Column: {column_display} ({row['Data Type']}) | "
                f"Meaning: {description}"
            ),
            metadata={"table": table_display, "column": column_display},
        ))

    schema_columns[t_lower] = cols
    schema_column_order[t_lower] = [str(col).strip().lower() for col in group["Column Name"]]
    schema_column_types[t_lower] = col_types
    schema_column_descriptions[t_lower] = col_descriptions
    schema_table_metadata[t_lower] = {
        "domain": "Core Copilot Schema",
        "purpose": str(group["What this table stores"].iloc[0]).strip()
        or "Excel-backed schema table used by the active SQL copilot.",
        "owner": "data-platform",
        "tags": ["core", "excel"],
        "version": "1.0.0",
        "source": "excel",
        "last_updated": "2026-06-12",
        "business_glossary": {},
        "aliases": [table_display],
    }

    table_documents.append(Document(
        page_content=(
            f"Table: {table_display}\n"
            f"Description: {group['What this table stores'].iloc[0]}\n\n"
            f"Columns:\n{col_lines}"
        ),
        metadata={"table": table_display},
    ))

VIRTUAL_SCHEMA_EXTENSIONS = {
    "clients": [
        (
            "tier",
            "TEXT",
            "Synthetic planning dimension for client service tier "
            "(for example strategic, enterprise, growth, or standard).",
        ),
    ],
}

for table, extensions in VIRTUAL_SCHEMA_EXTENSIONS.items():
    if table not in schema_tables:
        continue
    for column, data_type, description in extensions:
        if column in schema_columns.get(table, set()):
            continue
        schema_columns[table].add(column)
        schema_column_order[table].append(column)
        schema_column_types[table][column] = data_type
        schema_column_descriptions.setdefault(table, {})[column] = description
        virtual_schema_columns.add((table, column))
        col_to_tables.setdefault(column, []).append(table)
        column_documents.append(Document(
            page_content=(
                f"Table: {table} | Column: {column} ({data_type}) | "
                f"Meaning: {description}"
            ),
            metadata={"table": table, "column": column, "source": "synthetic"},
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


def _normalise_identifier(value: object, fallback: str = "field") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return fallback
    if text[0].isdigit():
        text = f"{fallback}_{text}"
    return text


def _ensure_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def _column_payload(column: object, ordinal: int = 0) -> dict[str, object]:
    if isinstance(column, dict):
        raw_name = column.get("name") or column.get("column_name") or column.get("field")
        name = _normalise_identifier(raw_name, f"column_{ordinal + 1}")
        data_type = str(column.get("data_type") or column.get("type") or "TEXT").upper()
        description = str(column.get("description") or column.get("purpose") or "").strip()
        return {
            "name": name,
            "data_type": data_type,
            "description": description or f"Inferred column {name.replace('_', ' ')}.",
            "is_pk": bool(column.get("is_pk") or column.get("primary_key")),
            "is_fk": bool(column.get("is_fk") or column.get("foreign_key") or column.get("references")),
            "references_table": _normalise_identifier(column.get("references_table"), "")
            if column.get("references_table") else "",
            "references_column": _normalise_identifier(column.get("references_column"), "")
            if column.get("references_column") else "",
        }
    name = _normalise_identifier(column, f"column_{ordinal + 1}")
    return {
        "name": name,
        "data_type": "TEXT",
        "description": f"Inferred column {name.replace('_', ' ')}.",
        "is_pk": ordinal == 0 and name.endswith("_id"),
        "is_fk": False,
        "references_table": "",
        "references_column": "",
    }


def _relationship_payload(relationship: object, default_from_table: str) -> dict[str, str] | None:
    if isinstance(relationship, str):
        target = relationship.strip()
        if not target:
            return None
        if "." in target:
            to_table, to_column = target.split(".", 1)
        else:
            to_table = target
            to_column = f"{_normalise_identifier(target)}_id"
        to_table = _normalise_identifier(to_table, "target_table")
        to_column = _normalise_identifier(to_column, "target_id")
        return {
            "from_table": default_from_table,
            "from_column": to_column,
            "to_table": to_table,
            "to_column": to_column,
        }
    if not isinstance(relationship, dict):
        return None
    from_table = _normalise_identifier(
        relationship.get("from_table") or relationship.get("source_table") or default_from_table,
        default_from_table,
    )
    from_column = _normalise_identifier(
        relationship.get("from_column") or relationship.get("source_column") or relationship.get("column"),
        "source_id",
    )
    to_table = _normalise_identifier(
        relationship.get("to_table") or relationship.get("target_table") or relationship.get("table"),
        "target_table",
    )
    to_column = _normalise_identifier(
        relationship.get("to_column") or relationship.get("target_column") or relationship.get("references_column"),
        "target_id",
    )
    if not from_column or not to_table or not to_column:
        return None
    return {
        "from_table": from_table,
        "from_column": from_column,
        "to_table": to_table,
        "to_column": to_column,
    }


def _table_documents_for(table: str) -> tuple[Document, list[Document]]:
    metadata = schema_table_metadata.get(table, {})
    purpose = str(metadata.get("purpose") or "Dynamic enterprise schema table.")
    lines = []
    column_docs = []
    for column in schema_column_order.get(table, []):
        data_type = str(schema_column_types.get(table, {}).get(column, "TEXT"))
        description = schema_column_descriptions.get(table, {}).get(
            column,
            f"Column {column.replace('_', ' ')}.",
        )
        lines.append(f"  - {column} ({data_type}): {description}")
        column_docs.append(Document(
            page_content=(
                f"Table: {table} | Column: {column} ({data_type}) | "
                f"Meaning: {description}"
            ),
            metadata={"table": table, "column": column, "source": metadata.get("source", "dynamic")},
        ))
    table_doc = Document(
        page_content=(
            f"Table: {table}\n"
            f"Description: {purpose}\n"
            f"Domain: {metadata.get('domain', 'Dynamic Enterprise Schema')}\n\n"
            f"Columns:\n" + "\n".join(lines)
        ),
        metadata={"table": table, "source": metadata.get("source", "dynamic")},
    )
    return table_doc, column_docs


def _replace_schema_documents(table: str) -> None:
    global table_documents, column_documents
    table_documents = [
        doc for doc in table_documents
        if str(doc.metadata.get("table", "")).lower() != table
    ]
    column_documents = [
        doc for doc in column_documents
        if str(doc.metadata.get("table", "")).lower() != table
    ]
    if table not in schema_columns:
        return
    table_doc, column_docs = _table_documents_for(table)
    table_documents.append(table_doc)
    column_documents.extend(column_docs)


def _save_dynamic_schema() -> None:
    DYNAMIC_SCHEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tables": [],
    }
    for table in sorted(dynamic_schema_tables):
        if table not in schema_tables:
            continue
        metadata = schema_table_metadata.get(table, {})
        payload["tables"].append({
            "name": table,
            "domain": metadata.get("domain", "Dynamic Enterprise Schema"),
            "purpose": metadata.get("purpose", "Dynamic enterprise schema table."),
            "owner": metadata.get("owner", "data-platform"),
            "tags": metadata.get("tags", []),
            "version": metadata.get("version", "1.0.0"),
            "source": metadata.get("source", "dynamic"),
            "last_updated": metadata.get("last_updated"),
            "business_glossary": metadata.get("business_glossary", {}),
            "aliases": metadata.get("aliases", []),
            "indexes": metadata.get("indexes", []),
            "columns": [
                {
                    "name": column,
                    "data_type": schema_column_types.get(table, {}).get(column, "TEXT"),
                    "description": schema_column_descriptions.get(table, {}).get(column, ""),
                    "is_pk": column == schema_column_order.get(table, [""])[0] and column.endswith("_id"),
                    "is_fk": any(rel[0] == column for rel in schema_graph.get(table, [])),
                }
                for column in schema_column_order.get(table, [])
            ],
            "relationships": [
                {
                    "from_table": table,
                    "from_column": from_column,
                    "to_table": to_table,
                    "to_column": to_column,
                }
                for from_column, to_table, to_column in schema_graph.get(table, [])
            ],
        })
    DYNAMIC_SCHEMA_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def schema_catalog_entry(table: str) -> dict[str, object]:
    metadata = schema_table_metadata.get(table, {})
    columns = [
        {
            "name": column,
            "data_type": str(schema_column_types.get(table, {}).get(column, "")),
            "description": schema_column_descriptions.get(table, {}).get(column, ""),
            "is_pk": column.endswith("_id") and column == schema_column_order.get(table, [""])[0],
            "is_fk": any(rel[0] == column for rel in schema_graph.get(table, [])),
            "is_virtual": (table, column) in virtual_schema_columns,
        }
        for column in schema_column_order.get(table, [])
    ]
    relationships = [
        {
            "from_table": table,
            "from_column": from_column,
            "to_table": to_table,
            "to_column": to_column,
        }
        for from_column, to_table, to_column in schema_graph.get(table, [])
    ]
    indexes = metadata.get("indexes") or [
        column["name"]
        for column in columns
        if column["is_pk"] or column["is_fk"] or column["name"] in {"status", "created_at"}
    ]
    return {
        "name": table,
        "domain": metadata.get("domain", "Core Copilot Schema"),
        "purpose": metadata.get("purpose", "Schema table used by the active SQL copilot."),
        "row_count": "live",
        "columns": columns,
        "relationships": relationships,
        "indexes": indexes,
        "owner": metadata.get("owner", "data-platform"),
        "tags": metadata.get("tags", []),
        "version": metadata.get("version", "1.0.0"),
        "source": metadata.get("source", "excel"),
        "business_glossary": metadata.get("business_glossary", {}),
        "aliases": metadata.get("aliases", []),
        "last_updated": metadata.get("last_updated", "2026-06-12"),
    }


def _upsert_schema_table(
    payload: dict[str, object],
    *,
    source: str = "dynamic",
    persist: bool = True,
    refresh: bool = True,
) -> dict[str, object]:
    table = _normalise_identifier(payload.get("name") or payload.get("table_name"), "dynamic_table")
    if table in schema_tables and table not in dynamic_schema_tables:
        raise ValueError(f"'{table}' is an Excel-backed table. Create a new dynamic table instead.")

    raw_columns = payload.get("columns") or []
    if isinstance(raw_columns, str):
        raw_columns = [item.strip() for item in raw_columns.split(",") if item.strip()]
    columns = [
        _column_payload(column, index)
        for index, column in enumerate(raw_columns if isinstance(raw_columns, list) else [])
    ]
    if not columns:
        base = table[:-1] if table.endswith("s") else table
        columns = [
            {"name": f"{base}_id", "data_type": "INTEGER", "description": f"Primary key for {table}.", "is_pk": True},
            {"name": "name", "data_type": "TEXT", "description": f"Business label for {table}.", "is_pk": False},
            {"name": "status", "data_type": "TEXT", "description": "Lifecycle status.", "is_pk": False},
        ]

    for entries in col_to_tables.values():
        while table in entries:
            entries.remove(table)

    schema_tables.add(table)
    dynamic_schema_tables.add(table)
    schema_columns[table] = {str(column["name"]) for column in columns}
    schema_column_order[table] = [str(column["name"]) for column in columns]
    schema_column_types[table] = {
        str(column["name"]): str(column.get("data_type") or "TEXT")
        for column in columns
    }
    schema_column_descriptions[table] = {
        str(column["name"]): str(column.get("description") or "")
        for column in columns
    }
    for column in schema_column_order[table]:
        col_to_tables.setdefault(column, []).append(table)

    metadata = dict(payload.get("metadata") or {})
    domain = str(payload.get("domain") or metadata.get("domain") or "Dynamic Enterprise Schema")
    purpose = str(
        payload.get("purpose")
        or payload.get("business_purpose")
        or metadata.get("purpose")
        or f"Dynamic table for {table.replace('_', ' ')}."
    )
    indexes = payload.get("indexes") or metadata.get("indexes") or [
        column["name"]
        for column in columns
        if column.get("is_pk") or column.get("is_fk") or column["name"] in {"status", "created_at"}
    ]
    schema_table_metadata[table] = {
        "domain": domain,
        "purpose": purpose,
        "owner": str(payload.get("owner") or metadata.get("owner") or "data-platform"),
        "tags": _ensure_list(payload.get("tags") or metadata.get("tags") or ["dynamic"]),
        "version": str(payload.get("version") or metadata.get("version") or "1.0.0"),
        "source": source,
        "last_updated": datetime.now(timezone.utc).date().isoformat(),
        "business_glossary": payload.get("business_glossary") or metadata.get("business_glossary") or {},
        "aliases": _ensure_list(payload.get("aliases") or metadata.get("aliases") or [table.replace("_", " ")]),
        "indexes": list(indexes),
    }

    schema_graph[table] = []
    raw_relationships = payload.get("relationships") or []
    if isinstance(raw_relationships, str):
        raw_relationships = [
            item.strip() for item in raw_relationships.split(",") if item.strip()
        ]
    for column in columns:
        if column.get("references_table") and column.get("references_column"):
            raw_relationships.append({
                "from_table": table,
                "from_column": column["name"],
                "to_table": column["references_table"],
                "to_column": column["references_column"],
            })
    for relationship in raw_relationships if isinstance(raw_relationships, list) else []:
        parsed = _relationship_payload(relationship, table)
        if not parsed or parsed["from_table"] != table:
            continue
        if parsed["to_table"] not in schema_tables:
            continue
        if parsed["to_column"] not in schema_columns.get(parsed["to_table"], set()):
            continue
        if parsed["from_column"] not in schema_columns.get(table, set()):
            schema_columns[table].add(parsed["from_column"])
            schema_column_order[table].append(parsed["from_column"])
            schema_column_types[table][parsed["from_column"]] = "INTEGER"
            schema_column_descriptions[table][parsed["from_column"]] = (
                f"Foreign key to {parsed['to_table']}.{parsed['to_column']}."
            )
        _register_fk(table, parsed["from_column"], parsed["to_table"], parsed["to_column"])

    _replace_schema_documents(table)
    if persist:
        _save_dynamic_schema()
    if refresh:
        refresh_metadata_engine(reason=f"schema_upsert:{table}")
    return schema_catalog_entry(table)


def _register_builtin_schema_table(payload: dict[str, object]) -> dict[str, object]:
    table = _normalise_identifier(payload.get("name") or payload.get("table_name"), "builtin_table")
    raw_columns = payload.get("columns") or []
    columns = [
        _column_payload(column, index)
        for index, column in enumerate(raw_columns if isinstance(raw_columns, list) else [])
    ]
    if not columns:
        return {}

    for entries in col_to_tables.values():
        while table in entries:
            entries.remove(table)

    schema_tables.add(table)
    dynamic_schema_tables.discard(table)
    schema_columns[table] = {str(column["name"]) for column in columns}
    schema_column_order[table] = [str(column["name"]) for column in columns]
    schema_column_types[table] = {
        str(column["name"]): str(column.get("data_type") or "TEXT")
        for column in columns
    }
    schema_column_descriptions[table] = {
        str(column["name"]): str(column.get("description") or "")
        for column in columns
    }
    for column in schema_column_order[table]:
        col_to_tables.setdefault(column, []).append(table)

    metadata = dict(payload.get("metadata") or {})
    schema_table_metadata[table] = {
        "domain": str(payload.get("domain") or metadata.get("domain") or "Built-in Enterprise Schema"),
        "purpose": str(payload.get("purpose") or metadata.get("purpose") or f"Built-in table for {table}."),
        "owner": str(payload.get("owner") or metadata.get("owner") or "data-platform"),
        "tags": _ensure_list(payload.get("tags") or metadata.get("tags") or ["builtin"]),
        "version": str(payload.get("version") or metadata.get("version") or "1.0.0"),
        "source": str(payload.get("source") or metadata.get("source") or "builtin"),
        "last_updated": "2026-08-11",
        "business_glossary": payload.get("business_glossary") or metadata.get("business_glossary") or {},
        "aliases": _ensure_list(payload.get("aliases") or metadata.get("aliases") or [table.replace("_", " ")]),
        "indexes": list(payload.get("indexes") or metadata.get("indexes") or []),
    }
    schema_graph[table] = []
    _replace_schema_documents(table)
    return schema_catalog_entry(table)


def register_custody_balance_schema() -> int:
    loaded = 0
    for table_payload in CUSTODY_BALANCE_SCHEMA_TABLES:
        if _register_builtin_schema_table(table_payload):
            loaded += 1
    for relationship in CUSTODY_BALANCE_RELATIONSHIPS:
        parsed = _relationship_payload(relationship, str(relationship.get("from_table") or ""))
        if not parsed:
            continue
        _register_fk(
            parsed["from_table"],
            parsed["from_column"],
            parsed["to_table"],
            parsed["to_column"],
        )
    return loaded


def _delete_schema_table(table_name: str) -> tuple[bool, str]:
    table = _normalise_identifier(table_name, "dynamic_table")
    if table not in schema_tables:
        return False, "schema table not found"
    if table not in dynamic_schema_tables:
        return False, "Excel-backed schema tables are read-only"

    schema_tables.discard(table)
    dynamic_schema_tables.discard(table)
    schema_columns.pop(table, None)
    schema_column_order.pop(table, None)
    schema_column_types.pop(table, None)
    schema_column_descriptions.pop(table, None)
    schema_table_metadata.pop(table, None)
    schema_graph.pop(table, None)
    for from_table, relationships in list(schema_graph.items()):
        schema_graph[from_table] = [
            relation for relation in relationships if relation[1] != table
        ]
    for entries in col_to_tables.values():
        while table in entries:
            entries.remove(table)
    _replace_schema_documents(table)
    _save_dynamic_schema()
    refresh_metadata_engine(reason=f"schema_delete:{table}")
    return True, table


def _load_dynamic_schema() -> int:
    if not DYNAMIC_SCHEMA_FILE.exists():
        return 0
    try:
        payload = json.loads(DYNAMIC_SCHEMA_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log_step(f"[schema] Dynamic schema file could not be read: {exc}")
        return 0
    loaded = 0
    for table_payload in payload.get("tables", []):
        if not isinstance(table_payload, dict):
            continue
        try:
            _upsert_schema_table(table_payload, source="dynamic", persist=False, refresh=False)
            loaded += 1
        except Exception as exc:
            log_step(f"[schema] Dynamic table skipped: {exc}")
    return loaded


inferred_fk_count = infer_foreign_keys_from_schema()
if inferred_fk_count:
    log_step(f"[schema] Inferred {inferred_fk_count} FK relationships from schema descriptions")
loaded_dynamic_count = _load_dynamic_schema()
if loaded_dynamic_count:
    log_step(f"[schema] Loaded {loaded_dynamic_count} dynamic schema tables")
builtin_custody_count = register_custody_balance_schema()
if builtin_custody_count:
    log_step(f"[schema] Registered {builtin_custody_count} custody balance schema tables")

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

metadata_refresh_status: dict[str, object] = {
    "version": 1,
    "last_refreshed_at": datetime.now(timezone.utc).isoformat(),
    "reason": "startup",
    "bm25_enabled": bool(bm25_ret),
    "faiss_enabled": bool(table_vs and column_vs),
    "tables_count": len(schema_tables),
    "columns_count": len(column_documents),
}


def refresh_metadata_engine(reason: str = "manual") -> dict[str, object]:
    global table_vs, column_vs, faiss_table_ret, faiss_col_ret, bm25_ret, enterprise_copilot

    if BM25Retriever:
        bm25_ret = BM25Retriever.from_documents(table_documents)
        bm25_ret.k = 3

    faiss_ready = False
    if FAISS is not None and embeddings is not None:
        try:
            table_vs = FAISS.from_documents(table_documents, embeddings)
            column_vs = FAISS.from_documents(column_documents, embeddings)
            table_vs.save_local(FAISS_TABLE_INDEX_PATH)
            column_vs.save_local(FAISS_COL_INDEX_PATH)
            faiss_table_ret = table_vs.as_retriever(search_kwargs={"k": 3})
            faiss_col_ret = column_vs.as_retriever(search_kwargs={"k": 5})
            faiss_ready = True
        except Exception as exc:
            faiss_table_ret = None
            faiss_col_ret = None
            log_step(f"[metadata] FAISS refresh skipped: {exc}")
    else:
        faiss_table_ret = None
        faiss_col_ret = None

    if "sync_dynamic_query_hints" in globals():
        sync_dynamic_query_hints()
    enterprise_copilot = None
    metadata_refresh_status.update({
        "version": int(metadata_refresh_status.get("version", 0)) + 1,
        "last_refreshed_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "bm25_enabled": bool(bm25_ret),
        "faiss_enabled": faiss_ready,
        "tables_count": len(schema_tables),
        "columns_count": len(column_documents),
        "dynamic_tables_count": len(dynamic_schema_tables),
    })
    log_step(
        "[metadata] Refreshed schema engine "
        f"v{metadata_refresh_status['version']} ({reason})"
    )
    return dict(metadata_refresh_status)


 
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
    "insert", "create", "merge", "call",
}
_META = {
    "schema", "tables", "columns", "describe",
    "list tables", "show tables", "what tables",
}


def classify_query(query: str) -> str:
    q = query.lower()
    stripped = q.strip()
    if ";" in stripped.rstrip(";"):
        return "DANGEROUS"
    if re.search(r"\b(stored\s+procedure|procedure|proc)\b", q):
        return "DANGEROUS"
    if any(re.search(rf"\b{re.escape(w)}\b", q) for w in _DANGEROUS):
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
    if not sql_lower:
        return False, "SQL is empty"
    if not sql_lower.startswith("select"):
        return False, "Only SELECT SQL can be generated. The system returned a clarification instead of executable SQL."
    if ";" in sql_lower.rstrip(";"):
        return False, "Multiple SQL statements are not allowed"

    for word in _FORBIDDEN_OPS:
        if re.search(rf"\b{word}\b", sql_lower):
            return False, f"Forbidden operation: '{word}'"

    used_tables, alias_map = extract_tables_and_aliases(sql)
    if not used_tables:
        return False, "SQL must include a FROM table"

    for table in used_tables:
        if table not in schema_tables:
            return False, f"Unknown table: '{table}'"

    if sqlglot is not None:
        try:
            parsed = sqlglot.parse_one(sql)
            selected_aliases = {
                alias.alias.lower()
                for alias in parsed.find_all(sqlglot.exp.Alias)
                if alias.alias
            }
            for col_expr in parsed.find_all(sqlglot.exp.Column):
                col_name = col_expr.name.lower()
                table_ref = col_expr.table.lower() if col_expr.table else None

                if col_name == "*":
                    return False, "Wildcard SELECT is not allowed; use explicit columns"

                if table_ref:
                    real_table = alias_map.get(table_ref, table_ref)
                    if real_table not in schema_columns:
                        return False, f"Unknown table or alias reference: '{table_ref}'"
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
                    if col_name in selected_aliases:
                        continue
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
 

from agentic.confidence_coordinator import ConfidenceCoordinator


_CONF_COORDINATOR = ConfidenceCoordinator()


def confidence_score(sql: str, is_valid: bool, original_query: str) -> int:
    """Backward-compatible wrapper that returns an int confidence score.

    Uses the centralized ConfidenceCoordinator heuristic fallback.
    """
    breakdown = _CONF_COORDINATOR.compute_from_sql_heuristic(sql, is_valid, original_query)
    return int(round(breakdown.get("overall", 0.0)))


 
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


def load_ppo_agent():
    global ppo_agent
    if ppo_agent is not None:
        return ppo_agent
    if not RL_ENABLED or PPOAgent is None or not Path(RL_MODEL_PATH).exists():
        return None
    try:
        env = SQLQueryOptimizationEnv(
            db_path=DB_PATH,
            feedback_db_path=FEEDBACK_DB_PATH,
            validator=validate_sql,
        )
        ppo_agent = PPOAgent.load(env, RL_MODEL_PATH)
        log_step(f"[rl] Loaded PPO model from {RL_MODEL_PATH}")
    except Exception as exc:
        log_step(f"[rl] PPO model unavailable: {exc}")
        ppo_agent = None
    return ppo_agent


def _matched_business_logic_rule(insights: dict | None) -> str:
    if not isinstance(insights, dict):
        return ""
    top_level_rule = insights.get("business_logic_rule")
    if top_level_rule:
        return str(top_level_rule)
    coverage_report = insights.get("coverage_report")
    if not isinstance(coverage_report, dict):
        return ""
    business_logic = coverage_report.get("business_logic")
    if not isinstance(business_logic, dict):
        return ""
    return str(business_logic.get("matched_rule") or "")


def optimize_with_rl_feedback(query: str, sql: str, insights: dict) -> dict:
    original_sql = sql
    optimized_sql = sql
    action_name = "keep_current_query"
    matched_rule = _matched_business_logic_rule(insights)

    if matched_rule:
        is_valid, validation_message = validate_sql(original_sql)
        stats = execute_sql_for_stats(DB_PATH, original_sql)
        reward = compute_reward(is_valid, stats)
        existing_confidence = insights.get("confidence", 0) if isinstance(insights, dict) else 0
        try:
            confidence = float(existing_confidence)
        except (TypeError, ValueError):
            confidence = confidence_score(original_sql, is_valid, query)
        if not is_valid:
            confidence = min(confidence, confidence_score(original_sql, is_valid, query))

        store_experience(
            FEEDBACK_DB_PATH,
            query,
            original_sql,
            reward,
            stats.execution_time,
            validation_message,
        )

        updated_insights = dict(insights)
        updated_insights.update({
            "confidence": confidence,
            "valid": is_valid,
            "validation": validation_message,
            "business_logic_rule": matched_rule,
            "rl": {
                "enabled": RL_ENABLED,
                "model_loaded": False,
                "action": "skipped_business_logic_rule",
                "original_sql": original_sql,
                "optimized_sql": original_sql,
                "reward_score": reward,
                "confidence_score": confidence,
                "execution_time": stats.execution_time,
                "row_count": stats.row_count,
                "optimization_reasoning": (
                    f"RL rewrite skipped because {matched_rule} is a registered "
                    "business-logic rule with schema-bound SQL."
                ),
            },
        })
        return {
            "sql": original_sql,
            "insights": updated_insights,
        }

    agent = load_ppo_agent()
    if agent is not None:
        try:
            env = SQLQueryOptimizationEnv(
                db_path=DB_PATH,
                feedback_db_path=FEEDBACK_DB_PATH,
                validator=validate_sql,
            )
            obs, _ = env.reset(options={
                "state": SQLState(
                    user_query=query,
                    schema_context="",
                    generated_sql=sql,
                )
            })
            action = agent.predict(obs)
            _obs, _reward, _terminated, _truncated, info = env.step(action)
            optimized_sql = info.get("optimized_sql", sql)
            action_name = ACTION_NAMES.get(action, "unknown")
        except Exception as exc:
            log_step(f"[rl] Optimization skipped: {exc}")

    is_valid, validation_message = validate_sql(optimized_sql)
    stats = execute_sql_for_stats(DB_PATH, optimized_sql)
    reward = compute_reward(is_valid, stats)
    if action_name == "keep_current_query" or original_sql == optimized_sql:
        try:
            confidence = float(insights.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = confidence_score(optimized_sql, is_valid, query)
        if not confidence:
            confidence = confidence_score(optimized_sql, is_valid, query)
    else:
        confidence = confidence_score(optimized_sql, is_valid, query)
    if not is_valid:
        confidence = min(confidence, confidence_score(optimized_sql, is_valid, query))

    store_experience(
        FEEDBACK_DB_PATH,
        query,
        optimized_sql,
        reward,
        stats.execution_time,
        validation_message,
    )

    if action_name == "keep_current_query" or original_sql == optimized_sql:
        reasoning = (
            "The RL feedback layer kept the generated SQL because it passed the "
            "available validation and policy checks."
        )
    else:
        reasoning = (
            f"The RL optimizer selected {action_name.replace('_', ' ')} based on "
            "policy feedback from prior executions."
        )

    updated_insights = dict(insights)
    updated_insights.update({
        "confidence": confidence,
        "valid": is_valid,
        "validation": validation_message,
        "rl": {
            "enabled": RL_ENABLED,
            "model_loaded": agent is not None,
            "action": action_name,
            "original_sql": original_sql,
            "optimized_sql": optimized_sql,
            "reward_score": reward,
            "confidence_score": confidence,
            "execution_time": stats.execution_time,
            "row_count": stats.row_count,
            "optimization_reasoning": reasoning,
        },
    })

    return {
        "sql": optimized_sql,
        "insights": updated_insights,
    }


 
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
    "departments": "d",
    "invoices": "i",
    "payments": "pay",
    "sprints": "s",
    "deployments": "dep",
}

TABLE_QUERY_HINTS = {
    "employees": {
        "employee", "employees", "staff", "worker", "workers", "developer",
        "developers", "qa", "manager", "managers", "devops", "department",
        "role", "email",
    },
    "clients": {
        "client", "clients", "customer", "customers", "industry",
        "organization", "contact", "tier", "segment",
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
    "payments": {
        "payment", "payments", "paid", "revenue", "cash", "receipt",
        "payment date", "payment method",
    },
    "invoices": {
        "invoice", "invoices", "billing", "billed", "revenue", "amount",
        "issued date", "due date",
    },
    "departments": {
        "department", "departments", "division", "location",
    },
    "sprints": {
        "sprint", "sprints", "iteration", "iterations", "goal",
        "start date", "end date",
    },
    "deployments": {
        "deployment", "deployments", "release", "releases", "environment",
        "version", "deployed", "production", "staging",
    },
}

DEFAULT_DISPLAY_COLUMNS = {
    "employees": ["employee_id", "full_name", "email", "role", "department", "status"],
    "clients": ["client_id", "client_name", "tier", "contact_email", "industry", "created_at"],
    "projects": ["project_id", "project_name", "client_id", "status", "budget", "start_date", "end_date"],
    "project_team": ["id", "project_id", "employee_id", "role_in_project", "assigned_at"],
    "tasks": ["task_id", "title", "project_id", "assigned_to", "priority", "status", "due_date"],
    "time_logs": ["log_id", "task_id", "employee_id", "hours_spent", "log_date", "remarks"],
    "bugs": ["bug_id", "project_id", "reported_by", "assigned_to", "severity", "status", "created_at"],
    "payments": ["payment_id", "invoice_id", "client_id", "amount_paid", "payment_date", "payment_method", "status"],
    "invoices": ["invoice_id", "client_id", "project_id", "invoice_number", "amount", "status", "issued_date", "due_date"],
    "departments": ["department_id", "department_name", "manager_id", "location", "created_at"],
    "sprints": ["sprint_id", "project_id", "sprint_name", "start_date", "end_date", "status", "goal"],
    "deployments": ["deployment_id", "project_id", "deployed_by", "environment", "version", "status", "deployed_at"],
}

PRIMARY_LABEL_COLUMNS = {
    "employees": "full_name",
    "clients": "client_name",
    "projects": "project_name",
    "tasks": "title",
    "time_logs": "log_id",
    "bugs": "bug_id",
    "project_team": "id",
    "sprints": "sprint_name",
    "deployments": "version",
}
TABLE_ALIASES.update(CUSTODY_BALANCE_ALIASES)
DEFAULT_DISPLAY_COLUMNS.update(CUSTODY_BALANCE_DEFAULT_DISPLAY_COLUMNS)
PRIMARY_LABEL_COLUMNS.update(CUSTODY_BALANCE_LABEL_COLUMNS)

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
        "tier": {"tier", "client tier", "customer tier", "segment", "client segment"},
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
    "payments": {
        "payment_id": {"payment id"},
        "invoice_id": {"invoice", "invoice id"},
        "client_id": {"client", "client id"},
        "amount_paid": {"amount paid", "paid amount", "revenue", "payment amount"},
        "payment_date": {"payment date", "paid date", "month", "quarter"},
        "payment_method": {"payment method", "method"},
        "status": {"status"},
    },
    "invoices": {
        "invoice_id": {"invoice id"},
        "client_id": {"client", "client id"},
        "project_id": {"project", "project id"},
        "invoice_number": {"invoice number"},
        "amount": {"invoice amount", "billed amount", "revenue"},
        "status": {"status"},
        "issued_date": {"issued date", "invoice date", "month", "quarter"},
        "due_date": {"due date", "deadline"},
    },
    "departments": {
        "department_id": {"department id"},
        "department_name": {"department", "department name", "division"},
        "manager_id": {"manager", "manager id"},
        "location": {"location"},
        "created_at": {"created", "created at"},
    },
    "sprints": {
        "sprint_id": {"sprint id"},
        "project_id": {"project", "project id"},
        "sprint_name": {"sprint", "sprint name", "iteration"},
        "start_date": {"start", "start date"},
        "end_date": {"end", "end date", "ending"},
        "status": {"status", "active", "completed"},
        "goal": {"goal", "objective"},
    },
    "deployments": {
        "deployment_id": {"deployment id"},
        "project_id": {"project", "project id"},
        "deployed_by": {"deployed by", "releaser", "employee"},
        "environment": {"environment", "production", "staging"},
        "version": {"version", "release"},
        "status": {"status", "successful", "failed"},
        "deployed_at": {"deployed", "deployment date", "released"},
    },
}

for table, hints in CUSTODY_BALANCE_TABLE_HINTS.items():
    TABLE_QUERY_HINTS.setdefault(table, set()).update(hints)
for table, columns in CUSTODY_BALANCE_COLUMN_HINTS.items():
    COLUMN_QUERY_HINTS.setdefault(table, {})
    for column, hints in columns.items():
        COLUMN_QUERY_HINTS[table].setdefault(column, set()).update(hints)

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
    "sprints": {
        "status": {
            "active": "active",
            "completed": "completed",
            "complete": "completed",
        },
    },
    "deployments": {
        "status": {
            "successful": "successful",
            "failed": "failed",
        },
    },
}
VALUE_FILTERS["custody_block"] = {
    "block_status": {
        "active": "ACTIVE",
        "released": "RELEASED",
        "cancelled": "CANCELLED",
        "canceled": "CANCELLED",
        "expired": "EXPIRED",
    }
}

DATE_ORDER_COLUMNS = {
    "employees": "joining_date",
    "clients": "created_at",
    "projects": "start_date",
    "tasks": "created_at",
    "time_logs": "log_date",
    "bugs": "created_at",
    "project_team": "assigned_at",
    "sprints": "start_date",
    "deployments": "deployed_at",
}
DATE_ORDER_COLUMNS.update({
    "portfolio": "created_datetime",
    "custody_position": "last_carry_forward_date",
    "security_movement": "trade_date",
    "custody_block": "block_valid_from_date",
})


def _hint_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9_]*", text.lower().replace("-", " ")))


def sync_dynamic_query_hints() -> None:
    for table in sorted(dynamic_schema_tables):
        if table not in schema_tables:
            continue
        metadata = schema_table_metadata.get(table, {})
        hint_terms = _hint_tokens(table.replace("_", " "))
        hint_terms.update(_hint_tokens(str(metadata.get("purpose", ""))))
        for alias in _ensure_list(metadata.get("aliases")):
            hint_terms.add(str(alias).lower())
            hint_terms.update(_hint_tokens(str(alias)))
        TABLE_QUERY_HINTS[table] = {
            term for term in hint_terms if len(term) > 1
        } or {table.replace("_", " ")}
        COLUMN_QUERY_HINTS[table] = {}
        for column in schema_column_order.get(table, []):
            description = schema_column_descriptions.get(table, {}).get(column, "")
            terms = {column, column.replace("_", " ")}
            terms.update(_hint_tokens(description))
            COLUMN_QUERY_HINTS[table][column] = {term for term in terms if len(term) > 1}
        display_columns = schema_column_order.get(table, [])[:6]
        DEFAULT_DISPLAY_COLUMNS[table] = display_columns
        label = next(
            (column for column in display_columns if not column.endswith("_id")),
            display_columns[0] if display_columns else "",
        )
        if label:
            PRIMARY_LABEL_COLUMNS[table] = label
        TABLE_ALIASES.setdefault(table, table[:1] or "t")


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


def get_enterprise_copilot() -> EnterpriseSQLCopilot:
    global enterprise_copilot
    if enterprise_copilot is None:
        sync_dynamic_query_hints()
        enterprise_copilot = EnterpriseSQLCopilot(
            tables=schema_tables,
            columns=schema_columns,
            column_order=schema_column_order,
            column_types=schema_column_types,
            relationships=schema_graph,
            table_hints=TABLE_QUERY_HINTS,
            column_hints=COLUMN_QUERY_HINTS,
            value_filters=VALUE_FILTERS,
            aliases=TABLE_ALIASES,
            defaults=DEFAULT_DISPLAY_COLUMNS,
            labels=PRIMARY_LABEL_COLUMNS,
            validator=validate_sql,
            state_db_path=Path(FEEDBACK_DB_PATH),
            logs_root=RUNTIME_PATHS.logs_root,
            llm_provider=LLM_PROVIDER_CLIENT,
            max_generation_retries=MAX_RETRIES,
            confidence_low_threshold=CONFIDENCE_THRESHOLD,
            confidence_high_threshold=int(os.getenv("CONFIDENCE_HIGH_THRESHOLD", "90")),
        )
    return enterprise_copilot


def get_spider_text_sql_rag() -> SpiderTextSqlRag:
    global spider_text_sql_rag
    if spider_text_sql_rag is None:
        spider_text_sql_rag = SpiderTextSqlRag(SPIDER_TEXT_SQL_FILE)
        log_step(
            f"[spider-rag] Loaded {len(spider_text_sql_rag.examples)} text-to-SQL examples "
            f"from {SPIDER_TEXT_SQL_FILE}"
        )
    return spider_text_sql_rag


def enterprise_result_to_insights(result) -> dict[str, object]:
    query_type = "Clarification" if result.clarification_required else detect_query_type(result.sql)
    business_logic = result.coverage_report.get("business_logic", {}) if isinstance(result.coverage_report, dict) else {}
    business_logic_rule = (
        str(business_logic.get("matched_rule") or "")
        if isinstance(business_logic, dict)
        else ""
    )
    index_suggestions = [
        item.removeprefix("Index suggested: ").removeprefix("Index suggested for filter: ")
        for item in result.optimizations
        if item.lower().startswith("index suggested")
    ]
    execution_plan = [
        f"Scan {result.selected_tables[0]}" if result.selected_tables else "No executable plan",
        *[f"Join {item}" for item in result.join_path],
        "Apply read-only validation",
        "Return projected columns",
    ]
    fallback_reason = _friendly_llm_fallback_reason(result.llm_trace)
    return {
        "confidence": result.confidence,
        "threshold": 70,
        "valid": result.valid,
        "validation": result.validation,
        "source": "Enterprise local agent pipeline",
        "attempts": 0,
        "max_attempts": MAX_RETRIES,
        "tables": result.selected_tables,
        "columns": result.selected_columns,
        "query_type": query_type,
        "has_limit": bool(result.intent.get("limit")),
        "summary": (
            "Clarification required before SQL generation"
            if result.clarification_required
            else f"{query_type} query using {', '.join(result.selected_tables) or 'the available schema'}"
        ),
        "clarification_required": result.clarification_required,
        "clarification_options": result.clarification_options,
        "intent": result.intent,
        "entities": result.entities,
        "selected_tables": result.selected_tables,
        "join_path": result.join_path,
        "plan": result.plan,
        "optimizations": result.optimizations,
        "optimized_sql": result.sql,
        "optimization_explanation": (
            result.optimizations
            or ["Planner output is already explicit and read-only; no SQL rewrite was required."]
        ),
        "execution_plan": execution_plan,
        "cost_reduction_percent": 0,
        "index_suggestions": index_suggestions,
        "confidence_breakdown": result.confidence_breakdown,
        "confidence_evidence": result.confidence_evidence,
        "coverage_report": result.coverage_report,
        "business_logic_rule": business_logic_rule,
        "agent_telemetry": result.agent_telemetry,
        "execution_trace": result.execution_trace,
        "runtime_metrics": result.runtime_metrics,
        "benchmark_record": result.benchmark_record,
        "query_complexity": result.query_complexity,
        "confidence_band": result.confidence_band,
        "provider_status": result.provider_status,
        "llm_trace": result.llm_trace,
        "model_confidence": result.model_confidence,
        "planner_confidence": result.planner_confidence,
        "validator_confidence": result.validator_confidence,
        "coverage_confidence": result.coverage_confidence,
        "llm_provider": result.llm_trace.get("provider") or result.provider_status.get("provider"),
        "llm_model": result.llm_trace.get("model") or result.provider_status.get("model"),
        "fallback_used": bool(result.llm_trace.get("fallback_used")),
        "fallback_reason": fallback_reason,
        "repair_attempts": int(result.llm_trace.get("retry_count") or 0),
        "cache_hit": result.cache_hit,
    }


def _friendly_llm_fallback_reason(llm_trace: dict[str, object]) -> str:
    reason = str(llm_trace.get("fallback_reason") or "")
    if not reason:
        return ""
    messages = {
        "provider_error": "NVIDIA assist could not connect; deterministic SQL was used.",
        "timeout": "NVIDIA assist timed out; deterministic SQL was used.",
        "rate_limit": "NVIDIA assist was rate limited; deterministic SQL was used.",
        "configuration": "NVIDIA assist needs a valid provider configuration; deterministic SQL was used.",
        "network_blocked": "Backend network access to NVIDIA is blocked; deterministic SQL was used.",
        "provider_unavailable": "NVIDIA assist is unavailable; deterministic SQL was used.",
        "candidate_failed_validation": "NVIDIA candidate failed deterministic validation; deterministic SQL was used.",
        "generic_candidate_failed_validation": "NVIDIA generic candidate failed read-only validation; nearest Spider example was used.",
        "plan_validation_failed": "The deterministic plan was not safe for LLM generation; deterministic fallback was used.",
        "clarification_required_before_llm": "Clarification is required before LLM assist can run.",
    }
    return messages.get(reason, "LLM assist was skipped; deterministic SQL was used.")


def _result_has_schema_anchor(result) -> bool:
    if result.selected_tables or result.selected_columns:
        return True
    plan = result.plan or {}
    if isinstance(plan, dict):
        if str(plan.get("main_table") or "").strip():
            return True
        for key in ("selected_columns", "joins", "filters", "aggregations", "group_by"):
            if plan.get(key):
                return True
    return False


def _schema_terms_for_table(table: str) -> set[str]:
    terms = set(re.findall(r"[a-z][a-z0-9_]*", table.lower().replace("_", " ")))
    for hint in TABLE_QUERY_HINTS.get(table, set()):
        terms.update(re.findall(r"[a-z][a-z0-9_]*", str(hint).lower().replace("_", " ")))
    return terms


def _schema_terms_for_column(table: str, column: str) -> set[str]:
    terms = set(re.findall(r"[a-z][a-z0-9_]*", column.lower().replace("_", " ")))
    for hint in COLUMN_QUERY_HINTS.get(table, {}).get(column, set()):
        terms.update(re.findall(r"[a-z][a-z0-9_]*", str(hint).lower().replace("_", " ")))
    return terms


def _query_mentions_selected_schema(user_query: str, result) -> bool:
    query_terms = set(re.findall(r"[a-z][a-z0-9_]*", user_query.lower().replace("_", " ")))
    generic_terms = {
        "all", "any", "by", "count", "date", "display", "find", "get", "group", "how",
        "id", "list", "many", "name", "names", "number", "order", "ordered", "rank",
        "show", "sort", "sorted", "the", "top", "total", "what", "which",
    }
    for table in result.selected_tables or []:
        if query_terms & (_schema_terms_for_table(table) - generic_terms):
            return True
    for item in result.selected_columns or []:
        table, _, column = str(item).partition(".")
        if table and column and query_terms & (_schema_terms_for_column(table, column) - generic_terms):
            return True
    return False


def _clarification_mentions_known_schema(result) -> bool:
    options = [str(item).lower() for item in (result.clarification_options or [])]
    if not options:
        return False
    for option in options:
        for table in schema_tables:
            table_name = table.lower()
            if f"{table_name}." in option:
                return True
            if re.search(rf"(?<!\w){re.escape(table_name)}(?!\w)", option):
                return True
    return False


def _should_use_spider_generic_rag(user_query: str, result) -> bool:
    if not result.clarification_required:
        return False
    if result.confidence >= CONFIDENCE_THRESHOLD:
        return False
    if _result_has_schema_anchor(result) and _query_mentions_selected_schema(user_query, result):
        return False
    if _clarification_mentions_known_schema(result):
        return False
    rag = get_spider_text_sql_rag()
    return rag.available and rag.looks_like_text_to_sql(user_query)


def _sql_tables(sql: str) -> list[str]:
    matches = re.findall(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)", sql, flags=re.IGNORECASE)
    return sorted({item.split(".")[-1] for item in matches})


def _spider_generic_sql_response(
    user_query: str,
    result,
    *,
    max_retries: int,
) -> dict[str, object] | None:
    if not _should_use_spider_generic_rag(user_query, result):
        return None
    answer = get_spider_text_sql_rag().answer(user_query, provider=LLM_PROVIDER_CLIENT)
    if not answer:
        return None

    sql = str(answer["sql"])
    llm_trace = dict(answer.get("llm_trace") or {})
    examples = list(answer.get("examples") or [])
    model_confidence = float(answer.get("confidence") or 0.0)
    tables = _sql_tables(sql)
    execution_trace = {
        "workflow": {
            "engine": "spider_rag",
            "requested_engine": "spider_text_sql_rag",
            "available": True,
            "nodes": [
                {"key": "enterprise_schema_gate", "label": "Enterprise Schema Gate"},
                {"key": "spider_retrieval", "label": "Spider Example Retrieval"},
                {"key": "generic_llm_generation", "label": "Generic NVIDIA SQL Generation"},
                {"key": "read_only_guard", "label": "Read-only Guard"},
            ],
        },
        "events": [
            {
                "stage": "enterprise_schema_gate",
                "reason": "No enterprise schema anchor was found; generic Spider RAG was allowed.",
                "enterprise_confidence": result.confidence,
            },
            {"stage": "spider_retrieval", "examples": examples},
            {
                "stage": "generic_generation",
                "provider": llm_trace.get("provider"),
                "model": llm_trace.get("model"),
                "fallback_used": llm_trace.get("fallback_used"),
                "fallback_reason": llm_trace.get("fallback_reason"),
            },
        ],
    }
    return {
        "sql": sql,
        "insights": {
            "confidence": model_confidence,
            "threshold": CONFIDENCE_THRESHOLD,
            "valid": True,
            "validation": "Generic read-only SQL pattern generated from Spider text-to-SQL RAG; not validated against the enterprise database schema.",
            "source": (
                "Spider text-to-SQL RAG + NVIDIA LLM"
                if llm_trace.get("active") and not llm_trace.get("fallback_used")
                else "Spider text-to-SQL RAG"
            ),
            "attempts": int(llm_trace.get("retry_count") or 0),
            "max_attempts": max_retries,
            "tables": tables,
            "columns": [],
            "query_type": "Generic SQL",
            "has_limit": " limit " in f" {sql.lower()} ",
            "summary": "No matching enterprise schema objects were found, so a generic Spider-style SQL solution was generated.",
            "clarification_required": False,
            "clarification_options": [],
            "selected_tables": [],
            "join_path": [],
            "plan": None,
            "optimizations": [],
            "optimized_sql": sql,
            "optimization_explanation": [
                "Generic Spider RAG output is illustrative and is not optimized against the enterprise database."
            ],
            "execution_plan": [
                "Retrieve similar Spider text-to-SQL examples",
                "Generate a generic read-only SQL pattern",
                "Validate that the generic SQL is SELECT/WITH only",
            ],
            "cost_reduction_percent": 0,
            "index_suggestions": [],
            "confidence_breakdown": {
                "model_confidence": model_confidence,
                "retrieval_confidence": float(examples[0].get("score", 0.0)) if examples else 0.0,
                "system_confidence": model_confidence,
            },
            "confidence_evidence": [
                {
                    "key": "spider_retrieval",
                    "label": "Spider Retrieval",
                    "score": None,
                    "applicable": True,
                    "status": "passed",
                    "required": [user_query],
                    "matched": [str(examples[0].get("text_query", ""))] if examples else [],
                    "missing": [],
                    "note": "Similar public text-to-SQL examples were used because the enterprise schema did not match.",
                },
                {
                    "key": "model_confidence",
                    "label": "LLM Model",
                    "score": model_confidence,
                    "applicable": True,
                    "status": "passed" if model_confidence >= 70 else "warning",
                    "required": [],
                    "matched": [],
                    "missing": [],
                    "note": (
                        "NVIDIA generated a generic SQL pattern from Spider examples."
                        if llm_trace.get("active")
                        else "Nearest Spider example was used."
                    ),
                },
            ],
            "coverage_report": {
                "mode": "spider_generic_rag",
                "enterprise_schema_gate": {
                    "matched": False,
                    "enterprise_confidence": result.confidence,
                    "enterprise_clarification_options": result.clarification_options,
                },
                "spider_examples": examples,
            },
            "business_logic_rule": "",
            "agent_telemetry": {},
            "execution_trace": execution_trace,
            "runtime_metrics": {
                "query_complexity": "GENERIC",
                "llm_provider": llm_trace.get("provider"),
                "llm_model": llm_trace.get("model"),
                "fallback_used": bool(llm_trace.get("fallback_used")),
                "fallback_reason": llm_trace.get("fallback_reason", ""),
                "total_ms": answer.get("latency_ms"),
            },
            "benchmark_record": {},
            "query_complexity": "GENERIC",
            "confidence_band": "MEDIUM" if model_confidence < 90 else "HIGH",
            "provider_status": LLM_PROVIDER_CLIENT.health_check(deep=False),
            "llm_trace": llm_trace,
            "model_confidence": model_confidence,
            "planner_confidence": 0,
            "validator_confidence": 100,
            "coverage_confidence": 0,
            "llm_provider": llm_trace.get("provider"),
            "llm_model": llm_trace.get("model"),
            "fallback_used": bool(llm_trace.get("fallback_used")),
            "fallback_reason": _friendly_llm_fallback_reason(llm_trace),
            "repair_attempts": int(llm_trace.get("retry_count") or 0),
            "cache_hit": False,
            "generic_sql": True,
            "generic_mode": "spider_text_sql_rag",
            "generic_warning": "This SQL is illustrative. Register or connect the target schema before executing it against a real database.",
            "spider_examples": examples,
        },
    }



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
    result = get_enterprise_copilot().run(normalised or user_query)
    generic_result = _spider_generic_sql_response(user_query, result, max_retries=max_retries)
    if generic_result is not None:
        log_step("[spider-rag] No enterprise schema anchor found; returning generic SQL example")
        chat_session.add(user_query, str(generic_result["sql"]))
        return generic_result
    sql = result.sql
    provider_label = result.llm_trace.get("provider") or result.provider_status.get("provider") or "local"
    source = "Enterprise deterministic planner"
    if result.llm_trace.get("active") and not result.llm_trace.get("fallback_used"):
        source = f"Enterprise planner + {provider_label} LLM"
    elif result.llm_trace.get("fallback_used"):
        source = "Enterprise deterministic planner with LLM fallback"

    log_step(f"[enterprise] Source: {source}")
    log_step(f"[enterprise] Complexity: {result.query_complexity} | Confidence: {result.confidence}/100 | Valid: {result.valid}")
    if result.llm_trace.get("fallback_used"):
        log_step(f"[enterprise] Fallback reason: {result.llm_trace.get('fallback_reason')}")
    if result.clarification_required:
        log_step(f"[enterprise] Clarification options: {result.clarification_options}")
    else:
        log_step(f"[enterprise] SQL: {sql}")
        chat_session.add(user_query, sql)
    return {
        "sql": sql,
        "insights": {
            **enterprise_result_to_insights(result),
            "source": source,
            "attempts": int(result.llm_trace.get("retry_count") or 0),
            "max_attempts": max_retries,
        },
    }


 
# 18. ROUTES
 

@app.post("/auth/signup")
def auth_signup():
    limited = _rate_limit("signup", 5, 3600)
    if limited:
        return limited
    payload = request.get_json(silent=True) or {}
    try:
        user = auth_store.create_user(
            str(payload.get("name") or ""),
            str(payload.get("email") or ""),
            str(payload.get("password") or ""),
        )
    except ValueError as exc:
        auth_store.log(
            "auth_logs",
            "signup_rejected",
            level="warning",
            details={"email": str(payload.get("email") or "")[:254], "reason": str(exc)},
            ip_address=_client_ip(),
        )
        return jsonify({"error": str(exc)}), 400
    session_data = auth_store.issue_session(
        user,
        bool(payload.get("remember")),
        _client_ip(),
        request.headers.get("User-Agent", ""),
    )
    auth_store.log(
        "auth_logs",
        "signup_succeeded",
        user_id=user["id"],
        details={"role": user["role"]},
        ip_address=_client_ip(),
    )
    response = make_response(jsonify({"user": user, "csrf_token": session_data["csrf_token"]}), 201)
    _set_auth_cookies(response, session_data)
    return response


@app.post("/auth/login")
def auth_login():
    limited = _rate_limit("login", 8, 300)
    if limited:
        return limited
    payload = request.get_json(silent=True) or {}
    user = auth_store.authenticate(
        str(payload.get("email") or ""),
        str(payload.get("password") or ""),
    )
    if not user:
        auth_store.log(
            "auth_logs",
            "login_failed",
            level="warning",
            details={"email": str(payload.get("email") or "")[:254]},
            ip_address=_client_ip(),
        )
        return jsonify({"error": "Invalid email or password."}), 401
    session_data = auth_store.issue_session(
        user,
        bool(payload.get("remember")),
        _client_ip(),
        request.headers.get("User-Agent", ""),
    )
    auth_store.log(
        "session_logs",
        "session_created",
        user_id=user["id"],
        details={"remember": bool(payload.get("remember"))},
        ip_address=_client_ip(),
    )
    response = make_response(jsonify({"user": user, "csrf_token": session_data["csrf_token"]}))
    _set_auth_cookies(response, session_data)
    return response


@app.get("/auth/me")
def auth_me():
    return jsonify({"user": g.current_user, "expires_at": g.auth_session["expires_at"]})


@app.post("/auth/logout")
def auth_logout():
    auth_store.revoke_session(str(g.auth_session["token_id"]))
    auth_store.log(
        "session_logs",
        "session_revoked",
        user_id=g.current_user["id"],
        ip_address=_client_ip(),
    )
    response = make_response(jsonify({"status": "logged_out"}))
    _clear_auth_cookies(response)
    return response


@app.post("/auth/forgot-password")
def auth_forgot_password():
    limited = _rate_limit("forgot_password", 5, 3600)
    if limited:
        return limited
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip().lower()
    token = auth_store.create_password_reset(email)
    response: dict[str, object] = {
        "message": "If the account exists, a password reset link has been sent."
    }
    expose_token = os.getenv(
        "AUTH_EXPOSE_RESET_TOKEN",
        "1" if APP_ENV != "production" else "0",
    ).lower() in {"1", "true", "yes"}
    delivery: dict[str, object] = {}
    if token:
        delivery = send_password_reset_email(EMAIL_CONFIG, email, token)
        if APP_ENV != "production":
            response["email_delivery"] = delivery
            response["reset_url"] = password_reset_url(EMAIL_CONFIG, token)
    elif APP_ENV != "production":
        response["email_delivery"] = {
            "sent": False,
            "status": "account_not_found",
            "provider": EMAIL_CONFIG.backend,
            "reason": "No active account exists for that email in this local database.",
        }
    if token and expose_token:
        response["reset_token"] = token
    auth_store.log(
        "auth_logs",
        "password_reset_requested",
        details={
            "account_found": bool(token),
            "email_delivery_status": delivery.get("status") if delivery else "account_not_found",
            "email_delivery_provider": delivery.get("provider") if delivery else "",
        },
        ip_address=_client_ip(),
    )
    return jsonify(response)


@app.post("/auth/reset-password")
def auth_reset_password():
    limited = _rate_limit("reset_password", 8, 3600)
    if limited:
        return limited
    payload = request.get_json(silent=True) or {}
    try:
        reset = auth_store.reset_password(
            str(payload.get("token") or ""),
            str(payload.get("password") or ""),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not reset:
        return jsonify({"error": "Reset token is invalid or expired."}), 400
    auth_store.log(
        "auth_logs",
        "password_reset_succeeded",
        ip_address=_client_ip(),
    )
    return jsonify({"message": "Password updated. Sign in with your new password."})


@app.get("/")
def home():
    return jsonify({
        "service": "SQL Copilot API",
        "status": "ok",
        "frontend": "Run the Next.js app in ../frontend",
        "legacy_ui": "/legacy",
        "endpoints": [
            "/health",
            "/auth/login",
            "/auth/signup",
            "/auth/me",
            "/sql",
            "/schema/catalog",
            "/schema/relationships",
            "/schema/er",
            "/schema/studio/tables",
            "/metadata/status",
            "/metadata/refresh",
            "/enterprise-schema",
            "/schema-request",
            "/schema-requests",
            "/metrics",
            "/runtime/config",
            "/runtime/provider/configure",
            "/runtime/email/configure",
            "/diagnostics/provider",
        ],
    })


@app.get("/legacy")
def legacy_ui():
    for filename in ("index.html", "index .html"):
        if (STATIC_DIR / filename).exists():
            return send_from_directory(STATIC_DIR, filename)
    return jsonify({
        "service": "SQL Copilot API",
        "status": "ok",
        "frontend": "Run the Next.js app in ../frontend",
        "endpoints": ["/sql", "/schema/relationships", "/schema/er", "/metrics"],
    })


@app.get("/favicon.ico")
def favicon():
    for filename in ("favicon.ico", "robot.jpg", "robot .jpg"):
        if (STATIC_DIR / filename).exists():
            return send_from_directory(STATIC_DIR, filename)
    return ("", 204)


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "schema_tables": sorted(schema_tables),
        "columns": len(column_documents),
        "provider": LLM_PROVIDER_CLIENT.health_check(deep=False),
    })


@app.get("/runtime/config")
def runtime_config_api():
    return jsonify({
        "provider": _current_provider_payload(deep=False),
        "email": _current_email_payload(),
        "paths": {
            "project_root": str(RUNTIME_PATHS.project_root),
            "runtime_root": str(RUNTIME_PATHS.runtime_root),
            "cache_root": str(RUNTIME_PATHS.cache_root),
            "sqlite_root": str(RUNTIME_PATHS.sqlite_root),
            "logs_root": str(RUNTIME_PATHS.logs_root),
            "model_root": str(RUNTIME_PATHS.model_root),
            "faiss_root": str(RUNTIME_PATHS.faiss_root),
            "temp_root": str(RUNTIME_PATHS.temp_root),
            "dynamic_schema_file": str(DYNAMIC_SCHEMA_FILE),
            "provider_config_file": str(RUNTIME_PROVIDER_ENV_FILE),
            "email_config_file": str(RUNTIME_EMAIL_ENV_FILE),
        },
    })


@app.post("/runtime/provider/configure")
@provider_config_required
def runtime_provider_configure_api():
    payload = request.get_json(silent=True) or {}
    try:
        result = _apply_runtime_provider_config(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    auth_store.log(
        "audit_logs",
        "llm_provider_configured",
        user_id=g.current_user["id"],
        details={
            "provider": PROVIDER_CONFIG.provider,
            "model": PROVIDER_CONFIG.chat_model,
            "base_url": PROVIDER_CONFIG.base_url,
            "api_key_present": bool(PROVIDER_CONFIG.api_key),
            "available": bool(LLM_PROVIDER_CLIENT.available),
        },
        ip_address=_client_ip(),
    )
    return jsonify(result)


@app.post("/runtime/email/configure")
@provider_config_required
def runtime_email_configure_api():
    payload = request.get_json(silent=True) or {}
    try:
        result = _apply_runtime_email_config(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    delivery = result.get("delivery") if isinstance(result, dict) else None
    auth_store.log(
        "audit_logs",
        "email_delivery_configured",
        user_id=g.current_user["id"],
        details={
            "backend": EMAIL_CONFIG.backend,
            "host": EMAIL_CONFIG.host,
            "sender": EMAIL_CONFIG.sender,
            "smtp_configured": EMAIL_CONFIG.smtp_configured,
            "password_present": bool(EMAIL_CONFIG.password),
            "delivery_status": delivery.get("status") if isinstance(delivery, dict) else "",
        },
        ip_address=_client_ip(),
    )
    return jsonify(result)


@app.get("/diagnostics/provider")
@admin_required
def provider_diagnostics_api():
    deep = str(request.args.get("deep", "0")).lower() in {"1", "true", "yes"}
    return jsonify({
        "status": LLM_PROVIDER_CLIENT.health_check(deep=deep),
        "metrics": LLM_PROVIDER_CLIENT.metrics(),
    })


@app.get("/schema/catalog")
def schema_catalog():
    relationships = get_enterprise_copilot().relationship_map()
    tables = [schema_catalog_entry(table) for table in sorted(schema_tables)]
    for table in tables:
        table["relationships"] = relationships.get(str(table["name"]), table["relationships"])
    enterprise_catalog = synthetic_enterprise_engine.generate_catalog()
    return jsonify({
        "summary": {
            "tables_count": len(tables),
            "relationships_count": sum(len(items) for items in relationships.values()),
            "dynamic_tables": len(dynamic_schema_tables),
            "enterprise_virtual_tables": enterprise_catalog["summary"]["tables_count"],
            "enterprise_virtual_relationships": enterprise_catalog["summary"]["relationships_count"],
        },
        "tables": tables,
        "relationships": relationships,
        "enterprise_preview": enterprise_catalog["summary"],
    })


@app.get("/schema/relationships")
def schema_relationships():
    return jsonify({
        "tables": sorted(schema_tables),
        "relationships": get_enterprise_copilot().relationship_map(),
    })


@app.get("/schema/er")
def schema_er_diagram():
    return jsonify({
        "format": "mermaid",
        "diagram": get_enterprise_copilot().er_diagram(),
    })


@app.get("/enterprise-schema")
def enterprise_schema():
    return jsonify(synthetic_enterprise_engine.generate_catalog())


def _dtype_to_sql(dtype: object) -> str:
    text = str(dtype).lower()
    if "int" in text:
        return "INTEGER"
    if any(token in text for token in ("float", "double", "decimal")):
        return "DECIMAL(18,2)"
    if "bool" in text:
        return "BOOLEAN"
    if "date" in text or "time" in text:
        return "TIMESTAMP"
    return "TEXT"


def _dataframe_schema(
    frame: pd.DataFrame,
    *,
    table_name: str,
    source_format: str,
) -> dict[str, object]:
    clean = frame.copy()
    clean.columns = [
        _normalise_identifier(column, f"column_{index + 1}")
        for index, column in enumerate(clean.columns)
    ]
    columns = [
        {
            "name": column,
            "data_type": _dtype_to_sql(clean[column].dtype),
            "description": f"Inferred from {source_format} field {column}.",
            "is_pk": index == 0 and column.endswith("_id"),
        }
        for index, column in enumerate(clean.columns)
    ]
    return {
        "source_format": source_format,
        "table": {
            "name": table_name,
            "domain": "Uploaded Schema",
            "purpose": f"Inferred from uploaded {source_format} sample.",
            "columns": columns,
            "sample_rows": clean.head(5).where(pd.notnull(clean), None).to_dict(orient="records"),
            "relationships": [],
            "indexes": [
                column["name"]
                for column in columns
                if column.get("is_pk") or column["name"] in {"status", "created_at"}
            ],
        },
    }


def _split_sql_columns(definition: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in definition:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _infer_sql_ddl_schema(content: str, filename: str) -> dict[str, object]:
    match = re.search(
        r"create\s+table\s+(?:if\s+not\s+exists\s+)?[`\"\[]?([a-zA-Z_][\w.]*).*?\((.*)\)",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise ValueError("SQL upload must contain a CREATE TABLE statement.")
    raw_table = match.group(1).split(".")[-1].strip("`\"[]")
    table_name = _normalise_identifier(raw_table or Path(filename).stem, "uploaded_table")
    body = match.group(2)
    columns: list[dict[str, object]] = []
    relationships: list[dict[str, str]] = []
    table_pk: set[str] = set()

    for part in _split_sql_columns(body):
        constraint = part.strip()
        lower = constraint.lower()
        if lower.startswith(("primary key", "foreign key", "unique", "constraint", "check")):
            pk_match = re.search(r"primary\s+key\s*\((.*?)\)", constraint, re.IGNORECASE)
            if pk_match:
                table_pk.update(
                    _normalise_identifier(item.strip(" `\"[]"), "id")
                    for item in pk_match.group(1).split(",")
                )
            fk_match = re.search(
                r"foreign\s+key\s*\((.*?)\)\s*references\s+([a-zA-Z_][\w.]*)\s*\((.*?)\)",
                constraint,
                re.IGNORECASE,
            )
            if fk_match:
                from_column = _normalise_identifier(fk_match.group(1).strip(" `\"[]"), "source_id")
                to_table = _normalise_identifier(fk_match.group(2).split(".")[-1], "target_table")
                to_column = _normalise_identifier(fk_match.group(3).strip(" `\"[]"), "target_id")
                relationships.append({
                    "from_table": table_name,
                    "from_column": from_column,
                    "to_table": to_table,
                    "to_column": to_column,
                })
            continue
        tokens = constraint.split()
        if len(tokens) < 2:
            continue
        name = _normalise_identifier(tokens[0].strip("`\"[]"), f"column_{len(columns) + 1}")
        data_type_tokens = []
        for token in tokens[1:]:
            if token.lower() in {
                "primary", "references", "not", "null", "default", "unique",
                "check", "constraint", "collate", "generated",
            }:
                break
            data_type_tokens.append(token)
        data_type = " ".join(data_type_tokens) or "TEXT"
        ref_match = re.search(
            r"references\s+([a-zA-Z_][\w.]*)\s*\((.*?)\)",
            constraint,
            re.IGNORECASE,
        )
        if ref_match:
            relationships.append({
                "from_table": table_name,
                "from_column": name,
                "to_table": _normalise_identifier(ref_match.group(1).split(".")[-1], "target_table"),
                "to_column": _normalise_identifier(ref_match.group(2).strip(" `\"[]"), "target_id"),
            })
        columns.append({
            "name": name,
            "data_type": data_type.upper(),
            "description": f"Inferred from SQL DDL column {name}.",
            "is_pk": "primary key" in lower or name in table_pk,
            "is_fk": bool(ref_match),
        })
    for column in columns:
        if column["name"] in table_pk:
            column["is_pk"] = True
    if not columns:
        raise ValueError("No columns could be inferred from SQL DDL.")
    return {
        "source_format": "sql",
        "table": {
            "name": table_name,
            "domain": "Uploaded Schema",
            "purpose": "Inferred from uploaded SQL DDL.",
            "columns": columns,
            "relationships": relationships,
            "indexes": [
                column["name"]
                for column in columns
                if column.get("is_pk") or column.get("is_fk")
            ],
        },
    }


def infer_uploaded_schema(filename: str, content: bytes) -> dict[str, object]:
    suffix = Path(filename).suffix.lower()
    table_name = _normalise_identifier(Path(filename).stem, "uploaded_table")
    if suffix == ".csv":
        frame = pd.read_csv(io.BytesIO(content), nrows=100)
        return _dataframe_schema(frame, table_name=table_name, source_format="csv")
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(io.BytesIO(content), nrows=100)
        return _dataframe_schema(frame, table_name=table_name, source_format="excel")
    if suffix == ".json":
        parsed = json.loads(content.decode("utf-8", errors="replace"))
        rows = parsed
        if isinstance(parsed, dict):
            rows = parsed.get("rows") or parsed.get("data") or parsed.get("items") or [parsed]
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise ValueError("JSON upload did not contain tabular rows.")
        return _dataframe_schema(frame, table_name=table_name, source_format="json")
    if suffix == ".sql":
        return _infer_sql_ddl_schema(content.decode("utf-8", errors="replace"), filename)
    if suffix == ".parquet":
        try:
            frame = pd.read_parquet(io.BytesIO(content))
        except Exception as exc:
            raise ValueError(
                "Parquet upload requires a pandas parquet engine such as pyarrow or fastparquet."
            ) from exc
        return _dataframe_schema(frame.head(100), table_name=table_name, source_format="parquet")
    raise ValueError("Unsupported upload type.")


@app.get("/metadata/status")
def metadata_status_api():
    return jsonify({
        "status": dict(metadata_refresh_status),
        "dynamic_schema_file": str(DYNAMIC_SCHEMA_FILE),
        "dynamic_tables": [
            schema_catalog_entry(table)
            for table in sorted(dynamic_schema_tables)
            if table in schema_tables
        ],
        "storage": {
            "runtime_root": str(RUNTIME_PATHS.runtime_root),
            "faiss_root": str(RUNTIME_PATHS.faiss_root),
            "model_root": str(RUNTIME_PATHS.model_root),
        },
    })


@app.post("/metadata/refresh")
@admin_required
def metadata_refresh_api():
    status = refresh_metadata_engine(reason="admin_api")
    auth_store.log(
        "audit_logs",
        "metadata_refreshed",
        user_id=g.current_user["id"],
        details=status,
        ip_address=_client_ip(),
    )
    return jsonify({"status": status})


@app.post("/schema/studio/tables")
@admin_required
def schema_studio_create_table_api():
    payload = request.get_json(silent=True) or {}
    try:
        table = _normalise_identifier(payload.get("name") or payload.get("table_name"), "dynamic_table")
        if table in schema_tables and table not in dynamic_schema_tables:
            return jsonify({"error": f"'{table}' is an Excel-backed table and cannot be overwritten."}), 409
        entry = _upsert_schema_table(payload, source="dynamic")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    auth_store.log(
        "audit_logs",
        "schema_table_upserted",
        user_id=g.current_user["id"],
        details={"table": entry["name"]},
        ip_address=_client_ip(),
    )
    return jsonify({
        "table": entry,
        "metadata_status": dict(metadata_refresh_status),
    }), 201


@app.patch("/schema/studio/tables/<table_name>")
@admin_required
def schema_studio_update_table_api(table_name: str):
    payload = request.get_json(silent=True) or {}
    table = _normalise_identifier(table_name, "dynamic_table")
    if table not in dynamic_schema_tables:
        return jsonify({"error": "Only dynamic schema tables can be edited live."}), 400
    payload["name"] = table
    try:
        entry = _upsert_schema_table(payload, source="dynamic")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "table": entry,
        "metadata_status": dict(metadata_refresh_status),
    })


@app.delete("/schema/studio/tables/<table_name>")
@admin_required
def schema_studio_delete_table_api(table_name: str):
    deleted, message = _delete_schema_table(table_name)
    if not deleted:
        status = 404 if "not found" in message else 400
        return jsonify({"error": message}), status
    auth_store.log(
        "audit_logs",
        "schema_table_deleted",
        user_id=g.current_user["id"],
        details={"table": message},
        ip_address=_client_ip(),
    )
    return jsonify({
        "deleted": message,
        "metadata_status": dict(metadata_refresh_status),
    })


@app.post("/schema/studio/apply-request/<int:request_id>")
@admin_required
def schema_studio_apply_request_api(request_id: int):
    schema_request = schema_request_repo.get(request_id)
    if not schema_request:
        return jsonify({"error": "schema request not found"}), 404
    generated = schema_request.get("generated_schema") or {}
    tables = generated.get("tables") if isinstance(generated, dict) else []
    if not isinstance(tables, list) or not tables:
        return jsonify({"error": "schema request has no generated tables to apply"}), 400
    applied = []
    top_level_relationships = generated.get("relationships", []) if isinstance(generated, dict) else []
    for table_payload in tables:
        if not isinstance(table_payload, dict):
            continue
        table_name = _normalise_identifier(table_payload.get("name") or table_payload.get("table_name"), "dynamic_table")
        table_relationships = list(table_payload.get("relationships") or [])
        for relationship in top_level_relationships if isinstance(top_level_relationships, list) else []:
            parsed = _relationship_payload(relationship, table_name)
            if parsed and parsed["from_table"] == table_name:
                table_relationships.append(parsed)
        merged = {
            **table_payload,
            "relationships": table_relationships,
            "domain": table_payload.get("domain") or generated.get("domain") or "Dynamic Enterprise Schema",
            "purpose": table_payload.get("purpose") or schema_request.get("user_notes") or schema_request.get("business_context"),
            "source": f"schema_request:{request_id}",
        }
        try:
            applied.append(_upsert_schema_table(merged, source=f"schema_request:{request_id}"))
        except ValueError as exc:
            return jsonify({"error": str(exc), "table": table_name}), 400
    schema_request_repo.update_status(request_id, "generated")
    auth_store.log(
        "audit_logs",
        "schema_request_applied",
        user_id=g.current_user["id"],
        details={"request_id": request_id, "tables": [item["name"] for item in applied]},
        ip_address=_client_ip(),
    )
    return jsonify({
        "request_id": request_id,
        "applied_tables": applied,
        "metadata_status": dict(metadata_refresh_status),
    })


@app.route("/schema-request", methods=["POST", "OPTIONS"])
def schema_request_api():
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    payload["requested_by_user_id"] = g.current_user["id"]
    upload = request.files.get("file")
    if upload and upload.filename:
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in {".csv", ".json", ".xlsx", ".xls", ".sql", ".parquet"}:
            return jsonify({"error": "Only CSV, Excel, JSON, SQL, and Parquet uploads are supported."}), 400
        content = upload.read(5_000_001)
        if len(content) > 5_000_000:
            return jsonify({"error": "Upload must be 5 MB or smaller."}), 400
        try:
            inferred_schema = infer_uploaded_schema(upload.filename, content)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        payload["attachment_name"] = Path(upload.filename).name[:255]
        payload["attachment_content"] = json.dumps({
            "inferred_schema": inferred_schema,
            "preview_bytes": len(content),
        })
        payload["inferred_schema"] = inferred_schema
        inferred_table = inferred_schema.get("table", {}) if isinstance(inferred_schema, dict) else {}
        if not payload.get("table_name") and isinstance(inferred_table, dict):
            payload["table_name"] = inferred_table.get("name", "")
        if not payload.get("columns") and isinstance(inferred_table, dict):
            payload["columns"] = [
                column.get("name")
                for column in inferred_table.get("columns", [])
                if isinstance(column, dict) and column.get("name")
            ]
        payload["request_kind"] = {
            ".csv": "csv_upload",
            ".json": "json_upload",
            ".xlsx": "excel_upload",
            ".xls": "excel_upload",
            ".sql": "sql_upload",
            ".parquet": "parquet_upload",
        }[suffix]
    if isinstance(payload.get("columns"), str):
        payload["columns"] = [
            item.strip() for item in str(payload["columns"]).split(",") if item.strip()
        ]
    if not any(payload.get(key) for key in ("table_name", "requested_tables", "business_purpose", "user_notes")):
        return jsonify({"error": "table_name, requested_tables, business_purpose, or user_notes is required"}), 400
    created = schema_request_repo.create(payload)
    auth_store.log(
        "feedback_logs",
        "schema_request_created",
        user_id=g.current_user["id"],
        details={"request_id": created.get("request_id"), "kind": payload.get("request_kind", "table")},
        ip_address=_client_ip(),
    )
    return jsonify(created), 201


@app.get("/schema-requests")
def schema_requests_api():
    status = request.args.get("status")
    user_id = None if g.current_user["role"] == "admin" else g.current_user["id"]
    return jsonify({
        "requests": schema_request_repo.list(status=status, user_id=user_id),
        "analytics": schema_request_repo.analytics(user_id=user_id),
    })


@app.patch("/schema-request/<int:request_id>/status")
@admin_required
def schema_request_status_api(request_id: int):
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"pending", "approved", "generated", "rejected"}:
        return jsonify({"error": "status must be pending, approved, generated, or rejected"}), 400
    updated = schema_request_repo.update_status(request_id, status)
    if not updated:
        return jsonify({"error": "schema request not found"}), 404
    auth_store.log(
        "audit_logs",
        "schema_request_status_updated",
        user_id=g.current_user["id"],
        details={"request_id": request_id, "status": status},
        ip_address=_client_ip(),
    )
    return jsonify(updated)


@app.post("/feedback")
def feedback_api():
    payload = request.get_json(silent=True) or {}
    try:
        created = auth_store.add_feedback(
            g.current_user["id"],
            str(payload.get("category") or "general"),
            str(payload.get("message") or ""),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    auth_store.log(
        "feedback_logs",
        "feedback_created",
        user_id=g.current_user["id"],
        details={"feedback_id": created.get("id"), "category": created.get("category")},
        ip_address=_client_ip(),
    )
    return jsonify(created), 201


@app.get("/feedback")
@admin_required
def feedback_list_api():
    return jsonify({"feedback": auth_store.list_feedback()})


@app.post("/logs/frontend")
def frontend_log_api():
    payload = request.get_json(silent=True) or {}
    level = str(payload.get("level") or "error").lower()
    table = "ui_errors" if level == "error" else "frontend_logs"
    auth_store.log(
        table,
        str(payload.get("event") or "frontend_event"),
        user_id=g.current_user["id"],
        level=level,
        details={
            "message": str(payload.get("message") or "")[:5000],
            "path": str(payload.get("path") or "")[:500],
            "stack": str(payload.get("stack") or "")[:10_000],
        },
        ip_address=_client_ip(),
    )
    return ("", 204)


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
        if (
            str(result.get("sql", "")).lower().strip().startswith("select")
            and not result.get("insights", {}).get("generic_sql")
        ):
            result = optimize_with_rl_feedback(query, result["sql"], result["insights"])

        return jsonify({
            "query": query,
            "sql": result["sql"],
            "message": (
                "Generated using enterprise schema agents, grounded validation, "
                "confidence scoring, and provider fallback."
            ),
            "insights": result["insights"],
        })

    except Exception as exc:
        log_step(f"[error] {exc}")
        return jsonify({"error": str(exc)}), 500


METRICS_RANGE_DAYS: dict[str, int | None] = {
    "day": 1,
    "week": 7,
    "month": 30,
    "quarter": 90,
    "year": 365,
    "all": None,
}


def _metric_timestamp_seconds(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _filter_metrics_by_range(
    rows: list,
    days: int | None,
    timestamp_getter,
) -> list:
    if days is None:
        return list(rows)
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86_400)
    return [
        row
        for row in rows
        if (timestamp := _metric_timestamp_seconds(timestamp_getter(row))) is not None
        and timestamp >= cutoff
    ]


def _metrics_range_from_request() -> tuple[str, int | None]:
    raw = str(request.args.get("range", "week")).strip().lower()
    range_key = raw if raw in METRICS_RANGE_DAYS else "week"
    return range_key, METRICS_RANGE_DAYS[range_key]


def _metrics_range_payload(range_key: str, days: int | None) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    start = None
    if days is not None:
        start = datetime.fromtimestamp(now.timestamp() - (days * 86_400), timezone.utc).isoformat()
    return {
        "key": range_key,
        "days": days,
        "from": start,
        "to": now.isoformat(),
    }


def load_agent_telemetry_metrics(days: int | None = None) -> dict:
    with sqlite3.connect(FEEDBACK_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_telemetry'"
        ).fetchone()
        if not exists:
            return {
                "intent_accuracy": 0,
                "planner_accuracy": 0,
                "validation_accuracy": 0,
                "optimization_accuracy": 0,
                "coverage_score": 0,
                "missing_concepts": [],
                "trend": [],
            }
        available_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(agent_telemetry)").fetchall()
        }
        base_columns = [
            "query", "confidence", "valid", "intent_score", "entity_score", "join_score",
            "column_score", "aggregation_score", "semantic_score", "missing_concepts", "timestamp",
        ]
        optional_defaults = {
            "provider": "'local'",
            "model": "'deterministic'",
            "complexity": "'SIMPLE'",
            "system_confidence": "confidence",
            "model_confidence": "0",
            "planner_confidence": "0",
            "validator_confidence": "0",
            "coverage_confidence": "0",
            "fallback_used": "0",
            "retry_count": "0",
            "latency_ms": "0",
        }
        selected = [
            column if column in available_columns else f"{default} AS {column}"
            for column, default in {**{column: column for column in base_columns}, **optional_defaults}.items()
        ]
        rows = conn.execute(
            f"""
            SELECT {', '.join(selected)}
            FROM agent_telemetry
            ORDER BY timestamp ASC
            """
        ).fetchall()
    rows = _filter_metrics_by_range(rows, days, lambda row: row["timestamp"])
    if not rows:
        return {
            "intent_accuracy": 0,
            "planner_accuracy": 0,
            "validation_accuracy": 0,
            "optimization_accuracy": 0,
            "coverage_score": 0,
            "missing_concepts": [],
            "trend": [],
        }

    def avg(name: str) -> float:
        return round(sum(float(row[name]) for row in rows) / len(rows), 2)

    def has_signal(name: str) -> bool:
        return any(float(row[name] or 0) > 0 for row in rows)

    missing: list[str] = []
    for row in rows[-25:]:
        try:
            missing.extend(json.loads(row["missing_concepts"] or "[]"))
        except json.JSONDecodeError:
            pass
    enterprise_rows = [row for row in rows if row["complexity"] == "ENTERPRISE"]
    fallback_rows = [row for row in rows if int(row["fallback_used"] or 0)]
    planner_metric = avg("planner_confidence") if has_signal("planner_confidence") else avg("entity_score")
    validator_metric = avg("validator_confidence") if has_signal("validator_confidence") else avg("semantic_score")
    coverage_metric = avg("coverage_confidence") if has_signal("coverage_confidence") else avg("confidence")
    return {
        "intent_accuracy": avg("intent_score"),
        "planner_accuracy": planner_metric,
        "validation_accuracy": validator_metric,
        "optimization_accuracy": round((sum(1 for row in rows if row["valid"]) / len(rows)) * 100, 2),
        "coverage_score": coverage_metric,
        "missing_concepts": sorted(set(missing))[:20],
        "fallback_rate": round((len(fallback_rows) / len(rows)) * 100, 2),
        "enterprise_success_rate": round((
            sum(1 for row in enterprise_rows if row["valid"]) / len(enterprise_rows)
        ) * 100, 2) if enterprise_rows else 0,
        "trend": [
            {
                "query": row["query"],
                "confidence": float(row["confidence"]),
                "valid": bool(row["valid"]),
                "intent_score": float(row["intent_score"]),
                "entity_score": float(row["entity_score"]),
                "join_score": float(row["join_score"]),
                "column_score": float(row["column_score"]),
                "aggregation_score": float(row["aggregation_score"]),
                "semantic_score": float(row["semantic_score"]),
                "timestamp": row["timestamp"],
                "provider": row["provider"],
                "model": row["model"],
                "complexity": row["complexity"],
                "system_confidence": float(row["system_confidence"]),
                "model_confidence": float(row["model_confidence"]),
                "planner_confidence": float(row["planner_confidence"]),
                "validator_confidence": float(row["validator_confidence"]),
                "coverage_confidence": float(row["coverage_confidence"]),
                "fallback_used": bool(row["fallback_used"]),
                "retry_count": int(row["retry_count"]),
                "latency_ms": float(row["latency_ms"]),
            }
            for row in rows[-100:]
        ],
    }


def load_feedback_metrics(*, days: int | None = None, range_key: str = "all") -> dict:
    ensure_feedback_table(FEEDBACK_DB_PATH)
    with sqlite3.connect(FEEDBACK_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT query, generated_sql, reward, execution_time, validation_status, timestamp
            FROM agent_feedback
            ORDER BY timestamp ASC
            """
        ).fetchall()
    rows = _filter_metrics_by_range(rows, days, lambda row: row[5])

    if not rows:
        telemetry = load_agent_telemetry_metrics(days=days)
        telemetry_trend = list(telemetry.get("trend") or [])
        trend = [
            {
                "query": point.get("query", ""),
                "reward": 1.0 if point.get("valid") else 0.0,
                "execution_time": round(float(point.get("latency_ms") or 0.0) / 1000, 4),
                "validation_status": "Valid" if point.get("valid") else "Needs review",
                "timestamp": point.get("timestamp", ""),
                "valid": bool(point.get("valid")),
                "confidence": float(point.get("confidence", 0.0)),
                "planner_score": float(point.get("planner_confidence") or point.get("entity_score") or 0.0),
                "validator_score": float(point.get("validator_confidence") or point.get("semantic_score") or 0.0),
                "intent_score": float(point.get("intent_score") or 0.0),
                "join_score": float(point.get("join_score") or 0.0),
                "column_score": float(point.get("column_score") or 0.0),
                "aggregation_score": float(point.get("aggregation_score") or 0.0),
                "semantic_score": float(point.get("semantic_score") or 0.0),
                "system_confidence": float(point.get("system_confidence") or point.get("confidence") or 0.0),
                "coverage_confidence": float(point.get("coverage_confidence") or 0.0),
                "model_confidence": float(point.get("model_confidence") or 0.0),
                "provider": point.get("provider", "local"),
                "model": point.get("model", "deterministic"),
                "complexity": point.get("complexity", "SIMPLE"),
                "fallback_used": bool(point.get("fallback_used")),
                "retry_count": int(point.get("retry_count") or 0),
                "latency_ms": float(point.get("latency_ms") or 0.0),
            }
            for point in telemetry_trend[-100:]
        ]
        llm_metrics = LLM_PROVIDER_CLIENT.metrics()
        return {
            "total": len(trend),
            "average_reward": round(sum(float(point["reward"]) for point in trend) / len(trend), 2) if trend else 0,
            "query_success_rate": round((sum(1 for point in trend if point["valid"]) / len(trend)) * 100, 2) if trend else 0,
            "sql_accuracy": round((sum(1 for point in trend if point["valid"]) / len(trend)) * 100, 2) if trend else 0,
            "average_latency": round(sum(float(point["execution_time"]) for point in trend) / len(trend), 4) if trend else 0,
            "trend": trend,
            "range": _metrics_range_payload(range_key, days),
            "planner_accuracy": telemetry["planner_accuracy"],
            "validator_precision": telemetry["validation_accuracy"],
            "confidence_reliability": telemetry["coverage_score"],
            "agent_telemetry": telemetry,
            "schema_growth": schema_request_repo.analytics(),
            "enterprise_schema": synthetic_enterprise_engine.generate_catalog()["summary"],
            "llm_provider": LLM_PROVIDER_CLIENT.health_check(deep=False),
            "llm_metrics": llm_metrics,
            "research_metrics": {
                "multi_hop_success_rate": 0,
                "five_plus_table_success_rate": 0,
                "clarification_rate": 0,
                "fallback_rate": llm_metrics.get("fallback_rate", 0),
            },
        }

    telemetry = load_agent_telemetry_metrics(days=days)
    telemetry_trend = list(telemetry.get("trend") or [])
    used_telemetry: set[int] = set()

    def timestamp_value(value: object) -> float:
        text = str(value or "").strip()
        if not text:
            return 0.0
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            return 0.0

    def matching_telemetry(query: str, timestamp: object) -> dict[str, object]:
        target_time = timestamp_value(timestamp)
        candidates = [
            (index, point)
            for index, point in enumerate(telemetry_trend)
            if index not in used_telemetry and point.get("query") == query
        ]
        if not candidates:
            return {}
        index, point = min(
            candidates,
            key=lambda item: abs(timestamp_value(item[1].get("timestamp")) - target_time),
        )
        used_telemetry.add(index)
        return point

    trend = []
    for row in rows[-100:]:
        telemetry_point = matching_telemetry(str(row[0]), row[5])
        validation_status = str(row[4])
        valid = validation_status.lower().startswith("valid")
        trend.append({
            "query": row[0],
            "reward": float(row[2]),
            "execution_time": float(row[3]),
            "validation_status": validation_status,
            "timestamp": row[5],
            "valid": bool(telemetry_point.get("valid", valid)),
            "confidence": float(telemetry_point.get("confidence", 100.0 if valid else 0.0)),
            "planner_score": float(telemetry_point.get("planner_confidence") or telemetry_point.get("entity_score") or 0.0),
            "validator_score": float(telemetry_point.get("validator_confidence") or telemetry_point.get("semantic_score") or (100.0 if valid else 0.0)),
            "intent_score": float(telemetry_point.get("intent_score", 0.0)),
            "join_score": float(telemetry_point.get("join_score", 0.0)),
            "column_score": float(telemetry_point.get("column_score", 0.0)),
            "aggregation_score": float(telemetry_point.get("aggregation_score", 0.0)),
            "semantic_score": float(telemetry_point.get("semantic_score", 0.0)),
            "system_confidence": float(telemetry_point.get("system_confidence") or telemetry_point.get("confidence") or (100.0 if valid else 0.0)),
            "coverage_confidence": float(telemetry_point.get("coverage_confidence", 0.0)),
            "model_confidence": float(telemetry_point.get("model_confidence", 0.0)),
            "provider": telemetry_point.get("provider", "local"),
            "model": telemetry_point.get("model", "deterministic"),
            "complexity": telemetry_point.get("complexity", "SIMPLE"),
            "fallback_used": bool(telemetry_point.get("fallback_used", False)),
            "retry_count": int(telemetry_point.get("retry_count", 0)),
            "latency_ms": float(telemetry_point.get("latency_ms", 0.0)),
        })

    rewards = [float(row[2]) for row in rows]
    latencies = [float(row[3]) for row in rows]
    successes = [
        row for row in rows
        if str(row[4]).lower().startswith("valid") and float(row[2]) > 0
    ]
    valid_sql = [
        row for row in rows
        if str(row[4]).lower().startswith("valid")
    ]

    llm_metrics = LLM_PROVIDER_CLIENT.metrics()
    return {
        "total": len(rows),
        "average_reward": round(sum(rewards) / len(rewards), 2),
        "query_success_rate": round((len(successes) / len(rows)) * 100, 2),
        "sql_accuracy": round((len(valid_sql) / len(rows)) * 100, 2),
        "planner_accuracy": telemetry["planner_accuracy"],
        "validator_precision": telemetry["validation_accuracy"],
        "confidence_reliability": telemetry["coverage_score"],
        "average_latency": round(sum(latencies) / len(latencies), 4),
        "trend": trend,
        "range": _metrics_range_payload(range_key, days),
        "agent_telemetry": telemetry,
        "schema_growth": schema_request_repo.analytics(),
        "enterprise_schema": synthetic_enterprise_engine.generate_catalog()["summary"],
        "llm_provider": LLM_PROVIDER_CLIENT.health_check(deep=False),
        "llm_metrics": llm_metrics,
        "research_metrics": {
            "multi_hop_success_rate": round((
                sum(1 for point in telemetry_trend if float(point.get("join_score", 0.0)) >= 90.0 and point.get("valid"))
                / len(telemetry_trend)
            ) * 100, 2) if telemetry_trend else 0,
            "five_plus_table_success_rate": telemetry.get("enterprise_success_rate", 0),
            "clarification_rate": round((
                sum(1 for point in telemetry_trend if not point.get("valid"))
                / len(telemetry_trend)
            ) * 100, 2) if telemetry_trend else 0,
            "fallback_rate": telemetry.get("fallback_rate", llm_metrics.get("fallback_rate", 0)),
        },
    }


@app.get("/metrics")
def metrics_api():
    range_key, days = _metrics_range_from_request()
    return jsonify(load_feedback_metrics(days=days, range_key=range_key))


@app.get("/dashboard")
def dashboard():
    metrics = load_feedback_metrics()
    trend_json = json.dumps(metrics["trend"])
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>SQL Copilot RL Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f7f8fa; color: #18202a; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px; }}
    h1 {{ font-size: 28px; margin: 0 0 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }}
    .card {{ background: #fff; border: 1px solid #dde2ea; border-radius: 8px; padding: 16px; }}
    .label {{ color: #5b6675; font-size: 13px; }}
    .value {{ font-size: 26px; font-weight: 700; margin-top: 6px; }}
    .chart {{ margin-top: 18px; background: #fff; border: 1px solid #dde2ea; border-radius: 8px; padding: 12px; }}
  </style>
</head>
<body>
<main>
  <h1>RL Agent Metrics</h1>
  <section class="grid">
    <div class="card"><div class="label">Average reward</div><div class="value">{metrics["average_reward"]}</div></div>
    <div class="card"><div class="label">Query success rate</div><div class="value">{metrics["query_success_rate"]}%</div></div>
    <div class="card"><div class="label">SQL accuracy</div><div class="value">{metrics["sql_accuracy"]}%</div></div>
    <div class="card"><div class="label">Average latency</div><div class="value">{metrics["average_latency"]}s</div></div>
  </section>
  <div id="reward-chart" class="chart"></div>
  <div id="latency-chart" class="chart"></div>
</main>
<script>
const trend = {trend_json};
const x = trend.map((row, index) => row.timestamp || index);
Plotly.newPlot('reward-chart', [{{
  x, y: trend.map(row => row.reward), mode: 'lines+markers', name: 'Reward'
}}], {{ title: 'Agent Reward Trend', margin: {{ t: 48, r: 24, b: 48, l: 48 }} }});
Plotly.newPlot('latency-chart', [{{
  x, y: trend.map(row => row.execution_time), mode: 'lines+markers', name: 'Latency'
}}], {{ title: 'Execution Latency Trend', margin: {{ t: 48, r: 24, b: 48, l: 48 }} }});
</script>
</body>
</html>
"""


 
# 19. RUN
 

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    Timer(1, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    try:
        import uvicorn
    except ImportError:
        log_step("[server] uvicorn not installed; falling back to Flask development server")
        app.run(host="0.0.0.0", port=port, debug=True)
    else:
        if asgi_app is None:
            raise RuntimeError("asgiref is required to run this Flask app with uvicorn")
        uvicorn.run(asgi_app, host="0.0.0.0", port=port)
