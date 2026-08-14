from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BalanceRequest:
    business_partner_id: str | None = None
    portfolio_id: str | None = None
    balance_date: str | None = None
    balance_type: int = 1
    balance_level: int = 1


def _column(name: str, data_type: str, description: str) -> dict[str, object]:
    return {
        "name": name,
        "data_type": data_type,
        "description": description,
    }


CUSTODY_BALANCE_SCHEMA_TABLES: list[dict[str, object]] = [
    {
        "name": "portfolio",
        "domain": "Custody Portfolio Balance",
        "purpose": "Portfolio master data used to validate a customer portfolio before balance lookup.",
        "owner": "custody-platform",
        "tags": ["custody", "portfolio", "balance", "tcs"],
        "version": "2026.08",
        "source": "builtin_business_logic",
        "aliases": ["portfolio", "prtfl", "customer portfolio", "portfolio reference"],
        "business_glossary": {
            "portfolio_id": "Unique identifier of a portfolio account.",
            "business_partner_id": "Customer or business partner that owns the portfolio.",
        },
        "columns": [
            _column("portfolio_id", "VARCHAR(40)", "Unique portfolio identifier, also called PRTFL_ID."),
            _column("business_partner_id", "VARCHAR(40)", "Customer or business partner identifier for the portfolio."),
            _column("portfolio_reference", "VARCHAR(40)", "External portfolio reference number."),
            _column("portfolio_number", "VARCHAR(40)", "Portfolio account number used by movement records."),
            _column("portfolio_name", "VARCHAR(200)", "Business display name for the portfolio."),
            _column("portfolio_status", "VARCHAR(30)", "Lifecycle status of the portfolio."),
            _column("created_datetime", "TIMESTAMP", "Portfolio creation timestamp."),
            _column("updated_datetime", "TIMESTAMP", "Latest portfolio update timestamp."),
        ],
        "indexes": ["portfolio_id", "business_partner_id", "portfolio_reference", "portfolio_number"],
    },
    {
        "name": "custody_position",
        "domain": "Custody Portfolio Balance",
        "purpose": "Position-level custody records for each client, portfolio, instrument, custodian, and market combination.",
        "owner": "custody-platform",
        "tags": ["custody", "position", "balance", "cp", "tcs"],
        "version": "2026.08",
        "source": "builtin_business_logic",
        "aliases": ["cp", "custody position", "position records", "portfolio position"],
        "business_glossary": {
            "position_number": "Unique custody position number for a client, market, and instrument.",
            "position_type": "Position type such as book-entry or normal security position.",
            "currency": "Currency in which the position and movement are maintained.",
        },
        "columns": [
            _column("position_number", "VARCHAR(40)", "Unique custody position number, also called POS_NUM."),
            _column("position_type", "NUMBER(4,0)", "Custody position type, also called POS_TYPE."),
            _column("business_partner_id", "VARCHAR(40)", "Customer or business partner identifier, also called BP_ID."),
            _column("portfolio_id", "VARCHAR(40)", "Portfolio identifier for the customer portfolio, also called PRTFL_ID."),
            _column("instrument_id", "VARCHAR(40)", "Unique instrument or security identifier."),
            _column("security_position_type", "NUMBER(3,0)", "Security position type for book entry, normal, or related position categories."),
            _column("custodian_id", "VARCHAR(40)", "Custodian business partner reference."),
            _column("custodian_account_number", "VARCHAR(80)", "Custodian account number assigned to the position."),
            _column("currency", "VARCHAR(12)", "Currency for the custody position."),
            _column("stock_exchange", "VARCHAR(20)", "Stock exchange or trading market identifier."),
            _column("market", "NUMBER(4,0)", "Market domain identifier."),
            _column("place_of_settlement", "VARCHAR(40)", "Place of settlement for the custody position."),
            _column("pset", "VARCHAR(40)", "Participant settlement or place of settlement reference."),
            _column("contract_id", "VARCHAR(40)", "Contract identifier for the position."),
            _column("long_short_flag", "NUMBER(1,0)", "Long or short flag for the position."),
            _column("last_carry_forward_date", "DATE", "Last carry-forward date for the position balance."),
            _column("created_datetime", "TIMESTAMP", "Position creation timestamp."),
            _column("updated_datetime", "TIMESTAMP", "Latest position update timestamp."),
        ],
        "indexes": [
            "business_partner_id",
            "portfolio_id",
            "position_number",
            "position_type",
            "instrument_id",
            "stock_exchange",
            "custodian_id",
            "custodian_account_number",
        ],
    },
    {
        "name": "security_movement",
        "domain": "Custody Portfolio Balance",
        "purpose": "Security movement records used to calculate settled balance by adding buys and subtracting sells.",
        "owner": "custody-platform",
        "tags": ["custody", "movement", "settled balance", "sm", "tcs"],
        "version": "2026.08",
        "source": "builtin_business_logic",
        "aliases": ["sm", "security movement", "settled movement", "movement records"],
        "business_glossary": {
            "credit_and_debit_flag": "1 means buy/credit quantity, 2 means sell/debit quantity.",
            "amount_quantity": "Quantity or amount used in settled balance calculation.",
        },
        "columns": [
            _column("security_movement_id", "NUMBER(18,0)", "Unique identifier of a security movement."),
            _column("security_movement_position_id", "NUMBER(18,0)", "Position identifier attached to the security movement."),
            _column("security_movement_position_type", "NUMBER(4,0)", "Position type attached to the security movement."),
            _column("customer_reference", "VARCHAR(40)", "Customer reference, mapped from custody_position.business_partner_id."),
            _column("portfolio_number", "VARCHAR(40)", "Portfolio number, mapped from custody_position.portfolio_id."),
            _column("instrument_id", "VARCHAR(40)", "Instrument involved in the movement."),
            _column("custody_position_number", "VARCHAR(40)", "Custody position number related to the movement."),
            _column("custody_position_type", "NUMBER(4,0)", "Custody position type related to the movement."),
            _column("custodian_id", "VARCHAR(40)", "Custodian reference for the movement."),
            _column("custodian_account_number", "VARCHAR(80)", "Custodian account number for the movement."),
            _column("stock_exchange_id", "VARCHAR(20)", "Stock exchange identifier for the movement."),
            _column("cost_price_currency", "VARCHAR(12)", "Currency associated with cost price and movement balance."),
            _column("position_type", "NUMBER(4,0)", "Position type in the movement chain."),
            _column("market", "NUMBER(4,0)", "Market domain identifier."),
            _column("place_of_settlement", "VARCHAR(40)", "Place of settlement involved in the movement."),
            _column("credit_and_debit_flag", "NUMBER(1,0)", "Credit/debit flag. 1 is buy/credit; 2 is sell/debit."),
            _column("unit", "VARCHAR(20)", "Unit or nominal value for the movement quantity."),
            _column("amount_currency", "VARCHAR(12)", "Movement amount currency."),
            _column("amount_quantity", "NUMBER(24,6)", "Quantity used in settled balance calculation."),
            _column("cost_price", "NUMBER(24,8)", "Cost price for the initiated business transaction."),
            _column("trade_date", "DATE", "Trade date used when balance_type is 1."),
            _column("value_date", "DATE", "Value date used when balance_type is 2."),
            _column("transaction_date", "DATE", "Transaction date used when balance_type is 5."),
            _column("availability_date", "DATE", "Date from which the position should be available."),
            _column("accounting_date", "DATE", "Accounting date used in ledger booking."),
            _column("movement_generation_date", "DATE", "Security movement generation date."),
            _column("movement_generation_time", "TIMESTAMP", "Security movement generation time."),
            _column("security_movement_description", "VARCHAR(255)", "Description from initiating custody transaction."),
            _column("external_reference_number", "VARCHAR(85)", "External reference provided by custodian or settlement transaction."),
            _column("broker_flag", "NUMBER(1,0)", "Indicates whether the movement involves a broker."),
            _column("order_type", "NUMBER(2,0)", "Order type for the movement."),
            _column("booking_creation_date", "DATE", "System date on which booking was created."),
            _column("booking_creation_time", "TIMESTAMP", "System time on which booking was created."),
        ],
        "indexes": [
            "customer_reference",
            "portfolio_number",
            "instrument_id",
            "custody_position_number",
            "custody_position_type",
            "trade_date",
            "value_date",
            "transaction_date",
        ],
    },
    {
        "name": "custody_block",
        "domain": "Custody Portfolio Balance",
        "purpose": "Active custody block records used to subtract blocked quantity from settled quantity.",
        "owner": "custody-platform",
        "tags": ["custody", "block", "blocked balance", "cb", "tcs"],
        "version": "2026.08",
        "source": "builtin_business_logic",
        "aliases": ["cb", "custody block", "blocked balance", "security block"],
        "business_glossary": {
            "block_quantity_amount": "Blocked security quantity or blocked amount quantity.",
            "block_valid_from_date": "Date from which the block should be considered active.",
            "block_release_date": "Date on which the custody block was released.",
        },
        "columns": [
            _column("block_id", "NUMBER(18,0)", "Unique identifier of a custody block."),
            _column("business_partner_id", "VARCHAR(40)", "Customer or business partner for the block."),
            _column("portfolio_id", "VARCHAR(40)", "Portfolio identifier for the blocked position."),
            _column("portfolio_reference", "VARCHAR(40)", "Portfolio reference for the blocked position."),
            _column("position_number", "VARCHAR(40)", "Custody position number that is blocked."),
            _column("position_type", "NUMBER(4,0)", "Custody position type that is blocked."),
            _column("instrument_id", "VARCHAR(40)", "Instrument involved in the block."),
            _column("security_position_type", "NUMBER(3,0)", "Security position type involved in the block."),
            _column("custodian_id", "VARCHAR(40)", "Custodian reference for the block."),
            _column("custodian_account_number", "VARCHAR(80)", "Custodian account for the block."),
            _column("stock_exchange_id", "VARCHAR(20)", "Stock exchange identifier for the block."),
            _column("currency", "VARCHAR(12)", "Security issue or bond currency for the block."),
            _column("block_quantity_amount", "NUMBER(24,6)", "Security block quantity or amount."),
            _column("block_status", "VARCHAR(30)", "Business status of the block, such as active or released."),
            _column("block_status_code", "NUMBER(9,0)", "Domain code for block status."),
            _column("block_type", "VARCHAR(30)", "Business block type."),
            _column("block_type_code", "NUMBER(9,0)", "Domain code for block type."),
            _column("position_type_code", "NUMBER(9,0)", "Domain code for position type."),
            _column("block_valid_from_date", "DATE", "Date from which the custody block should be considered active."),
            _column("block_release_date", "DATE", "Date on which the custody block was released."),
            _column("block_creation_date", "DATE", "Block creation date."),
            _column("block_creation_time", "TIMESTAMP", "Block creation time."),
            _column("block_release_time", "TIMESTAMP", "Block release time."),
            _column("block_for_transaction_id", "NUMBER(18,0)", "Transaction id for which the custody block is created."),
            _column("block_for_transaction_type", "NUMBER(4,0)", "Transaction type for which the custody block is created."),
            _column("remarks", "VARCHAR(255)", "Remarks explaining the block."),
            _column("from_balance", "NUMBER(24,6)", "Balance before the block transaction."),
            _column("to_balance", "NUMBER(24,6)", "Balance after the block transaction."),
            _column("to_balance_final", "NUMBER(24,6)", "Final balance after the block transaction."),
            _column("created_datetime", "TIMESTAMP", "Block creation timestamp."),
            _column("updated_datetime", "TIMESTAMP", "Latest block update timestamp."),
        ],
        "indexes": [
            "business_partner_id",
            "portfolio_id",
            "position_number",
            "position_type",
            "instrument_id",
            "block_valid_from_date",
            "block_release_date",
            "block_status",
            "block_status_code",
        ],
    },
]


