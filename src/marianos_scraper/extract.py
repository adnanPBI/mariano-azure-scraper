"""Extract strictly observed product fields from an HTML product card or detail page.

No undocumented retailer API is called; promotion prices are accepted only when
explicitly displayed. DOM selectors are isolated so approved access can be
adapted as the retailer's layout evolves.
"""
from __future__ import annotations
import json
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag
from .promotions import apply_deals, DIGITAL, VOLUME
from .schema import APPROX_WEIGHT, private_label, price_text

BASE = "https://www.marianos.com"
PRICE_PATTERN = re.compile(r"\$\s*\d{1,5}(?:\.\d{1,2})?")
PPM_PATTERN = re.compile(r"\$\s*\d+(?:\.\d{1,3})?\s*/\s*(?:fl\.?\s*oz|fluid\s+ounces?|oz|lbs?|pounds?|cts?|count|each|ea|qt|gal|ml|l|g|kg)\b", re.I)
WEIGHT_PATTERN = re.compile(r"^(?:\d+(?:\.\d+)?\s*(?:fl\.?\s*oz|oz|lb|lbs|g|kg|ml|l|ct|count|pk|pack|gal|qt|each|ea))(?:\s*(?:[x×]\s*\d+(?:\.\d+)?\s*(?:oz|ml|ct))?)$", re.I)
UPC_PATTERN = re.compile(r"\bUPC\s*[:#]?\s*([0-9]{8,14})\b", re.I)
TITLE_SELECTORS = ('[data-testid*="product-name"]','[data-testid*="product-title"]','[itemprop="name"]','h3','h4','a[href*="/p/"]')
SIZE_SELECTORS = ('[data-testid*="product-size"]','[data-testid*="item-size"]','[class*="productSize"]','[class*="ProductSize"]','[itemprop="size"]')
REGULAR_PRICE_SELECTORS = ('[data-testid*="regular-price"]','[data-testid*="original-price"]','[aria-label*="Regular price"]','[class*="RegularPrice"]','[class*="OriginalPrice"]')
SALE_PRICE_SELECTORS = ('[data-testid*="sale-price"]','[data-testid*="promo-price"]','[aria-label*="Sale price"]','[class*="SalePrice"]')
CURRENT_PRICE_SELECTORS = ('[data-testid="price"]','[data-testid="product-price"]','[itemprop="price"]','[class*="ProductPrice"]')
OFFER_SELECTORS = ('[data-testid*="coupon"]','[data-testid*="promotion"]','[data-testid*="offer"]','[data-testid*="deal"]','[class*="Coupon"]','[class*="Promotion"]','[class*="Offer"]')

def _text(node: Tag | None) -> str:
    return " ".join(node.stripped_strings) if node else ""

def _first_text(root: Tag, selectors: tuple[str,...]) -> str:
    for selector in selectors:
        for node in root.select(selector):
            val = _text(node)
            if val:
                return val
    return ""

def _explicit_price(root: Tag, selectors: tuple[str,...]) -> str:
    for selector in selectors:
        for node in root.select(selector):
            text = _text(node)
            if PRICE_PATTERN.search(text):
                return price_text(PRICE_PATTERN.search(text).group(0))
            val = node.get("content")
            if val and price_text(val):
                return price_text(val)
    return ""

def _original_href(href: str) -> str:
    """Absolutize only, preserving path spelling, query, and image size params."""
    return urljoin(BASE, href.strip()) if href else ""

def _source_url_valid(url: str) -> bool:
    return bool(url and urlparse(url).hostname in ("marianos.com", "www.marianos.com") and urlparse(url).path.startswith("/p/"))

def _product_node_for_anchor(a: Tag) -> Tag:
    """Nearest product enclosing element, never a container holding sibling cards."""
    for parent in a.parents:
        if not isinstance(parent, Tag) or parent.name == "body":
            break
        attr = " ".join(map(str, parent.get("class") or [])) + " " + str(parent.get("data-testid", ""))
        is_card = bool(re.search(r"product.?card|product.?tile|product.?item|item.?card", attr, re.I)) or parent.name in ("article", "li")
        if is_card and len(parent.select('a[href*="/p/"]')) <= 3:
            return parent
    # Fallback to a bounded ancestor, avoids whole-page text contaminating fields.
    node = a
    for _ in range(3):
        if node.parent and isinstance(node.parent, Tag) and node.parent.name not in ("body", "main", "section") and len(node.parent.select('a[href*="/p/"]')) <= 2:
            node = node.parent
        else:
            break
    return node

def _observed_offers(root: Tag) -> list[tuple[str,str]]:
    offers=[]
    for selector in OFFER_SELECTORS:
        for node in root.select(selector):
            desc = _text(node)
            if not desc or (not DIGITAL.search(desc) and not VOLUME.search(desc)):
                continue
            # Dedicated labeled promotional-price nodes, if exposed.
            p = _explicit_price(node, ('[data-testid*="offer-price"]','[data-testid*="deal-price"]','[data-testid*="coupon-price"]'))
            if (desc, p) not in offers:
                offers.append((desc,p))
    if not offers:
        # Preserve sentence-like promotions even without a special DOM class.
        for text in root.stripped_strings:
            term = " ".join(text.split())
            if (DIGITAL.search(term) or VOLUME.search(term)) and len(term) <= 400:
                if (term, "") not in offers:
                    offers.append((term,""))
    return offers

