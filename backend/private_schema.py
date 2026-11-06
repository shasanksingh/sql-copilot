from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_TOKEN = re.compile(r"[a-z][a-z0-9_]{1,63}")
_EMBEDDING_DIMENSIONS = 384


def _tokens(value: object) -> list[str]:
    text = str(value or "").lower().replace("-", " ").replace("_", " ")
    return _TOKEN.findall(text)


def _normalise_identifier(value: object, label: str) -> str:
    identifier = str(value or "").strip().lower()
    if not _IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"Invalid {label}: {value!r}")
    return identifier


def _normalise_list(value: object, *, limit: int = 80) -> list[str]:
    if isinstance(value, str):
        raw = value.split(",")
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result: list[str] = []
    for item in raw[:limit]:
        cleaned = " ".join(str(item or "").strip().split())[:160]
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _feature_embedding(text: str, dimensions: int = _EMBEDDING_DIMENSIONS) -> list[float]:
    """Create a stable local embedding without sending confidential text off-host."""
    vector = [0.0] * dimensions
    tokens = _tokens(text)
    features = tokens + [f"{left}:{right}" for left, right in zip(tokens, tokens[1:])]
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return [round(value / norm, 8) for value in vector] if norm else vector


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class ConfidentialSchemaCatalog:
    """Runtime-only schema catalog and retrieval index for administrator sessions."""

    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self.index_path = catalog_path.with_name(f"{catalog_path.stem}.embeddings.json")
        self.tables: dict[str, dict[str, Any]] = {}
        self.relationships: list[dict[str, str]] = []
        self.documents: list[dict[str, Any]] = []
        self.fingerprint = ""
        self.loaded_at: str | None = None
        self.load()

    @property
    def enabled(self) -> bool:
        return bool(self.tables)

    def load(self) -> None:
        self.tables = {}
        self.relationships = []
        self.documents = []
        self.fingerprint = ""
        self.loaded_at = None
        if not self.catalog_path.exists():
            return
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        normalised = self._normalise_payload(payload)
        self._apply(normalised)

    def import_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalised = self._normalise_payload(payload)
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(json.dumps(normalised, indent=2), encoding="utf-8")
        self._apply(normalised)
        return self.admin_payload()

    def reindex(self) -> dict[str, Any]:
        if self.tables:
            self._build_documents()
            self._persist_index()
        return self.embedding_status()

    def _normalise_payload(self, payload: object) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Private schema payload must be a JSON object.")
        raw_tables = payload.get("tables")
        if not isinstance(raw_tables, list) or not raw_tables:
            raise ValueError("Private schema payload must include at least one table.")
        if len(raw_tables) > 100:
            raise ValueError("Private schema payload cannot exceed 100 tables.")

        tables: list[dict[str, Any]] = []
        table_columns: dict[str, set[str]] = {}
        for raw_table in raw_tables:
            if not isinstance(raw_table, dict):
                raise ValueError("Each private schema table must be an object.")
            name = _normalise_identifier(raw_table.get("name") or raw_table.get("table_name"), "table name")
            raw_columns = raw_table.get("columns")
            if not isinstance(raw_columns, list) or not raw_columns:
                raise ValueError(f"Private table '{name}' must include columns.")
            if len(raw_columns) > 400:
                raise ValueError(f"Private table '{name}' cannot exceed 400 columns.")
            columns: list[dict[str, Any]] = []
            seen: set[str] = set()
            for raw_column in raw_columns:
                item = raw_column if isinstance(raw_column, dict) else {"name": raw_column}
                column = _normalise_identifier(item.get("name"), "column name")
                if column in seen:
                    continue
                seen.add(column)
                columns.append({
                    "name": column,
                    "data_type": " ".join(str(item.get("data_type") or "TEXT").split())[:80],
                    "description": " ".join(str(item.get("description") or "").split())[:1000],
                    "is_pk": bool(item.get("is_pk")),
                    "is_fk": bool(item.get("is_fk")),
                })
            table_columns[name] = seen
            tables.append({
                "name": name,
                "domain": " ".join(str(raw_table.get("domain") or "Confidential business schema").split())[:160],
                "purpose": " ".join(str(raw_table.get("purpose") or "Private administrator schema table.").split())[:1200],
                "owner": " ".join(str(raw_table.get("owner") or "private-data-owner").split())[:160],
                "aliases": _normalise_list(raw_table.get("aliases")),
                "tags": _normalise_list(raw_table.get("tags")),
                "business_glossary": {
                    str(key)[:128]: " ".join(str(value).split())[:600]
                    for key, value in dict(raw_table.get("business_glossary") or {}).items()
                },
                "columns": columns,
                "indexes": [
                    _normalise_identifier(item, "index column")
                    for item in _normalise_list(raw_table.get("indexes"))
                    if str(item).strip().lower() in seen
                ],
            })

        relationships: list[dict[str, str]] = []
        raw_relationships = payload.get("relationships") or []
        if not isinstance(raw_relationships, list):
            raise ValueError("Private schema relationships must be a list.")
        for raw in raw_relationships[:1000]:
            if not isinstance(raw, dict):
                continue
            relationship = {
                "from_table": _normalise_identifier(raw.get("from_table"), "relationship source table"),
                "from_column": _normalise_identifier(raw.get("from_column"), "relationship source column"),
                "to_table": _normalise_identifier(raw.get("to_table"), "relationship target table"),
                "to_column": _normalise_identifier(raw.get("to_column"), "relationship target column"),
            }
            if relationship["from_table"] not in table_columns or relationship["to_table"] not in table_columns:
                raise ValueError("Private relationships may reference only private tables.")
            if relationship["from_column"] not in table_columns[relationship["from_table"]]:
                raise ValueError(f"Unknown private relationship column: {relationship['from_table']}.{relationship['from_column']}")
            if relationship["to_column"] not in table_columns[relationship["to_table"]]:
                raise ValueError(f"Unknown private relationship column: {relationship['to_table']}.{relationship['to_column']}")
            relationships.append(relationship)

        return {
            "version": int(payload.get("version") or 1),
            "classification": "confidential-admin-only",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "tables": tables,
            "relationships": relationships,
        }

    def _apply(self, payload: dict[str, Any]) -> None:
        self.tables = {str(table["name"]): table for table in payload["tables"]}
        self.relationships = list(payload.get("relationships") or [])
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.loaded_at = datetime.now(timezone.utc).isoformat()
        self._build_documents()
        self._persist_index()

    def _build_documents(self) -> None:
        documents: list[dict[str, Any]] = []
        for table_name, table in self.tables.items():
            glossary = " ".join(f"{key} {value}" for key, value in table.get("business_glossary", {}).items())
            table_text = " ".join([
                table_name,
                table.get("domain", ""),
                table.get("purpose", ""),
                " ".join(table.get("aliases", [])),
                " ".join(table.get("tags", [])),
                glossary,
            ])
            documents.append({
                "kind": "table",
                "table": table_name,
                "column": None,
                "text": table_text,
                "embedding": _feature_embedding(table_text),
            })
            for column in table.get("columns", []):
                column_text = " ".join([
                    table_name,
                    column["name"],
                    column.get("data_type", ""),
                    column.get("description", ""),
                    str(table.get("business_glossary", {}).get(column["name"], "")),
                ])
                documents.append({
                    "kind": "column",
                    "table": table_name,
                    "column": column["name"],
                    "text": column_text,
                    "embedding": _feature_embedding(column_text),
                })
        self.documents = documents

    def _persist_index(self) -> None:
        if not self.documents:
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps({
            "version": 1,
            "classification": "confidential-admin-only",
            "algorithm": "local-feature-hash-cosine",
            "dimensions": _EMBEDDING_DIMENSIONS,
            "catalog_fingerprint": self.fingerprint,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "documents": [
                {
                    "kind": item["kind"],
                    "table": item["table"],
                    "column": item["column"],
                    "embedding": item["embedding"],
                }
                for item in self.documents
            ],
        }, separators=(",", ":")), encoding="utf-8")

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query_vector = _feature_embedding(query)
        matches = sorted(
            (
                {
                    "kind": item["kind"],
                    "table": item["table"],
                    "column": item["column"],
                    "score": round(max(0.0, _cosine(query_vector, item["embedding"])) * 100, 2),
                }
                for item in self.documents
            ),
            key=lambda item: item["score"],
            reverse=True,
        )
        return [item for item in matches[: max(1, min(int(limit), 25))] if item["score"] > 0]

    def embedding_status(self) -> dict[str, Any]:
        return {
            "ready": bool(self.documents),
            "algorithm": "local-feature-hash-cosine",
            "dimensions": _EMBEDDING_DIMENSIONS,
            "documents": len(self.documents),
            "catalog_fingerprint": self.fingerprint[:16] if self.fingerprint else "",
            "built_at": self.loaded_at,
            "remote_transfer": False,
        }

    def admin_payload(self) -> dict[str, Any]:
        return {
            "classification": "confidential-admin-only",
            "enabled": self.enabled,
            "tables": list(self.tables.values()),
            "relationships": list(self.relationships),
            "embedding": self.embedding_status(),
            "loaded_at": self.loaded_at,
        }

    def copilot_components(self) -> dict[str, Any]:
        columns: dict[str, set[str]] = {}
        column_order: dict[str, list[str]] = {}
        column_types: dict[str, dict[str, str]] = {}
        table_hints: dict[str, set[str]] = {}
        column_hints: dict[str, dict[str, set[str]]] = {}
        aliases: dict[str, str] = {}
        defaults: dict[str, list[str]] = {}
        labels: dict[str, str] = {}
        relationships: dict[str, list[tuple[str, str, str]]] = {name: [] for name in self.tables}
        for name, table in self.tables.items():
            table_columns = list(table.get("columns") or [])
            column_order[name] = [str(column["name"]) for column in table_columns]
            columns[name] = set(column_order[name])
            column_types[name] = {
                str(column["name"]): str(column.get("data_type") or "TEXT")
                for column in table_columns
            }
            table_hints[name] = set(_tokens(" ".join([
                name,
                str(table.get("domain") or ""),
                str(table.get("purpose") or ""),
                " ".join(table.get("aliases") or []),
                " ".join(table.get("tags") or []),
            ]))) | {name, name.replace("_", " ")}
            column_hints[name] = {
                str(column["name"]): set(_tokens(" ".join([
                    str(column["name"]),
                    str(column.get("description") or ""),
                    str(table.get("business_glossary", {}).get(column["name"], "")),
                ]))) | {str(column["name"]), str(column["name"]).replace("_", " ")}
                for column in table_columns
            }
            aliases[name] = str((table.get("aliases") or [name[:2]])[0]).replace(" ", "_")[:12]
            defaults[name] = column_order[name][: min(8, len(column_order[name]))]
            labels[name] = next(
                (column for column in column_order[name] if column.endswith("_name")),
                column_order[name][0],
            )
        for item in self.relationships:
            relationships.setdefault(item["from_table"], []).append((
                item["from_column"], item["to_table"], item["to_column"]
            ))
        return {
            "tables": set(self.tables),
            "columns": columns,
            "column_order": column_order,
            "column_types": column_types,
            "relationships": relationships,
            "table_hints": table_hints,
            "column_hints": column_hints,
            "aliases": aliases,
            "defaults": defaults,
            "labels": labels,
        }
