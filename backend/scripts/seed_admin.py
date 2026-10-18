"""CLI: seed admin reference data + demo data, promote a national admin.

Usage (from backend/):
  .venv/bin/python -m scripts.seed_admin                       # seed everything
  .venv/bin/python -m scripts.seed_admin --admin-phone 09...   # seed + promote
  .venv/bin/python -m scripts.seed_admin --reference-only      # provinces/cities/centers
"""

import argparse
import sys

from app.core.db import SessionLocal
from app.services.seed_admin import (
    promote_national_admin,
    run_full_seed,
    seed_centers,
    seed_provinces_and_cities,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed admin panel data (B42)")
    parser.add_argument(
        "--admin-phone", help="promote this phone to ادمین ملی"
    )
    parser.add_argument(
        "--reference-only", action="store_true", help="only provinces/cities/centers"
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.reference_only:
            seed_provinces_and_cities(db)
            created = seed_centers(db)
            print(f"reference seeded; centers created: {created}")
        else:
            result = run_full_seed(db)
            print(f"seed complete; centers created: {result['centers_created']}")
        if args.admin_phone:
            user_id = promote_national_admin(db, args.admin_phone)
            print(f"national admin promoted: {user_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
