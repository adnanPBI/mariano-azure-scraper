"""Focused client regression: source regular/sale roles must never interchange.

All data are synthetic: no Mariano's network, actual prices, or Azure usage.
"""
from __future__ import annotations

from dataclasses import replace
import copy
import pytest

from marianos_scraper.config import Category, Options, Store
from marianos_scraper.source_context import SourceContextError, SourceResponseLedger

STORE = Store(
    id="fixture-vernon-hills", zipcode="60061", name="Mariano's",
    address="1720 N Milwaukee Ave, Vernon Hills, IL 60061",
    verification_text="1720 N Milwaukee Ave",
    source_store_ref="531/00502", fulfillment_mode="PICKUP",
    price_response_paths=["/offline-fixture/price-response"],
)
PRODUCT = "https://www.marianos.com/p/fixture-yogurt/0001111111111"
SOURCE = "https://www.marianos.com/offline-fixture/price-response"


def bound_ledger(*, regular="5.00", sale="3.00", unpriced=False, missing=()):
    payload = {
        "url": PRODUCT, "upc": "0001111111111",
        "regular_price": regular, "sale_price": sale,
    }
    for field in missing:
        payload.pop(field, None)
    if unpriced:
        payload["unpriced"] = True
    ledger = SourceResponseLedger(STORE)
    response = {
        "schema": "retailer-price-source-v1",
        "store": {"division": "531", "number": "00502"},
        "fulfillment": {"mode": "PICKUP"},
        "products": [payload],
    }
    assert ledger.ingest(SOURCE, response) == 1
    return ledger


def output(*, regular="5.00", sale="3.00"):
    return {
        "url": PRODUCT,
        "upc": "0001111111111",
        "regular_price": regular,
        "sale_price": sale,
    }


def test_correct_regular_and_sale_slots_are_individually_verified():
    ledger = bound_ledger()
    proof = ledger.audit_unit([output()])
    assert proof["verified"] is True
    assert proof["verified_product_count"] == 1
    assert ledger.events["/p/fixture-yogurt/0001111111111"].regular_price == "5.00"
    assert ledger.events["/p/fixture-yogurt/0001111111111"].sale_price == "3.00"


@pytest.mark.parametrize("regular,sale,wrong_slot", [
    ("3.00", "5.00", "regular_price"),  # exact client bug: same set, reversed roles
    ("3.00", "", "regular_price"),      # regular cannot inherit correct sale
    ("", "5.00", "sale_price"),         # sale cannot inherit correct regular
    ("6.00", "3.00", "regular_price"),
    ("5.00", "4.00", "sale_price"),
])
def test_swapped_or_wrong_value_slot_fails_audit_unit(regular, sale, wrong_slot):
    ledger = bound_ledger()
    item = output(regular=regular, sale=sale)
    before = copy.deepcopy(item)
    with pytest.raises(SourceContextError, match=wrong_slot):
        ledger.audit_unit([item])
    assert item == before  # no in-place role correction


@pytest.mark.parametrize("missing_field,regular,sale", [
    ("regular_price", "3.00", ""),  # only source sale=3.00
    ("sale_price", "", "5.00"),     # only source regular=5.00
])
def test_missing_source_role_never_borrows_the_other_role(missing_field, regular, sale):
    ledger = bound_ledger(missing=(missing_field,))
    with pytest.raises(SourceContextError, match="corresponding source " + missing_field):
        ledger.audit_unit([output(regular=regular, sale=sale)])


@pytest.mark.parametrize("source_regular,source_sale,regular,sale,missing_field", [
    ("", "3.00", "3.00", "", "regular_price"),
    ("5.00", "", "", "5.00", "sale_price"),
])
def test_explicit_blank_source_price_role_stays_blank(
    source_regular, source_sale, regular, sale, missing_field
):
    ledger = bound_ledger(regular=source_regular, sale=source_sale)
    with pytest.raises(SourceContextError, match="corresponding source " + missing_field):
        ledger.require_price(output(regular=regular, sale=sale))