CUSTODY_BALANCE_RELATIONSHIPS: list[dict[str, str]] = [
    {"from_table": "custody_position", "from_column": "portfolio_id", "to_table": "portfolio", "to_column": "portfolio_id"},
    {"from_table": "custody_position", "from_column": "business_partner_id", "to_table": "portfolio", "to_column": "business_partner_id"},
    {"from_table": "security_movement", "from_column": "customer_reference", "to_table": "custody_position", "to_column": "business_partner_id"},
    {"from_table": "security_movement", "from_column": "portfolio_number", "to_table": "custody_position", "to_column": "portfolio_id"},
    {"from_table": "security_movement", "from_column": "instrument_id", "to_table": "custody_position", "to_column": "instrument_id"},
    {"from_table": "security_movement", "from_column": "custody_position_number", "to_table": "custody_position", "to_column": "position_number"},
    {"from_table": "security_movement", "from_column": "custody_position_type", "to_table": "custody_position", "to_column": "position_type"},
    {"from_table": "security_movement", "from_column": "custodian_id", "to_table": "custody_position", "to_column": "custodian_id"},
    {"from_table": "security_movement", "from_column": "custodian_account_number", "to_table": "custody_position", "to_column": "custodian_account_number"},
    {"from_table": "security_movement", "from_column": "stock_exchange_id", "to_table": "custody_position", "to_column": "stock_exchange"},
    {"from_table": "security_movement", "from_column": "cost_price_currency", "to_table": "custody_position", "to_column": "currency"},
    {"from_table": "custody_block", "from_column": "business_partner_id", "to_table": "custody_position", "to_column": "business_partner_id"},
    {"from_table": "custody_block", "from_column": "portfolio_id", "to_table": "custody_position", "to_column": "portfolio_id"},
    {"from_table": "custody_block", "from_column": "position_number", "to_table": "custody_position", "to_column": "position_number"},
    {"from_table": "custody_block", "from_column": "position_type", "to_table": "custody_position", "to_column": "position_type"},
    {"from_table": "custody_block", "from_column": "instrument_id", "to_table": "custody_position", "to_column": "instrument_id"},
    {"from_table": "custody_block", "from_column": "custodian_id", "to_table": "custody_position", "to_column": "custodian_id"},
    {"from_table": "custody_block", "from_column": "custodian_account_number", "to_table": "custody_position", "to_column": "custodian_account_number"},
    {"from_table": "custody_block", "from_column": "stock_exchange_id", "to_table": "custody_position", "to_column": "stock_exchange"},
    {"from_table": "custody_block", "from_column": "currency", "to_table": "custody_position", "to_column": "currency"},
]


