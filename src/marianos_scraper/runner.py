"""Orchestrates durable per-subcategory checkpoints, validation, and atomic publish."""
from __future__ import annotations
from collections import Counter,OrderedDict,defaultdict
from datetime import datetime,timedelta
from hashlib import sha256
import json
import logging
import os
import re
from zoneinfo import ZoneInfo
from .browser import BrowserSource,CrawlFailure,CoverageGap
from .config import Category,Store,Options
from .schema import FIELDS,APPROX_WEIGHT,RecordError,record,validate,fingerprint

LOG=logging.getLogger(__name__)

def slot_id(now:datetime|None=None):
    local=(now or datetime.now(ZoneInfo("America/Chicago"))).astimezone(ZoneInfo("America/Chicago"))
    day=local.date()
    while day.weekday() not in (0,3):day-=timedelta(days=1)
    return day.isoformat()

def _key(store:Store,slot:str,cat:str,url:str):
    digest=sha256((cat+"\0"+url).encode()).hexdigest()[:20]
    return f"runs/{store.id}/{slot}/units/{digest}.json"

def _cat_key(store,slot,cat):
    digest=sha256(cat.name.encode()).hexdigest()[:20]
    return f"runs/{store.id}/{slot}/discovery/{digest}.json"

def _fields_ratio(items,field):
    return round(sum(bool(p[field]) for p in items)/len(items),4) if items else 0

def _summarize(items:list[dict],counts:dict,subcats:dict,duplicates:int,previous:dict|None,store:Store,slot:str,started:str) -> dict:
    return {
        "status":"validated", "store_id":store.id,"store_name":store.name,
        "zipcode":store.zipcode,"address":store.address,"slot":slot,
        "started_at":started,"finished_at":datetime.now(ZoneInfo("UTC")).isoformat(),
        "runtime_seconds":round((datetime.now(ZoneInfo("UTC"))-datetime.fromisoformat(started)).total_seconds(),2),
        "records":len(items),"duplicates_removed":duplicates,
        "category_counts":counts,"subcategories_by_category":subcats,
        "field_completeness":{f:_fields_ratio(items,f) for f in FIELDS},
        "ppm_examples":[p["ppm"] for p in items if p["ppm"]][:10],
        "volume_deal_examples":[{"description":p["volume_deals_description"],"price":p["volume_deals_price"]} for p in items if p["volume_deals_description"]][:10],
        "digital_deal_examples":[{"description":p["digital_deals_description"],"price":p["digital_deals_price"]} for p in items if p["digital_deals_description"]][:10],
        "prior_count":previous.get("records",0) if previous else None,
        "json_fields":list(FIELDS),
        "published":False,
    }

def _check_coverage(items:list[dict], counts:dict, subcats:dict, categories:list[Category], options:Options, previous:dict|None, store:Store):
    if len(items)<options.min_records_per_store:
        raise CoverageGap(f"store {store.id} collected {len(items)}, minimum {options.min_records_per_store}")
    for cat in categories:
        n=counts.get(cat.name,0)
        if n<options.min_per_category:
            raise CoverageGap(f"missing/empty {cat.name}: {n} records; cannot publish")
    if previous:
        before=previous.get("records",0)
        if before and len(items)<before*options.prior_yield_ratio:
            raise CoverageGap(f"total unusually thin: {len(items)} vs previously {before}")
        for cat in categories:
            old=previous.get("category_counts",{}).get(cat.name,0)
            if old and counts.get(cat.name,0)<old*options.prior_category_ratio:
                raise CoverageGap(f"category thin: {cat.name} {counts.get(cat.name)} vs prior {old}")
            prior_urls=set(previous.get("subcategories_by_category",{}).get(cat.name,[]))
            now_urls=set(subcats.get(cat.name,[]))
            if prior_urls and (len(now_urls)<len(prior_urls)*options.min_subcategory_retention):
                raise CoverageGap(f"subcategory count dropped: {cat.name}: {len(now_urls)} vs {len(prior_urls)}")
            missing=prior_urls-now_urls
            if missing:
                raise CoverageGap(f"subcategory vanished for {cat.name}: {sorted(missing)[:5]}")
    if store.canary_urls:
        found={x["url"].split("?",1)[0] for x in items}
        missing=[url for url in store.canary_urls if url.split("?",1)[0] not in found]
        if missing:raise CoverageGap(f"missing canary products: {missing[:4]}")

