"""Evidence separation regressions, no retailer/network/Azure access."""
import json
from pathlib import Path

from marianos_scraper.evidence_domains import describe_release_evidence
from marianos_scraper.qualification import release_report


def test_default_no_go_never_relabels_offline_fixtures_as_retailer_proof():
    result = release_report(
        "config/Marianos_Category_URLs.csv",
        "config/stores.yaml",
    )
    assert result["status"] == "NO_GO"
    domains = result["evidence_domains"]
    for key in (
        "vernon_hills_pickup_source_binding",
        "complete_categories_subcategories_coupons",
        "live_recovery_and_repeat_run",
        "azure_execution",
    ):
        assert domains[key]["status"] == "NOT_VERIFIED"
        assert domains[key]["production_proven_by_offline_tests"] is False
    assert domains["contest_entry_and_award"]["status"].startswith("UNVERIFIED_")


def test_self_reported_source_and_azure_do_not_equal_independent_observation():
    claims = describe_release_evidence({
        "source_coverage": {"passed": True},
        "azure": {"passed": True, "execution_id": "SYNTHETIC-NOT-REAL"},
        "authorization": {"passed": False},
        "observed_acceptance": {"passed": False},
    })
    assert claims["vernon_hills_pickup_source_binding"]["status"] == (
        "MACHINE_REPORTED_PENDING_INDEPENDENT_OBSERVATION"
    )
    assert claims["complete_categories_subcategories_coupons"]["status"] == (
        "MACHINE_REPORTED_PENDING_INDEPENDENT_OBSERVATION"
    )
    assert claims["azure_execution"]["status"] == (
        "MACHINE_REPORTED_PENDING_INDEPENDENT_OBSERVATION"
    )
    assert claims["live_recovery_and_repeat_run"]["status"] == "NOT_VERIFIED"


def test_even_signed_claim_requires_external_source_and_azure_corrob():
    reported = describe_release_evidence({
        "authorization": {"passed": True},
        "source_coverage": {"passed": True},
        "azure": {"passed": True},
        "observed_acceptance": {"passed": True},
    })
    for field in ("vernon_hills_pickup_source_binding",
                  "complete_categories_subcategories_coupons",
                  "live_recovery_and_repeat_run", "azure_execution"):
        assert reported[field]["status"] == (
            "SIGNED_REVIEW_CLAIM_REQUIRES_EXTERNAL_CORROBORATION"
        )
        assert not reported[field]["production_proven_by_offline_tests"]


def test_checkpoint_register_explicitly_blocks_all_unobserved_gates():
    path = Path(__file__).resolve().parents[1] / "release" / "evidence-register-20261104.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["release_status"] == "NO_GO"
    assert payload["technical_target"]["fulfillment_intended"] == "PICKUP"
    assert payload["technical_target"]["public_directory_reference"] == "531/00502"
    assert payload["technical_target"]["source_returned_store_id"] is None
    assert payload["technical_target"]["same_session_price_verified"] is False
    assert payload["contest"]["entry_number"] is None
    assert payload["contest"]["award_commitment"] is False
    assert payload["acquisition"]["route"] == "direct_playwright"
    assert payload["acquisition"]["walmart_oxylabs_entitlement_applies"] is False
    stages = payload["owner_dependent_evidence"]
    for name in ("collection_authorization", "source_bound_prices",
                 "complete_catalog_coupons", "actual_recovery",
                 "azure_job", "independent_client_signoff"):
        assert stages[name]["status"] == "NOT_VERIFIED"
        assert stages[name]["evidence_ids"] == []
    ci = payload["independently_rechecked_ci"]
    assert ci["source_commit_sha"] == "313bf6995aa57fe07946383d2910dbade47aa75a"
    assert ci["workflow_run_id"] == 41664946302
    assert ci["result"] == "success"
    assert len(ci["jobs"]) == 3
    assert all(j["tests_passed"] == 82 and j["package_build"] == "success"
               for j in ci["jobs"])
    # This is a separate, later GitHub job-log inspection, not a rewrite
    # of the historical November 3 CI record or proof of live acceptance.
    latest = payload["latest_independently_rechecked_ci"]
    assert latest["source_commit_sha"] == "b3ae7c7f59e415d28e8bc21c173e895a2af8e6d4"
    assert latest["workflow_run_id"] == 41763745403
    assert latest["conclusion"] == "success"
    assert len(latest["jobs"]) == 3
    assert all(j["tests_passed"] == 86 and j["python_build"] == "success"
               for j in latest["jobs"])
    assert latest["qualification"] == "OFFLINE_ENGINEERING_ONLY"
    assert latest["genuine_retailer_records_observed"] == 0
    assert latest["azure_job_observed"] is False
    assert latest["contest_entry_verified"] is False
    assert payload["release_status"] == "NO_GO"