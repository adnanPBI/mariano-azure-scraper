"""Only retailer-DISPLAYED promotional prices, no arithmetic or inferred final prices."""
from __future__ import annotations
import re
from dataclasses import dataclass
from .schema import price_text

DIGITAL = re.compile(r"\b(?:digital\s+coupon|clip(?:ped|ping)?\s+(?:a\s+)?coupon|coupon\s+to\s+card|with\s+(?:a\s+)?(?:clipped|digital)\s+coupon|activate\s+(?:this\s+)?(?:offer|coupon)|add\s+(?:to\s+card|coupon))\b", re.I)
VOLUME = re.compile(r"\b(?:\d+\s+for\s+\$\s*\d|buy\s+\d+\s*[,;&]?\s*get\s+\d+|bogo|mix\s*(?:or|&)\s*match|must\s+buy\s+\d+|save\s+\$\s*\d+(?:\.\d+)?\s+when\s+you\s+buy\s+\d+|\d+\s+or\s+more\b)\b", re.I)
# Only explicit final deal price labels are accepted. 'Save $1' isn't a final price.
EXPLICIT_EACH = re.compile(r"(?:\$\s*(\d+(?:\.\d{1,2})?)\s*(?:each|ea\.?|apiece)\b|\b(?:your\s+price|for\s+only|pay)\s*\$\s*(\d+(?:\.\d{1,2})?))", re.I)
EXPLICIT_BUNDLE = re.compile(r"\b\d+\s+for\s+\$\s*(\d+(?:\.\d{1,2})?)\b", re.I)

@dataclass(frozen=True)
class Deal:
    kind: str  # digital | volume | other
    description: str
    displayed_price: str

def classify(description: str, displayed_price: str = "") -> Deal:
    text = " ".join(str(description).split())
    kind = "digital" if DIGITAL.search(text) else "volume" if VOLUME.search(text) else "other"
    if kind == "other":
        return Deal("other", text, "")
    price = price_text(displayed_price)
    if not price:
        found = EXPLICIT_EACH.search(text)
        if found:
            price = price_text(next(g for g in found.groups() if g))
        elif kind == "volume":
            # '2 for $5' is an explicit displayed BUNDLE price. Not per-item arithmetic.
            found = EXPLICIT_BUNDLE.search(text)
            if found:
                price = price_text(found.group(1))
    return Deal(kind, text, price)

def apply_deals(item: dict, offers: list[tuple[str,str]]) -> None:
    for full_description, explicit_price in offers:
        deal = classify(full_description, explicit_price)
        if deal.kind == "other":
            continue
        dkey = "digital_deals_description" if deal.kind == "digital" else "volume_deals_description"
        pkey = "digital_deals_price" if deal.kind == "digital" else "volume_deals_price"
        if deal.description not in item.get(dkey, ""):
            item[dkey] = (item.get(dkey, "") + " | " + deal.description).strip(" |")
        if deal.displayed_price:
            if item.get(pkey, "") and item[pkey] != deal.displayed_price:
                raise ValueError(f"conflicting explicit {deal.kind} prices")
            item[pkey] = deal.displayed_price