class Pipeline:
    def __init__(self,storage,source_factory=BrowserSource):
        self.storage=storage
        self.source_factory=source_factory

    def run(self,store:Store,categories:list[Category],options:Options,slot:str|None=None,force:bool=False) -> dict:
        slot=slot or slot_id()
        started=datetime.now(ZoneInfo("UTC")).isoformat()
        prefix=f"runs/{store.id}/{slot}"
        latest_key=f"published/{store.id}/latest.json"
        with self.storage.lease(store.id):
            self.storage.assert_healthy()
            previous,previous_etag=self.storage.get_json_versioned(latest_key)
            if previous and previous.get("slot")==slot and not force:
                LOG.info("slot_already_published",extra={"store":store.id,"slot":slot})
                return previous
            combined=[]
            count_per_cat=Counter()
            subcat_map=defaultdict(list)
            completion_evidence=defaultdict(list)
            proofs=[]
            proof_keys=[]
            try:
                with self.source_factory(store,options) as source:
                    if hasattr(source,"screenshot_proof"):
                        key=f"{prefix}/proof/store-start.png"
                        self.storage.put_bytes(key,source.screenshot_proof())
                        proof_keys.append(key)
                    for cat in categories:
                        dkey=_cat_key(store,slot,cat)
                        discovery=self.storage.get_json(dkey)
                        if (not force and discovery and discovery.get("complete")
                                and discovery.get("category")==cat.name and discovery.get("source_url")==cat.url):
                            units=discovery["units"]
                            LOG.info("discovery_resume",extra={"store":store.id,"category":cat.name,"units":len(units)})
                        else:
                            units=source.discover_units(cat)
                            self.storage.put_json(dkey,{"complete":True,"category":cat.name,"units":units,"source_url":cat.url})
                        if not units:raise CoverageGap(f"no subcategories for {cat.name}")
                        for sub_name,url in units:
                            subcat_map[cat.name].append(url)
                            ukey=_key(store,slot,cat.name,url)
                            checkpoint=self.storage.get_json(ukey)
                            if (not force and checkpoint and checkpoint.get("complete")
                                    and checkpoint.get("store_id")==store.id and checkpoint.get("category")==cat.name
                                    and checkpoint.get("url")==url and checkpoint.get("subcategory")==sub_name):
                                items=checkpoint["items"]
                                if not checkpoint.get("proof"):
                                    raise CoverageGap("checkpoint without location proof")
                                if getattr(source, "requires_positive_coverage", False) and not (
                                    isinstance(checkpoint.get("coverage"), dict)
                                    and checkpoint["coverage"].get("passed") is True
                                ):
                                    raise CoverageGap("completed source checkpoint lacks positive pagination-end evidence")
                                if checkpoint.get("coverage"):
                                    completion_evidence[cat.name].append(checkpoint["coverage"])
                                proofs.append(checkpoint["proof"])
                                LOG.info("unit_resume",extra={"store":store.id,"category":cat.name,"subcategory":sub_name,"items":len(items)})
                            else:
                                partial=(checkpoint.get("items",[]) if checkpoint and not force
                                         and checkpoint.get("store_id")==store.id
                                         and checkpoint.get("category")==cat.name
                                         and checkpoint.get("subcategory")==sub_name
                                         and checkpoint.get("url")==url else [])
                                def on_progress(items):
                                    self.storage.assert_healthy()
                                    self.storage.put_json(ukey,{"complete":False,"store_id":store.id,"category":cat.name,"url":url,"collected_date":datetime.now(ZoneInfo("America/Chicago")).date().isoformat(),"items":items})
                                outcome=source.crawl_listing(cat,sub_name,url,progress=on_progress,resume_items=partial)
                                items=outcome.items
                                proofs.append(outcome.proof)
                                if getattr(source, "requires_positive_coverage", False) and not (
                                    isinstance(outcome.coverage, dict)
                                    and outcome.coverage.get("passed") is True
                                ):
                                    raise CoverageGap("source unit lacks positive end-of-results evidence")
                                if outcome.coverage:
                                    completion_evidence[cat.name].append(outcome.coverage)
                                # Completed unit is atomically committed only after proof and nonzero results.
                                if not outcome.proof or not items:
                                    raise CoverageGap(f"incomplete unit {url}")
                                self.storage.put_json(ukey,{"complete":True,"store_id":store.id,"category":cat.name,"subcategory":sub_name,"url":url,"proof":outcome.proof,"observed_count":outcome.observed_count,"coverage":outcome.coverage,
                                                       "collected_date":datetime.now(ZoneInfo("America/Chicago")).date().isoformat(),"items":items})
                            for item in items:
                                data={**item,"zipcode":store.zipcode,"store_name":store.name,"store_location":store.address,"store_logo":(store.logo_url or getattr(source,"logo_url",""))}
                                obj=record(data,(checkpoint.get("collected_date") if checkpoint and not force and checkpoint.get("complete") else datetime.now(ZoneInfo("America/Chicago")).date().isoformat()))
                                if APPROX_WEIGHT.search(obj["weight"]):continue
                                validate(obj)
                                combined.append(obj)
                                # Only an eligible, validated product counts toward category coverage.
                                # A raw card excluded for approximate weight cannot satisfy the gate.
                                count_per_cat[cat.name]+=1
                        LOG.info("category_complete",extra={"store":store.id,"category":cat.name,"items":count_per_cat[cat.name],"subcategories":len(units)})
                    if hasattr(source,"screenshot_proof"):
                        key=f"{prefix}/proof/store-end.png"
                        self.storage.put_bytes(key,source.screenshot_proof())
                        proof_keys.append(key)
                if not proofs or any(store.verification_text.casefold() not in s.casefold() for s in proofs):
                    raise CoverageGap("one or more unit checkpoints failed selected-store proof")
                unique=OrderedDict()
                duplicate_count=0
                for p in combined:
                    key=fingerprint(p)
                    if key in unique:
                        duplicate_count+=1
                        # Keep richer, unaltered observed values; category assignment follows first appearance.
                        old=unique[key]
                        if sum(bool(v) for v in p.values())>sum(bool(v) for v in old.values()):
                            new=dict(p)
                            new["category"]=old["category"]
                            new["sub_category"]=old["sub_category"]
                            unique[key]=record(new,old["crawl_date"])
                    else:unique[key]=p
                items=list(unique.values())
                exported_counts=Counter(p["category"] for p in items)
                # Global deduplication can suppress a category completely. Never
                # claim that every category is represented in the published export.
                missing_exported=[cat.name for cat in categories if not exported_counts[cat.name]]
                if missing_exported:
                    raise CoverageGap(f"categories absent after global deduplication: {missing_exported}")
                _check_coverage(items,exported_counts,subcat_map,categories,options,previous,store)
                self.storage.assert_healthy()
                report=_summarize(items,dict(exported_counts),dict(subcat_map),duplicate_count,previous,store,slot,started)
                report["eligible_category_counts_before_dedup"]=dict(count_per_cat)
                report["positive_listing_evidence_by_category"]=dict(completion_evidence)
                report["positive_completion_unit_count"]=sum(len(v) for v in completion_evidence.values())
                data=json.dumps(items,ensure_ascii=False,separators=(",", ":")).encode("utf-8")
                digest=sha256(data).hexdigest()
                report["sha256"]=digest
                report["dataset_key"]=f"exports/{store.id}/{slot}/catalog-{digest[:16]}.json"
                report["report_key"]=f"exports/{store.id}/{slot}/validation-{digest[:16]}.json"
                report["location_proof_samples"]=list(dict.fromkeys(proofs))[:8]
                report["location_proof_images"]=proof_keys
                self.storage.put_bytes(report["dataset_key"],data)
                self.storage.put_json(report["report_key"],report)
                # LAST action in success path. A failed run can never alter this pointer.
                self.storage.assert_healthy()
                published={**report,"status":"passed","published":True,"published_at":datetime.now(ZoneInfo("UTC")).isoformat()}
                self.storage.publish_pointer(latest_key,published,previous_etag)
                LOG.info("published",extra={"store":store.id,"slot":slot,"records":len(items),"sha256":digest})
                return published
            except Exception as exc:
                failure={"status":"failed","store_id":store.id,"slot":slot,"started_at":started,
                         "finished_at":datetime.now(ZoneInfo("UTC")).isoformat(),"error_type":type(exc).__name__,"error":str(exc)[:1000],"last_successful_pointer_unchanged":True}
                try:self.storage.put_json(f"{prefix}/FAILED.json",failure)
                except Exception:LOG.exception("failure_checkpoint_write_failed")
                LOG.error("run_failed",extra={"store":store.id,"slot":slot,"error":str(exc)})
                raise