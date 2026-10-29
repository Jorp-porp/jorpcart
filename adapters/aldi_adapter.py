"""Aldi weekly-ad adapter.

Flow:
1. GraphQL `FlyerActivities` on aldi.us (Instacart-powered) -> list of deal names
2. For each name: fetch the aldi.us search page, parse the schema.org JSON-LD
   (Product / ItemList) -> product URL + price
3. Normalize to the common deal schema.

Note: prices returned are ALDI's online (Instacart-fulfilled) prices, which run
slightly above in-store prices. Good enough for tracking/optimization; deltas
are what matter.
"""
import json
import os
import re
import requests

STORE = "aldi"
GRAPHQL = "https://www.aldi.us/graphql"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
}
FLYER_ACTIVITIES_HASH = (
    "fc39114380b7f436c900dd89ca4a0a9ac6bba3922251bcb3727ec47a4cece9d9"
)


def fetch_activities(shop_id="538598", flyer_id=None):
    if flyer_id is None:
        flyer_id = os.environ.get("ALDI_FLYER_ID", "21481044298013836")
    params = {
        "operationName": "FlyerActivities",
        "variables": json.dumps({
            "shopId": shop_id,
            "flyerId": flyer_id,
            "filter": {"key": "all", "value": None},
        }),
        "extensions": json.dumps({
            "persistedQuery": {"version": 1, "sha256Hash": FLYER_ACTIVITIES_HASH}
        }),
    }
    r = requests.get(GRAPHQL, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["data"]["flyerActivities"]


LDJSON_RE = re.compile(
    r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', re.S
)


def parse_ld_products(html):
    """Extract all Product offers from schema.org JSON-LD blocks in a page."""
    products = []
    for m in LDJSON_RE.finditer(html):
        try:
            blob = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for node in _walk(blob):
            if node.get("@type") == "Product":
                offers = node.get("offers") or {}
                price = offers.get("price")
                if price:
                    products.append({
                        "name": node.get("name"),
                        "price": float(price),
                        "url": offers.get("url"),
                        "size": node.get("size"),
                        "brand": ((node.get("brand") or {}).get("name")),
                        "category": node.get("category"),
                    })
    return products


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def search_products(query):
    r = requests.get(
        f"https://www.aldi.us/store/aldi/s",
        params={"k": query},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return parse_ld_products(r.text)


def collect(flyer_id=None, max_items=None):
    activities = fetch_activities(flyer_id=flyer_id)
    if max_items:
        activities = activities[:max_items]

    deals = []
    for act in activities:
        name = (act.get("description") or act.get("extActivityId") or "").strip()
        if not name:
            continue
        matches = search_products(name)
        if not matches:
            deals.append(_deal(name, None, act))
            continue
        best = matches[0]
        deals.append(_deal(best["name"], best["price"], act, url=best.get("url")))
    return deals


def _deal(name, price, act, url=None):
    return {
        "store": STORE,
        "store_location": os.environ.get("ALDI_STORE_LOCATION"),
        "product_name": name,
        "price": price,
        "unit_price": None,
        "unit": None,
        "deal_text": act.get("extActivityId") or name,
        "valid_from": None,
        "valid_to": None,
        "source": f"aldi-flyer:{act.get('id')}",
        "raw": {"activity": act, "url": url},
    }


if __name__ == "__main__":
    import sys

    flyer = sys.argv[1] if len(sys.argv) > 1 else None
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print(json.dumps(collect(flyer, limit), indent=2, default=str))
