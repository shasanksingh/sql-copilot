from __future__ import annotations

import importlib
import io
import json
from pathlib import Path

from agentic.custody_balance_domain import CUSTODY_BALANCE_RELATIONSHIPS, CUSTODY_BALANCE_SCHEMA_TABLES
from backend.auth import AuthStore, SlidingWindowRateLimiter
from backend.private_schema import ConfidentialSchemaCatalog


def _payload() -> dict[str, object]:
    return {
        "version": 1,
        "tables": [
            {
                "name": "custody_position",
                "domain": "Private custody",
                "purpose": "Position records for a customer portfolio and instrument.",
                "aliases": ["custody position", "portfolio position"],
                "columns": [
                    {"name": "position_number", "data_type": "NUMBER(9,0)", "is_pk": True},
                    {"name": "business_partner_id", "data_type": "VARCHAR2(20 CHAR)"},
                    {"name": "portfolio_id", "data_type": "VARCHAR2(20 CHAR)"},
                    {"name": "instrument_id", "data_type": "NUMBER(9,0)"},
                ],
            },
            {
                "name": "security_movement",
                "domain": "Private custody",
                "purpose": "Security movement quantities for customer positions.",
                "columns": [
                    {"name": "security_movement_id", "data_type": "NUMBER(9,0)", "is_pk": True},
                    {"name": "customer_reference", "data_type": "VARCHAR2(20 CHAR)"},
                    {"name": "amount_quantity", "data_type": "NUMBER(21,7)"},
                ],
            },
        ],
        "relationships": [
            {
                "from_table": "security_movement",
                "from_column": "customer_reference",
                "to_table": "custody_position",
                "to_column": "business_partner_id",
            }
        ],
    }


def _custody_payload() -> dict[str, object]:
    return {
        "version": 1,
        "tables": CUSTODY_BALANCE_SCHEMA_TABLES,
        "relationships": CUSTODY_BALANCE_RELATIONSHIPS,
    }


def _login(client, email: str, password: str = "StrongPass1") -> str:
    response = client.post("/auth/login", json={"email": email, "password": password, "remember": False})
    assert response.status_code == 200
    csrf = client.get_cookie("sql_copilot_csrf")
    assert csrf is not None
    return csrf.value


def test_private_catalog_builds_local_embedding_index(tmp_path: Path) -> None:
    catalog = ConfidentialSchemaCatalog(tmp_path / "private" / "catalog.json")
    result = catalog.import_payload(_payload())

    assert result["classification"] == "confidential-admin-only"
    assert result["embedding"]["ready"] is True
    assert result["embedding"]["remote_transfer"] is False
    assert result["embedding"]["dimensions"] == 384
    assert catalog.index_path.exists()
    matches = catalog.search("movement quantity by customer")
    assert matches
    assert {item["table"] for item in matches} & {"security_movement", "custody_position"}


