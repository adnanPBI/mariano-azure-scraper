"""Real Chromium + Playwright against fully intercepted pages; ZERO retailer calls.

An engineering integration test, NOT a harvested dataset or contest evidence.
"""
from shutil import which
from urllib.parse import urlparse,parse_qs
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
from playwright.sync_api import sync_playwright
from marianos_scraper.config import Category,Store,Options
from marianos_scraper.browser import BrowserSource

HEADER='<header>Pickup at Mariano\'s 123 Main Street</header>'
LANDING=f'<html><body>{HEADER}<main><a href="/pl/pasta/123">Pasta & Noodles</a></main></body></html>'
PAGE1=f'''<html><body>{HEADER}<main><h1>Pasta</h1><p>3 results</p>
<article class="product-card"><a href="/p/kroger-shells/0001111111111"><h3>Kroger® Shells</h3></a>
<span data-testid="product-size">16 oz</span><span data-testid="regular-price">$3.99</span><span data-testid="ppm">$0.25/oz</span>
<span data-testid="coupon">Clip Coupon: Save $2, limit 5</span></article>
<article class="product-card"><a href="/p/fish/0002222222222"><h3>Fish</h3></a><span data-testid="product-size">approx. 2 lb</span></article>
<nav aria-label="Pagination"><a rel="next" href="https://www.marianos.com/pl/pasta/123?page=2">Next page</a></nav>
</main></body></html>'''
PAGE2=f'''<html><body>{HEADER}<main><h1>Pasta</h1>
<article class="product-card"><a href="/p/pasta-twists/0003333333333"><h3>Twists Pasta</h3></a>
<span data-testid="product-size">8 oz</span><span data-testid="price">$1.50</span>
<span data-testid="deal">Buy 1, Get 1 Free</span></article>
</main></body></html>'''
DETAIL=f'''<html><body>{HEADER}<main><h1>Product Details</h1>
<p>UPC: 0001111111111</p><span data-testid="ppm">$0.25/oz</span></main></body></html>'''

def test_actual_browser_navigation_and_coverage_no_retailer_network():
    store=Store('id','60601',"Mariano's",'123 Main Street, Chicago, IL','123 Main Street')
    options=Options(max_listing_scrolls=12,max_detail_pages=10,delay_seconds=0,verify_every=3)
    source=BrowserSource(store,options)
    visited=[]
    with sync_playwright() as pw:
        try:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        except Exception:
            if which('chromium'):
                browser=pw.chromium.launch(executable_path=which('chromium'),headless=True,args=['--no-sandbox'])
            else:
                pytest.skip('Chromium binary not available in this test runner')
        context=browser.new_context()
        source.page=context.new_page()
        source.page.set_default_timeout(6000)
        # All website navigation is intercepted IN PROCESS with set_content.
        # This exercises browser DOM/pagination extraction, never reaches the internet.
        def local_navigation(url):
            p=urlparse(url)
            assert p.hostname=='www.marianos.com'
            visited.append(url)
            if p.path.startswith('/p/'):html=DETAIL
            elif p.path.startswith('/pl/'):
                html=PAGE2 if 'page=2' in url else PAGE1
            else:html=LANDING
            html=html.replace('<head>', '<head><base href="https://www.marianos.com/">') if '<head>' in html else html.replace('<html>', '<html><head><base href="https://www.marianos.com/"></head>')
            source.page.set_content(html,wait_until='domcontentloaded')
        source._navigate=local_navigation
        source._check_block=lambda:None
        source._navigate('https://www.marianos.com/')
        source.verify_store()
        category=Category('Grocery','https://www.marianos.com/d/grocery')
        units=source.discover_units(category)
        assert units==[('Pasta & Noodles','https://www.marianos.com/pl/pasta/123')]
        outcome=source.crawl_listing(category,units[0][0],units[0][1])
        assert len(outcome.items)==2
        assert outcome.items[0]['upc']=='0001111111111'
        assert outcome.items[0]['ppm']=='$0.25/oz'
        assert outcome.items[0]['digital_deals_description']=='Clip Coupon: Save $2, limit 5'
        assert outcome.items[0]['digital_deals_price']==''
        assert outcome.items[1]['volume_deals_description']=='Buy 1, Get 1 Free'
        assert outcome.items[1]['volume_deals_price']==''
        assert any('page=2' in x for x in visited)
        assert all(urlparse(x).hostname=='www.marianos.com' for x in visited)
        context.close()
        browser.close()