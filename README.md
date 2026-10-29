# jorpcart — local grocery price tracker & shopping optimizer

Phase 1: weekly-ad (circular) price collection for Aldi, then Meijer.
Store adapters normalize deals into one Postgres schema; optimizer comes later.

## Layout
- `adapters/` — per-store fetchers, all output the same normalized deal dict
- `sql/schema.sql` — Postgres schema (run once)
- `scripts/` — helper entrypoints (collect, dump)

## Normalized deal schema (all adapters MUST return this)
```
{
  "store":        "aldi",                  # slug: aldi | meijer | walmart | costco
  "store_location": "your-store-city",     # or store id if known
  "product_name": "Fairlife 2% Milk",
  "price":        3.49,                    # current/promo price, USD
  "unit_price":   0.029,                   # $ per unit if computable, else None
  "unit":         "oz",                    # oz | lb | ea | ct | gal ...
  "deal_text":    "Fairlife Milk 52oz $3.49",  # raw flyer line
  "valid_from":   "2026-10-19",
  "valid_to":     "2026-10-25",
  "source":       "flipp:3661712",         # provenance
  "raw":          {...}                   # original item payload (JSON-able)
}
```

## Adapters

### aldi_adapter.py (Phase 1)
Weekly circular via Flipp's backbone API (powers most US grocery circulars,
including Aldi). Flow:

1. `GET https://backbone-api.marketing.flipp.com/flyers/{flyer_id}`
   → JSON with `flyer_pages[]` and `items[]`.
2. Each item: `name` / `desc` / `current_price` (or `sale_price`) / `image` /
   `valid_from` / `valid_to` / `dollar_value` etc.
3. `parse_price()` handles common flyer price formats ("2/$5", "$3.49", "5.00").
4. If items lack prices in the listing, fall back to `flipp_items` on the
   flyer's item endpoints — or parse the page-level `content` blobs.

**Find your Aldi flyer_id:** open weeklyads.aldi.us (or the Flipp-powered
circular on aldi.us) in a browser, open DevTools → Network tab, filter
`backbone-api`, grab the numeric flyer ID from the request. Aldi rotates
flyer IDs weekly — resolve the CURRENT id by name/brand via:

`GET https://backbone-api.marketing.flipp.com/flyers?q=aldi`  (verify works;
if not, use the store-locator/weeklyad page's embedded JSON: look for
`flyer_id` or `flipp` keys in page source).

If Flipp requires headers that a bare curl lacks, add:
`Accept: application/json` and a normal `User-Agent` (browser-like).
If the API is dead/gated on your IP, fall back to scraping
weeklyads.aldi.us directly with requests+BeautifulSoup — Aldi's own site
has minimal anti-bot.

### meijer_adapter.py (Phase 2)
Meijer's site/app uses an internal search/list API (see community
reverse-engineering: github.com/dapperfu/python_Meijer). Do the same
DevTools capture on meijer.com search → find the XHR returning product JSON
(includes price + mPerks promo data). Requires store-locator ZIP header
to get real store prices.

### walmart_adapter.py / costco_adapter.py (Phase 5 — stretch)
Do NOT build these until Aldi+Meijer are working. Anti-bot (PerimeterX/
Akamai) means: use the crawl4ai container (10.126.124.196:11235), fresh
browser profile (NOT the Amazon-poisoned `crawl4ai-profile` volume),
≤50 products per run, 1–2 runs/day max, treat gaps as normal.

## Postgres

Reuse the Postgres from the PriceGhost compose if it can host another
database — create a separate `jorpcart` DB there (do NOT touch PriceGhost's
own DB). Otherwise run a tiny dedicated Postgres.

Create schema (run as a user that can hit the DB — see scripts/db.py for
env-based connection):
```
psql "$JORPCART_DB_URL" -f sql/schema.sql
```

## Scripts
- `scripts/collect.py` — runs chosen adapters, upserts deals
- `scripts/db.py` — Postgres helpers (env: `JORPCART_DB_URL` or
  PGHOST/PGUSER/PGPASSWORD/PGDATABASE, plus JORPCART_FALLBACK_URL for
  containers that only expose a port on ZeroTier)

## Env / secrets
No secrets yet. DB URL goes in an env file on jorpserver, never committed:
`JORPCART_DB_URL=postgres://user:pass@10.126.124.196:5432/jorpcart`

## User-run (elevated) commands needed on JorpWindows/jorpserver
These require the user (jorp) at the keyboard — vibe cli cannot and
should not auto-elevate:
- psql schema apply (if run via docker exec into the PriceGhost postgres:
  needs docker group rights or sudo)
- any new Postgres container/compose changes (bind to 10.126.124.196 only,
  never 0.0.0.0)
- cron/systemd-timer creation on jorpserver for scheduled collection
- restoring/creating the crawl4ai fresh profile volume