CUSTODY_BALANCE_TABLE_HINTS: dict[str, set[str]] = {
    "portfolio": {"portfolio", "prtfl", "portfolio reference", "portfolio id", "portfolio account"},
    "custody_position": {
        "cp",
        "custody position",
        "position",
        "position records",
        "pos num",
        "pos type",
        "portfolio balance",
    },
    "security_movement": {
        "sm",
        "security movement",
        "movement",
        "settled balance",
        "amount quantity",
        "credit debit",
        "buy",
        "sell",
    },
    "custody_block": {
        "cb",
        "custody block",
        "blocked balance",
        "blocked quantity",
        "active block",
        "release date",
    },
}


CUSTODY_BALANCE_COLUMN_HINTS: dict[str, dict[str, set[str]]] = {
    "portfolio": {
        "portfolio_id": {"portfolio id", "prtfl id", "portfolio reference"},
        "business_partner_id": {"business partner id", "bp id", "customer id", "client id"},
        "portfolio_number": {"portfolio number", "prtfl num"},
    },
    "custody_position": {
        "position_number": {"position number", "pos num", "custody position number"},
        "position_type": {"position type", "pos type"},
        "business_partner_id": {"business partner id", "bp id", "customer id", "client id"},
        "portfolio_id": {"portfolio id", "prtfl id", "portfolio reference"},
        "instrument_id": {"instrument id", "security id"},
        "currency": {"currency", "crncy"},
        "stock_exchange": {"stock exchange", "exchange"},
    },
    "security_movement": {
        "customer_reference": {"customer reference", "business partner id", "bp id"},
        "portfolio_number": {"portfolio number", "portfolio id", "prtfl id"},
        "credit_and_debit_flag": {"credit debit flag", "cr dr flag", "buy sell flag"},
        "amount_quantity": {"amount quantity", "amt qty", "settled quantity", "settled balance"},
        "trade_date": {"trade date", "balance type 1"},
        "value_date": {"value date", "balance type 2"},
        "transaction_date": {"transaction date", "txn date", "balance type 5"},
    },
    "custody_block": {
        "block_quantity_amount": {"blocked quantity", "blocked amount", "block amount quantity"},
        "block_valid_from_date": {"valid from date", "block date", "active from date"},
        "block_release_date": {"release date", "released date"},
        "block_status": {"block status", "active block"},
        "block_status_code": {"block status code", "active block status"},
    },
}


