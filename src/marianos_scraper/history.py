"""Immutable historical catalog union: no deletion or inferred live availability.

The 22-field retailer JSON remains unchanged. Genuine first/last observation
dates, fresh-vs-carried state and historical prices live in a sidecar.
"""
from __future__ import annotations

from collections import OrderedDict, Counter, defaultdict
from datetime import date
from hashlib import sha256
import json
from urllib.parse import urlparse
from .schema import FIELDS, validate, record


class HistoryConflict(ValueError):
    pass


def identity_tokens(item: dict) -> tuple[str, ...]:
    url = item.get("url", "").split("?", 1)[0].rstrip("/")
    parsed = urlparse(url)
    if parsed.hostname not in ("www.marianos.com", "marianos.com") or not parsed.path.startswith("/p/"):
        raise HistoryConflict("product source URL is not a first-party Mariano's /p/ identity")
    keys = ["url:" + url]
    upc = item.get("upc", "")
    if upc:
        if not upc.isdecimal() or not 8 <= len(upc) <= 14:
            raise HistoryConflict("non-genuine UPC identifier")
        keys.append("upc:" + upc)
    return tuple(keys)


def _merge_promos(old: dict, new: dict) -> None:
    for kind in ("volume", "digital"):
        dkey = kind + "_deals_description"
        pkey = kind + "_deals_price"
        clauses = []
        for source in (old, new):
            for part in source.get(dkey, "").split(" | "):
                part = part.strip()
                if part and part not in clauses:
                    clauses.append(part)
        old[dkey] = " | ".join(clauses)
        a, b = old.get(pkey, ""), new.get(pkey, "")
        if a and b and a != b:
            raise HistoryConflict(f"conflicting same-slot {kind} promotional prices")
        old[pkey] = b or a


def merge_same_run(existing: dict, incoming: dict) -> dict:
    """Merge exact same-product same-slot observations, never a previous run."""
    if existing.get("upc") and incoming.get("upc") and existing["upc"] != incoming["upc"]:
        raise HistoryConflict("UPC identity drift for an observed product URL")
    old = dict(existing)
    new = dict(incoming)
    # Preserve primary catalog category: coupon placement is provenance, not
    # a second invented product. The caller records source coverage separately.
    if old["category"] == "Coupons" and new["category"] != "Coupons":
        old["category"], old["sub_category"] = new["category"], new["sub_category"]
    for field in ("zipcode", "store_location"):
        if old[field] != new[field]:
            raise HistoryConflict("store context mismatch within same-slot product observations")
    for field in ("regular_price", "sale_price"):
        a, b = old.get(field, ""), new.get(field, "")
        if a and b and a != b:
            raise HistoryConflict(f"contradictory same-slot {field} for {old['url']}")
        old[field] = b or a
    for field in ("product_title", "weight", "upc", "ppm", "image_url", "store_logo"):
        a, b = old.get(field, ""), new.get(field, "")
        if not a and b:
            old[field] = b
        elif a and b and field in ("upc", "ppm") and a != b:
            raise HistoryConflict(f"conflicting same-slot {field}")
    _merge_promos(old, new)
    # Existing product URL is authoritative for stable product identity.
    result = record(old, old["crawl_date"])
    validate(result)
    return result


def consolidate_fresh(items: list[dict]) -> tuple[list[dict], dict]:
    result: OrderedDict[str, dict] = OrderedDict()
    index: dict[str, str] = {}
    categories: dict[str, set[str]] = defaultdict(set)
    duplicates = 0
    for item in items:
        validate(item)
        keys = identity_tokens(item)
        hits = {index[token] for token in keys if token in index}
        if len(hits) > 1:
            raise HistoryConflict("multiple distinct products claimed the same UPC/URL")
        current = next(iter(hits)) if hits else keys[0]
        if hits:
            duplicates += 1
            old = result[current]
            result[current] = merge_same_run(old, item)
        else:
            result[current] = item
        categories[current].add(item["category"])
        # Index both URL and UPC tokens after enrichment.
        for token in identity_tokens(result[current]) + keys:
            if token in index and index[token] != current:
                raise HistoryConflict("ambiguous product aliases")
            index[token] = current
    evidence = {
        "fresh_duplicates_consolidated": duplicates,
        "source_categories_by_product": {
            key: sorted(v) for key, v in categories.items()
        },
        "source_category_unique_products": dict(Counter(
            name for names in categories.values() for name in names
        )),
    }
    return list(result.values()), evidence


