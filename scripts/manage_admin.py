from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.auth import AuthStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an SQL Copilot administrator or promote an existing user."
    )
    parser.add_argument("--email", required=True, help="Administrator email address")
    parser.add_argument("--name", default="SQL Copilot Admin", help="Name for a new account")
    parser.add_argument(
        "--db-path",
        default=os.getenv("AUTH_DB_PATH", str(ROOT_DIR / "backend" / "sql_copilot.db")),
        help="Authentication SQLite database path",
    )
    args = parser.parse_args()

    store = AuthStore(Path(args.db_path))
    existing = store.get_user_by_email(args.email)
    try:
        if existing:
            user = store.set_user_role(args.email, "admin")
            print(f"Promoted {user['email']} to admin.")
            print("The existing password is unchanged.")
            return 0

        password = getpass.getpass("New admin password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("Passwords do not match.", file=sys.stderr)
            return 1
        user = store.create_user(args.name, args.email, password, role="admin")
        print(f"Created admin account {user['email']}.")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