CUSTODY_BALANCE_DEFAULT_DISPLAY_COLUMNS: dict[str, list[str]] = {
    "portfolio": ["portfolio_id", "business_partner_id", "portfolio_reference", "portfolio_status"],
    "custody_position": [
        "business_partner_id",
        "portfolio_id",
        "position_number",
        "position_type",
        "instrument_id",
        "currency",
    ],
    "security_movement": [
        "customer_reference",
        "portfolio_number",
        "custody_position_number",
        "instrument_id",
        "amount_quantity",
        "trade_date",
    ],
    "custody_block": [
        "business_partner_id",
        "portfolio_id",
        "position_number",
        "instrument_id",
        "block_quantity_amount",
        "block_status",
    ],
}


CUSTODY_BALANCE_LABEL_COLUMNS: dict[str, str] = {
    "portfolio": "portfolio_id",
    "custody_position": "position_number",
    "security_movement": "security_movement_id",
    "custody_block": "block_id",
}


CUSTODY_BALANCE_ALIASES: dict[str, str] = {
    "portfolio": "pf",
    "custody_position": "cp",
    "security_movement": "sm",
    "custody_block": "cb",
}


def _normalise_text(query: str) -> str:
    return re.sub(r"\s+", " ", query.lower().replace("_", " ").replace("-", " ")).strip()


