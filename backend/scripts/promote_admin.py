import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.services.seed import promote_admin

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/promote_admin.py <phone>")
        raise SystemExit(2)
    try:
        with SessionLocal() as db:
            uid = promote_admin(db, sys.argv[1])
    except LookupError as exc:
        print(str(exc))
        raise SystemExit(1)
    print(f"system_admin granted to user {uid}")
