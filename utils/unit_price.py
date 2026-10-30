"""Unit-price normalization + cross-unit display conversion.

Canonical families (comparison ONLY within a family):
- weight: base per_oz   (aliases: per_lb, per_g, per_kg)
- volume: base per_fl_oz (aliases: per_gal, per_pt, per_qt, per_l, per_ml)
- count: base per_ct   (aliases: per_ea, per_dozen)

Not convertible: weight <-> volume (needs product density), count <-> anything.
"""
import re

OZ_PER_LB = 16.0
G_PER_OZ = 28.3495
OZ_PER_KG = 35.274
FL_OZ_PER_GAL = 128.0
FL_OZ_PER_QT = 32.0
FL_OZ_PER_PT = 16.0
ML_PER_FL_OZ = 29.5735
FL_OZ_PER_L = 33.814

# canonical_key -> family
FAMILIES = {
    "per_oz": "weight", "per_lb": "weight", "per_g": "weight", "per_kg": "weight",
    "per_fl_oz": "volume", "per_gal": "volume", "per_qt": "volume",
    "per_pt": "volume", "per_l": "volume", "per_ml": "volume",
    "per_ct": "count", "per_ea": "count",
}

# conversion factor: 1 canonical-unit -> base units (weight->oz, volume->fl oz, count->ct)
TO_BASE = {
    "per_oz": 1.0, "per_lb": OZ_PER_LB, "per_g": 1 / G_PER_OZ,
    "per_kg": OZ_PER_KG,
    "per_fl_oz": 1.0, "per_gal": FL_OZ_PER_GAL, "per_qt": FL_OZ_PER_QT,
    "per_pt": FL_OZ_PER_PT, "per_l": FL_OZ_PER_L, "per_ml": 1 / ML_PER_FL_OZ,
    "per_ct": 1.0, "per_ea": 1.0,
}

SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(fl\.?\s*oz|fluid ounces?|floz|oz|ounces?|ounce|"
    r"lbs?|pounds?|gal|gallons?|qt|quarts?|pt|pints?|"
    r"l\b|liters?|litres?|ml|milliliters?|"
    r"g\b|grams?|kg|kilograms?|"
    r"ct|count|pk|pack)\b",
    re.I,
)

SIZE_UNIT_CANON = {
    "oz": "per_oz", "ounce": "per_oz", "ounces": "per_oz",
    "lb": "per_lb", "lbs": "per_lb", "pound": "per_lb", "pounds": "per_lb",
    "g": "per_g", "gram": "per_g", "grams": "per_g",
    "kg": "per_kg", "kilogram": "per_kg", "kilograms": "per_kg",
    "fl oz": "per_fl_oz", "floz": "per_fl_oz",
    "fluid ounce": "per_fl_oz", "fluid ounces": "per_fl_oz",
    "gal": "per_gal", "gallon": "per_gal", "gallons": "per_gal",
    "qt": "per_qt", "quart": "per_qt", "quarts": "per_qt",
    "pt": "per_pt", "pint": "per_pt", "pints": "per_pt",
    "l": "per_l", "liter": "per_l", "liters": "per_l",
    "litre": "per_l", "litres": "per_l",
    "ml": "per_ml", "milliliter": "per_ml", "milliliters": "per_ml",
    "ct": "per_ct", "count": "per_ct", "pk": "per_ct", "pack": "per_ct",
}


def normalize(price, unit):
    """Return (unit_price_in_base, canonical_key) or (None, None).

    - Rate units ('lb', 'ea'): price is already per that unit -> convert to base.
    - Size units ('64 fl oz', '3 lb'): unit_price = price / qty -> convert to base.
    """
    if price is None or not unit:
        return None, None
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None, None
    u = str(unit).strip().lower().rstrip(".").strip()

    # Rate units
    if u in ("lb", "lbs", "pound", "pounds"):
        return round(price, 4), "per_lb"
    if u in ("ea", "each"):
        return round(price, 4), "per_ea"

    # Size units
    m = SIZE_RE.search(str(unit))
    if not m:
        return None, None
    qty = float(m.group(1))
    raw = m.group(2).lower().strip()
    if raw.startswith("fl"):
        raw = "fl oz"
    canon = SIZE_UNIT_CANON.get(raw)
    if not canon or qty <= 0:
        return None, None
    return round(price / qty, 4), canon


def convert(unit_price, from_key, to_key):
    """Convert a per-unit price between units in the same family.

    Returns the converted value or None (different families / unknown keys).
    """
    if unit_price is None or not from_key or not to_key:
        return None
    f_fam, t_fam = FAMILIES.get(from_key), FAMILIES.get(to_key)
    if not f_fam or not t_fam or f_fam != t_fam:
        return None
    per_base = unit_price / TO_BASE[from_key]   # value per base unit (oz / fl oz / ct)
    out = per_base * TO_BASE[to_key]            # value per target unit
    return round(out, 4)


# Human-friendly default display: weight -> per lb, volume -> per gal
PREFERRED_DISPLAY = {"weight": "per_lb", "volume": "per_gal", "count": "per_ct"}
DISPLAY_LABEL = {
    "per_oz": "$/oz", "per_lb": "$/lb", "per_g": "$/g", "per_kg": "$/kg",
    "per_fl_oz": "$/fl oz", "per_gal": "$/gal", "per_qt": "$/qt",
    "per_pt": "$/pt", "per_l": "$/L", "per_ml": "$/ml",
    "per_ct": "$/ct", "per_ea": "$/ea",
}


def display(unit_price, canonical_key):
    """Return (display_value, label) using preferred human units."""
    if unit_price is None or not canonical_key:
        return None, None
    fam = FAMILIES.get(canonical_key)
    target = PREFERRED_DISPLAY.get(fam)
    if not target:
        return None, None
    val = convert(unit_price, canonical_key, target)
    return val, DISPLAY_LABEL[target]


if __name__ == "__main__":
    tests = [
        (2.99, "per_oz", "per_lb"),   # 47.84
        (2.29, "per_lb", "per_oz"),    # 0.143
        (0.0452, "per_fl_oz", "per_gal"),  # 5.79
        (1.69, "0.5 gal"),            # normalize -> per_gal 3.38
        (2.29, "lb"),
        (6.89, "3 lb"),
    ]
    print("convert(2.99/oz -> /lb) =", convert(2.99, "per_oz", "per_lb"))
    print("convert(0.0452/fl oz -> /gal) =", convert(0.0452, "per_fl_oz", "per_gal"))
    print("convert weight->volume (should be None) =", convert(1.0, "per_oz", "per_gal"))
    for p, u in tests[3:]:
        print(f"normalize({p}, {u!r}) =", normalize(p, u))
    up, ck = normalize(1.69, "0.5 gal")
    print("display(1.69/0.5gal) =", display(up, ck))
