"""One-time (and repeatable) backfill: compute unit_price from price+unit.

Run:  py -m scripts.backfill_unit_price
"""
import sys

sys.path.insert(0, ".")
from utils.unit_price import normalize  # noqa: E402

from scripts import db  # noqa: E402


def main():
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, price, unit FROM deals WHERE unit IS NOT NULL AND unit != ''"
        )
        rows = cur.fetchall()
        updated = 0
        for rid, price, unit in rows:
            up, key = normalize(price, unit)
            cur.execute(
                "UPDATE deals SET unit_price = %s WHERE id = %s",
                (up, rid),
            )
            if up is not None:
                updated += 1
        print(f"checked {len(rows)} rows, set unit_price on {updated}")


if __name__ == "__main__":
    main()
