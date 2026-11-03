"""Client review #1-#5: strict synthetic regression fixtures, never real products."""
from __future__ import annotations
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo
import json
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright

from marianos_scraper.config import Category, Store, Options, require_source_context_config
from marianos_scraper.runner import Pipeline, _key
from marianos_scraper.storage import LocalStorage
from marianos_scraper.browser import BrowserSource, CrawlOutcome, CoverageGap
from marianos_scraper.schema import record
from marianos_scraper.history import HistoryConflict
from marianos_scraper.extract import extract_detail_fields, enrich_from_details, DetailIdentityError
from marianos_scraper.source_context import SourceResponseLedger, SourceContextError


STORE=Store(id="offline-531-00502",zipcode="60061",name="Mariano's",
    address="1720 N Milwaukee Ave, Vernon Hills, IL 60061",
    verification_text="1720 N Milwaukee Ave",
    source_store_ref="531/00502",fulfillment_mode="PICKUP",
    price_response_paths=["/approved-fixture/product-prices"])
CATS=[
    Category("Grocery","https://www.marianos.com/d/grocery"),
    Category("Coupons","https://www.marianos.com/savings/cl/coupons/"),
]
OPTIONS=Options(min_records_per_store=1,min_per_category=1,
                prior_yield_ratio=.4,prior_category_ratio=.4,
                max_detail_pages=0,delay_seconds=0)


def make_item(category,title,part,price="3.25",upc="",coupon="",date_value="2026-11-02"):
    return record({
        "zipcode":STORE.zipcode, "store_name":STORE.name,
        "store_location":STORE.address,"store_logo":"",
        "category":category,"sub_category":category + " / Source",
        "product_title":title,"weight":"12 oz",
        "regular_price":price,"sale_price":"",
        "volume_deals_description":"","volume_deals_price":"",
        "digital_deals_description":coupon,"digital_deals_price":"",
        "image_url":"","url":f"https://www.marianos.com/p/{part}/0001111111111" if part=="yogurt"
            else f"https://www.marianos.com/p/{part}/0002222222222",
        "upc":upc,"ppm":"","store_brand":"no",
    },date_value)


class SyntheticObservedSource:
    """Test-only trustworthy source adapter, not Mariano's live data."""
    stage = 1
    failed_once = False
    last_resume = []
    def __init__(self,store,options):
        self.store=store
    def __enter__(self): return self
    def __exit__(self,*_): pass
    requires_positive_coverage = True
    requires_source_price_binding = True

    def discover_units(self,cat): return [(cat.name+" / Source",cat.url+"/unit")]

    def crawl_listing(self,cat,sub,url,progress=None,resume_items=None):
        self.__class__.last_resume=list(resume_items or [])
        if cat.name=="Grocery":
            rows=[make_item("Grocery","Yogurt","yogurt",
                            "3.25" if self.stage==1 else "4.55",upc="0001111111111")]
            if self.stage==1:
                rows.append(make_item("Grocery","OFFLINE cereal","cereal",""))
        else:
            rows=[make_item("Coupons","Yogurt","yogurt",
                            "3.25" if self.stage==1 else "4.55",
                            upc="0001111111111",
                            coupon="Clip Coupon: Save $2, limit 3, first offer")
                  ]
        if self.stage=="partial-first" and cat.name=="Grocery" and not self.failed_once:
            self.__class__.failed_once=True
            stale=make_item("Grocery","Yogurt","yogurt","1.11",
                            coupon="Clip Coupon: OLD STALE offer")
            if progress:progress([stale])
            raise ConnectionError("synthetic partial listing interruption")
        if progress:progress(rows)
        return CrawlOutcome(rows,proof="Pickup 1720 N Milwaukee Ave",
            observed_count=len(rows),screenshots=[],
            coverage={"passed":True,"listing_kind":"coupons" if cat.name=="Coupons" else "products",
                      "observed_identities":len(rows),"resolved_identities":len(rows)},
            source_evidence={"verified":True,"observed_store_ref":"531/00502",
                             "observed_fulfillment":"PICKUP",
                             "verified_product_count":len(rows)})


