"""Strict same-session first-party price and fulfillment evidence.

This module supplies an explicit *contract*, not an assertion that Mariano's
currently emits this JSON structure. Only an authorized observed source trace
may qualify an adapter/response path for the real store.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from uuid import uuid4
from urllib.parse import urlparse
from .schema import price_text


class SourceContextError(ValueError):
    pass


def canonical_product_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme != "https" or p.hostname not in ("www.marianos.com", "marianos.com"):
        raise SourceContextError("product response is not a first-party HTTPS Mariano's URL")
    if not p.path.startswith("/p/"):
        raise SourceContextError("source response does not identify a product path")
    return p.path.rstrip("/")


@dataclass(frozen=True)
class BoundPrice:
    store_ref: str
    fulfillment: str
    product_path: str
    regular_price: str
    sale_price: str
    unpriced: bool
    upc: str
    response_path: str
    response_digest: str


class SourceResponseLedger:
    """Evidence from a configured approved same-session XHR/fetch response.

    Response content is *observed*, never separately fetched or synthesized.
    All contextual fields must be returned by the same source observation.
    """
    def __init__(self, store):
        self.store = store
        self.session_id = uuid4().hex
        self.events: dict[str, BoundPrice] = {}
        self.paths = tuple(store.price_response_paths)
        self._rejected: list[str] = []
        self.raw_response_count = 0

    def accepts_response_url(self, url: str) -> bool:
        p = urlparse(url)
        return (p.scheme == "https" and p.hostname in ("www.marianos.com", "marianos.com")
                and bool(self.paths)
                and any(p.path.startswith(prefix) for prefix in self.paths))

    def ingest(self, response_url: str, raw: dict) -> int:
        """Parse only the explicitly supported typed-first-party JSON v1.

        The production adapter must be checked against a real authorized
        response before use. Arbitrary JSON field names are never treated as
        store/price proof.
        """
        if not self.accepts_response_url(response_url):
            raise SourceContextError("response path is not an approved first-party price source")
        if not isinstance(raw, dict) or raw.get("schema") != "retailer-price-source-v1":
            raise SourceContextError("response does not match the explicitly configured typed price schema")
        store = raw.get("store")
        fulfillment = raw.get("fulfillment")
        products = raw.get("products")
        if not isinstance(store, dict) or not isinstance(fulfillment, dict) or not isinstance(products, list):
            raise SourceContextError("typed response missing store, fulfillment or products")
        division = str(store.get("division", ""))
        number = str(store.get("number", ""))
        if not (division.isdecimal() and number.isdecimal()):
            raise SourceContextError("returned source store division/number missing")
        observed_ref = f"{division}/{number}"
        observed_mode = str(fulfillment.get("mode", "")).upper()
        if observed_ref != self.store.source_store_ref or observed_mode != self.store.fulfillment_mode:
            raise SourceContextError(
                f"live source context mismatch: {observed_ref} {observed_mode} "
                f"vs configured authorized store/fulfillment"
            )
        response_digest=sha256(json.dumps(raw,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        response_path=urlparse(response_url).path
        accepted = 0
        for product in products:
            if not isinstance(product, dict):
                raise SourceContextError("typed product element must be an object")
            path = canonical_product_url(str(product.get("url", "")))
            # Each source price has an independent semantic role. Missing or
            # empty fields stay empty; an invalid non-empty value must not be
            # silently interpreted as an absent role or inferred from its peer.
            for field in ("regular_price", "sale_price"):
                raw_value = product.get(field, "")
                if raw_value is not None and str(raw_value).strip() and not price_text(raw_value):
                    raise SourceContextError(
                        f"invalid source {field}: cannot bind price role"
                    )
            regular = price_text(product.get("regular_price", ""))
            sale = price_text(product.get("sale_price", ""))
            unpriced = product.get("unpriced") is True
            if not regular and not sale and not unpriced:
                raise SourceContextError(f"product {path} has no actual price or explicit unpriced flag")
            upc = str(product.get("upc", "")).strip()
            if upc and (not upc.isdecimal() or not 8 <= len(upc) <= 14):
                raise SourceContextError("response UPC is not a real source identifier")
            bound = BoundPrice(observed_ref, observed_mode, path, regular, sale,
                               unpriced, upc, response_path, response_digest)
            if path in self.events:
                old=self.events[path]
                if old.store_ref!=bound.store_ref or old.fulfillment!=bound.fulfillment:
                    raise SourceContextError("fulfillment/store drift in source responses")
                # Current response supersedes older in this SAME session;
                # publication later verifies actual scraped source price.
            self.events[path] = bound
            accepted += 1
        self.raw_response_count += 1
        return accepted

    def mark_rejected(self, message: str) -> None:
        self._rejected.append(message[:240])

    def require_price(self, item: dict) -> BoundPrice:
        if self._rejected:
            raise SourceContextError("unresolved source binding errors: "+self._rejected[0])
        path = canonical_product_url(item.get("url", ""))
        price = self.events.get(path)
        if price is None:
            raise SourceContextError("no same-session first-party source-price response for product "+path)
        if price.store_ref != self.store.source_store_ref or price.fulfillment != self.store.fulfillment_mode:
            raise SourceContextError("source binding changed store/fulfillment")
        # A value-set comparison is unsafe: regular=3.00/sale=5.00 must
        # NEVER validate against source regular=5.00/sale=3.00. Check
        # every populated output slot only against the same source slot.
        # Never repair, swap, or infer values from the other price role.
        has_output_price = False
        for field in ("regular_price", "sale_price"):
            raw_value = item.get(field, "")
            if raw_value is None or str(raw_value).strip() == "":
                continue
            has_output_price = True
            observed = price_text(raw_value)
            if not observed:
                raise SourceContextError(f"invalid displayed {field}: not an explicit price")
            expected = getattr(price, field)
            if not expected:
                raise SourceContextError(
                    f"displayed {field} has no corresponding source {field} "
                    "(missing or blank); cannot infer its role"
                )
            if observed != expected:
                raise SourceContextError(
                    f"displayed product prices disagree with same-session price source: {field}"
                )
        if not has_output_price and not price.unpriced:
            raise SourceContextError("unpriced card lacks explicit source unpriced response")
        if item.get("upc") and price.upc and item["upc"]!=price.upc:
            raise SourceContextError("source UPC differs from product detail")
        return price

    def audit_unit(self, items: list[dict]) -> dict:
        if not items:
            raise SourceContextError("empty product set has no source-price proof")
        bindings = [self.require_price(item) for item in items]
        return {
            "verified": True,
            "source": "same-session first-party XHR/fetch observed, not independently fetched",
            "adapter": "retailer-price-source-v1",
            "browser_session_id": self.session_id,
            "observed_store_ref": self.store.source_store_ref,
            "observed_fulfillment": self.store.fulfillment_mode,
            "verified_product_count":len(bindings),
            "response_digest_samples":list(dict.fromkeys(
                b.response_digest for b in bindings))[:15],
            "response_paths":list(dict.fromkeys(
                b.response_path for b in bindings))[:15],
            "source_response_count": self.raw_response_count,
            "note": "Requires separately approved real retailer adapter and source trace",
        }
