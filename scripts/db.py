"""Postgres helpers — env-driven, no secrets in code.

Connection precedence:
1. JORPCART_DB_URL (full postgres:// URL)
2. PGHOST/PGUSER/PGPASSWORD/PGDATABASE/PGPORT
"""
import os
import psycopg


def connect():
    url = os.environ.get("JORPCART_DB_URL")
    if url:
        return psycopg.connect(url)
    return psycopg.connect(
        host=os.environ.get("PGHOST", "10.126.124.196"),
        port=int(os.environ.get("PGPORT", "5432")),
        user=os.environ.get("PGUSER", "jorpcart"),
        password=os.environ["PGPASSWORD"],
        dbname=os.environ.get("PGDATABASE", "jorpcart"),
    )


def upsert_deals(deals):
    """Inserts deals, skipping duplicates (same store/name/text/valid_from)."""
    sql = """
    INSERT INTO deals (store, store_location, product_name, price, unit_price,
                       unit, deal_text, valid_from, valid_to, source, raw)
    VALUES (%(store)s, %(store_location)s, %(product_name)s, %(price)s,
            %(unit_price)s, %(unit)s, %(deal_text)s, %(valid_from)s,
            %(valid_to)s, %(source)s, %(raw)s::jsonb)
    ON CONFLICT (store, product_name, deal_text, valid_from) DO NOTHING
    RETURNING id;
    """
    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for d in deals:
                cur.execute(sql, {**d, "raw": psycopg.types.json.Jsonb(d["raw"])})
                if cur.fetchone():
                    inserted += 1
    return inserted


if __name__ == "__main__":
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT store, count(*) FROM deals GROUP BY store")
        for row in cur.fetchall():
            print(row)
