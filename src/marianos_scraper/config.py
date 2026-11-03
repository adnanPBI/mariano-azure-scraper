"""Parse the client-owned URL manifest and store settings without editing crawler code."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import os
from urllib.parse import urlparse
import csv
import yaml

@dataclass(frozen=True)
class Category:
    name: str
    url: str
    scope: str = ""

@dataclass(frozen=True)
class Store:
    id: str
    zipcode: str
    name: str
    address: str
    verification_text: str
    logo_url: str = ""
    canary_urls: list[str] = field(default_factory=list)
    source_store_ref: str = ""  # e.g. 531/00502, MUST match returned source
    fulfillment_mode: str = ""  # e.g. PICKUP; must be returned by source
    price_response_paths: list[str] = field(default_factory=list)  # observed authorized XHR routes

@dataclass(frozen=True)
class Options:
    max_listing_scrolls: int = 125
    max_listing_pages: int = 800
    max_subcategory_depth: int = 12
    min_records_per_store: int = 500
    min_per_category: int = 1
    prior_yield_ratio: float = .65
    prior_category_ratio: float = .50
    min_subcategory_retention: float = .65
    max_detail_pages: int = 0
    timeout_ms: int = 35000
    delay_seconds: float = 1.5
    verify_every: int = 20
    category_hard_limit: int = 1500
    browser_headless: bool = True
    # CSS selectors are configurable; if no store proof is detected, stop (no loose matching).
    store_selector_button: str = 'button:has-text("Pickup"), button:has-text("Store")'
    store_search_input: str = 'input[placeholder*="ZIP"], input[placeholder*="City"], input[placeholder*="zip"]'
    store_result_selector: str = 'button:has-text("Shop This Store"), button:has-text("Select This Store")'
    store_proof_selector: str = 'header, [data-testid="store-location"], [aria-label*="Pickup at"]'

def require_source_context_config(store: Store) -> None:
    """Production browser route cannot start using a configured label as proof."""
    import re
    if not re.fullmatch(r"[0-9]{2,5}/[0-9]{3,8}", store.source_store_ref or ""):
        raise ValueError("real source division/store reference must be configured from authoritative evidence")
    if store.fulfillment_mode not in ("PICKUP", "IN_STORE", "DELIVERY"):
        raise ValueError("real product-pricing fulfillment mode must be configured")
    if (not store.price_response_paths
        or any(not p.startswith("/") or "?" in p or ".." in p for p in store.price_response_paths)):
        raise ValueError("approved first-party price response path(s) require live source qualification")


def load_categories(path: str) -> list[Category]:
    with Path(path).open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        needed = {"Retailer", "Category (Auto)", "URL", "Scope"}
        if not needed <= set(reader.fieldnames or []):
            raise ValueError(f"category CSV missing {needed - set(reader.fieldnames or [])}")
        rows = [Category(r["Category (Auto)"].strip(), r["URL"].strip(), r["Scope"].strip()) for r in reader if "Mariano" in r["Retailer"]]
    if not rows or len(set(c.name for c in rows)) != len(rows):
        raise ValueError("category manifest missing or duplicate names")
    if any(urlparse(c.url).hostname != "www.marianos.com" for c in rows):
        raise ValueError("unexpected domain in category manifest")
    return rows

def load_settings(path: str) -> tuple[list[Store],Options]:
    if path.startswith("blob:"):
        from azure.storage.blob import BlobServiceClient
        from azure.identity import DefaultAzureCredential
        account=os.environ.get("AZURE_STORAGE_ACCOUNT")
        if not account:
            raise ValueError("AZURE_STORAGE_ACCOUNT required for blob config")
        connection=os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        client=(BlobServiceClient.from_connection_string(connection) if connection else
                BlobServiceClient(f"https://{account}.blob.core.windows.net",credential=DefaultAzureCredential()))
        cn=os.environ.get("AZURE_STORAGE_CONTAINER","marianos-crawls")
        raw=client.get_container_client(cn).download_blob(path[5:]).readall().decode("utf-8")
    else:
        raw=Path(path).read_text(encoding="utf-8")
    obj = yaml.safe_load(raw) or {}
    stores = [Store(**s) for s in obj.get("stores", [])]
    if not stores or len({s.id for s in stores}) != len(stores):
        raise ValueError("configure at least one uniquely identified Mariano's store")
    for s in stores:
        if not s.id or not s.zipcode or not s.name or not s.address or not s.verification_text:
            raise ValueError("each store needs id, zip, name, address, unique verification_text")
        if not all(c.isalnum() or c in ("-", "_") for c in s.id):
            raise ValueError("store id must be URL-safe")
        if len(s.verification_text) < 6:
            raise ValueError("verification_text must identify a specific store")
        if any("REPLACE" in v.upper() or "YOUR_" in v.upper() for v in (s.id,s.zipcode,s.address,s.verification_text)):
            raise ValueError("placeholder store settings must be replaced with verified values")
    options=Options(**obj.get("options", {}))
    if (options.max_listing_scrolls<6 or not (1 <= options.max_listing_pages <= 3000)
            or options.max_detail_pages<0
            or options.verify_every<1 or not (0 <= options.max_subcategory_depth <= 24)):
        raise ValueError("invalid scroll, detail or location-verification limits")
    if options.min_records_per_store<1 or options.min_per_category<1:
        raise ValueError("minimum yield and category requirements must be positive")
    for ratio in (options.prior_yield_ratio,options.prior_category_ratio,options.min_subcategory_retention):
        if not 0<ratio<=1:
            raise ValueError("yield comparison ratios must be in (0,1]")
    return stores,options