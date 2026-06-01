from __future__ import annotations

import importlib.util
from pathlib import Path

from asgiref.wsgi import WsgiToAsgi


BASE_DIR = Path(__file__).resolve().parent
LEGACY_APP_FILE = BASE_DIR / "app .py"

spec = importlib.util.spec_from_file_location("sql_copilot_legacy_app", LEGACY_APP_FILE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load Flask app from {LEGACY_APP_FILE}")

legacy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy_module)

app = legacy_module.app
asgi_app = getattr(legacy_module, "asgi_app", None) or WsgiToAsgi(app)