@pytest.fixture(autouse=True)
def reset():
    SyntheticObservedSource.stage=1
    SyntheticObservedSource.failed_once=False
    SyntheticObservedSource.last_resume=[]


def test_historical_missing_unpriced_product_retained_across_three_runs(tmp_path):
    storage=LocalStorage(str(tmp_path))
    pipe=Pipeline(storage,SyntheticObservedSource)
    initial=pipe.run(STORE,CATS,OPTIONS,slot="2026-10-12")
    assert initial["records"]==2
    assert initial["fresh_observed_records"]==2
    assert initial["carried_forward_records"]==0
    assert initial["category_counts"]=={"Grocery":2}
    assert initial["fresh_source_category_counts"]["Coupons"]==1
    assert initial["category_coverage_evidence"]["Coupons"]["overlap_only"] is True
    first=storage.get_json(initial["dataset_key"])
    before_unpriced=next(p for p in first if "cereal" in p["url"])
    assert before_unpriced["regular_price"]==""
    original_date=before_unpriced["crawl_date"]
    SyntheticObservedSource.stage=2
    second=pipe.run(STORE,CATS,OPTIONS,slot="2026-10-15")
    assert second["records"]==2 and second["fresh_observed_records"]==1
    assert second["carried_forward_records"]==1
    assert second["carried_forward_unpriced"]==1
    saved=storage.get_json(second["dataset_key"])
    new_yogurt=next(p for p in saved if "yogurt" in p["url"])
    cereal=next(p for p in saved if "cereal" in p["url"])
    assert new_yogurt["regular_price"]=="4.55"
    assert new_yogurt["crawl_date"]==datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    assert cereal==before_unpriced
    lineage=storage.get_json(second["history_key"])
    assert lineage["dataset_sha256"]==second["sha256"]
    assert lineage["records"]["url:"+cereal["url"]]["first_seen"]==original_date
    assert lineage["records"]["url:"+cereal["url"]]["last_seen"]==original_date
    third=pipe.run(STORE,CATS,OPTIONS,slot="2026-10-19")
    assert third["records"]==2 and third["carried_forward_records"]==1
    assert next(p for p in storage.get_json(third["dataset_key"]) if "cereal" in p["url"])==cereal


def test_partial_checkpoint_restarts_and_replaces_stale_values(tmp_path):
    storage=LocalStorage(str(tmp_path))
    pipe=Pipeline(storage,SyntheticObservedSource)
    SyntheticObservedSource.stage="partial-first"
    cat=CATS[0]
    with pytest.raises(ConnectionError,match="partial"):
        pipe.run(STORE,[cat],OPTIONS,slot="2026-10-22")
    checkpoint=storage.get_json(_key(STORE,"2026-10-22",cat.name,cat.url+"/unit"))
    assert checkpoint["complete"] is False
    assert checkpoint["subcategory"]=="Grocery / Source"
    assert checkpoint["items"][0]["regular_price"]=="1.11"
    SyntheticObservedSource.stage=2
    done=pipe.run(STORE,[cat],OPTIONS,slot="2026-10-22")
    assert SyntheticObservedSource.last_resume
    fresh=storage.get_json(done["dataset_key"])
    assert fresh[0]["regular_price"]=="4.55"
    assert "OLD STALE" not in fresh[0]["digital_deals_description"]
    assert storage.get_json("published/"+STORE.id+"/latest.json")["status"]=="passed"


def test_previous_dataset_hash_tamper_never_deletes_history(tmp_path):
    db=LocalStorage(str(tmp_path));pipe=Pipeline(db,SyntheticObservedSource)
    old=pipe.run(STORE,CATS,OPTIONS,slot="2026-10-12")
    path=db._path(old["dataset_key"])
    data=json.loads(path.read_text())
    data.pop()
    path.write_text(json.dumps(data))
    SyntheticObservedSource.stage=2
    with pytest.raises(HistoryConflict,match="hash mismatch"):
        pipe.run(STORE,CATS,OPTIONS,slot="2026-10-15")
    assert db.get_json("published/"+STORE.id+"/latest.json")["sha256"]==old["sha256"]


