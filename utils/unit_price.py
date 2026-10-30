"""Unit-price normalization — makes cross-store comparison possible.

Rules:
- If a deal's unit is a SIZE ("64 fl oz", "3 lb", "12 ct"), unit_price is
  price divided by the size, converted to a canonical base unit.
- If a deal's unit is a RATE ("lb", "ea"), the price is already per that
  unit; unit_price = price in the canonical base unit.
- Canonical units: per_oz (weight), per_fl_oz (volume), per_ct (count),
  per_gal, per_lb stays per_lb (produce/meat are sold per lb).

Returns (unit_price, canonical_unit_key) or (None, None).
"""
import re

OZ_IN_LB = 16.0
FL_OZ_IN_GAL = 128.0
FL_OZ_IN_QT = 32.0
FL_OZ_IN_PT = 16.0
ML_IN_FL_OZ = 29.5735
G_IN_OZ = 28.3495
KG_IN_OZ = 35.274

SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(fl\.?\s*oz|fluid ounces?|oz|ounces?|ounce|lbs?|pounds?|"
    r"gal|gallons?|qt|quarts?|pt|pints?|l|liter|liters?|ml|milliliters?|"
    r"g\b|grams?|kg|kilograms?|ct|count|pack|pk)\b",
    re.I,
)

# size-unit -> (canonical key, conversion factor to canonical base)
SIZE_UNITS = {
    "oz": ("per_oz", 1.0), "ounce": ("per_oz", 1.0), "ounces": ("per_oz", 1.0),
    "lb": ("per_lb", 1.0), "lbs": ("per_lb", 1.0),
    "pound": ("per_lb", 1.0), "pounds": ("per_lb", 1.0),
    "fl oz": ("per_fl_oz", 1.0), "fluid ounce": ("per_fl_oz", 1.0),
    "fluid ounces": ("per_fl_oz", 1.0), "floz": ("per_fl_oz", 1.0),
    "gal": ("per_gal", 1.0), "gallon": ("per_gal", 1.0),
    "gallons": ("per_gal", 1.0),
    "qt": ("per_gal", 1 / FL_OZ_IN_QT * FL_OZ_IN_GAL / FL_OZ_IN_GAL),  # per-qt->gal handled below
    "pt": ("per_gal", 1.0),
    "l": ("per_fl_oz", 1 / ML_IN_FL_OZ * 1000 / 1000),  # liter -> fl oz below
    "liter": ("per_fl_oz", 1 / ML_IN_FL_OZ * 1000),
    "ml": ("per_fl_oz", 1 / ML_IN_FL_OZ),
    "g": ("per_oz", 1 / G_IN_OZ),
    "gram": ("per_oz", 1 / G_IN_OZ), "grams": ("per_oz", 1 / G_IN_OZ),
    "kg": ("per_oz", 1 / KG_IN_OZ),
    "kilogram": ("per_oz", 1 / KG_IN_OZ), "kilograms": ("per_oz", 1 / KG_IN_OZ),
    "ct": ("per_ct", 1.0), "count": ("per_ct", 1.0), "pk": ("per_ct", 1.0),
    "pack": ("per_ct", 1.0),
}


def normalize(price, unit):
    """Return (unit_price, canonical_key) or (None, None)."""
    if price is None or not unit:
        return None, None
    u = str(unit).strip().lower().replace(".", "")
    price = float(price)

    # Rate units: price is already per-unit
    if u in ("lb", "lbs", "pound", "pounds"):
        return round(price, 4), "per_lb"
    if u in ("ea", "each"):
        return round(price, 4), "per_ea"
    if u in ("oz", "ounce", "ounces"):
        return round(price, 4), "per_oz"

    # Size units: find "N <unit>" in the string
    m = SIZE_RE.search(str(unit))
    if not m:
        return None, None
    qty = float(m.group(1))
    raw_unit = m.group(2).lower().replace(".", "").strip()
    if raw_unit.startswith("fl"):
        key, factor = "per_fl_oz", 1.0
    elif raw_unit in ("oz", "ounce", "ounces"):
        key, factor = "per_oz", 1.0
    elif raw_unit in ("lb", "lbs", "pound", "pounds"):
        key, factor = "per_lb", 1.0
    elif raw_unit in ("gal", "gallon", "gallons"):
        # convert gallons to fl oz for finer comparison
        key, factor = "per_fl_oz", FL_OZ_IN_GAL
    elif raw_unit in ("qt", "quart", "quarts"):
        key, factor = "per_fl_oz", FL_OZ_IN_QT
    elif raw_unit in ("pt", "pint", "pints"):
        key, factor = "per_fl_oz", FL_OZ_IN_PT
    elif raw_unit in ("l", "liter", "liters", "litre", "litres"):
        key, factor = "per_fl_oz", 1000 / ML_IN_FL_OZ
    elif raw_unit in ("ml", "milliliter", "milliliters"):
        key, factor = "per_fl_oz", 1 / ML_IN_FL_OZ
    elif raw_unit in ("g", "gram", "grams"):
        key, factor = "per_oz", 1 / G_IN_OZ
    elif raw_unit in ("kg", "kilogram", "kilograms"):
        key, factor = "per_oz", KG_IN_OZ
    elif raw_unit in ("ct", "count", "pk", "pack"):
        key, factor = "per_ct", 1.0
    else:
        return None, None

    if qty <= 0:
        return None, None
    return round(price / (qty * factor), 4), key


if __name__ == "__main__":
    tests = [
        (2.89, "64 fl oz"),      # Aldi lactose-free milk -> per fl oz
        (6.89, "3 lb"),          # grapes -> per lb
        (2.29, "lb"),            # Meijer chicken, price already per lb
        (1.69, "0.5 gal"),       # half-gallon milk
        (6.00, "when you buy 3 or more"),  # should fail gracefully
        (3.49, "12 ct"),
        (5.99, "1 lb"),
        (4.29, "ea"),
    ]
    for p, u in tests:
        print(f"{p!r} / {u!r} -> {normalize(p, u)}")
