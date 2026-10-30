"""jorpcart web API — deals, scoring, cross-store compare, history.

All comparisons use unit_price (per canonical unit) where computable.

Run: uvicorn server:app --host 10.126.124.196 --port 8090
"""
import os
import re
from datetime import date

import psycopg
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from psycopg.rows import dict_row

sys_path = os.path.dirname(os.path.abspath(__file__))
import sys

if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from utils.unit_price import normalize, display  # noqa: E402

DB_URL = os.environ.get(
    "JORPCART_DB_URL",
    "postgresql://jorpcart:jorpcart-local-2026@10.126.124.196:5432/jorpcart",
)

app = FastAPI()


def connect():
    return psycopg.connect(DB_URL, row_factory=dict_row)


def week_deals():
    """This week's deals: dated rows use the valid window; else latest run."""
    today = date.today()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.* FROM deals d
            WHERE d.price IS NOT NULL
              AND (
                (d.valid_from IS NOT NULL AND d.valid_from <= %s
                 AND (d.valid_to IS NULL OR d.valid_to >= %s))
                OR
                (d.valid_from IS NULL
                 AND d.first_seen_at >= (SELECT max(first_seen_at) - interval '2 days'
                                         FROM deals WHERE store = d.store))
              )
            """,
            (today, today),
        )
        rows = cur.fetchall()
    for r in rows:
        up, key = normalize(r["price"], r["unit"])
        r["unit_price_v"] = up
        r["canonical"] = key
        r["disp_val"], r["disp_label"] = display(up, key)
        r["norm_name"] = norm_name(r["product_name"])
        r["score"] = None
        r["hist_min"] = None
        r["hist_avg"] = None
        r["norm_name"] = norm_name(r["product_name"])
    return rows


def norm_name(name: str) -> str:
    """Product-name normalizer for cross-store matching."""
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(
        r"\b(asst|assorted|assort|select|varieties|variety|and|w/|"
        r"\d+(\.\d+)?\s?(oz|fl|lb|ct|pk|gal|pt|qt|l|ml|g|kg|ea))\b",
        " ",
        s,
    )
    words = [w for w in s.split() if len(w) > 2]
    return " ".join(sorted(set(words))[:6])


@app.get("/api/deals")
def deals(limit: int = 200):
    rows = week_deals()
    rows = [r for r in rows if r["unit_price_v"] is not None]
    for r in rows:
        r["score"] = None
        r["hist_min"] = None
    # score against history using unit_price stored at insert (backfilled)
    with connect() as conn, conn.cursor() as cur:
        for r in rows:
            if not r["norm_name"]:
                continue
            cur.execute(
                """
                SELECT min(d.unit_price) AS mn, avg(d.unit_price) AS av, count(*) AS n
                FROM deals d
                WHERE d.unit_price IS NOT NULL
                  AND d.first_seen_at < now() - interval '5 days'
                  AND lower(d.product_name) LIKE %s
                """,
                (f"%{r['norm_name'].split()[0]}%",),
            )
            row = cur.fetchone()
            if row and row["n"]:
                r["hist_min"] = float(row["mn"]) if row["mn"] else None
                r["hist_avg"] = float(row["av"]) if row["av"] else None
                if r["hist_min"] and r["hist_min"] > 0:
                    r["score"] = round(
                        100 * (r["hist_min"] - r["unit_price_v"]) / r["hist_min"], 1
                    )
    rows.sort(key=lambda r: (r["score"] if r["score"] is not None else -999), reverse=True)
    out = []
    for r in rows[:limit]:
        out.append(
            {
                "store": r["store"],
                "product_name": r["product_name"],
                "price": float(r["price"]),
                "unit_price": r["unit_price_v"],
                "canonical": r["canonical"],
                "disp_val": r["disp_val"],
                "disp_label": r["disp_label"],
                "unit": r["unit"],
                "deal_text": r["deal_text"],
                "score": r["score"],
                "hist_min": r["hist_min"],
                "hist_avg": r["hist_avg"],
            }
        )
    return out


@app.get("/api/search")
def search(q: str):
    """Cross-store compare: best unit price per store."""
    like = f"%{q}%"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT store, product_name, price, unit, unit_price, deal_text, first_seen_at
            FROM deals
            WHERE unit_price IS NOT NULL AND lower(product_name) LIKE %s
            ORDER BY unit_price ASC
            """,
            (like,),
        )
        rows = cur.fetchall()
    by_store = {}
    for r in rows:
        s = r["store"]
        if s not in by_store:
            up, ck = normalize(r["price"], r["unit"]) if not r["unit_price"] else (float(r["unit_price"]), None)
            dv, dl = display(up or (float(r["unit_price"]) if r["unit_price"] else None), ck) if ck else (None, None)
            by_store[s] = {
                "store": s,
                "product_name": r["product_name"],
                "price": float(r["price"]),
                "unit_price": float(r["unit_price"]),
                "disp_val": dv,
                "disp_label": dl,
                "unit": r["unit"],
                "deal_text": r["deal_text"],
                "first_seen": str(r["first_seen_at"])[:10],
            }
    return sorted(by_store.values(), key=lambda x: x["unit_price"])


@app.get("/api/history")
def history(q: str):
    """Unit-price history for a search term, oldest -> newest."""
    like = f"%{q}%"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT store, product_name, price, unit, unit_price, deal_text,
                   valid_from, valid_to, first_seen_at
            FROM deals
            WHERE unit_price IS NOT NULL AND lower(product_name) LIKE %s
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
            "unit_price": float(r["unit_price"]),
            "unit": r["unit"],
            "date": str(r["valid_from"] or str(r["first_seen_at"])[:10]),
        }
        for r in rows
    ]


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html")) as f:
        return f.read()
