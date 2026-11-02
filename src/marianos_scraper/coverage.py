"""Fail-closed, source-backed listing and coupon termination qualification.

A quiet scroll or a missing Next button alone is not proof of full catalog
coverage. A listing must reconcile all encountered product/card identities to
a retailer-displayed total or an explicit terminal signal.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

class IncompleteListing(RuntimeError):
    """Retailer page coverage cannot be positively established."""

EXPLICIT_END = re.compile(
    r"(?:no more (?:products|items|results|coupons|offers)|"
    r"end of (?:the )?(?:results|product list|coupon list)|"
    r"you(?:'ve| have) (?:seen|viewed) all (?:products|results|offers|coupons)|"
    r"all (?:products|results|coupons|offers) (?:shown|loaded))",
    re.I,
)

@dataclass(frozen=True)
class Completion:
    source_total: int | None
    observed_identities: int
    resolved_identities: int
    explicit_end: bool
    disabled_terminal_control: bool
    stable_at_bottom: bool
    active_next: bool = False
    active_load_more: bool = False
    pages: int = 1
    listing_kind: str = "products"

def verify_completion(value: Completion) -> dict:
    """Return auditable evidence or raise rather than silently undercount.

    In coupons mode a resolved identity is a coupon with an actual product
    URL and observed activation terms, NOT the number of mapped products.
    """
    if value.listing_kind not in ("products", "coupons"):
        raise IncompleteListing("unsupported listing type")
    if value.observed_identities <= 0 or value.resolved_identities <= 0:
        raise IncompleteListing("no positively observed eligible identities")
    if value.resolved_identities != value.observed_identities:
        raise IncompleteListing(
            f"unresolved {value.listing_kind}: {value.resolved_identities} "
            f"of {value.observed_identities} source identities reconciled"
        )
    if not value.stable_at_bottom or value.active_next or value.active_load_more:
        raise IncompleteListing("pagination/load-more/scroll termination not established")
    if value.source_total is not None:
        if value.source_total < 1 or value.observed_identities != value.source_total:
            raise IncompleteListing(
                f"source-count mismatch for {value.listing_kind}: "
                f"observed {value.observed_identities}, displayed {value.source_total}"
            )
        method = "retailer_total_exact_match"
    elif value.explicit_end:
        method = "retailer_explicit_end_marker"
    elif value.disabled_terminal_control:
        method = "retailer_disabled_terminal_control"
    else:
        raise IncompleteListing("no retailer count or explicit end-of-results evidence")
    return {
        "passed": True,
        "listing_kind": value.listing_kind,
        "source_total": value.source_total,
        "observed_identities": value.observed_identities,
        "resolved_identities": value.resolved_identities,
        "completion_method": method,
        "stable_at_bottom": value.stable_at_bottom,
        "active_next": value.active_next,
        "active_load_more": value.active_load_more,
        "pages": value.pages,
    }