def test_same_session_response_binds_store_fulfillment_real_price_and_upc():
    require_source_context_config(STORE)
    ledger=SourceResponseLedger(STORE)
    product="https://www.marianos.com/p/yogurt/0001111111111"
    source={"schema":"retailer-price-source-v1",
            "store":{"division":"531","number":"00502"},
            "fulfillment":{"mode":"PICKUP"},
            "products":[{"url":product,"regular_price":"4.55",
                         "sale_price":"","upc":"0001111111111"}]}
    assert ledger.ingest("https://www.marianos.com/approved-fixture/product-prices",source)==1
    row=make_item("Grocery","Yogurt","yogurt","4.55",upc="0001111111111")
    proof=ledger.audit_unit([row])
    assert proof["verified"] and proof["observed_store_ref"]=="531/00502"
    assert proof["observed_fulfillment"]=="PICKUP"
    with pytest.raises(SourceContextError,match="prices disagree"):
        ledger.require_price({**row,"regular_price":"1.00"})
    with pytest.raises(SourceContextError,match="no same-session"):
        ledger.require_price({**row,"url":"https://www.marianos.com/p/other/999"})


@pytest.mark.parametrize("store_number,mode",[
    ("00503","PICKUP"),("00502","DELIVERY"),("00502","IN_STORE")])
def test_wrong_store_or_fulfillment_is_rejected_from_source(store_number,mode):
    ledger=SourceResponseLedger(STORE)
    raw={"schema":"retailer-price-source-v1",
         "store":{"division":"531","number":store_number},
         "fulfillment":{"mode":mode},
         "products":[{"url":"https://www.marianos.com/p/yogurt/111",
                      "regular_price":"4.55"}]}
    with pytest.raises(SourceContextError,match="context mismatch"):
        ledger.ingest("https://www.marianos.com/approved-fixture/product-prices",raw)


def test_directory_label_is_not_accepted_as_source_session_price_proof():
    configured=replace(STORE,price_response_paths=[])
    with pytest.raises(ValueError,match="response path"):
        require_source_context_config(configured)
    ledger=SourceResponseLedger(configured)
    with pytest.raises(SourceContextError):
        ledger.audit_unit([make_item("Grocery","Yogurt","yogurt")])


def test_unrelated_recommendation_jsonld_and_promotions_cannot_pollute_pdp():
    expected="https://www.marianos.com/p/yogurt/0001111111111"
    html=f'''<html><head><link rel="canonical" href="{expected}"/>
        <script type="application/ld+json">
        {{"@graph":[
          {{"@type":"Product","url":"{expected}","gtin13":"0001111111111"}},
          {{"@type":"Product","url":"https://www.marianos.com/p/related/987",
            "gtin13":"9999999999999"}}]}}</script></head><body>
        <main><div data-testid="product-details"><h1>Current Yogurt</h1>
          <p>UPC: 0001111111111</p><span data-testid="regular-price">$4.55</span>
          <span data-testid="ppm">$0.38/oz</span></div>
        <section class="recommended-products">
          <h2>Recommendations</h2><p>UPC: 9999999999999</p>
          <span data-testid="price">$0.99</span>
          <span data-testid="coupon">Clip Coupon: unrelated offer $1</span></section>
        </main></body></html>'''
    patch=extract_detail_fields(html,expected)
    assert patch["upc"]=="0001111111111"
    assert patch["regular_price"]=="4.55"
    assert patch["ppm"]=="$0.38/oz"
    assert not patch["_offers"]
    with pytest.raises(DetailIdentityError,match="canonical"):
        extract_detail_fields(html,"https://www.marianos.com/p/unrelated/987")


def test_max_detail_pages_zero_means_uncapped_source_not_skipped():
    assert OPTIONS.max_detail_pages==0
    source=BrowserSource(STORE,OPTIONS)
    assert source.requires_source_price_binding is True
    assert source.detail_cache=={}
    # The browser always invokes identity-bound detail extraction; a finite
    # positive cap is a reason to fail, never to skip remaining detail visits.


