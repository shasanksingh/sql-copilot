import sys
import os

# Ensure repository root is on sys.path for imports like `agentic` and `rl`
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("SQL_COPILOT_DISABLE_RUNTIME_SECRETS", "1")