def _observable_upc(root: Tag) -> str:
    for selector in ('[data-upc]','[itemprop="gtin"]','[itemprop="gtin13"]','[itemprop="gtin12"]','[itemprop="gtin14"]','[data-testid="upc"]'):
        n=root.select_one(selector)
        if n:
            val=n.get("data-upc") or n.get("content") or _text(n)
            if re.fullmatch(r"\d{8,14}", str(val).strip()):
                return str(val).strip()
    match=UPC_PATTERN.search(_text(root))
    return match.group(1) if match else ""

def _observable_weight(root: Tag) -> str:
    weight = _first_text(root,SIZE_SELECTORS)
    if weight:
        return weight
    for n in root.stripped_strings:
        if WEIGHT_PATTERN.fullmatch(n.strip()):
            return n.strip()
    return ""

def _ppm(root: Tag) -> str:
    for raw in root.stripped_strings:
        match=PPM_PATTERN.search(str(raw))
        if match:
            return match.group(0).strip()  # original displayed spelling and unit
    return ""

def extract_card(html: str, category: str, sub_category: str) -> dict | None:
    root = BeautifulSoup(html,"html.parser")
    a = root.select_one('a[href*="/p/"]')
    if not a:
        return None
    url = _original_href(str(a.get("href") or ""))
    if not _source_url_valid(url):
        return None
    title = _first_text(root,TITLE_SELECTORS) or str(a.get("aria-label") or "")
    if not title:
        return None
    weight = _observable_weight(root)
    if APPROX_WEIGHT.search(weight):
        return None
    img = root.select_one('img[src], img[data-src]')
    img_url = str((img.get("src") or img.get("data-src")) if img else "")
    image_url = _original_href(img_url) if img_url and not img_url.startswith("data:") else ""
    brand_node=root.select_one('[data-testid*="brand"], [itemprop="brand"]')
    brand=_text(brand_node)
    if not brand:
        title_lower=title.lower()
        for b in ("Kroger", "Private Selection", "Simple Truth", "Mariano's", "Home Chef", "Murray's"):
            if title_lower.startswith(b.lower()):
                brand=b;break
    regular=_explicit_price(root,REGULAR_PRICE_SELECTORS)
    sale=_explicit_price(root,SALE_PRICE_SELECTORS)
    if not regular and not sale:
        # Accept a single explicitly marked current price, never guess among promotions.
        regular=_explicit_price(root,CURRENT_PRICE_SELECTORS)
    return {
        "category":category,"sub_category":sub_category,"product_title":title,
        "weight":weight,"regular_price":regular,"sale_price":sale,
        "volume_deals_description":"","volume_deals_price":"",
        "digital_deals_description":"","digital_deals_price":"",
        "image_url":image_url,"url":url,"upc":_observable_upc(root),
        "ppm":_ppm(root),"store_brand":private_label(brand),
        "_offers":_observed_offers(root),
    }

def extract_cards(html: str, category: str, sub_category: str) -> list[dict]:
    root = BeautifulSoup(html,"html.parser")
    seen = set(); out=[]
    for a in root.select('a[href*="/p/"]'):
        url=_original_href(str(a.get("href") or ""))
        if not _source_url_valid(url) or url in seen:
            continue
        parent = _product_node_for_anchor(a)
        candidate = extract_card(str(parent),category,sub_category)
        if candidate:
            seen.add(candidate["url"]); out.append(candidate)
    return out

def _find_ld_products(value: object) -> list[dict]:
    if isinstance(value,list):
        return [p for item in value for p in _find_ld_products(item)]
    if not isinstance(value,dict):
        return []
    own=[]
    typ=value.get("@type", "")
    if typ == "Product" or (isinstance(typ,list) and "Product" in typ):
        own.append(value)
    for n in ("@graph", "mainEntity", "itemListElement"):
        if n in value:
            own.extend(_find_ld_products(value[n]))
    return own

def enrich_from_details(item: dict, html: str) -> dict:
    root=BeautifulSoup(html,"html.parser")
    for script in root.select('script[type="application/ld+json"]'):
        try:
            products=_find_ld_products(json.loads(script.string or script.get_text()))
        except (json.JSONDecodeError,TypeError,ValueError):
            continue
        for prod in products:
            for field in ("gtin12","gtin13","gtin14","gtin","upc"):
                if not item.get("upc") and re.fullmatch(r"\d{8,14}",str(prod.get(field,""))):
                    item["upc"]=str(prod[field]);break
    if not item.get("upc"):
        item["upc"]=_observable_upc(root)
    if not item.get("weight"):
        item["weight"]=_observable_weight(root)
    if not item.get("ppm"):
        item["ppm"]=_ppm(root)
    if not item.get("regular_price"):
        item["regular_price"]=_explicit_price(root,REGULAR_PRICE_SELECTORS)
    if not item.get("sale_price"):
        item["sale_price"]=_explicit_price(root,SALE_PRICE_SELECTORS)
    if not item.get("image_url"):
        img = root.select_one('main img[src],main img[data-src]')
        if img:
            item["image_url"]=_original_href(str(img.get("src") or img.get("data-src") or ""))
    offers=item.pop("_offers",[])
    offers.extend(_observed_offers(root))
    apply_deals(item, offers)
    if APPROX_WEIGHT.search(item.get("weight", "")):
        return {}  # genuine product exclusion
    return item

def finalize_card(item: dict) -> dict:
    out=dict(item)
    offers=out.pop("_offers",[])
    apply_deals(out, offers)
    return out