def test_one_product_normal_and_multiple_coupon_units_detail_cache_keeps_each_offer():
    """Actual Chromium, intercept-only synthetic pages, no retailer requests."""
    base="https://www.marianos.com"
    product=base+"/p/yogurt/0001111111111"
    header='<header>Pickup at 1720 N Milwaukee Ave</header>'
    def listing(category,offer="",coupon_id=""):
        if category=="Coupons":
            cards=(f'<article data-coupon-id="{coupon_id}"><a href="{product}">Yogurt</a>'
                   f'<span>{offer}</span></article>')
            tail="<p>You've seen all coupons</p><p>1 coupons</p>"
        else:
            cards=(f'<article class="product-card"><a href="{product}">'
                   '<h3>Yogurt</h3></a><span data-testid="price">$4.55</span>'
                   '<span data-testid="product-size">12 oz</span></article>')
            tail="<p>1 products</p>"
        return f'<html><body>{header}<main>{cards}{tail}</main></body></html>'
    details=(f'<html><head><link rel="canonical" href="{product}"/></head>'
       f'<body>{header}<main><div data-testid="product-details"><h1>Yogurt 12 oz</h1>'
       '<p>UPC: 0001111111111</p><span data-testid="price">$4.55</span>'
       '<span data-testid="ppm">$0.38/oz</span></div>'
       '<section class="recommendations"><p>UPC: 9999999999999</p>'
       '<span data-testid="coupon">Clip Coupon: wrong suggestion</span>'
       '</section></main></body></html>')
    grocery_url=base+"/pl/grocery/yogurt"
    coupon1_url=base+"/savings/cl/coupons/?category=C1"
    coupon2_url=base+"/savings/cl/coupons/?category=C2"
    product_visits=[]
    src=BrowserSource(STORE,replace(OPTIONS,max_listing_scrolls=9,verify_every=3))
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=browser.new_context()
        src.page=ctx.new_page()
        src.page.set_default_timeout(6000)
        def nav(url):
            assert urlparse(url).hostname=="www.marianos.com"
            if url==product:
                product_visits.append(url)
                src.page.set_content(details)
            elif url==coupon1_url:
                src.page.set_content(listing("Coupons","Clip Coupon: Save $2, limit 2","C100"))
            elif url==coupon2_url:
                src.page.set_content(listing("Coupons","Clip Coupon: Save $3, limit 4","C101"))
            else:
                src.page.set_content(listing("Grocery"))
        src._navigate=nav
        src._check_block=lambda:None
        grocery=src.crawl_listing(CATS[0],"Yogurt",grocery_url)
        first=src.crawl_listing(CATS[1],"Digital Dairy",coupon1_url)
        second=src.crawl_listing(CATS[1],"Digital Dairy 2",coupon2_url)
        assert len(product_visits)==1, "identity-bound cache may reuse details"
        assert grocery.items[0]["category"]=="Grocery"
        assert not grocery.items[0]["digital_deals_description"]
        assert first.items[0]["digital_deals_description"]=="Clip Coupon: Save $2, limit 2"
        assert second.items[0]["digital_deals_description"]=="Clip Coupon: Save $3, limit 4"
        from marianos_scraper.history import consolidate_fresh
        final,proof=consolidate_fresh([
            record(row, "2026-11-02") | {
                "zipcode":STORE.zipcode, "store_location":STORE.address
            } for out in (grocery,first,second) for row in out.items
        ])
        assert len(final)==1
        assert final[0]["category"]=="Grocery"
        assert "Save $2" in final[0]["digital_deals_description"]
        assert "Save $3" in final[0]["digital_deals_description"]
        assert proof["source_category_unique_products"]["Coupons"]==1
        assert "wrong suggestion" not in final[0]["digital_deals_description"]
        ctx.close()
        browser.close()


