from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import bcrypt
import jwt


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,128}$")
LOG_TABLES = {
    "audit_logs",
    "frontend_logs",
    "auth_logs",
    "ui_errors",
    "session_logs",
    "feedback_logs",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "email": str(row["email"]),
        "role": str(row["role"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login": row["last_login"],
        "is_active": bool(row["is_active"]),
    }


class AuthStore:
    def __init__(self, db_path: Path, signing_secret: str | None = None) -> None:
        self.db_path = Path(db_path)
        self._signing_secret = (signing_secret or "").strip()
        if self._signing_secret and len(self._signing_secret.encode("utf-8")) < 32:
            raise ValueError("JWT signing secret must be at least 32 bytes.")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_id TEXT NOT NULL UNIQUE,
                    csrf_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    revoked_at TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS password_resets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event TEXT NOT NULL,
                    level TEXT NOT NULL,
                    details TEXT NOT NULL,
                    ip_address TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS frontend_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event TEXT NOT NULL,
                    level TEXT NOT NULL,
                    details TEXT NOT NULL,
                    ip_address TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event TEXT NOT NULL,
                    level TEXT NOT NULL,
                    details TEXT NOT NULL,
                    ip_address TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ui_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event TEXT NOT NULL,
                    level TEXT NOT NULL,
                    details TEXT NOT NULL,
                    ip_address TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event TEXT NOT NULL,
                    level TEXT NOT NULL,
                    details TEXT NOT NULL,
                    ip_address TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event TEXT NOT NULL,
                    level TEXT NOT NULL,
                    details TEXT NOT NULL,
                    ip_address TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_token_id ON sessions(token_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_password_resets_hash ON password_resets(token_hash);
                CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at);
                """
            )

    def signing_secret(self) -> str:
        if self._signing_secret:
            return self._signing_secret
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'jwt_secret'"
            ).fetchone()
            if row:
                return str(row["value"])
            secret = secrets.token_urlsafe(64)
            now = isoformat(utc_now())
            conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES ('jwt_secret', ?, ?)",
                (secret, now),
            )
            return secret

    def create_user(
        self,
        name: str,
        email: str,
        password: str,
        role: str = "user",
    ) -> dict[str, Any]:
        name = " ".join(name.strip().split())[:120]
        email = email.strip().lower()[:254]
        if len(name) < 2:
            raise ValueError("Name must contain at least 2 characters.")
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        if not PASSWORD_PATTERN.fullmatch(password):
            raise ValueError(
                "Password must be 8-128 characters and include uppercase, lowercase, and a number."
            )
        if role not in {"user", "admin"}:
            role = "user"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
        now = isoformat(utc_now())
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO users (
                        name, email, password_hash, role, created_at, updated_at, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (name, email, password_hash, role, now, now),
                )
                row = conn.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("An account with this email already exists.") from exc
        if row is None:
            raise RuntimeError("User creation failed.")
        return public_user(row)

    def bootstrap_admin(self, name: str, email: str, password: str) -> dict[str, Any] | None:
        if not email or not password:
            return None
        existing = self.get_user_by_email(email)
        if existing:
            return self.set_user_role(email, "admin")
        return self.create_user(name or "SQL Copilot Admin", email, password, role="admin")

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                (email.strip().lower(),),
            ).fetchone()
        return public_user(row) if row else None

    def set_user_role(self, email: str, role: str) -> dict[str, Any]:
        normalized_email = email.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized_email):
            raise ValueError("Enter a valid email address.")
        if role not in {"user", "admin"}:
            raise ValueError("Role must be user or admin.")
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE email = ? COLLATE NOCASE",
                (role, isoformat(utc_now()), normalized_email),
            )
            if cursor.rowcount == 0:
                raise ValueError("No account exists with this email.")
            row = conn.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                (normalized_email,),
            ).fetchone()
        if row is None:
            raise RuntimeError("User role update failed.")
        return public_user(row)

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                (email.strip().lower(),),
            ).fetchone()
            if (
                row is None
                or not bool(row["is_active"])
                or not bcrypt.checkpw(password.encode("utf-8"), str(row["password_hash"]).encode("ascii"))
            ):
                return None
            now = isoformat(utc_now())
            conn.execute(
                "UPDATE users SET last_login = ?, updated_at = ? WHERE id = ?",
                (now, now, row["id"]),
            )
            refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
        return public_user(refreshed) if refreshed else None

    def issue_session(
        self,
        user: dict[str, Any],
        remember: bool,
        ip_address: str,
        user_agent: str,
    ) -> dict[str, Any]:
        now = utc_now()
        expires = now + (timedelta(days=30) if remember else timedelta(hours=8))
        token_id = secrets.token_urlsafe(24)
        csrf_token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    user_id, token_id, csrf_token, created_at, expires_at,
                    last_seen_at, ip_address, user_agent
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    token_id,
                    csrf_token,
                    isoformat(now),
                    isoformat(expires),
                    isoformat(now),
                    ip_address[:128],
                    user_agent[:512],
                ),
            )
        payload = {
            "sub": str(user["id"]),
            "jti": token_id,
            "role": user["role"],
            "csrf": csrf_token,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "iss": "sql-copilot",
        }
        token = jwt.encode(payload, self.signing_secret(), algorithm="HS256")
        return {
            "token": token,
            "csrf_token": csrf_token,
            "token_id": token_id,
            "expires_at": expires,
        }

    def validate_session(self, token: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        try:
            payload = jwt.decode(
                token,
                self.signing_secret(),
                algorithms=["HS256"],
                issuer="sql-copilot",
            )
        except jwt.PyJWTError:
            return None
        token_id = str(payload.get("jti") or "")
        user_id = str(payload.get("sub") or "")
        if not token_id or not user_id:
            return None
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    s.token_id, s.csrf_token, s.expires_at, s.revoked_at,
                    u.id, u.name, u.email, u.role, u.created_at, u.updated_at,
                    u.last_login, u.is_active
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_id = ? AND u.id = ?
                """,
                (token_id, int(user_id)),
            ).fetchone()
            if (
                row is None
                or row["revoked_at"] is not None
                or not bool(row["is_active"])
                or datetime.fromisoformat(str(row["expires_at"])) <= now
            ):
                return None
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE token_id = ?",
                (isoformat(now), token_id),
            )
        return public_user(row), {
            "token_id": token_id,
            "csrf_token": str(row["csrf_token"]),
            "expires_at": str(row["expires_at"]),
        }

    def revoke_session(self, token_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token_id = ? AND revoked_at IS NULL",
                (isoformat(utc_now()), token_id),
            )

    def create_password_reset(self, email: str) -> str | None:
        with self._connect() as conn:
            user = conn.execute(
                "SELECT id FROM users WHERE email = ? COLLATE NOCASE AND is_active = 1",
                (email.strip().lower(),),
            ).fetchone()
            if user is None:
                return None
            token = secrets.token_urlsafe(40)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            now = utc_now()
            conn.execute(
                """
                INSERT INTO password_resets (
                    user_id, token_hash, created_at, expires_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    user["id"],
                    token_hash,
                    isoformat(now),
                    isoformat(now + timedelta(minutes=30)),
                ),
            )
        return token

    def reset_password(self, token: str, password: str) -> bool:
        if not PASSWORD_PATTERN.fullmatch(password):
            raise ValueError(
                "Password must be 8-128 characters and include uppercase, lowercase, and a number."
            )
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, expires_at, used_at
                FROM password_resets
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if (
                row is None
                or row["used_at"] is not None
                or datetime.fromisoformat(str(row["expires_at"])) <= now
            ):
                return False
            password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
            timestamp = isoformat(now)
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, timestamp, row["user_id"]),
            )
            conn.execute(
                "UPDATE password_resets SET used_at = ? WHERE id = ?",
                (timestamp, row["id"]),
            )
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (timestamp, row["user_id"]),
            )
        return True

    def add_feedback(self, user_id: int, category: str, message: str) -> dict[str, Any]:
        category = " ".join(category.strip().split())[:80] or "general"
        message = message.strip()[:5000]
        if len(message) < 5:
            raise ValueError("Feedback must contain at least 5 characters.")
        now = isoformat(utc_now())
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO feedback (user_id, category, message, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, category, message, now),
            )
            row = conn.execute(
                "SELECT * FROM feedback WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return dict(row) if row else {}

    def list_feedback(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT f.id, f.category, f.message, f.status, f.created_at,
                       u.id AS user_id, u.name AS user_name, u.email AS user_email
                FROM feedback f
                LEFT JOIN users u ON u.id = f.user_id
                ORDER BY f.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def log(
        self,
        table: str,
        event: str,
        *,
        user_id: int | None = None,
        level: str = "info",
        details: dict[str, Any] | None = None,
        ip_address: str = "",
    ) -> None:
        if table not in LOG_TABLES:
            raise ValueError(f"Unsupported log table: {table}")
        payload = json.dumps(details or {}, default=str)[:20_000]
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {table} (
                    user_id, event, level, details, ip_address, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    event[:160],
                    level[:32],
                    payload,
                    ip_address[:128],
                    isoformat(utc_now()),
                ),
            )


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int, now: float) -> bool:
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True
