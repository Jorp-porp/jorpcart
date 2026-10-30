"""Aldi weekly-ad adapter (aldi.us is Instacart-powered).

Pipeline (all plain HTTP, no browser):
1. Warm a session on aldi.us (sets required cookies)
2. GraphQL `FlyerActivities` -> this week's deal names
3. For each deal: GraphQL `SearchResultsPlacements` -> product match + price
4. Normalize to the common deal schema

Prices are ALDI's online (Instacart-fulfilled) prices; they run slightly above
in-store but deltas/trends are consistent.
"""
import json
import os
import re
import time

import requests

STORE = "aldi"
BASE = "https://www.aldi.us"
GRAPHQL = f"{BASE}/graphql"
SHOP_ID = "538598"
POSTAL = os.environ.get("ALDI_ZIP", "49001")
ZONE_ID = os.environ.get("ALDI_ZONE", "604")

FLYER_ACTIVITIES_HASH = (
    "fc39114380b7f436c900dd89ca4a0a9ac6bba3922251bcb3727ec47a4cece9d9"
)
SEARCH_RESULTS_HASH = (
    "a33c9cadee5e69f199e0266cd91e53d837202d55041fbd74ed5342e698ac2707"
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)


def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    s.get(BASE, timeout=30)
    return s


def gql(s, operation, variables, sha):
    params = {
        "operationName": operation,
        "variables": json.dumps(variables),
        "extensions": json.dumps(
            {"persistedQuery": {"version": 1, "sha256Hash": sha}}
        ),
    }
    r = s.get(GRAPHQL, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("data", {})


def fetch_activities(s, flyer_id):
    data = gql(
        s,
        "FlyerActivities",
        {
            "shopId": SHOP_ID,
            "flyerId": flyer_id,
            "filter": {"key": "all", "value": None},
        },
        FLYER_ACTIVITIES_HASH,
    )
    return data.get("flyerActivities") or []


def search(s, query, first=8):
    data = gql(
        s,
        "SearchResultsPlacements",
        {
            "action": None,
            "query": query,
            "pageViewId": "00000000-0000-0000-0000-000000000000",
            "elevatedProductId": None,
            "searchSource": "search",
            "filters": [],
            "disableReformulation": False,
            "disableLlm": False,
            "forceInspiration": False,
            "orderBy": "bestMatch",
            "clusterId": None,
            "includeDebugInfo": False,
            "clusteringStrategy": None,
            "contentManagementSearchParams": {"itemGridColumnCount": 1},
            "shopId": SHOP_ID,
            "postalCode": POSTAL,
            "zoneId": ZONE_ID,
            "first": first,
        },
        SEARCH_RESULTS_HASH,
    )
    return extract_items(data)


def extract_items(data):
    """Walk the placements tree; pair items with their prices via product_id."""
    items = {}
    prices = {}

    def walk(o):
        if isinstance(o, dict):
            pid = o.get("product_id")
            if pid and "price" in o:
                prices[pid] = {
                    "price": o.get("price"),
                    "badge": o.get("badge_type"),
                    "save_amount": o.get("save_amount"),
                }
            elif o.get("productId") and o.get("name"):
                items[o["productId"]] = {
                    "product_id": o["productId"],
                    "name": o.get("name"),
                    "size": o.get("size"),
                    "brand": o.get("brandName"),
                    "evergreen_url": o.get("evergreenUrl"),
                }
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    out = []
    for pid, item in items.items():
        p = prices.get(pid, {})
        item["price"] = p.get("price")
        item["badge"] = p.get("badge")
        item["save_amount"] = p.get("save_amount")
        out.append(item)
    return out


def parse_price(text):
    if not text:
        return None
    m = re.search(r"\$?\s*(\d{1,3}(?:\.\d{2})?)", str(text))
    return float(m.group(1)) if m else None


def collect(flyer_id=None, max_items=None, delay=2.0):
    if flyer_id is None:
        flyer_id = os.environ.get("ALDI_FLYER_ID", "21481044298013836")
    s = make_session()

    activities = fetch_activities(s, flyer_id)
    if max_items:
        activities = activities[:max_items]

    deals = []
    for act in activities:
        name = (act.get("description") or act.get("extActivityId") or "").strip()
        if not name:
            continue
        try:
            matches = search(s, name)
        except requests.RequestException as e:
            deals.append(_deal(name, None, act, error=str(e)))
            continue
        best = matches[0] if matches else None
        if best and best.get("price"):
            deals.append(_deal(best["name"], parse_price(best["price"]), act,
                               url=best.get("evergreen_url"), match=best))
        else:
            deals.append(_deal(name, None, act))
        time.sleep(delay)
    return deals


def _deal(name, price, act, url=None, match=None, error=None):
    return {
        "store": STORE,
        "store_location": os.environ.get("ALDI_STORE_LOCATION"),
        "product_name": name,
        "price": price,
        "unit_price": None,
        "unit": (match or {}).get("size"),
        "deal_text": act.get("extActivityId") or name,
        "valid_from": None,
        "valid_to": None,
        "source": f"aldi-flyer:{act.get('id')}",
        "raw": {"activity": act, "url": url, "match": match, "error": error},
    }


if __name__ == "__main__":
    import sys

    flyer = sys.argv[1] if len(sys.argv) > 1 else None
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    deals = collect(flyer, limit)
    ok = [d for d in deals if d["price"] is not None]
    print(f"fetched {len(deals)} deals, {len(ok)} with prices", file=sys.stderr)
    print(json.dumps(deals, indent=2, default=str))