def test_missing_output_role_is_not_automatically_inferred_or_inserted():
    ledger = bound_ledger()
    item = output(regular="5.00", sale="")
    assert ledger.audit_unit([item])["verified"] is True
    assert item["sale_price"] == ""


def test_legitimate_sale_only_source_and_output_pass_without_regular_price():
    ledger = bound_ledger(regular="", sale="3.00", missing=("regular_price",))
    assert ledger.audit_unit([output(regular="", sale="3.00")])["verified"]


def test_explicit_unpriced_response_can_verify_blank_product():
    ledger = bound_ledger(regular="", sale="", unpriced=True)
    assert ledger.audit_unit([output(regular="", sale="")])["verified"]


def test_no_output_price_without_source_unpriced_flag_is_rejected():
    ledger = bound_ledger()
    with pytest.raises(SourceContextError, match="unpriced card lacks explicit"):
        ledger.audit_unit([output(regular="", sale="")])


@pytest.mark.parametrize("role", ["regular_price", "sale_price"])
def test_invalid_populated_output_price_is_rejected_not_treated_as_missing(role):
    ledger = bound_ledger()
    item = output()
    item[role] = "Save $1 on two"
    with pytest.raises(SourceContextError, match="invalid displayed " + role):
        ledger.require_price(item)


@pytest.mark.parametrize("role", ["regular_price", "sale_price"])
def test_invalid_nonempty_source_role_rejected_before_binding(role):
    values = {"regular": "5.00", "sale": "3.00"}
    values["regular" if role == "regular_price" else "sale"] = "Save $1"
    with pytest.raises(SourceContextError, match="invalid source " + role):
        bound_ledger(**values)


@pytest.mark.parametrize("swapped", [True, False])
def test_browser_crawl_refuses_swapped_prices_before_returning_products(swapped):
    """Actual Chromium, intercepted synthetic HTML, no retailer requests."""
    from playwright.sync_api import sync_playwright
    from marianos_scraper.browser import BrowserSource

    ledger = bound_ledger()
    source = BrowserSource(STORE, replace(
        Options(), max_listing_scrolls=9, delay_seconds=0,
        verify_every=3, max_detail_pages=0,
    ))
    source.source_ledger = ledger
    list_url = "https://www.marianos.com/pl/offline-fixture"
    regular, sale = ("3.00", "5.00") if swapped else ("5.00", "3.00")
    header = "<header>Pickup at 1720 N Milwaukee Ave</header>"
    listing = (
        f'<html><body>{header}<main><p>1 products</p>'
        '<article class="product-card">'
        f'<a href="{PRODUCT}"><h3>Fixture Yogurt</h3></a>'
        f'<span data-testid="regular-price">${regular}</span>'
        f'<span data-testid="sale-price">${sale}</span>'
        '</article></main></body></html>'
    )
    detail = (
        f'<html><head><link rel="canonical" href="{PRODUCT}"/></head>'
        f'<body>{header}<main><div data-testid="product-details">'
        '<h1>Fixture Yogurt 12 oz</h1>'
        '<p>UPC: 0001111111111</p>'
        f'<span data-testid="regular-price">${regular}</span>'
        f'<span data-testid="sale-price">${sale}</span>'
        '</div></main></body></html>'
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context()
            source.page = context.new_page()
            source.page.set_default_timeout(6000)
            source._navigate = lambda url: source.page.set_content(
                detail if url == PRODUCT else listing
            )
            source._check_block = lambda: None
            if swapped:
                with pytest.raises(SourceContextError, match="regular_price"):
                    source.crawl_listing(
                        Category("Grocery", list_url), "Fixture Dairy", list_url
                    )
            else:
                got = source.crawl_listing(
                    Category("Grocery", list_url), "Fixture Dairy", list_url
                )
                assert got.source_evidence["verified"] is True
                assert len(got.items) == 1
                assert got.items[0]["regular_price"] == "5.00"
                assert got.items[0]["sale_price"] == "3.00"
        finally:
            browser.close()
