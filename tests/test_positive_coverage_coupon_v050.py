"""Adversarial source-coverage, coupon and full-term tests: offline only.

All HTML and prices are synthetic; this suite never navigates to a retailer.
"""
from dataclasses import replace
from urllib.parse import urlparse
import pytest
from playwright.sync_api import sync_playwright

from marianos_scraper.coverage import Completion, IncompleteListing, verify_completion
from marianos_scraper.coupons import scan_coupon_cards
from marianos_scraper.browser import BrowserSource, CoverageGap
from marianos_scraper.config import Category, Options, Store
from marianos_scraper.extract import extract_cards, approximate_excluded_urls
from marianos_scraper.promotions import classify


def test_exact_source_total_is_positive_coverage():
    evidence=verify_completion(Completion(3,3,3,False,False,True,pages=2))
    assert evidence["passed"]
    assert evidence["completion_method"]=="retailer_total_exact_match"


def test_prior_90_percent_tolerance_is_now_rejected():
    with pytest.raises(IncompleteListing,match="source-count mismatch"):
        verify_completion(Completion(100,90,90,False,False,True))


@pytest.mark.parametrize("data", [
    Completion(3,3,2,False,False,True),
    Completion(None,3,3,False,False,True),
    Completion(3,3,3,False,False,False),
    Completion(3,3,3,False,False,True,active_next=True),
    Completion(3,3,3,False,False,True,active_load_more=True),
])
def test_absent_positive_proof_never_passes(data):
    with pytest.raises(IncompleteListing):
        verify_completion(data)


def test_explicit_source_end_marker_qualifies_without_count():
    result=verify_completion(Completion(None,4,4,True,False,True))
    assert result["completion_method"]=="retailer_explicit_end_marker"


def test_disabled_final_control_qualifies_without_count():
    result=verify_completion(Completion(None,4,4,False,True,True))
    assert result["completion_method"]=="retailer_disabled_terminal_control"


def test_coupons_need_explicit_unique_identity_link_and_clip_terms():
    html='''<main>
    <article data-coupon-id="C100"><a href="/p/kroger-yogurt/111">Kroger Yogurt</a>
      <span>Clip Coupon: Save $2; limit 5, expires Friday</span></article>
    <article data-coupon-id="C101"><a href="/p/coffee/222">Coffee</a>
      <span>With Digital Coupon: $4.99 each</span></article>
    </main>'''
    scan=scan_coupon_cards(html)
    assert scan.identities==("C100","C101")
    assert len(scan.mappings)==2 and not scan.unresolved
    assert scan.mappings[0].product_urls==("https://www.marianos.com/p/kroger-yogurt/111",)


@pytest.mark.parametrize("card,reason", [
    ('<article data-coupon-id="C1"><span>Clip Coupon: Save $2</span></article>',"no explicit first-party"),
    ('<article><a href="/p/one/111">One</a><span>Clip Coupon: Save $2</span></article>',"no stable first-party"),
    ('<article data-coupon-id="C1"><a href="/p/one/111">One</a><span>Sale $2</span></article>',"no explicit clipping"),
    ('<article data-coupon-id="C1"><a href="https://another-store.example/p/one/111">One</a><span>Clip Coupon: Save $2</span></article>',"no explicit first-party"),
])
def test_opaque_or_offsite_coupon_is_not_product_coverage(card,reason):
    scan=scan_coupon_cards("<main>"+card+"</main>")
    # The missing-ID case doesn't match the selector without a coupon class,
    # making it unqualifiable rather than fabricating an identity.
    if not scan.identities:
        assert not scan.mappings
    else:
        assert scan.unresolved and reason in scan.unresolved[0]


