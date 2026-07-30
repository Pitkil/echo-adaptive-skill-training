"""Create the first ECHO system administrator without a public setup endpoint."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPOSITORY_ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app import ensure_catalog, pwd_context  # noqa: E402
from database import SessionLocal, TrainingProgram, User, UserRole, init_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize an ECHO system administrator.")
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--promote-existing",
        action="store_true",
        help="Promote an existing account without changing its password.",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        ensure_catalog(db)
        existing = db.query(User).filter_by(username=args.username).first()
        if existing is not None:
            if not args.promote_existing:
                raise SystemExit(
                    "Account already exists. Re-run with --promote-existing to make it an administrator."
                )
            existing.role = UserRole.SYSTEM_ADMIN.value
            db.commit()
            print(f"Promoted {existing.username} to system_admin.")
            return

        password = getpass.getpass("Administrator password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")
        if len(password) < 10:
            raise SystemExit("Password must contain at least 10 characters.")

        program = db.query(TrainingProgram).order_by(TrainingProgram.id).first()
        if program is None:
            raise SystemExit("Training catalog was not initialized.")
        administrator = User(
            organization_id=program.organization_id,
            username=args.username,
            hashed_password=pwd_context.hash(password),
            role=UserRole.SYSTEM_ADMIN.value,
        )
        db.add(administrator)
        db.commit()
        print(f"Created system administrator {administrator.username}.")
    finally:
        db.close()
if __name__ == "__main__":
    main()
