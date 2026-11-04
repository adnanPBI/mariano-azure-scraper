"""Classify acceptance evidence without converting offline tests into live proof.

Machine checks and signed claims are NOT physical/third-party verification.
The stage labels stay separate even if release_report() later returns GO.
"""
from __future__ import annotations


def _reported(checks: dict, name: str) -> bool:
    result = checks.get(name)
    return isinstance(result, dict) and result.get("passed") is True


def describe_release_evidence(checks: dict) -> dict:
    """Provide independent evidence domains, never inferred from CI fixtures.

    A signed observed-acceptance attestation records a reviewer's claims; it
    cannot by itself demonstrate an actual retailer or Azure exchange.
    """
    if not isinstance(checks, dict):
        raise TypeError("checks must be a dictionary")
    human_signed = _reported(checks, "observed_acceptance")
    auth = _reported(checks, "authorization")
    source = _reported(checks, "source_coverage")
    azure = _reported(checks, "azure")

    def domain(machine_claim: bool, independently_attested: bool,
               required_proof: str) -> dict:
        if independently_attested:
            status = "SIGNED_REVIEW_CLAIM_REQUIRES_EXTERNAL_CORROBORATION"
        elif machine_claim:
            status = "MACHINE_REPORTED_PENDING_INDEPENDENT_OBSERVATION"
        else:
            status = "NOT_VERIFIED"
        return {"status": status, "required_evidence": required_proof,
                "production_proven_by_offline_tests": False}

    return {
        "offline_engineering": {
            "status": "CHECK_GITHUB_CI_SEPARATELY",
            "required_evidence": "Exact SHA, three matching GitHub job logs, "
                                 "source/wheel builds, and tests' fixture provenance",
            "production_proven_by_offline_tests": False,
        },
        "collection_authorization": domain(
            auth, auth and human_signed,
            "Actual signed retailer/licensor grant; authorized access method, "
            "store/product/coupon scope, historical retention and human grantor review",
        ),
        "vernon_hills_pickup_source_binding": domain(
            source, source and human_signed and auth,
            "Same authorized shopping session: source-returned store ID, PICKUP, "
            "product/UPC/price response IDs, captured network trace and independent spot checks. "
            "Public directory 531/00502 alone is never sufficient.",
        ),
        "complete_categories_subcategories_coupons": domain(
            source, source and human_signed,
            "All 28 categories and applicable subcategories, positive end-of-list "
            "proofs, real coupon eligibility and terms, and >=500 fresh genuine unique records",
        ),
        "live_recovery_and_repeat_run": domain(
            False, human_signed and source,
            "Witnessed real interruption/checkpoint resume, price refresh, "
            "retained unavailable products, repeat collection, and last-good readbacks",
        ),
        "azure_execution": domain(
            azure, azure and human_signed,
            "Authorized Azure subscription/job execution ID, control-plane "
            "status, runtime, costs, logs, Blob digest readback and schedule",
        ),
        "contest_entry_and_award": {
            "status": "UNVERIFIED_SEPARATE_FROM_ENGINEERING_AND_PRODUCTION",
            "required_evidence": "Actual Mariano's contest entry number/link "
                                 "and platform eligibility decision; no award promise",
            "production_proven_by_offline_tests": False,
        },
    }
