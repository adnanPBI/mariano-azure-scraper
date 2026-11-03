"""External observed-export evidence audit, separate from historical 22-field rows.

A carried historical row is never counted as a *fresh* retailer observation,
and an overlapping coupon is not duplicated solely to fill its category.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
from .schema import validate


def audit_source_coverage(dataset_path: str, validation_path: str, categories) -> dict:
    result={"passed":False,"reason":"missing observed dataset/coverage report"}
    if not dataset_path or not validation_path:
        return result
    a=Path(dataset_path)
    b=Path(validation_path)
    if not a.is_file() or not b.is_file():
        return result
    try:
        payload=a.read_bytes()
        data=json.loads(payload)
        report=json.loads(b.read_text(encoding="utf-8"))
        if not isinstance(data,list) or not data:
            raise ValueError("empty actual dataset")
        for p in data:
            validate(p)
        if report.get("sha256")!=sha256(payload).hexdigest():
            raise ValueError("coverage evidence not bound to actual JSON bytes")
        if report.get("dataset_key","").split("/")[-1] != (
            "catalog-"+report["sha256"][:16]+".json"
        ):
            raise ValueError("source report dataset identity mismatch")
        n=report.get("fresh_observed_records")
        if not isinstance(n,int) or n<500:
            raise ValueError("fewer than 500 fresh source records; carried history cannot substitute")
        if report.get("records")!=len(data):
            raise ValueError("report total differs from exported source rows")
        if report.get("historical_total_records")!=len(data):
            raise ValueError("retained dataset total mismatch")
        if report.get("retention_policy")!="no_deletions_permanent_carry_forward":
            raise ValueError("missing no-deletion retention policy")
        by_category=report.get("category_coverage_evidence")
        if not isinstance(by_category,dict):
            raise ValueError("no independent category source coverage")
        for cat in categories:
            row=by_category.get(cat.name)
            if not isinstance(row,dict):
                raise ValueError(f"missing real category evidence for {cat.name}")
            if row.get("fresh_source_count",0)<1 or row.get("unique_source_products",0)<1:
                raise ValueError(f"no unique source identities for {cat.name}")
            if row.get("verified_units",0)<1:
                raise ValueError(f"no positively completed units for {cat.name}")
            units=row.get("unit_completion_proofs",[])
            if len(units)!=row["verified_units"]:
                raise ValueError(f"unit proof count mismatch for {cat.name}")
            if not all(u.get("passed") is True and u.get("resolved_identities",0)>0 for u in units):
                raise ValueError(f"unverified positive termination in {cat.name}")
            if cat.name=="Coupons":
                if not all(u.get("listing_kind")=="coupons" for u in units):
                    raise ValueError("coupon category lacks authentic coupon-list termination")
            source_prices=row.get("source_price_proofs",[])
            if len(source_prices)!=row["verified_units"] or not all(
                p.get("verified") is True
                and p.get("observed_store_ref")
                and p.get("observed_fulfillment")
                and p.get("verified_product_count",0)>0
                for p in source_prices
            ):
                raise ValueError(f"no linked store/mode/price source responses for {cat.name}")
        return {
            "passed":True,"fresh_observed_records":n,
            "historical_records":len(data),"carried_forward":report.get("carried_forward_records",0),
            "categories_verified":len(categories),
            "missing_primary_categories_allowed_only_with_independent_source_proof":True,
            "limitation":"Source proofs still need a genuine attended retailer/Azure review",
        }
    except Exception as exc:
        return {"passed":False,"reason":str(exc)}