from __future__ import annotations

import json
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class EmailConfig:
    backend: str
    host: str
    port: int
    username: str
    password: str
    sender: str
    use_tls: bool
    use_ssl: bool
    timeout_seconds: float
    outbox_dir: Path
    frontend_origin: str

    @property
    def smtp_configured(self) -> bool:
        return bool(self.host and self.port and self.sender)


def load_email_config(runtime_root: Path, frontend_origin: str) -> EmailConfig:
    backend = os.getenv("EMAIL_BACKEND", "").strip().lower()
    host = os.getenv("SMTP_HOST", "").strip()
    if not backend:
        backend = "smtp" if host else "file"
    try:
        port = int(os.getenv("SMTP_PORT", "465" if _truthy(os.getenv("SMTP_USE_SSL")) else "587"))
    except ValueError:
        port = 587
    try:
        timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "20"))
    except ValueError:
        timeout = 20.0
    username = os.getenv("SMTP_USERNAME", os.getenv("SMTP_USER", "")).strip()
    sender = os.getenv("SMTP_FROM", os.getenv("MAIL_FROM", username)).strip()
    return EmailConfig(
        backend=backend,
        host=host,
        port=port,
        username=username,
        password=os.getenv("SMTP_PASSWORD", os.getenv("SMTP_PASS", "")),
        sender=sender,
        use_tls=_truthy(os.getenv("SMTP_USE_TLS", "1")),
        use_ssl=_truthy(os.getenv("SMTP_USE_SSL")),
        timeout_seconds=timeout,
        outbox_dir=Path(os.getenv("EMAIL_OUTBOX_DIR", runtime_root / "mail-outbox")),
        frontend_origin=os.getenv("PASSWORD_RESET_BASE_URL", frontend_origin).rstrip("/"),
    )


def password_reset_url(config: EmailConfig, token: str) -> str:
    return f"{config.frontend_origin}/reset-password?token={token}"


def _message(config: EmailConfig, recipient: str, reset_url: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = os.getenv("PASSWORD_RESET_EMAIL_SUBJECT", "Reset your SQL Copilot password")
    message["From"] = config.sender
    message["To"] = recipient
    message.set_content(
        "\n".join([
            "A password reset was requested for your SQL Copilot account.",
            "",
            "Use this link within 30 minutes:",
            reset_url,
            "",
            "If you did not request this, you can ignore this email.",
        ])
    )
    message.add_alternative(
        f"""
        <html>
          <body>
            <p>A password reset was requested for your SQL Copilot account.</p>
            <p><a href="{reset_url}">Reset your password</a></p>
            <p>This link expires in 30 minutes. If you did not request this, you can ignore this email.</p>
          </body>
        </html>
        """,
        subtype="html",
    )
    return message


def _write_outbox(config: EmailConfig, recipient: str, reset_url: str) -> dict[str, Any]:
    config.outbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_recipient = recipient.replace("@", "_at_").replace(".", "_")[:90]
    path = config.outbox_dir / f"password-reset-{timestamp}-{safe_recipient}.json"
    payload = {
        "kind": "password_reset",
        "recipient": recipient,
        "reset_url": reset_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "sent": False,
        "status": "outbox",
        "provider": "file",
        "outbox_path": str(path),
    }


def _write_test_outbox(config: EmailConfig, recipient: str) -> dict[str, Any]:
    config.outbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_recipient = recipient.replace("@", "_at_").replace(".", "_")[:90]
    path = config.outbox_dir / f"email-test-{timestamp}-{safe_recipient}.json"
    payload = {
        "kind": "email_test",
        "recipient": recipient,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "sent": False,
        "status": "outbox",
        "provider": "file",
        "outbox_path": str(path),
    }


def _send_smtp_message(config: EmailConfig, message: EmailMessage) -> dict[str, Any]:
    if not config.smtp_configured:
        return {
            "sent": False,
            "status": "not_configured",
            "provider": "smtp",
            "reason": "Set SMTP_HOST, SMTP_PORT, SMTP_FROM, SMTP_USERNAME, and SMTP_PASSWORD.",
        }
    try:
        if config.use_ssl:
            with smtplib.SMTP_SSL(
                config.host,
                config.port,
                timeout=config.timeout_seconds,
                context=ssl.create_default_context(),
            ) as smtp:
                if config.username or config.password:
                    smtp.login(config.username, config.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(config.host, config.port, timeout=config.timeout_seconds) as smtp:
                smtp.ehlo()
                if config.use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if config.username or config.password:
                    smtp.login(config.username, config.password)
                smtp.send_message(message)
    except Exception as exc:
        return {
            "sent": False,
            "status": "failed",
            "provider": "smtp",
            "reason": str(exc)[:300],
        }
    return {
        "sent": True,
        "status": "sent",
        "provider": "smtp",
    }


def send_password_reset_email(config: EmailConfig, recipient: str, token: str) -> dict[str, Any]:
    reset_url = password_reset_url(config, token)
    if config.backend == "file":
        return _write_outbox(config, recipient, reset_url)
    if config.backend != "smtp":
        return {
            "sent": False,
            "status": "disabled",
            "provider": config.backend,
            "reason": "Email backend is disabled.",
        }

    message = _message(config, recipient, reset_url)
    return _send_smtp_message(config, message)


def send_test_email(config: EmailConfig, recipient: str) -> dict[str, Any]:
    if config.backend == "file":
        return _write_test_outbox(config, recipient)
    if config.backend != "smtp":
        return {
            "sent": False,
            "status": "disabled",
            "provider": config.backend,
            "reason": "Email backend is disabled.",
        }
    message = EmailMessage()
    message["Subject"] = "SQL Copilot email delivery test"
    message["From"] = config.sender
    message["To"] = recipient
    message.set_content(
        "\n".join([
            "SQL Copilot SMTP delivery is configured correctly.",
            "",
            "Password reset emails will use this same delivery path.",
        ])
    )
    message.add_alternative(
        """
        <html>
          <body>
            <p>SQL Copilot SMTP delivery is configured correctly.</p>
            <p>Password reset emails will use this same delivery path.</p>
          </body>
        </html>
        """,
        subtype="html",
    )
    return _send_smtp_message(config, message)
