from __future__ import annotations

import io
import json
import os
import sqlite3
import importlib
from pathlib import Path

import pytest

from backend.auth import AuthStore, SlidingWindowRateLimiter
from backend.email_delivery import load_email_config, send_password_reset_email


def test_auth_store_hashes_password_and_revokes_session(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")
    user = store.create_user(
        "Ada Lovelace",
        "ada@example.com",
        "StrongPass1",
    )

    with sqlite3.connect(store.db_path) as conn:
        password_hash = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()[0]

    assert password_hash.startswith(("$2a$", "$2b$"))
    assert store.authenticate("ada@example.com", "wrong") is None
    authenticated = store.authenticate("ada@example.com", "StrongPass1")
    assert authenticated is not None

    session = store.issue_session(authenticated, False, "127.0.0.1", "pytest")
    validated = store.validate_session(session["token"])
    assert validated is not None
    assert validated[0]["email"] == "ada@example.com"

    store.revoke_session(session["token_id"])
    assert store.validate_session(session["token"]) is None


def test_auth_store_uses_managed_signing_secret(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"
    secret = "managed-production-secret-with-32-bytes"
    store = AuthStore(db_path, signing_secret=secret)
    user = store.create_user("Mary Jackson", "mary@example.com", "RocketPass1")
    session = store.issue_session(user, False, "127.0.0.1", "pytest")

    assert AuthStore(
        db_path,
        signing_secret=secret,
    ).validate_session(session["token"])
    assert AuthStore(
        db_path,
        signing_secret="different-production-secret-with-32-bytes",
    ).validate_session(session["token"]) is None
    with pytest.raises(ValueError, match="at least 32 bytes"):
        AuthStore(db_path, signing_secret="too-short")


def test_existing_user_can_be_promoted_to_admin(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")
    store.create_user("Shashank Singh", "shashank@example.com", "StrongPass1")

    promoted = store.set_user_role("shashank@example.com", "admin")

    assert promoted["role"] == "admin"
    assert store.authenticate("shashank@example.com", "StrongPass1")["role"] == "admin"


def test_password_reset_is_single_use_and_revokes_sessions(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")
    user = store.create_user("Grace Hopper", "grace@example.com", "BeforePass1")
    session = store.issue_session(user, True, "127.0.0.1", "pytest")
    token = store.create_password_reset("grace@example.com")

    assert token
    assert store.reset_password(token, "AfterPass2") is True
    assert store.reset_password(token, "AfterPass2") is False
    assert store.authenticate("grace@example.com", "BeforePass1") is None
    assert store.authenticate("grace@example.com", "AfterPass2") is not None
    assert store.validate_session(session["token"]) is None


def test_password_reset_email_writes_development_outbox(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_BACKEND", "file")
    monkeypatch.setenv("EMAIL_OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:4000")
    config = load_email_config(tmp_path, "http://localhost:4000")

    result = send_password_reset_email(config, "grace@example.com", "reset-token")

    assert result["status"] == "outbox"
    outbox_path = Path(str(result["outbox_path"]))
    assert outbox_path.exists()
    assert "reset-token" in outbox_path.read_text(encoding="utf-8")


def test_auth_api_sets_http_only_cookie_and_enforces_csrf(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_module = importlib.import_module("backend.app")

    store = AuthStore(tmp_path / "api-auth.db")
    monkeypatch.setattr(app_module, "auth_store", store)
    monkeypatch.setattr(app_module, "rate_limiter", SlidingWindowRateLimiter())
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    signup = client.post(
        "/auth/signup",
        json={
            "name": "Katherine Johnson",
            "email": "katherine@example.com",
            "password": "OrbitalPass1",
        },
    )

    assert signup.status_code == 201
    assert "HttpOnly" in signup.headers.getlist("Set-Cookie")[0]
    assert client.get("/auth/me").status_code == 200

    duplicate = client.post(
        "/auth/signup",
        json={
            "name": "Katherine Johnson",
            "email": "katherine@example.com",
            "password": "OrbitalPass1",
        },
    )
    assert duplicate.status_code == 400

    assert client.get("/feedback").status_code == 403
    assert client.post("/auth/logout").status_code == 403
    csrf_cookie = client.get_cookie(app_module.CSRF_COOKIE)
    assert csrf_cookie is not None
    feedback = client.post(
        "/feedback",
        json={"category": "ux", "message": "Keep the chat composer visible."},
        headers={"X-CSRF-Token": csrf_cookie.value},
    )
    assert feedback.status_code == 201
    logout = client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": csrf_cookie.value},
    )
    assert logout.status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert client.post("/sql", json={"query": "Show projects"}).status_code == 401


def test_runtime_provider_configure_reloads_without_exposing_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_module = importlib.import_module("backend.app")

    for name in (
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_API_KEY",
        "LLM_API_BASE",
        "NVIDIA_API_KEY",
        "SQL_COPILOT_LLM_PROVIDER",
        "SQL_COPILOT_LLM_API_KEY",
        "SQL_COPILOT_REMOTE_LLM",
    ):
        monkeypatch.delenv(name, raising=False)

    for name in (
        "PROVIDER_CONFIG",
        "USE_REMOTE_LLM",
        "BASE_URL",
        "API_KEY",
        "MAX_RETRIES",
        "http_client",
        "embeddings",
        "LLM_PROVIDER_CLIENT",
        "llm",
        "enterprise_copilot",
    ):
        monkeypatch.setattr(app_module, name, getattr(app_module, name), raising=False)

    class FakeProvider:
        def __init__(self, config) -> None:
            self.config = config
            self.available = config.chat_enabled
            self.chat_client = None

        def health_check(self, *, deep: bool = False):
            return {
                "provider": self.config.provider,
                "model": self.config.chat_model,
                "adapter": "openai-chat-completions",
                "configured": bool(self.config.api_key),
                "available": self.available,
                "status": "ok" if deep and self.available else "ready",
                "base_url": self.config.base_url,
            }

        def metrics(self):
            return {}

    store = AuthStore(tmp_path / "api-auth.db")
    store.create_user("LLM User", "llm@example.com", "StrongPass1")
    monkeypatch.setattr(app_module, "auth_store", store)
    monkeypatch.setattr(app_module, "rate_limiter", SlidingWindowRateLimiter())
    monkeypatch.setattr(app_module, "APP_ENV", "development")
    monkeypatch.setattr(app_module, "RUNTIME_PROVIDER_ENV_FILE", tmp_path / "provider.env")
    monkeypatch.setattr(app_module, "create_llm_provider", lambda config, **_: FakeProvider(config))
    monkeypatch.setattr(app_module, "_create_http_client", lambda _config: None)
    monkeypatch.setattr(app_module, "_create_embeddings", lambda _config, _client: None)
    monkeypatch.setattr(app_module, "enterprise_copilot", object())
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    login = client.post(
        "/auth/login",
        json={
            "email": "llm@example.com",
            "password": "StrongPass1",
            "remember": False,
        },
    )
    assert login.status_code == 200
    csrf_cookie = client.get_cookie(app_module.CSRF_COOKIE)
    assert csrf_cookie is not None

    response = client.post(
        "/runtime/provider/configure",
        json={
            "provider": "nvidia",
            "model": "openai/gpt-oss-20b",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key": "secret-test-key",
            "verify": True,
        },
        headers={"X-CSRF-Token": csrf_cookie.value},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["provider"]["selected"] == "nvidia"
    assert body["provider"]["api_key_present"] is True
    assert body["provider"]["status"]["available"] is True
    assert "secret-test-key" not in json.dumps(body)
    saved_provider_config = (tmp_path / "provider.env").read_text(encoding="utf-8")
    assert "NVIDIA_API_KEY=secret-test-key" in saved_provider_config
    assert "LLM_API_KEY=secret-test-key" not in saved_provider_config
    assert app_module.enterprise_copilot is None


def test_runtime_provider_local_config_drops_stale_remote_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_module = importlib.import_module("backend.app")

    stale_runtime_file = tmp_path / "provider.env"
    stale_runtime_file.write_text(
        "LLM_PROVIDER=nvidia\n"
        "LLM_MODEL=openai/gpt-oss-20b\n"
        "LLM_API_BASE=https://integrate.api.nvidia.com/v1\n"
        "LLM_API_KEY=stale-key\n"
        "SQL_COPILOT_REMOTE_LLM=1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "RUNTIME_PROVIDER_ENV_FILE", stale_runtime_file)
    monkeypatch.setattr(app_module, "PROVIDER_CONFIG", app_module.load_provider_config(tmp_path))
    monkeypatch.setenv("LLM_API_KEY", "stale-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "stale-nvidia-key")

    result = app_module._apply_runtime_provider_config({
        "provider": "local",
        "model": "deterministic",
        "base_url": "",
    })

    saved = stale_runtime_file.read_text(encoding="utf-8")
    assert result["provider"]["selected"] == "local"
    assert "LLM_PROVIDER=local" in saved
    assert "LLM_MODEL=deterministic" in saved
    assert "SQL_COPILOT_REMOTE_LLM=0" in saved
    assert "LLM_API_KEY" not in saved
    assert "NVIDIA_API_KEY" not in saved
    assert "LLM_API_BASE" not in saved
    assert "LLM_API_KEY" not in os.environ
    assert "NVIDIA_API_KEY" not in os.environ


def test_runtime_email_configure_saves_smtp_and_redacts_password(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_module = importlib.import_module("backend.app")

    for name in (
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
    ):
        monkeypatch.delenv(name, raising=False)

    store = AuthStore(tmp_path / "api-auth.db")
    store.create_user("Mail User", "mail@example.com", "StrongPass1")
    monkeypatch.setattr(app_module, "auth_store", store)
    monkeypatch.setattr(app_module, "rate_limiter", SlidingWindowRateLimiter())
    monkeypatch.setattr(app_module, "APP_ENV", "development")
    monkeypatch.setattr(app_module, "RUNTIME_EMAIL_ENV_FILE", tmp_path / "email.env")
    monkeypatch.setattr(app_module, "EMAIL_CONFIG", load_email_config(tmp_path, "http://127.0.0.1:4000"))
    monkeypatch.setattr(
        app_module,
        "send_test_email",
        lambda _config, recipient: {"sent": True, "status": "sent", "provider": "smtp", "recipient": recipient},
    )
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    login = client.post(
        "/auth/login",
        json={
            "email": "mail@example.com",
            "password": "StrongPass1",
            "remember": False,
        },
    )
    assert login.status_code == 200
    csrf_cookie = client.get_cookie(app_module.CSRF_COOKIE)
    assert csrf_cookie is not None

    response = client.post(
        "/runtime/email/configure",
        json={
            "backend": "smtp",
            "host": "smtp.example.com",
            "port": 587,
            "username": "mail@example.com",
            "password": "smtp-secret",
            "sender": "mail@example.com",
            "use_tls": True,
            "use_ssl": False,
            "timeout_seconds": 20,
            "frontend_origin": "http://127.0.0.1:4000",
            "verify": True,
            "test_recipient": "mail@example.com",
        },
        headers={"X-CSRF-Token": csrf_cookie.value},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["email"]["backend"] == "smtp"
    assert body["email"]["smtp_configured"] is True
    assert body["email"]["password_present"] is True
    assert body["delivery"]["status"] == "sent"
    assert "smtp-secret" not in json.dumps(body)
    assert "SMTP_PASSWORD=smtp-secret" in (tmp_path / "email.env").read_text(encoding="utf-8")


def test_development_cors_allows_both_local_frontend_names() -> None:
    app_module = importlib.import_module("backend.app")
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    for origin in ("http://127.0.0.1:4000", "http://localhost:4000"):
        response = client.options(
            "/auth/signup",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.headers["Access-Control-Allow-Origin"] == origin
        assert response.headers["Access-Control-Allow-Credentials"] == "true"


def test_schema_requests_are_user_scoped_and_store_upload_metadata(tmp_path: Path) -> None:
    from backend.synthetic_enterprise_data import SchemaRequestRepository

    repository = SchemaRequestRepository(tmp_path / "requests.db")
    first = repository.create({
        "table_name": "vendor_scores",
        "business_purpose": "Track vendor quality",
        "requested_by_user_id": 1,
        "request_kind": "csv_upload",
        "attachment_name": "vendors.csv",
        "attachment_content": "vendor_id,score\n1,95",
    })
    repository.create({
        "table_name": "customer_health",
        "business_purpose": "Track customer risk",
        "requested_by_user_id": 2,
    })

    user_rows = repository.list(user_id=1)

    assert len(user_rows) == 1
    assert user_rows[0]["request_id"] == first["request_id"]
    assert user_rows[0]["request_kind"] == "csv_upload"
    assert user_rows[0]["attachment_name"] == "vendors.csv"
    assert user_rows[0]["has_attachment"] is True


def test_schema_request_upload_infers_sql_ddl(tmp_path: Path, monkeypatch) -> None:
    from backend.synthetic_enterprise_data import SchemaRequestRepository

    app_module = importlib.import_module("backend.app")
    monkeypatch.setattr(app_module, "auth_store", AuthStore(tmp_path / "api-auth.db"))
    monkeypatch.setattr(app_module, "schema_request_repo", SchemaRequestRepository(tmp_path / "requests.db"))
    monkeypatch.setattr(app_module, "rate_limiter", SlidingWindowRateLimiter())
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    signup = client.post(
        "/auth/signup",
        json={
            "name": "DDL User",
            "email": "ddl@example.com",
            "password": "StrongPass1",
        },
    )
    assert signup.status_code == 201
    csrf_cookie = client.get_cookie(app_module.CSRF_COOKIE)
    assert csrf_cookie is not None

    ddl = b"""
    CREATE TABLE vendor_risks (
        vendor_id INTEGER PRIMARY KEY,
        vendor_name TEXT NOT NULL,
        risk_score DECIMAL(10,2),
        supplier_id INTEGER REFERENCES suppliers(supplier_id)
    );
    """
    response = client.post(
        "/schema-request",
        data={
            "business_purpose": "Track vendor risk scoring.",
            "file": (io.BytesIO(ddl), "vendor_risks.sql"),
        },
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf_cookie.value},
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["request_kind"] == "sql_upload"
    proposal = body["generated_schema"]
    assert proposal["tables"][0]["name"] == "vendor_risks"
    columns = {column["name"] for column in proposal["tables"][0]["columns"]}
    assert {"vendor_id", "vendor_name", "risk_score", "supplier_id"}.issubset(columns)


def test_admin_live_schema_upsert_refreshes_catalog_without_restart(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("backend.app")
    store = AuthStore(tmp_path / "api-auth.db")
    store.create_user("Admin User", "admin@example.com", "StrongPass1")
    store.set_user_role("admin@example.com", "admin")
    monkeypatch.setattr(app_module, "auth_store", store)
    monkeypatch.setattr(app_module, "DYNAMIC_SCHEMA_FILE", tmp_path / "dynamic_schema.json")
    monkeypatch.setattr(app_module, "rate_limiter", SlidingWindowRateLimiter())
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    login = client.post(
        "/auth/login",
        json={
            "email": "admin@example.com",
            "password": "StrongPass1",
            "remember": False,
        },
    )
    assert login.status_code == 200
    csrf_cookie = client.get_cookie(app_module.CSRF_COOKIE)
    assert csrf_cookie is not None

    payload = {
        "name": "vendor_observability",
        "purpose": "Track vendor telemetry and SLA health.",
        "columns": [
            {"name": "vendor_observability_id", "data_type": "INTEGER", "is_pk": True},
            {"name": "vendor_name", "data_type": "TEXT"},
            {"name": "sla_score", "data_type": "DECIMAL(18,2)"},
        ],
    }
    created = client.post(
        "/schema/studio/tables",
        json=payload,
        headers={"X-CSRF-Token": csrf_cookie.value},
    )
    assert created.status_code == 201

    catalog = client.get("/schema/catalog").get_json()
    names = {table["name"] for table in catalog["tables"]}
    assert "vendor_observability" in names

    deleted = client.delete(
        "/schema/studio/tables/vendor_observability",
        headers={"X-CSRF-Token": csrf_cookie.value},
    )
    assert deleted.status_code == 200
    assert "vendor_observability" not in app_module.schema_tables