def test_private_schema_api_is_admin_only_and_catalog_is_role_scoped(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("backend.app")
    store = AuthStore(tmp_path / "auth.db")
    store.create_user("Regular User", "user@example.com", "StrongPass1")
    store.create_user("Admin User", "admin@example.com", "StrongPass1", role="admin")
    catalog = ConfidentialSchemaCatalog(tmp_path / "private" / "catalog.json")
    catalog.import_payload(_payload())
    monkeypatch.setattr(app_module, "auth_store", store)
    monkeypatch.setattr(app_module, "private_schema_catalog", catalog)
    monkeypatch.setattr(app_module, "PRIVATE_FEEDBACK_DB_PATH", str(tmp_path / "private-feedback.db"))
    monkeypatch.setattr(app_module, "rate_limiter", SlidingWindowRateLimiter())
    monkeypatch.setattr(app_module, "admin_enterprise_copilot", None)
    app_module.app.config.update(TESTING=True)

    user_client = app_module.app.test_client()
    _login(user_client, "user@example.com")
    assert user_client.get("/admin/private-schema").status_code == 403
    public_catalog = user_client.get("/schema/catalog")
    assert public_catalog.status_code == 200
    public_names = {table["name"] for table in public_catalog.get_json()["tables"]}
    assert "custody_position" not in public_names
    assert "security_movement" not in public_names

    admin_client = app_module.app.test_client()
    _login(admin_client, "admin@example.com")
    private_response = admin_client.get("/admin/private-schema")
    assert private_response.status_code == 200
    assert {table["name"] for table in private_response.get_json()["tables"]} == {
        "custody_position",
        "security_movement",
    }
    admin_catalog = admin_client.get("/schema/catalog")
    admin_names = {table["name"] for table in admin_catalog.get_json()["tables"]}
    assert {"custody_position", "security_movement"}.issubset(admin_names)


def test_admin_can_import_private_catalog_and_regular_user_cannot(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("backend.app")
    store = AuthStore(tmp_path / "auth.db")
    store.create_user("Regular User", "user@example.com", "StrongPass1")
    store.create_user("Admin User", "admin@example.com", "StrongPass1", role="admin")
    catalog = ConfidentialSchemaCatalog(tmp_path / "private" / "catalog.json")
    monkeypatch.setattr(app_module, "auth_store", store)
    monkeypatch.setattr(app_module, "private_schema_catalog", catalog)
    monkeypatch.setattr(app_module, "PRIVATE_FEEDBACK_DB_PATH", str(tmp_path / "private-feedback.db"))
    monkeypatch.setattr(app_module, "rate_limiter", SlidingWindowRateLimiter())
    monkeypatch.setattr(app_module, "admin_enterprise_copilot", None)
    app_module.app.config.update(TESTING=True)
    content = json.dumps(_payload()).encode("utf-8")

    user_client = app_module.app.test_client()
    user_csrf = _login(user_client, "user@example.com")
    forbidden = user_client.post(
        "/admin/private-schema/import",
        data={"file": (io.BytesIO(content), "catalog.json")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": user_csrf},
    )
    assert forbidden.status_code == 403

    admin_client = app_module.app.test_client()
    admin_csrf = _login(admin_client, "admin@example.com")
    imported = admin_client.post(
        "/admin/private-schema/import",
        data={"file": (io.BytesIO(content), "catalog.json")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert imported.status_code == 201
    assert imported.get_json()["embedding"]["documents"] == 9


def test_admin_private_full_detail_query_uses_select_star(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("backend.app")
    catalog = ConfidentialSchemaCatalog(tmp_path / "private" / "catalog.json")
    catalog.import_payload(_payload())
    monkeypatch.setattr(app_module, "private_schema_catalog", catalog)
    monkeypatch.setattr(app_module, "PRIVATE_FEEDBACK_DB_PATH", str(tmp_path / "private-feedback.db"))
    monkeypatch.setattr(app_module, "admin_enterprise_copilot", None)

    result = app_module.get_enterprise_copilot(admin=True).run(
        "Show all custody position details",
        allow_cache=False,
    )

    assert result.valid is True
    assert result.sql == "SELECT *\nFROM custody_position;"
    assert result.selected_tables == ["custody_position"]


def test_admin_private_monthly_movements_use_business_date_mapping(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("backend.app")
    catalog = ConfidentialSchemaCatalog(tmp_path / "private" / "catalog.json")
    catalog.import_payload(_custody_payload())
    monkeypatch.setattr(app_module, "private_schema_catalog", catalog)
    monkeypatch.setattr(app_module, "PRIVATE_FEEDBACK_DB_PATH", str(tmp_path / "private-feedback.db"))
    monkeypatch.setattr(app_module, "admin_enterprise_copilot", None)

    result = app_module.get_enterprise_copilot(admin=True).run(
        "Custody movements by portfolio this month",
        allow_cache=False,
    )

    assert result.valid is True
    assert result.confidence >= 90
    assert "FROM security_movement sm" in result.sql
    assert "DATE_TRUNC('month', CURRENT_DATE)" in result.sql
    assert "GROUP BY sm.portfolio_number" in result.sql


def test_admin_private_available_balance_uses_all_business_sources(tmp_path: Path, monkeypatch) -> None:
    app_module = importlib.import_module("backend.app")
    catalog = ConfidentialSchemaCatalog(tmp_path / "private" / "catalog.json")
    catalog.import_payload(_custody_payload())
    monkeypatch.setattr(app_module, "private_schema_catalog", catalog)
    monkeypatch.setattr(app_module, "PRIVATE_FEEDBACK_DB_PATH", str(tmp_path / "private-feedback.db"))
    monkeypatch.setattr(app_module, "admin_enterprise_copilot", None)

    result = app_module.get_enterprise_copilot(admin=True).run(
        "Show available balance for business partner BP100 portfolio PF100 on 2026-11-07",
        allow_cache=False,
    )

    assert result.valid is True
    assert result.confidence >= 90
    assert "FROM custody_position cp" in result.sql
    assert "FROM security_movement sm" in result.sql
    assert "FROM custody_block cb" in result.sql
    assert "sm.stock_exchange_id = cp.stock_exchange_id" in result.sql
    assert "AS available_balance" in result.sql


def test_user_access_management_preserves_final_admin(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")
    admin = store.create_user("Admin User", "admin@example.com", "StrongPass1", role="admin")
    user = store.create_user("Regular User", "user@example.com", "StrongPass1")

    promoted = store.update_user_access(user["id"], role="admin")
    assert promoted["role"] == "admin"
    disabled = store.update_user_access(admin["id"], is_active=False)
    assert disabled["is_active"] is False

    try:
        store.update_user_access(user["id"], role="user")
    except ValueError as exc:
        assert "final active administrator" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected final administrator protection")
