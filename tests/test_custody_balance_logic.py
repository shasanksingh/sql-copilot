from __future__ import annotations

import importlib
import os

from agentic.custody_balance_domain import build_available_balance_sql, parse_balance_request


os.environ.setdefault("SQL_COPILOT_DISABLE_RUNTIME_SECRETS", "1")

BALANCE_QUERY = (
    "Fetch available balance for a client/customer whose business partner id is 122 "
    "portfolio id is 7 balance date is 2026_07_08 balance type is 1 and balance level is 1."
)


def test_custody_balance_request_parser_normalizes_inputs() -> None:
    request = parse_balance_request(BALANCE_QUERY)

    assert request is not None
    assert request.business_partner_id == "122"
    assert request.portfolio_id == "7"
    assert request.balance_date == "2026-07-08"
    assert request.balance_type == 1
    assert request.balance_level == 1


def test_custody_balance_sql_uses_position_level_business_logic() -> None:
    request = parse_balance_request(BALANCE_QUERY)
    assert request is not None

    sql = build_available_balance_sql(request)

    assert "FROM custody_position cp" in sql
    assert "JOIN portfolio p" in sql
    assert "FROM security_movement sm" in sql
    assert "FROM custody_block cb" in sql
    assert "sm.credit_and_debit_flag = 1 THEN sm.amount_quantity" in sql
    assert "sm.credit_and_debit_flag = 2 THEN -sm.amount_quantity" in sql
    assert "sm.trade_date <= DATE '2026-07-08'" in sql
    assert "cb.block_valid_from_date <= DATE '2026-07-08'" in sql
    assert "cb.block_release_date IS NULL OR cb.block_release_date > DATE '2026-07-08'" in sql
    assert "AS available_balance" in sql


def test_enterprise_copilot_returns_valid_custody_balance_sql() -> None:
    app_module = importlib.import_module("backend.app")

    result = app_module.get_enterprise_copilot().run(BALANCE_QUERY, allow_cache=False)

    assert result.valid is True
    assert result.clarification_required is False
    assert result.confidence >= 90
    assert result.query_complexity == "ENTERPRISE"
    assert result.llm_trace["stages"][0]["stage"] == "business_logic_lookup"
    assert set(result.selected_tables) == {
        "portfolio",
        "custody_position",
        "security_movement",
        "custody_block",
    }
    assert app_module.validate_sql(result.sql) == (True, "Valid")


def test_route_optimization_preserves_custody_balance_business_rule() -> None:
    app_module = importlib.import_module("backend.app")

    result = app_module.generate_sql(BALANCE_QUERY, app_module.session)
    optimized = app_module.optimize_with_rl_feedback(
        BALANCE_QUERY,
        result["sql"],
        result["insights"],
    )

    assert optimized["sql"] == result["sql"]
    assert "FROM custody_position cp" in optimized["sql"]
    assert "FROM security_movement sm" in optimized["sql"]
    assert "FROM custody_block cb" in optimized["sql"]
    assert optimized["insights"]["business_logic_rule"] == "custody_available_balance"
    assert optimized["insights"]["confidence"] >= 90
    assert optimized["insights"]["rl"]["action"] == "skipped_business_logic_rule"


def test_customer_details_uses_custody_position_not_demo_clients() -> None:
    app_module = importlib.import_module("backend.app")

    result = app_module.get_enterprise_copilot().run("give details of all customers", allow_cache=False)

    assert result.valid is True
    assert result.sql == "SELECT *\nFROM custody_position;"
    assert "clients" not in result.sql.lower()
    assert result.coverage_report["business_logic"]["matched_rule"] == "custody_customer_details"


def test_exact_custody_block_identifier_query_uses_custody_schema() -> None:
    app_module = importlib.import_module("backend.app")

    result = app_module.get_enterprise_copilot().run("Count custody_block by block_status", allow_cache=False)

    assert result.valid is True
    assert result.clarification_required is False
    assert result.selected_tables == ["custody_block"]
    assert result.selected_columns == ["custody_block.block_status"]
    assert result.llm_trace["fallback_used"] is False
    assert result.llm_trace["skip_reason"] == "deterministic_plan_validated"
    evidence = {item["key"]: item for item in result.confidence_evidence}
    assert evidence["model_confidence"]["note"] == "Deterministic plan validated; LLM assist was not needed."
    assert "FROM custody_block" in result.sql
    assert "block_status" in result.sql


def test_explicit_clients_still_uses_demo_clients_table() -> None:
    app_module = importlib.import_module("backend.app")

    result = app_module.get_enterprise_copilot().run("give details of all clients", allow_cache=False)

    assert result.valid is True
    assert "FROM clients" in result.sql
    assert "custody_position" not in result.sql


def test_custody_customer_example_rules_match_reference_phrasing() -> None:
    app_module = importlib.import_module("backend.app")
    copilot = app_module.get_enterprise_copilot()

    by_instrument = copilot.run("find all customer who have buy stock of given instrument", allow_cache=False)
    portfolios = copilot.run("find all the portfolio of a given customer", allow_cache=False)
    bought_instruments = copilot.run(
        "find all the instrument on which a specific customer have buy a stock",
        allow_cache=False,
    )

    assert by_instrument.valid is True
    assert "FROM custody_position" in by_instrument.sql
    assert "WHERE instrument_id = :instrument_id" in by_instrument.sql
    assert by_instrument.coverage_report["business_logic"]["matched_rule"] == "custody_customers_by_instrument"

    assert portfolios.valid is True
    assert "SELECT DISTINCT" in portfolios.sql
    assert "portfolio_id" in portfolios.sql
    assert "FROM custody_position" in portfolios.sql
    assert "WHERE business_partner_id = :business_partner_id" in portfolios.sql

    assert bought_instruments.valid is True
    assert "FROM security_movement sm" in bought_instruments.sql
    assert "sm.customer_reference = :business_partner_id" in bought_instruments.sql
    assert "sm.credit_and_debit_flag = 1" in bought_instruments.sql
