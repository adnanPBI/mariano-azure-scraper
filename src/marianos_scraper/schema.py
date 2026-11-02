"""Frozen export contract. Deliberately strict: no inferred UPC/GUPC/PPM."""
from __future__ import annotations
import re
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

FIELDS = (
    "zipcode", "store_name", "store_location", "store_logo", "store_brand",
    "category", "sub_category", "product_title", "weight", "regular_price",
    "sale_price", "volume_deals_description", "volume_deals_price",
    "digital_deals_description", "digital_deals_price", "image_url", "url",
    "upc", "gupc", "ppm", "unit_price", "crawl_date",
)
PRICE_FIELDS = ("regular_price", "sale_price", "volume_deals_price", "digital_deals_price")
APPROX_WEIGHT = re.compile(r"\b(?:approx(?:imately)?\.?|about|estimated|est\.?\s*wt|variable\s*weight|avg\.?\s*(?:wt|weight))\b", re.I)
PRIVATE_BRANDS = {"mariano's", "marianos", "kroger", "private selection", "simple truth", "simple truth organic", "p$$t", "comforts", "heritage farm", "homestyle", "home chef", "murray's"}
PRICE_RE = re.compile(r"^\$?\s*(?:\d{1,5})(?:\.\d{1,2})?$")

class RecordError(ValueError):
    pass

def price_text(value: object) -> str:
    if value is None or str(value).strip() == "":
        return ""
    text = str(value).strip().replace(",", "")
    if not PRICE_RE.fullmatch(text):
        return ""  # never derive from percentage-off, BOGO, or an ambiguous snippet
    try:
        amount = Decimal(text.lstrip("$").strip())
        return f"{amount:.2f}"
    except InvalidOperation:
        return ""

def private_label(brand: str) -> str:
    b = re.sub(r"[®™]", "", brand or "").strip().lower()
    return "yes" if b in PRIVATE_BRANDS or b.startswith("kroger ") else "no"

def record(values: dict, crawl_date: str) -> OrderedDict:
    if not isinstance(values, dict):
        raise RecordError("record must be an object")
    out = OrderedDict((k, "" if values.get(k) is None else str(values.get(k)).strip()) for k in FIELDS)
    for key in PRICE_FIELDS:
        out[key] = price_text(out[key])
    out["gupc"] = ""  # in all circumstances
    out["unit_price"] = ""  # downstream responsibility
    out["crawl_date"] = crawl_date
    if out["store_brand"] not in ("yes", "no"):
        out["store_brand"] = "no"
    return out

def validate(item: dict) -> None:
    if list(item.keys()) != list(FIELDS):
        raise RecordError("field order or names differ from contract")
    if any(not isinstance(v, str) for v in item.values()):
        raise RecordError("all values must be strings, never null")
    if item["gupc"] or item["unit_price"]:
        raise RecordError("gupc and unit_price must be blank")
    if item["weight"] and APPROX_WEIGHT.search(item["weight"]):
        raise RecordError("approximate-weight product must be excluded")
    if not item["product_title"] or not item["url"]:
        raise RecordError("missing product title or product URL")
    if not item["category"] or not item["crawl_date"]:
        raise RecordError("missing category or date")
    if not item["zipcode"] or not item["store_location"]:
        raise RecordError("missing verified location")
    for key in PRICE_FIELDS:
        if item[key] and not re.fullmatch(r"\d+\.\d{2}", item[key]):
            raise RecordError(f"malformed {key}")
    for key in ("url", "image_url"):
        if item[key] and urlparse(item[key]).scheme not in ("https", "http"):
            raise RecordError(f"invalid {key}")

def fingerprint(item: dict) -> str:
    # Dedup at store level, not globally. UPC is authoritative if available.
    return item["upc"] if item["upc"] else item["url"].split("?", 1)[0]