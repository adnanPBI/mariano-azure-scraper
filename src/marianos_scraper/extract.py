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
            if DIGITAL.search(term) or VOLUME.search(term):
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

def approximate_excluded_urls(html: str) -> set[str]:
    """Evidence: which observed /p/ cards were excluded for source approx weight.

    A missing name, price or unknown card shape is NOT a justified exclusion.
    The caller must reconcile other observed links to actual parsed cards.
    """
    soup = BeautifulSoup(html, "html.parser")
    result = set()
    for a in soup.select('main a[href*="/p/"]'):
        url = _original_href(str(a.get("href") or "")).split("?", 1)[0]
        if not _source_url_valid(url):
            continue
        node = _product_node_for_anchor(a)
        if APPROX_WEIGHT.search(_observable_weight(node)):
            result.add(url)
    return result


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

class DetailIdentityError(ValueError):
    pass


def _source_product_path(value: str) -> str:
    parsed=urlparse(_original_href(value))
    if parsed.hostname not in ("www.marianos.com","marianos.com"):
        raise DetailIdentityError("detail source identity is not first-party")
    if not parsed.path.startswith("/p/"):
        raise DetailIdentityError("detail page is not a product URL")
    return parsed.path.rstrip("/")


def extract_detail_fields(html: str, expected_url: str) -> dict:
    """Extract only the requested product's canonical and scoped primary PDP.

    JSON-LD products for recommendations are *never* accepted without an
    exact URL match. Products and offers outside the primary PDP container
    cannot supply UPC/size/PPM/price for this product.
    """
    root=BeautifulSoup(html,"html.parser")
    expected_path=_source_product_path(expected_url)
    canonical=root.select_one('link[rel="canonical"][href]')
    canonical_path=""
    if canonical:
        canonical_path=_source_product_path(str(canonical.get("href","")))
        if canonical_path!=expected_path:
            raise DetailIdentityError("canonical detail product differs from requested URL")
    main=root.select_one("main")
    if main is None:
        raise DetailIdentityError("no primary product content")
    # Prefer explicit product-bound DOM regions. If absent, require a
    # matching canonical and exactly one primary h1 in main. Recommendations
    # are stripped from the cloned main DOM before field extraction.
    scope=main.select_one(
        '[data-testid="product-details"],[data-testid="product-info"],'
        '[data-testid="pdp-product"],[data-product-url],'
        'article[data-product-id]'
    )
    if scope:
        scope_url=str(scope.get("data-product-url") or "")
        scope_id=str(scope.get("data-product-id") or "")
        if scope_url and _source_product_path(scope_url)!=expected_path:
            raise DetailIdentityError("product data region identifies an unrelated URL")
        if scope_id and scope_id!=expected_path.rsplit("/",1)[-1]:
            raise DetailIdentityError("product region identifier mismatches requested product")
        if not canonical and not (scope_url or scope_id):
            raise DetailIdentityError("unbound detail container without canonical proof")
    elif not canonical_path or len(main.select("h1"))!=1:
        raise DetailIdentityError("cannot bind primary detail content to requested product")
    primary=BeautifulSoup(str(scope or main),"html.parser")
    for unwanted in primary.select(
        '[data-testid*="recommend"],[data-testid*="related"],'
        '[class*="recommend"],[class*="Recommend"],[class*="related"],'
        '[class*="Related"],[aria-label*="Recommended"],'
        '[aria-label*="Related"],[data-testid*="carousel"],'
        'section[aria-label*="You May Also"]'
    ):
        unwanted.decompose()
    ld_matches=[]
    for script in root.select('script[type="application/ld+json"]'):
        try:
            products=_find_ld_products(json.loads(script.string or script.get_text()))
        except (json.JSONDecodeError,TypeError,ValueError):
            continue
        for prod in products:
            candidates=[prod.get("url"),prod.get("@id")]
            identity_ok=False
            for raw in candidates:
                if not isinstance(raw,str) or not raw:
                    continue
                try:
                    if _source_product_path(raw)==expected_path:
                        identity_ok=True
                except DetailIdentityError:
                    pass
            if identity_ok:
                ld_matches.append(prod)
    if len(ld_matches)>1:
        upcs={str(p.get("gtin13") or p.get("gtin12") or p.get("upc") or "")
              for p in ld_matches}
        if len(upcs)>1:
            raise DetailIdentityError("contradictory canonical Product JSON-LD identities")
    upc=_observable_upc(primary)
    for product in ld_matches:
        for key in ("gtin12","gtin13","gtin14","gtin","upc"):
            val=str(product.get(key,""))
            if re.fullmatch(r"\d{8,14}",val):
                if upc and upc!=val:
                    raise DetailIdentityError("canonical Product JSON-LD UPC disagrees with primary DOM")
                upc=val
                break
    img=primary.select_one("img[src],img[data-src]")
    title=_first_text(primary,('h1','[data-testid*="product-name"]','[data-testid*="product-title"]'))
    if not title:
        raise DetailIdentityError("primary detail product name missing")
    patch={
        "product_title":title,
        "weight":_observable_weight(primary),
        "regular_price":_explicit_price(primary,REGULAR_PRICE_SELECTORS)
            or _explicit_price(primary,CURRENT_PRICE_SELECTORS),
        "sale_price":_explicit_price(primary,SALE_PRICE_SELECTORS),
        "upc":upc,
        "ppm":_ppm(primary),
        "image_url":_original_href(str(img.get("src") or img.get("data-src") or "")) if img else "",
        "_offers":_observed_offers(primary),
        "_detail_bound_path":expected_path,
    }
    if APPROX_WEIGHT.search(patch["weight"]):
        return {"_excluded_approx_weight":True,"_detail_bound_path":expected_path}
    return patch


def apply_detail_fields(item: dict, patch: dict) -> dict:
    if patch.get("_excluded_approx_weight"):
        return {}
    if _source_product_path(item.get("url",""))!=patch.get("_detail_bound_path"):
        raise DetailIdentityError("cached detail belongs to another product")
    result=dict(item)
    # Fresh, correctly bound detail values replace stale partial-card fields.
    # Only missing detail fields retain values observed in this fresh listing.
    for field in ("product_title","weight","regular_price","sale_price","upc","ppm","image_url"):
        val=patch.get(field,"")
        if val:
            if field=="upc" and result.get("upc") and result["upc"]!=val:
                raise DetailIdentityError("listing UPC and scoped detail UPC disagree")
            result[field]=val
    offers=list(result.pop("_offers",[]))
    for offer in patch.get("_offers",[]):
        if offer not in offers:
            offers.append(offer)
    apply_deals(result, offers)
    if APPROX_WEIGHT.search(result.get("weight","")):
        return {}
    return result


def enrich_from_details(item: dict, html: str) -> dict:
    """Backward-compatible, identity-strict facade for detail enrichment."""
    return apply_detail_fields(item,extract_detail_fields(html,item["url"]))

def finalize_card(item: dict) -> dict:
    out=dict(item)
    offers=out.pop("_offers",[])
    apply_deals(out, offers)
    return out