def test_offer_term_over_400_chars_is_preserved_not_truncated():
    long_terms=" Clip Coupon: Save $2 on Kroger yogurt. "+("Valid only while supplies last. " * 25)
    html=f'''<main><article class="product-card">
      <a href="/p/yogurt/111"><h3>Kroger Yogurt</h3></a>
      <span data-testid="regular-price">$4.99</span>
      <span>{long_terms}</span></article></main>'''
    cards=extract_cards(html,"Dairy","Yogurt")
    assert len(cards)==1
    from marianos_scraper.extract import finalize_card
    item=finalize_card(cards[0])
    assert len(item["digital_deals_description"])>400
    assert "while supplies last" in item["digital_deals_description"]


def test_approximate_weight_exclusion_has_raw_link_evidence():
    html='''<main><article class="product-card">
    <a href="/p/fish/123">Fish</a>
    <span data-testid="product-size">approx. 2 lb</span></article></main>'''
    assert "https://www.marianos.com/p/fish/123" in approximate_excluded_urls(html)


def test_positive_coupon_browser_end_to_end_in_intercepted_chromium():
    store=Store("offline-test-store","60640","Mariano's","123 Example St, Chicago, IL","123 Example St")
    opts=Options(max_listing_scrolls=10,max_detail_pages=0,verify_every=2,delay_seconds=0)
    category=Category("Coupons","https://www.marianos.com/savings/cl/coupons/")
    words="Valid at participating locations. "*20
    listing=f'''<html><body><header>Pickup at Mariano's 123 Example St</header>
    <main><h1>Coupons</h1><p>2 coupons</p>
    <article data-coupon-id="M100"><a href="/p/yogurt/0001111111111">Yogurt</a>
      <span>Clip Coupon: Save $2, limit 5. {words}</span></article>
    <article data-coupon-id="M101"><a href="/p/coffee/0002222222222">Coffee</a>
      <span>With Digital Coupon: $4.99 each, limit 3.</span></article>
    <p>You've seen all coupons</p></main></body></html>'''
    source=BrowserSource(store,opts)
    seen=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
        context=browser.new_context()
        source.page=context.new_page()
        source.page.set_default_timeout(5000)
        def fake_navigate(url):
            assert urlparse(url).hostname=="www.marianos.com"
            seen.append(url)
            if "/p/yogurt" in url:
                page='<h1>Kroger Yogurt 16 oz</h1><span data-testid="price">$4.99</span><p>UPC: 0001111111111</p>'
            elif "/p/coffee" in url:
                page='<h1>Ground Coffee</h1><span data-testid="price">$6.99</span><p>UPC: 0002222222222</p>'
            else:
                source.page.set_content(listing)
                return
            source.page.set_content("<html><body><header>Pickup at Mariano's 123 Example St</header><main>"+page+"</main></body></html>")
        source._navigate=fake_navigate
        source._check_block=lambda:None
        units=source.discover_units(category)
        assert len(units)==1 and units[0][1]==category.url
        outcome=source.crawl_listing(category,*units[0])
        assert outcome.coverage["passed"]
        assert outcome.coverage["listing_kind"]=="coupons"
        assert outcome.coverage["observed_identities"]==2
        assert len(outcome.items)==2
        assert len(outcome.items[0]["digital_deals_description"])>400
        assert outcome.items[0]["product_title"]=="Kroger Yogurt 16 oz"
        assert outcome.items[0]["upc"]=="0001111111111"
        assert all(x["digital_deals_description"] for x in outcome.items)
        assert any("/p/coffee" in v for v in seen)
        context.close()
        browser.close()



