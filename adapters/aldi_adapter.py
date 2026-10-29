"""Aldi weekly-ad adapter — fetches the Flipp-powered circular.

Output: list of normalized deal dicts (see README schema).
"""
import os
import re
import requests

FLIPP_BASE = "https://backbone-api.marketing.flipp.com"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
}
STORE = "aldi"


def fetch_flyer(flyer_id):
    r = requests.get(f"{FLIPP_BASE}/flyers/{flyer_id}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def search_flyers(q="aldi"):
    r = requests.get(f"{FLIPP_BASE}/flyers", params={"q": q}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


N_FOR_X_RE = re.compile(r"^\s*\$?\s*(\d{1,3})\s*(?:for|/)\s*\$?\s*(\d{1,3}(?:[.,]\d{2})?)", re.I)
PRICE_RE = re.compile(r"\$?\s*(\d{1,3}(?:[.,]\d{2})?)")


def parse_price(text):
    """Handles '$3.49', '2/$5' (=$2.50 ea), '5.00', '$3.49 - $5.99' (low end)."""
    if not text:
        return None
    s = str(text)
    m = N_FOR_X_RE.match(s)
    if m:
        count = float(m.group(1))
        total = float(m.group(2).replace(",", "."))
        if count and total:
            return round(total / count, 2)
    m = PRICE_RE.search(s)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _get(item, *keys):
    for k in keys:
        v = item.get(k)
        if v not in (None, ""):
            return v
    return None


def normalize_item(item, flyer_id):
    name = _get(item, "name", "title")
    if not name:
        return None
    price = parse_price(
        _get(item, "current_price", "sale_price", "price", "dollar_value")
        or _get(item, "name", "title")
    )
    return {
        "store": STORE,
        "store_location": os.environ.get("ALDI_STORE_LOCATION"),
        "product_name": str(name).strip(),
        "price": price,
        "unit_price": None,
        "unit": _get(item, "unit", "sell_by_unit") or None,
        "deal_text": _get(item, "description", "desc") or str(name),
        "valid_from": str(_get(item, "valid_from") or "")[:10] or None,
        "valid_to": str(_get(item, "valid_to") or "")[:10] or None,
        "source": f"flipp:{flyer_id}",
        "raw": item,
    }


def collect(flyer_id=None):
    """Returns normalized deals for one Aldi flyer.

    flyer_id: numeric Flipp flyer ID. If None, tries ALDI_FLYER_ID env var,
    then a name search (verify search_flyers works from your network).
    """
    if flyer_id is None:
        flyer_id = os.environ.get("ALDI_FLYER_ID")
    if flyer_id is None:
        results = search_flyers("aldi")
        candidates = results if isinstance(results, list) else results.get("flyers", results.get("data", []))
        for f in candidates:
            brand = (f.get("brand") or f.get("name") or "").lower()
            if "aldi" in brand:
                flyer_id = f.get("id")
                break
    if not flyer_id:
        raise RuntimeError(
            "No Aldi flyer ID found. Open weeklyads.aldi.us with DevTools, "
            "find the backbone-api request, and pass flyer_id or set ALDI_FLYER_ID."
        )

    flyer = fetch_flyer(flyer_id)
    items = flyer.get("items") or []
    if not items:
        for page in flyer.get("flyer_pages", []):
            items.extend(page.get("items", []))

    deals = []
    for item in items:
        d = normalize_item(item, flyer_id)
        if d:
            deals.append(d)

    if not deals:
        raise RuntimeError(
            f"Flyer {flyer_id} fetched but no items parsed. Dump the raw JSON "
            "to a file and adjust normalize_item — Flipp payloads vary by retailer."
        )
    return deals


if __name__ == "__main__":
    import json
    import sys

    fid = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(collect(fid), indent=2, default=str))
