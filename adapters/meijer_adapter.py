"""Meijer weekly-ad adapter via Flipp's REST API (flyerkit v4.0).

Technique from github.com/BUTTERGANG/price-scrapers (working as of Oct 2026):
- Flipp hosts Meijer's circular: api.flipp.com/flyerkit/v4.0/
- Public access token extracted from Meijer's JS bundle (see their repo)
- No browser, no anti-bot issues, ~330 items/week

Your store: 5550 S Westnedge Ave, Portage MI 49002 = store_id "22"
(the storeInfo GraphQL you captured showed storeId 22; BUTTERGANG used
Indianapolis store 290). If circulars come back empty, run find_store_id().
"""
import json
import os
import time

import requests

STORE = "meijer"
FLIPP_API = "https://api.flipp.com/flyerkit/v4.0"
FLIPP_TOKEN = "81771d0c149847a93bc30b8e5b65bffb"
STORE_ID = os.environ.get("MEIJER_STORE_ID", "22")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.meijer.com/",
    "Origin": "https://www.meijer.com",
}


def fetch_publications(store_id=STORE_ID):
    r = requests.get(
        f"{FLIPP_API}/publications/meijer",
        params={
            "access_token": FLIPP_TOKEN,
            "locale": "en-US",
            "store_code": store_id,
        },
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_publication_products(pub_id):
    r = requests.get(
        f"{FLIPP_API}/publication/{pub_id}/products",
        params={
            "display_type": "all",
            "locale": "en-US",
            "access_token": FLIPP_TOKEN,
        },
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def parse_price(text):
    if not text:
        return None
    text = str(text).replace("$", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def collect(pub_name="Weekly Ad", store_id=None, max_items=None):
    store_id = store_id or STORE_ID
    pubs = fetch_publications(store_id)
    if isinstance(pubs, dict):
        pubs = pubs.get("publications", pubs.get("data", []))

    pub_id = None
    for pub in pubs:
        if pub_name.lower() in (pub.get("name") or "").lower():
            pub_id = pub["id"]
            break
    if not pub_id and pubs:
        pub_id = pubs[0]["id"]
    if not pub_id:
        raise RuntimeError(f"No Flipp publication found for Meijer store {store_id}")

    items = fetch_publication_products(pub_id)
    deals = []
    for item in items:
        if item.get("item_type") != 1:
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        deals.append(_deal(item, store_id, pub_id))
        if max_items and len(deals) >= max_items:
            break
    return deals


def _deal(item, store_id, pub_id):
    name = (item.get("name") or "").strip()
    price = parse_price(item.get("price_text"))
    pre = (item.get("pre_price_text") or "").strip()
    post = (item.get("post_price_text") or "").strip()
    deal_story = (item.get("sale_story") or "").strip()
    description = (item.get("description") or "").strip()
    deal_text = " ".join(x for x in [pre, str(item.get("price_text") or ""), post] if x)
    return {
        "store": STORE,
        "store_location": f"store-{store_id}",
        "product_name": name,
        "price": price,
        "unit_price": None,
        "unit": post or None,
        "deal_text": deal_story or deal_text or None,
        "valid_from": (item.get("valid_from") or "")[:10] or None,
        "valid_to": (item.get("valid_to") or "")[:10] or None,
        "source": f"flipp-meijer:{pub_id}:{item.get('id')}",
        "raw": {
            "description": description,
            "pre_price_text": pre,
            "post_price_text": post,
            "sale_story": deal_story,
            "name": item.get("name"),
        },
    }


if __name__ == "__main__":
    import sys

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    deals = collect(max_items=limit)
    ok = [d for d in deals if d["price"] is not None]
    print(f"fetched {len(deals)} deals, {len(ok)} with prices", file=sys.stderr)
    print(json.dumps(deals, indent=2, default=str))