def test_source_bound_checkpoint_requires_positive_coverage(tmp_path):
    """A forged or legacy complete flag cannot bypass positive end proof."""
    from marianos_scraper.runner import Pipeline
    from marianos_scraper.storage import LocalStorage
    from marianos_scraper.browser import CrawlOutcome

    store=Store("offline-store","60640","Mariano's","123 Example St","123 Example St")
    category=Category("Grocery","https://www.marianos.com/d/grocery")
    class StrictSource:
        requires_positive_coverage=True
        def __init__(self,store,options):self.store=store
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def discover_units(self,cat):
            return [(cat.name,cat.url)]
        def crawl_listing(self,cat,sub,url,progress=None,resume_items=None):
            return CrawlOutcome(
                items=[dict(category=cat.name,sub_category=sub,product_title="OFFLINE fixture",
                            weight="12 oz",regular_price="2.49",sale_price="",
                            volume_deals_description="",volume_deals_price="",
                            digital_deals_description="",digital_deals_price="",
                            image_url="",url="https://www.marianos.com/p/offline/123",
                            upc="",ppm="",store_brand="no")],
                proof="Pickup at 123 Example St",observed_count=1,
                screenshots=[],coverage=None)
    storage=LocalStorage(str(tmp_path))
    options=Options(min_records_per_store=1,min_per_category=1)
    with pytest.raises(CoverageGap,match="positive end"):
        Pipeline(storage,StrictSource).run(store,[category],options,slot="2026-11-02")
    assert storage.get_json("published/offline-store/latest.json") is None


def test_multiple_valid_coupons_for_same_product_keep_both_complete_terms():
    from marianos_scraper.promotions import apply_deals
    from marianos_scraper.coupons import scan_coupon_cards
    html='''<main>
        <article data-coupon-id="C1"><a href="/p/yogurt/1">Yogurt</a>
          <p>Clip Coupon: Save $2 on yogurt, limit 2</p></article>
        <article data-coupon-id="C2"><a href="/p/yogurt/1">Yogurt</a>
          <p>With Digital Coupon $3.99 each, limit 5</p></article>
        </main>'''
    scan=scan_coupon_cards(html)
    assert not scan.unresolved and len(scan.mappings)==2
    item={"digital_deals_description":"","digital_deals_price":""}
    apply_deals(item,[(m.terms,"") for m in scan.mappings])
    assert "limit 2" in item["digital_deals_description"]
    assert "limit 5" in item["digital_deals_description"]


@pytest.mark.parametrize("duplicate", [False, True])
def test_store_picker_requires_one_unique_visible_address_offline(duplicate):
    """Real Chromium DOM interaction, synthetic store selection only."""
    store=Store("offline-001","60640","Mariano's","123 Example St, Chicago","123 Example St")
    source=BrowserSource(store,Options(delay_seconds=0))
    second='''<div class="store-result"><span>123 Example St, Chicago</span>
          <button>Shop This Store</button></div>''' if duplicate else ''
    html=f'''<html><body><header>
      <button id="open" onclick="document.getElementById('modal').hidden=false">Select Store</button>
      <div id="chosen"></div></header>
      <div id="modal" hidden><input placeholder="ZIP code" />
        <div class="store-result"><span>123 Example St, Chicago</span>
          <button onclick="document.getElementById('chosen').innerText='Pickup at 123 Example St'">Shop This Store</button></div>
        {second}
      </div></body></html>'''
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
        context=browser.new_context()
        source.page=context.new_page()
        source.page.set_default_timeout(5500)
        source.page.set_content(html)
        if duplicate:
            from marianos_scraper.browser import StoreMismatch
            with pytest.raises(StoreMismatch,match="ambiguous"):
                source._select_store()
        else:
            source._select_store()
            assert "123 Example St" in source.verify_store()
        context.close()
        browser.close()

def test_coupons_no_direct_mapping_does_not_pass_discovery():
    store=Store("offline-test-store","60640","Mariano's","123 Example St","123 Example St")
    cat=Category("Coupons","https://www.marianos.com/savings/cl/coupons/")
    src=BrowserSource(store,Options())
    class Page:
        def content(self):
            return '<main><article data-coupon-id="C1"><span>Clip Coupon: Save $2</span></article></main>'
        def eval_on_selector_all(self,*_):
            return []
    src.page=Page()
    src._navigate=lambda _:None
    src.verify_store=lambda:'Pickup at 123 Example St'
    with pytest.raises(CoverageGap,match="coupon"):
        src.discover_units(cat)