def is_available_balance_query(query: str) -> bool:
    q = _normalise_text(query)
    if not q:
        return False
    if "available balance" in q or "available quantity" in q:
        return True
    balance_context = {"portfolio", "business partner", "bp id", "custody", "client", "customer"}
    return "balance" in q and any(term in q for term in balance_context)


def _extract_value(query: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            value = str(match.group(1)).strip().strip("'\"")
            if value:
                return value
    return None


def _extract_int(query: str, patterns: tuple[str, ...], default: int) -> int:
    value = _extract_value(query, patterns)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _normalise_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{4})[-_/](\d{1,2})[-_/](\d{1,2})", value)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def parse_balance_request(query: str) -> BalanceRequest | None:
    if not is_available_balance_query(query):
        return None

    business_partner_id = _extract_value(query, (
        r"\bbusiness\s+partner(?:\s+id)?\s*(?:is|=|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
        r"\bbp(?:\s+|_)?id\s*(?:is|=|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
        r"\bcustomer(?:\s+reference|\s+id)?\s*(?:is|=|:)\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
        r"\bclient(?:\s+id)?\s*(?:is|=|:)\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
    ))
    portfolio_id = _extract_value(query, (
        r"\bportfolio(?:\s+id|\s+reference|\s+number)?\s*(?:is|=|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
        r"\bprtfl(?:\s+num|\s+id)?\s*(?:is|=|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
    ))
    date_value = _extract_value(query, (
        r"\bbalance\s+date\s*(?:is|=|:)?\s*(\d{4}[-_/]\d{1,2}[-_/]\d{1,2})",
        r"\bas\s+of\s*(\d{4}[-_/]\d{1,2}[-_/]\d{1,2})",
        r"\bon\s*(\d{4}[-_/]\d{1,2}[-_/]\d{1,2})",
        r"\b(\d{4}[-_/]\d{1,2}[-_/]\d{1,2})\b",
    ))
    return BalanceRequest(
        business_partner_id=business_partner_id,
        portfolio_id=portfolio_id,
        balance_date=_normalise_date(date_value),
        balance_type=_extract_int(query, (r"\bbalance\s+type\s*(?:is|=|:)?\s*(\d+)",), 1),
        balance_level=_extract_int(query, (r"\bbalance\s+level\s*(?:is|=|:)?\s*(\d+)",), 1),
    )


def _sql_literal(value: str | None, placeholder: str) -> str:
    if value is None:
        return f":{placeholder}"
    cleaned = value.replace("'", "''")
    return f"'{cleaned}'"


def _date_literal(value: str | None) -> str:
    if value is None:
        return ":balance_date"
    return f"DATE '{value}'"


def _movement_date_condition(request: BalanceRequest) -> str:
    balance_date = _date_literal(request.balance_date)
    if request.balance_type == 2:
        return f"sm.value_date <= {balance_date}"
    if request.balance_type == 5:
        return f"sm.transaction_date <= {balance_date}"
    return f"sm.trade_date <= {balance_date}"


def _settled_subquery(request: BalanceRequest, indent: str = "    ") -> list[str]:
    return [
        f"{indent}SELECT SUM(CASE",
        f"{indent}  WHEN sm.credit_and_debit_flag = 1 THEN sm.amount_quantity",
        f"{indent}  WHEN sm.credit_and_debit_flag = 2 THEN -sm.amount_quantity",
        f"{indent}  ELSE 0",
        f"{indent}END)",
        f"{indent}FROM security_movement sm",
        f"{indent}WHERE sm.customer_reference = cp.business_partner_id",
        f"{indent}  AND sm.portfolio_number = cp.portfolio_id",
        f"{indent}  AND sm.instrument_id = cp.instrument_id",
        f"{indent}  AND sm.custody_position_number = cp.position_number",
        f"{indent}  AND sm.custody_position_type = cp.position_type",
        f"{indent}  AND (sm.custodian_id = cp.custodian_id OR sm.custodian_id IS NULL)",
        f"{indent}  AND (sm.custodian_account_number = cp.custodian_account_number OR sm.custodian_account_number IS NULL)",
        f"{indent}  AND (sm.stock_exchange_id = cp.stock_exchange OR sm.stock_exchange_id IS NULL)",
        f"{indent}  AND (sm.cost_price_currency = cp.currency OR sm.cost_price_currency IS NULL)",
        f"{indent}  AND {_movement_date_condition(request)}",
    ]