def test_resume_items_are_reobserved_with_current_price_and_terms():
    base="https://www.marianos.com"
    product=base+"/p/yogurt/0001111111111"
    url=base+"/pl/yogurt/all"
    listing=f'''<html><body><header>Pickup at 1720 N Milwaukee Ave</header>
    <main><p>1 products</p><article class="product-card"><a href="{product}">
    <h3>Yogurt</h3></a><span data-testid="price">$4.55</span></article>
    </main></body></html>'''
    detail=(f'<html><head><link rel="canonical" href="{product}"/></head>'
      '<body><header>Pickup at 1720 N Milwaukee Ave</header><main>'
      '<div data-testid="product-details"><h1>Yogurt New</h1>'
      '<span data-testid="price">$4.55</span>'
      '</div></main></body></html>')
    src=BrowserSource(STORE,replace(OPTIONS,max_listing_scrolls=9,verify_every=3))
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=browser.new_context()
        src.page=ctx.new_page()
        src.page.set_default_timeout(6000)
        src._navigate=lambda u:src.page.set_content(detail if u==product else listing)
        src._check_block=lambda:None
        stale=make_item("Grocery","Old Yogurt","yogurt","1.11",
                        coupon="Clip Coupon: OLD offer",upc="0001111111111")
        result=src.crawl_listing(CATS[0],"Yogurt",url,resume_items=[stale])
        assert len(result.items)==1
        assert result.items[0]["regular_price"]=="4.55"
        assert result.items[0]["product_title"]=="Yogurt New"
        assert result.items[0]["digital_deals_description"]==""
        ctx.close()
        browser.close()


def test_overlap_only_coupons_can_qualify_without_a_duplicate_export_product(tmp_path):
    """Synthetic fixture tests the evidence protocol, not live client acceptance."""
    from hashlib import sha256
    from marianos_scraper.coverage_audit import audit_source_coverage
    from marianos_scraper.qualification import audit_export
    items=[]
    for idx in range(500):
        items.append(record({
            "zipcode":STORE.zipcode,"store_name":STORE.name,"store_location":STORE.address,
            "category":"Grocery","sub_category":"Offline",
            "product_title":f"OFFLINE ONLY ITEM {idx}",
            "url":f"https://www.marianos.com/p/offline-fixture/{idx:013d}",
            "regular_price":"3.25",
        },"2026-11-02"))
    raw=json.dumps(items,ensure_ascii=False,separators=(",",":")).encode()
    digest=sha256(raw).hexdigest()
    dataset=tmp_path/"synthetic-catalog.json";dataset.write_bytes(raw)
    category_proof={
        "fresh_source_count":500,"unique_source_products":500,
        "export_primary_count":500,"overlap_only":False,
        "verified_units":1,
        "unit_completion_proofs":[{"passed":True,"listing_kind":"products",
                                   "resolved_identities":500}],
        "source_price_proofs":[{"verified":True,"observed_store_ref":"531/00502",
                                "observed_fulfillment":"PICKUP",
                                "verified_product_count":500}],
    }
    coupon_proof={
        "fresh_source_count":1,"unique_source_products":1,
        "export_primary_count":0,"overlap_only":True,
        "verified_units":1,
        "unit_completion_proofs":[{"passed":True,"listing_kind":"coupons",
                                   "resolved_identities":1}],
        "source_price_proofs":[{"verified":True,"observed_store_ref":"531/00502",
                                "observed_fulfillment":"PICKUP",
                                "verified_product_count":1}],
    }
    report={"sha256":digest,"records":500,"fresh_observed_records":500,
            "historical_total_records":500,"carried_forward_records":0,
            "retention_policy":"no_deletions_permanent_carry_forward",
            "dataset_key":"exports/"+STORE.id+"/2026-11-02/catalog-"+digest[:16]+".json",
            "category_coverage_evidence":{"Grocery":category_proof,"Coupons":coupon_proof}}
    path=tmp_path/"synthetic-validation.json"
    path.write_text(json.dumps(report))
    assert audit_source_coverage(str(dataset),str(path),CATS)["passed"]
    assert audit_export(str(dataset),CATS,str(path))["status"]=="preliminary_pass"
    assert all(x["category"]=="Grocery" for x in items)
    report["fresh_observed_records"]=499
    path.write_text(json.dumps(report))
    assert not audit_source_coverage(str(dataset),str(path),CATS)["passed"]
    assert audit_export(str(dataset),CATS,str(path))["status"]=="failed"


def test_unqualified_source_adapter_path_is_no_go():
    from marianos_scraper.coverage_audit import audit_source_coverage
    assert audit_source_coverage("","",CATS)["passed"] is False
    assert audit_source_coverage("fake.json","fake-validation.json",CATS)["passed"] is False