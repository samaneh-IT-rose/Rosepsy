"""Align alembic_version with the actual DB schema (dev reconciler)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.config import Config
from sqlalchemy import inspect, text

from alembic import command
from app.core.db import engine


def main() -> None:
    cfg = Config("alembic.ini")
    head = (command.heads(cfg) or "").split()[0]
    insp = inspect(engine)
    current = None
    if insp.has_table("alembic_version"):
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

    if current == head:
        print(f"db_sync: already at head ({head})")
        return

    if current is None:
        if insp.has_table("users", schema="core"):
            command.stamp(cfg, head)
            print(f"db_sync: stamped existing schema at {head}")
        else:
            command.upgrade(cfg, "head")
            print(f"db_sync: upgraded empty DB to {head}")
        return

    try:
        command.upgrade(cfg, "head")
        print(f"db_sync: upgraded {current} -> {head}")
    except Exception as exc:
        print(f"db_sync: upgrade failed ({exc.__class__.__name__}); stamping head.")
        command.stamp(cfg, head)
        print(f"db_sync: stamped at {head}")


if __name__ == "__main__":
    main()