def _blocked_subquery(request: BalanceRequest, indent: str = "    ") -> list[str]:
    balance_date = _date_literal(request.balance_date)
    return [
        f"{indent}SELECT SUM(cb.block_quantity_amount)",
        f"{indent}FROM custody_block cb",
        f"{indent}WHERE cb.business_partner_id = cp.business_partner_id",
        f"{indent}  AND cb.portfolio_id = cp.portfolio_id",
        f"{indent}  AND cb.instrument_id = cp.instrument_id",
        f"{indent}  AND cb.position_number = cp.position_number",
        f"{indent}  AND cb.position_type = cp.position_type",
        f"{indent}  AND (cb.custodian_id = cp.custodian_id OR cb.custodian_id IS NULL)",
        f"{indent}  AND (cb.custodian_account_number = cp.custodian_account_number OR cb.custodian_account_number IS NULL)",
        f"{indent}  AND (cb.stock_exchange_id = cp.stock_exchange OR cb.stock_exchange_id IS NULL)",
        f"{indent}  AND (cb.currency = cp.currency OR cb.currency IS NULL)",
        f"{indent}  AND cb.block_valid_from_date <= {balance_date}",
        f"{indent}  AND (cb.block_release_date IS NULL OR cb.block_release_date > {balance_date})",
        f"{indent}  AND (",
        f"{indent}    UPPER(cb.block_status) = 'ACTIVE'",
        f"{indent}    OR cb.block_status_code = 1",
        f"{indent}  )",
    ]


def build_available_balance_sql(request: BalanceRequest) -> str:
    bp_value = _sql_literal(request.business_partner_id, "business_partner_id")
    portfolio_value = _sql_literal(request.portfolio_id, "portfolio_id")
    settled = "\n".join(_settled_subquery(request, "    "))
    blocked = "\n".join(_blocked_subquery(request, "    "))
    settled_for_formula = "\n".join(_settled_subquery(request, "      "))
    blocked_for_formula = "\n".join(_blocked_subquery(request, "      "))

    return (
        "SELECT\n"
        "  cp.business_partner_id,\n"
        "  cp.portfolio_id,\n"
        "  cp.position_number,\n"
        "  cp.position_type,\n"
        "  cp.instrument_id,\n"
        "  cp.security_position_type,\n"
        "  cp.custodian_id,\n"
        "  cp.custodian_account_number,\n"
        "  cp.currency,\n"
        "  cp.stock_exchange,\n"
        "  COALESCE((\n"
        f"{settled}\n"
        "  ), 0) AS settled_balance,\n"
        "  COALESCE((\n"
        f"{blocked}\n"
        "  ), 0) AS blocked_balance,\n"
        "  COALESCE((\n"
        f"{settled_for_formula}\n"
        "  ), 0) - COALESCE((\n"
        f"{blocked_for_formula}\n"
        "  ), 0) AS available_balance\n"
        "FROM custody_position cp\n"
        "JOIN portfolio p\n"
        "  ON p.portfolio_id = cp.portfolio_id\n"
        " AND p.business_partner_id = cp.business_partner_id\n"
        f"WHERE cp.business_partner_id = {bp_value}\n"
        f"  AND cp.portfolio_id = {portfolio_value}\n"
        "ORDER BY cp.position_number, cp.instrument_id;"
    )


def balance_request_summary(request: BalanceRequest) -> dict[str, object]:
    date_basis = {
        1: "trade_date",
        2: "value_date",
        5: "transaction_date",
    }.get(request.balance_type, "trade_date")
    return {
        "business_partner_id": request.business_partner_id,
        "portfolio_id": request.portfolio_id,
        "balance_date": request.balance_date,
        "balance_type": request.balance_type,
        "balance_level": request.balance_level,
        "date_basis": date_basis,
        "mode": "position_level" if request.balance_level == 1 else "portfolio_level",
    }
