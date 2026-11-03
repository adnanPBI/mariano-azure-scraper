"""Conservative coupon-to-product source mapping.

Only a first-party coupon tile with an explicit source coupon/offer ID,
clipping/activation condition, and directly linked /p/ product URLs can be
qualified. Coupons with opaque product membership fail closed.
No coupon ID or product identity is inferred from a marketing heading.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from .promotions import DIGITAL

BASE = "https://www.marianos.com"
SELECTOR = (
    '[data-coupon-id], [data-offer-id], '
    '[data-testid="coupon-card"], [data-testid="coupon-tile"], '
    '[data-testid="CouponCard"], article[class*="coupon-card"], '
    'article[class*="CouponCard"]'
)

@dataclass(frozen=True)
class MappedCoupon:
    identity: str
    product_urls: tuple[str, ...]
    terms: str

@dataclass(frozen=True)
class CouponScan:
    identities: tuple[str, ...]
    mappings: tuple[MappedCoupon, ...]
    unresolved: tuple[str, ...]


def scan_coupon_cards(html: str) -> CouponScan:
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(SELECTOR)
    top_level = []
    selected = set(map(id, containers))
    for node in containers:
        if not any(id(p) in selected for p in node.parents):
            top_level.append(node)
    identity_seen = set()
    maps = []
    unresolved = []
    identities = []
    for index, node in enumerate(top_level, 1):
        identity = (
            node.get("data-coupon-id") or node.get("data-offer-id")
            or node.get("data-testid-id")
            or node.get("id") or ""
        )
        identity = str(identity).strip()
        label = identity or f"tile-{index}-missing-source-id"
        if label in identity_seen:
            unresolved.append(f"{label}: duplicate coupon identity")
            continue
        identity_seen.add(label)
        identities.append(label)
        # Product anchors identify eligibility; they are not the offer text.
        from bs4 import BeautifulSoup as _Soup
        text_root=_Soup(str(node),"html.parser")
        for product_link in text_root.select('a[href*="/p/"]'):
            product_link.decompose()
        terms = " ".join(text_root.stripped_strings).strip()
        products = []
        for a in node.select('a[href*="/p/"]'):
            href = a.get("href", "")
            url = urljoin(BASE, str(href))
            parsed = urlparse(url)
            if parsed.scheme == "https" and parsed.hostname in ("www.marianos.com", "marianos.com") and parsed.path.startswith("/p/"):
                if url not in products:
                    products.append(url)
        reasons = []
        if not identity:
            reasons.append("no stable first-party coupon ID")
        if not DIGITAL.search(terms):
            reasons.append("no explicit clipping or activation terms")
        if not products:
            reasons.append("no explicit first-party product link")
        if reasons:
            unresolved.append(label + ": " + "; ".join(reasons))
        else:
            maps.append(MappedCoupon(identity, tuple(products), terms))
    return CouponScan(tuple(identities), tuple(maps), tuple(unresolved))