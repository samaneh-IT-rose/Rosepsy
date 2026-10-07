import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal
from app.services.seed import seed_roles

if __name__ == "__main__":
    with SessionLocal() as db:
        seed_roles(db)
    print("seed ok: roles + permissions synced")