def _validate_previous(storage, manifest: dict, store) -> tuple[list[dict], dict]:
    if not manifest:
        return [], {}
    if manifest.get("status") != "passed" or manifest.get("published") is not True:
        raise HistoryConflict("last-good pointer is not a completed qualified publication")
    if (manifest.get("store_id") != store.id
            or manifest.get("zipcode") != store.zipcode
            or manifest.get("address") != store.address):
        raise HistoryConflict("previous export belongs to a different store/location")
    key = manifest.get("dataset_key", "")
    if not key.startswith(f"exports/{store.id}/") or not key.endswith(".json"):
        raise HistoryConflict("unsafe or missing previous dataset key")
    old = storage.get_json(key)
    if not isinstance(old, list) or not old:
        raise HistoryConflict("previous successful dataset cannot be loaded; do not delete history")
    payload = json.dumps(old, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if sha256(payload).hexdigest() != manifest.get("sha256"):
        raise HistoryConflict("previous successful dataset hash mismatch; no publication")
    for row in old:
        validate(row)
        if row["zipcode"] != store.zipcode or row["store_location"] != store.address:
            raise HistoryConflict("historical product location drift")
    # Original v0.5.0 exports predate history sidecars. In that case the
    # observed crawl_date is the earliest documented observation date.
    metadata = {}
    if manifest.get("history_key"):
        metadata = storage.get_json(manifest["history_key"])
        if not isinstance(metadata, dict) or metadata.get("dataset_sha256") != manifest["sha256"]:
            raise HistoryConflict("historical lineage sidecar absent/invalid")
    return old, metadata.get("records", {})


def retain_forever(storage, previous: dict | None, store, fresh: list[dict],
                   observed_at: str) -> tuple[list[dict], dict, dict]:
    """Return union with previous real products and an immutable lineage sidecar."""
    if not fresh:
        raise HistoryConflict("no fresh source records; cannot publish all-carried dataset")
    date.fromisoformat(observed_at)
    previous_rows, previous_lineage = _validate_previous(storage, previous, store)
    prior_index: dict[str, dict] = {}
    prior_lineage_by_id: dict[str, dict] = {}
    for row in previous_rows:
        keys = identity_tokens(row)
        meta = next((previous_lineage[k] for k in keys if k in previous_lineage), None)
        if meta is None:
            meta = {"first_seen": row["crawl_date"], "last_seen": row["crawl_date"],
                    "state": "previously_observed"}
        for token in keys:
            if token in prior_index and prior_index[token] is not row:
                raise HistoryConflict("previous dataset has colliding authentic identities")
            prior_index[token] = row
            prior_lineage_by_id[token] = meta
    fresh_index: dict[str, dict] = {}
    for row in fresh:
        validate(row)
        if row["zipcode"] != store.zipcode or row["store_location"] != store.address:
            raise HistoryConflict("fresh product store context mismatch")
        for token in identity_tokens(row):
            if token in fresh_index and fresh_index[token] is not row:
                raise HistoryConflict("fresh catalog has colliding authentic identities")
            fresh_index[token] = row
    merged = list(fresh)
    lineages = {}
    refreshed = 0
    newly_observed = 0
    carried = 0
    carried_unpriced = 0
    for row in fresh:
        hits = {id(prior_index[t]): prior_index[t] for t in identity_tokens(row) if t in prior_index}
        if len(hits) > 1:
            raise HistoryConflict("fresh source combined multiple old product identities")
        prior = next(iter(hits.values())) if hits else None
        if prior is not None and prior["upc"] and row["upc"] and prior["upc"] != row["upc"]:
            raise HistoryConflict("UPC drift on same product URL")
        historical_upc_retained=bool(prior and prior["upc"] and not row["upc"])
        if historical_upc_retained:
            # This UPC came from an immutable hash-checked historical
            # observation, not from an inferred product URL. Record lineage.
            token="upc:"+prior["upc"]
            if token in fresh_index and fresh_index[token] is not row:
                raise HistoryConflict("historical UPC is now claimed by another product")
            row["upc"]=prior["upc"]
            fresh_index[token]=row
        oldmeta = next((prior_lineage_by_id[t] for t in identity_tokens(row)
                        if t in prior_lineage_by_id), {})
        if prior is None:
            newly_observed += 1
        else:
            refreshed += 1
        meta = {
            "first_seen": oldmeta.get("first_seen") or (prior["crawl_date"] if prior else row["crawl_date"]),
            "last_seen": row["crawl_date"],
            "state": "fresh_observed_unpriced" if not row["regular_price"] and not row["sale_price"]
                     else "fresh_observed",
            "observation_count": int(oldmeta.get("observation_count", 1 if prior else 0)) + 1,
            "original_crawl_date": prior["crawl_date"] if prior else row["crawl_date"],
            "upc_historically_retained":historical_upc_retained,
            "known_source_urls":sorted(set(oldmeta.get("known_source_urls",[]))
                | {row["url"]} | ({prior["url"]} if prior else set())),
        }
        for token in identity_tokens(row):
            lineages[token] = meta
    for old in previous_rows:
        if any(token in fresh_index for token in identity_tokens(old)):
            continue
        # Never remove genuine records, even if price was blank on prior run,
        # the product is now unavailable, or it disappears for many cycles.
        merged.append(old)
        carried += 1
        if not old["regular_price"] and not old["sale_price"]:
            carried_unpriced += 1
        oldmeta = next((prior_lineage_by_id[t] for t in identity_tokens(old)
                        if t in prior_lineage_by_id), {})
        meta = {
            "first_seen": oldmeta.get("first_seen", old["crawl_date"]),
            "last_seen": oldmeta.get("last_seen", old["crawl_date"]),
            "state": "carried_forward_unobserved",
            "observation_count": int(oldmeta.get("observation_count", 1)),
            "original_crawl_date": oldmeta.get("original_crawl_date", old["crawl_date"]),
            "known_source_urls":oldmeta.get("known_source_urls",[old["url"]]),
            "upc_historically_retained":oldmeta.get("upc_historically_retained",False),
        }
        for token in identity_tokens(old):
            lineages[token] = meta
    for row in merged:
        validate(row)
    if len(merged) < len(previous_rows):
        raise HistoryConflict("history row count decreased; no publication")
    if len({identity_tokens(x)[0] for x in merged}) != len(merged):
        raise HistoryConflict("duplicate historical URL identities")
    statistics = {
        "fresh_observed_records": len(fresh),
        "newly_observed_records": newly_observed,
        "refreshed_records": refreshed,
        "carried_forward_records": carried,
        "carried_forward_unpriced": carried_unpriced,
        "fresh_observed_unpriced": sum(not x["regular_price"] and not x["sale_price"] for x in fresh),
        "previous_historical_records": len(previous_rows),
        "historical_total_records": len(merged),
        "retention_policy": "no_deletions_permanent_carry_forward",
    }
    return merged, lineages, statistics