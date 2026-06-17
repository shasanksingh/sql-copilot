from __future__ import annotations

import sqlite3
import importlib
from pathlib import Path

import pytest

from backend.auth import AuthStore, SlidingWindowRateLimiter


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


def test_development_cors_allows_both_local_frontend_names() -> None:
    app_module = importlib.import_module("backend.app")
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    for origin in ("http://127.0.0.1:3000", "http://localhost:3000"):
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
