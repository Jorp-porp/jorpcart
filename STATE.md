# jorpcart — PROJECT STATE & RUNBOOK

*If you (jorp) are reading this after a head bonk: this is everything. Start here.*

## What this is
Local grocery price tracker. Collects weekly-ad deals + live prices for local
stores (Aldi working; Meijer next), stores them in Postgres on jorpserver,
and will eventually suggest a shopping list based on what's cheap.

## Where things live
| Thing | Location |
|---|---|
| Code (this repo) | `C:\Users\jorp\jorpcart` on JorpWindows |
| Repo | https://github.com/Jorp-porp/jorpcart, branch `vibe/jorpcart-phase1` |
| Server copy | `~/jorpcart` on jorpserver (for cron) |
| Database | Docker container `jorpcart-postgres` on jorpserver |
| DB access | `postgresql://jorpcart:jorpcart-local-2026@10.126.124.196:5432/jorpcart` (ZeroTier-only bind) |

## How the Aldi adapter works (no browser needed)
aldi.us is Instacart-powered. Plain HTTP with a warmed cookie session:
1. `GET aldi.us` once (sets cookies)
2. GraphQL `FlyerActivities` (persisted query, hash
   `fc39114380b7f436c900dd89ca4a0a9ac6bba3922251bcb3727ec47a4cece9d9`,
   shopId `538598`, flyerId rotates weekly — current: `21481044298013836`)
   → list of ~130 deal names
3. GraphQL `SearchResultsPlacements` (hash
   `a33c9cadee5e69f199e0266cd91e53d837202d55041fbd74ed5342e698ac2707`,
   ZIP 49001, zoneId 604) per deal → product match + price
4. Deals with no price are usually "ALDI Finds" (in-store-only, not sold
   online). ~55/132 get prices. That's normal.
If GraphQL returns 401: the site rotated its persisted-query hashes. Re-capture
from DevTools (Network tab, filter `graphql`) and update the hashes in
`adapters/aldi_adapter.py`.

## Commands (JorpWindows, PowerShell)
```
cd C:\Users\jorp\jorpcart
py -m scripts.collect aldi          # fetch this week's deals + save to DB
py scripts\db.py                    # quick DB check (rows per store)
```
Python deps: `requests`, `psycopg[binary]` (`py -m pip install ...`)

## To update code after a push to the repo
```
Invoke-WebRequest -Uri "https://github.com/Jorp-porp/jorpcart/archive/refs/heads/vibe/jorpcart-phase1.zip" -OutFile C:\Users\jorp\jorpcart.zip
Expand-Archive C:\Users\jorp\jorpcart.zip -DestinationPath C:\Users\jorp\jorpcart-tmp -Force
Copy-Item C:\Users\jorp\jorpcart-tmp\jorpcart-vibe-jorpcart-phase1\* C:\Users\jorp\jorpcart -Recurse -Force
Remove-Item C:\Users\jorp\jorpcart-tmp, C:\Users\jorp\jorpcart.zip -Recurse -Force
```

## Database
- Container: `docker start jorpcart-postgres` (auto-restarts unless-stopped)
- Schema: `sql/schema.sql` — one `deals` table, dedup on
  `(store, product_name, deal_text, valid_from)`
- Logs: `ssh jorpserver "docker logs jorpcart-postgres"`

## Roadmap status
- [x] Phase 1: Aldi adapter (flyer + prices via GraphQL)
- [x] Meijer adapter (Flipp flyerkit API, store 21 = Gull Rd Kalamazoo;
      technique from github.com/BUTTERGANG/price-scrapers; token in adapter)
- [x] Postgres on jorpserver (ZeroTier-only bind)
- [x] Weekly automation on jorpserver: cron Wed 6am, ~/jorpcart/weekly.sh (Aldi)
- [x] Web UI: server.py (FastAPI) + static/index.html
      - run: uvicorn server:app --host 10.126.124.196 --port 8090
      - /api/deals (scored vs history), /api/search (cross-store compare),
        /api/history (price history), / for the UI
      - NOT yet daemonized on jorpserver — manual start for now
- [ ] Shopping-list SUGGESTER (not list-matching): surface what's worth
      buying — biggest discounts, cheapest staple prices per unit, regular
      buys that are currently cheap. Will use qwen (192.168.1.219:8888)
      to organize suggestions.
- [ ] Walmart/Costco: hard anti-bot (PerimeterX/Akamai). Would go through
      crawl4ai container (10.126.124.196:11235) with a FRESH browser
      profile — never the Amazon-poisoned `crawl4ai-profile` volume.

## Gotchas learned
- jorpserver disk fills up (was 100%; freed via `docker image prune -a -f`).
  Crawl4AI dies with ENOSPC when full. Check `df -h /` if anything breaks.
- PowerShell has no `<` redirect; use `Get-Content file | ssh ...`
- vibe cli on JorpWindows has broken command execution (no WSL/bash) —
  use it for coding suggestions only, run commands yourself.
- The 1TB HDD is apparently not mounted — future task.
