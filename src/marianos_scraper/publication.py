"""Publisher-owned, synchronous positive-result guard.

Adapted from the Walmart v0.5.7 fail-closed principle, not its provider
request protocol. This scraper makes no paid provider call. Neither a worker
thread nor a pending/failed manifest may publish a last-success pointer.
"""
from __future__ import annotations

import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def require_positive_publication(manifest: dict) -> None:
    """Validate immutable export reference before any last-good pointer write.

    The OS/filesystem's actual synchronous write/rename is NOT subject to a
    hard wall-clock deadline; a blocked filesystem can block the caller.
    """
    if not isinstance(manifest, dict):
        raise ValueError("publication manifest must be an object")
    if manifest.get("status") != "passed" or manifest.get("published") is not True:
        raise ValueError("only qualified passed manifests can publish")
    if not isinstance(manifest.get("records"), int) or manifest["records"] <= 0:
        raise ValueError("cannot publish an empty catalog")
    digest = manifest.get("sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("publication requires a complete lowercase SHA-256")
    store_id = manifest.get("store_id")
    slot = manifest.get("slot")
    key = manifest.get("dataset_key")
    if not all(isinstance(v, str) and v and "/" not in v and "\\" not in v and v not in (".", "..")
               for v in (store_id, slot)):
        raise ValueError("publication requires safe store/slot identifiers")
    expected = f"exports/{store_id}/{slot}/catalog-{digest[:16]}.json"
    if key != expected:
        raise ValueError("publication dataset key must match the validated immutable export")
    if not isinstance(manifest.get("published_at"), str) or not manifest["published_at"]:
        raise ValueError("publication requires final caller-owned timestamp")