"""jorpcart web API — deals, scoring, cross-store compare, history.

Run: uvicorn server:app --host 10.126.124.196 --port 8090
"""
import os
import re
import time
from datetime import date

import psycopg
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from psycopg.rows import dict_row

DB_URL = os.environ.get(
    "JORPCART_DB_URL",
    "postgresql://jorpcart:jorpcart-local-2026@10.126.124.196:5432/jorpcart",
)

app = FastAPI()

STOP = re.compile(
    r"\b(asst|assorted|assort|select|varieties|variety|or|the|with|and|w/|"
    r"\d+(\.\d+)?\s?(oz|fl oz|lb|ct|pk|gal|pt|qt|l|ml|g|kg|ea)\b\.?|"
    r"[\d.]+)\b",
    re.I,
)


def norm_name(name: str) -> str:
    """Crude product-name normalizer for cross-store matching."""
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = STOP.sub(" ", s)
    words = [w for w in s.split() if len(w) > 1]
    return " ".join(sorted(set(words))[:6])


def connect():
    return psycopg.connect(DB_URL, row_factory=dict_row)


def current_week-deals():
    """Deals whose valid window covers today, or (Aldi) most recent per source."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (source) source, min(first_seen_at) AS seen
            FROM deals GROUP BY source
            """
        )


def week_deals():
    """This week's deals: for dated rows use valid window; else latest run."""
    today = date.today()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.* FROM deals d
            WHERE (d.valid_from IS NOT NULL AND d.valid_from <= %s
                   AND (d.valid_to IS NULL OR d.valid_to >= %s))
            UNION
            SELECT d.* FROM deals d
            WHERE d.valid_from IS NULL
              AND d.first_seen_at >= (SELECT max(first_seen_at) - interval '2 days'
                                      FROM deals WHERE store = d.store)
            """,
            (today, today),
        )
        return cur.fetchall()


def stats_for(keys):
    """Historical min/avg price per normalized name key."""
    if not keys:
        return {}
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE _keys (k text PRIMARY KEY) ON COMMIT DROP
            """
        ) if False else None
        out = {}
        for k in set(keys):
            cur.execute(
                """
                SELECT min(price) AS mn, avg(price) AS av, count(*) AS n
                FROM deals
                WHERE price IS NOT NULL
                  AND (regexp_replace(lower(product_name), '[^a-z0-9 ]', ' ', 'g')
                       LIKE %s)
                  AND first_seen_at < now() - interval '6 days'
                """,
                (f"%{k.split(' ')[0]}%" if k else "%",),
            )
            row = cur.fetchone()
            if row and row["n"]:
                out[k] = row
        return out


def score_deals(deals):
    """Score = how good this week's price is vs history (per normalized name)."""
    stats = {}
    with connect() as conn, conn.cursor() as cur:
        for d in deals:
            k = norm_name(d["product_name"])
            if not k or k in stats:
                continue
            cur.execute(
                """
                SELECT min(price) AS mn, avg(price) AS av, count(*) AS n
                FROM deals
                WHERE price IS NOT NULL
                  AND lower(product_name) LIKE %s
                  AND first_seen_at < now() - interval '5 days'
                """,
                (f"%{k.split()[0]}%",),
            )
            row = cur.fetchone()
            if row and row["n"]:
                stats[k] = row

    for d in deals:
        d["norm_key"] = norm_name(d["product_name"])
        d["score"] = None
        d["hist_min"] = None
        d["hist_avg"] = None
        if d["price"] is None:
            continue
        st = stats.get(d["norm_key"])
        if st and st["mn"]:
            d["hist_min"] = float(st["mn"])
            d["hist_avg"] = float(st["av"])
            if d["hist_min"] > 0:
                d["score"] = round(
                    100 * (d["hist_min"] - float(d["price"])) / d["hist_min"], 1
                )
    return deals


@app.get("/api/deals")
def deals(min_price: float = 0, limit: int = 200):
    rows = week_deals()
    rows = [r for r in rows if r["price"] and float(r["price"]) >= min_price]
    rows = score_deals(rows)
    rows.sort(key=lambda r: (r["score"] or -999), reverse=True)
    out = []
    for r in rows[:limit]:
        out.append(
            {
                "store": r["store"],
                "product_name": r["product_name"],
                "price": float(r["price"]),
                "unit": r["unit"],
                "deal_text": r["deal_text"],
                "valid_from": str(r["valid_from"] or ""),
                "valid_to": str(r["valid_to"] or ""),
                "score": r["score"],
                "hist_min": r["hist_min"],
                "hist_avg": r["hist_avg"],
            }
        )
    return out


@app.get("/api/search")
def search(q: str):
    """Cross-store compare: best price per store for matching items."""
    like = f"%{q}%"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT store, product_name, price, unit, deal_text,
                   valid_from, valid_to, first_seen_at
            FROM deals
            WHERE price IS NOT NULL AND lower(product_name) LIKE %s
            ORDER BY price ASC
            """,
            (like,),
        )
        rows = cur.fetchall()
    by_store = {}
    for r in rows:
        s = r["store"]
        if s not in by_store:
            by_store[s] = {
                "store": s,
                "product_name": r["product_name"],
                "price": float(r["price"]),
                "unit": r["unit"],
                "deal_text": r["deal_text"],
                "first_seen": str(r["first_seen_at"])[:10],
            }
    return sorted(by_store.values(), key=lambda x: x["price"])


@app.get("/api/history")
def history(q: str):
    """Price history for a search term, oldest → newest."""
    like = f"%{q}%"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT store, product_name, price, unit, deal_text,
                   valid_from, valid_to, first_seen_at
            FROM deals
            WHERE price IS NOT NULL AND lower(product_name) LIKE %s
            ORDER BY first_seen_at ASC
            LIMIT 500
            """,
            (like,),
        )
        rows = cur.fetchall()
    return [
        {
            "store": r["store"],
            "product_name": r["product_name"],
            "price": float(r["price"]),
            "unit": r["unit"],
            "date": str(r["valid_from"] or str(r["first_seen_at"])[:10]),
        }
        for r in rows
    ]


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html")) as f:
        return f.read()
