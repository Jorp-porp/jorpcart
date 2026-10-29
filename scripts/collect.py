"""Run adapters and upsert deals into Postgres.

Usage:
  python -m scripts.collect aldi [flyer_id]
  python -m scripts.collect aldi
"""
import importlib
import json
import sys

sys.path.insert(0, ".")
from scripts import db  # noqa: E402


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python -m scripts.collect <store> [adapter-args...]")

    store = sys.argv[1]
    adapter = importlib.import_module(f"adapters.{store}_adapter")

    kwargs = {}
    if len(sys.argv) > 2 and sys.argv[2].isdigit():
        kwargs["flyer_id"] = sys.argv[2]

    deals = adapter.collect(**kwargs)
    print(f"{store}: fetched {len(deals)} deals")

    try:
        inserted = db.upsert_deals(deals)
        print(f"{store}: inserted {inserted} new deals")
    except Exception as e:
        out = f"deals_{store}.json"
        with open(out, "w") as f:
            json.dump(deals, f, indent=2, default=str)
        print(f"DB unavailable ({e}); wrote {len(deals)} deals to {out} instead")


if __name__ == "__main__":
    main()
