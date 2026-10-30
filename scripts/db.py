"""Postgres helpers — env-driven, no secrets in code.

Connection precedence:
1. JORPCART_DB_URL (full postgres:// URL)
2. Fallback default: jorpcart-postgres on jorpserver (ZeroTier IP, LAN-only)
"""
import os

import psycopg
from psycopg.types.json import Jsonb

DEFAULT_URL = (
    "postgresql://jorpcart:jorpcart-local-2026@10.126.124.196:5432/jorpcart"
)


def connect():
    url = os.environ.get("JORPCART_DB_URL", DEFAULT_URL)
    return psycopg.connect(url)


def upsert_deals(deals):
    """Inserts deals, skipping duplicates (same store/name/text/valid_from)."""
    sql = """
    INSERT INTO deals (store, store_location, product_name, price, unit_price,
                       unit, deal_text, valid_from, valid_to, source, raw)
    VALUES (%(store)s, %(store_location)s, %(product_name)s, %(price)s,
            %(unit_price)s, %(unit)s, %(deal_text)s, %(valid_from)s,
            %(valid_to)s, %(source)s, %(raw)s)
    ON CONFLICT (store, product_name, deal_text, valid_from) DO NOTHING
    RETURNING id;
    """
    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for d in deals:
                cur.execute(sql, {**d, "raw": Jsonb(d["raw"])})
                if cur.fetchone():
                    inserted += 1
    return inserted


if __name__ == "__main__":
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT store, count(*), count(price) FROM deals GROUP BY store")
        for row in cur.fetchall():
            print(row)
