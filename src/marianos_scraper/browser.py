"""Playwright collection engine. Execute only with explicit written permission.

No CAPTCHA solving, stealth/evasion, shadow API access, proxy rotation, or
credentials embedded in the code. Incomplete listings are rejected.
"""
from __future__ import annotations
import logging
from hashlib import sha256
import math
from bs4 import BeautifulSoup
import random
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse,urljoin
from playwright.sync_api import Page, sync_playwright, Error as PlaywrightError
from .config import Category,Store,Options
from .extract import extract_cards, enrich_from_details, finalize_card

LOG=logging.getLogger(__name__)
BLOCKING=re.compile(r"(?:verify\s+(?:that\s+)?you\s+are\s+human|captcha|access\s+denied|automated\s+requests|unusual\s+traffic|temporarily\s+blocked|bot\s+challenge|request\s+blocked)", re.I)
PRODUCT_COUNT=re.compile(r"\b([\d,]+)\s+(?:products|results|items)\b",re.I)

class CrawlFailure(RuntimeError):
    pass
class StoreMismatch(CrawlFailure):
    pass
class Blocked(CrawlFailure):
    pass
class CoverageGap(CrawlFailure):
    pass

@dataclass
class CrawlOutcome:
    items: list[dict]
    proof: str
    observed_count: int | None
    screenshots: list[str]

class BrowserSource:
    def __init__(self,store:Store, options:Options):
        self.store=store
        self.options=options
        self._playwright=None
        self.browser=None
        self.context=None
        self.page:Page|None=None
        self.detail_cache:dict[str,dict]={}
        self.logo_url=""
        self._requests=0
        self._failures=0

    def __enter__(self):
        self._playwright=sync_playwright().start()
        self.browser=self._playwright.chromium.launch(headless=self.options.browser_headless, args=["--disable-dev-shm-usage"])
        self.context=self.browser.new_context(locale="en-US", timezone_id="America/Chicago", viewport={"width":1480,"height":920})
        self.page=self.context.new_page()
        self.page.set_default_timeout(self.options.timeout_ms)
        self._navigate("https://www.marianos.com/")
        self._select_store()
        self.verify_store()
        return self

    def __exit__(self,*exc):
        if self.browser:self.browser.close()
        if self._playwright:self._playwright.stop()

    def _assert_response(self,response):
        if response is None:
            raise CrawlFailure("navigation returned no response")
        if response.status in (401,403,407,429):
            raise Blocked(f"HTTP {response.status}; stop, do not bypass access restrictions")
        if response.status>=500:
            raise CrawlFailure(f"HTTP {response.status}")
        if response.status>=400:
            raise CoverageGap(f"HTTP {response.status}")
        current = self.page.url
        if urlparse(current).hostname not in ("www.marianos.com","marianos.com"):
            raise Blocked(f"redirect outside approved retailer domain: {urlparse(current).hostname}")
        content=self.page.locator("body").inner_text(timeout=6000)[:6000]
        if BLOCKING.search(content):
            raise Blocked("human verification or access restriction detected")
        if not content.strip():
            raise CrawlFailure("empty body / hydration failure")

    def _navigate(self,url:str):
        if urlparse(url).hostname not in ("www.marianos.com", "marianos.com"):
            raise CoverageGap("untrusted off-site URL")
        for attempt in range(3):
            try:
                r=self.page.goto(url, wait_until="domcontentloaded", timeout=self.options.timeout_ms)
                self.page.wait_for_timeout(650)
                self._assert_response(r)
                self._requests+=1
                self._pace()
                return
            except (PlaywrightError,CrawlFailure) as exc:
                if isinstance(exc,(Blocked,CoverageGap)) or "ERR_BLOCKED_BY_ADMINISTRATOR" in str(exc):
                    raise Blocked("access blocked; no retry bypass attempted") from exc
                self._failures+=1
                if attempt==2: raise CrawlFailure(f"navigation failed after retries: {url}: {exc}") from exc
                LOG.warning("navigation_retry",extra={"url":url,"attempt":attempt+1,"error":str(exc)})
                time.sleep(min(2**attempt*2,8)+random.uniform(0,.4))

    def _pace(self):
        if self.options.delay_seconds:
            time.sleep(self.options.delay_seconds)

    def _select_store(self):
        """Store-selection UX varies; ambiguity always fails instead of using default store."""
        if self.verify_store(allow_unselected=True):
            return
        try:
            self.page.locator(self.options.store_selector_button).first.click(timeout=7000)
            input_box=self.page.locator(self.options.store_search_input).first
            input_box.wait_for(state="visible",timeout=7000)
            input_box.fill(self.store.zipcode)
            input_box.press("Enter")
            self.page.wait_for_timeout(1700)
            text=self.store.verification_text.casefold()
            options=self.page.locator(self.options.store_result_selector)
            matching=[]
            for i in range(min(options.count(),50)):
                opt=options.nth(i)
                nearby=opt.locator("xpath=../..").inner_text(timeout=3000).casefold()
                if text in nearby:
                    matching.append(i)
            if len(matching)!=1:
                raise StoreMismatch(f"store selection ambiguous: {len(matching)} results match {self.store.verification_text!r}")
            options.nth(matching[0]).click()
            self.page.wait_for_timeout(1300)
        except StoreMismatch:
            raise
        except Exception as exc:
            # Store could already be selected from current session; proof check decides.
            LOG.info("store_picker_unavailable",extra={"reason":str(exc)[:180]})
        self.verify_store()

    def verify_store(self,allow_unselected:bool=False) -> str:
        proof_nodes=self.page.locator(self.options.store_proof_selector)
        text=""
        for i in range(min(proof_nodes.count(),6)):
            node=proof_nodes.nth(i)
            try:
                if node.is_visible():
                    t=node.inner_text(timeout=4500)
                    if self.store.verification_text.casefold() in t.casefold():
                        text=t;break
            except Exception: continue
        if not text:
            if allow_unselected:return ""
            raise StoreMismatch(f"cannot VERIFY selected store via unique address {self.store.verification_text!r}; refusing collection")
        try:
            logos=self.page.locator('header img[alt*="Mariano"], header a[aria-label*="Mariano"] img')
            if logos.count():
                logo_src=logos.first.get_attribute("src") or logos.first.get_attribute("data-src")
                if logo_src and not logo_src.startswith("data:"):
                    self.logo_url=urljoin("https://www.marianos.com",logo_src)
        except Exception:
            LOG.debug("store_logo_not_observed")
        LOG.info("store_verified",extra={"store":self.store.id,"proof":text[:200]})
        return " ".join(text.split())[:480]

    def screenshot_proof(self)->bytes:
        """Evidence only after a current, visible, unique store check succeeds."""
        self.verify_store()
        return self.page.screenshot(type="png",full_page=False)

    def discover_units(self,category:Category) -> list[tuple[str,str]]:
        """Conservatively walk subdepartment landing pages to configured depth.

        Only child /d/ paths of the configured root can be recursively visited.
        /pl/ and /q/ listings are work units, never off-domain URLs.
        Failure to discover a listing is a coverage gap, not an empty category.
        """
        root_path=urlparse(category.url).path.rstrip("/")
        if root_path.startswith(("/pl/","/q/")):
            self._navigate(category.url)
            self.verify_store()
            return [(category.name,category.url)]
        max_depth=self.options.max_subcategory_depth
        to_visit=[(category.url,0)]
        visited=set()
        discovered={}
        while to_visit:
            landing,depth=to_visit.pop(0)
            # A repeated landing page or a product-link cycle cannot cause an
            # unbounded crawl through unrelated departments.
            if landing in visited:
                continue
            visited.add(landing)
            if len(visited)+len(discovered)>self.options.category_hard_limit:
                raise CoverageGap(f"category {category.name} exceeded safe discovery limit")
            self._navigate(landing)
            self.verify_store()
            links=self.page.eval_on_selector_all('main a[href], [role="main"] a[href]',
                '''els => els.map(a => ({href:a.href,text:(a.innerText||a.getAttribute('aria-label')||'').trim()}))''')
            for entry in links:
                href=entry.get("href","")
                p=urlparse(href)
                if p.hostname not in ("www.marianos.com","marianos.com"):
                    continue
                path=p.path.rstrip("/")
                sub_name=" ".join((entry.get("text") or "").split())[:120]
                if not sub_name or re.search(r"^(?:shop|view|see)\s+all$",sub_name,re.I):
                    sub_name=category.name + " / Shop All"
                if path.startswith(("/pl/","/q/")):
                    discovered.setdefault(href,(sub_name,href))
                elif (root_path.startswith("/d/") and path.startswith(root_path+"/")
                      and depth < max_depth and href not in visited
                      and all(href!=x[0] for x in to_visit)):
                    to_visit.append((href,depth+1))
                if len(visited)+len(discovered)+len(to_visit)>self.options.category_hard_limit:
                    raise CoverageGap(f"category {category.name} exceeded safe discovery limit")
        if not discovered:
            raise CoverageGap(f"no product-listing subcategories discovered for {category.name}; NOT a legitimate empty category")
        LOG.info("units_discovered",extra={"category":category.name,"units":len(discovered),"landing_pages":len(visited)})
        return list(discovered.values())

    def crawl_listing(self,category:Category, sub_name:str, url:str, progress=None, resume_items=None) -> CrawlOutcome:
        self._navigate(url)
        proof=self.verify_store()
        found:dict[str,dict]={p["url"]:p for p in (resume_items or []) if p.get("url")}
        observed_card_urls=set(found)
        displayed_total=None
        scroll_count=0
        page_count=0
        visited={self.page.url}
        # Many categories use infinite loading, some use explicit pagination.
        # Both must complete before the unit is durably committed.
        while True:
            page_count+=1
            if page_count>80:
                raise CoverageGap(f"pagination exceeded 80 pages: {url}")
            stable=0
            for n in range(self.options.max_listing_scrolls):
                self._check_block()
                html=self.page.content()
                before=len(found)
                # Count all actually linked retailer products, including approximate-weight
                # products that must be excluded from the final JSON.
                scope=BeautifulSoup(html,"html.parser").select_one("main")
                if scope:
                    for link in scope.select('a[href*="/p/"]'):
                        observed_card_urls.add(urljoin("https://www.marianos.com",str(link.get("href") or "")).split("?",1)[0])
                for item in extract_cards(html,category.name,sub_name):
                    prev=found.get(item["url"])
                    if prev is None:
                        found[item["url"]]=item
                    elif not prev.get("upc") and item.get("upc"):
                        found[item["url"]]=item
                if progress and len(found)!=before and n%5==0:
                    progress([finalize_card(x) for x in found.values()])
                if displayed_total is None:
                    m=PRODUCT_COUNT.search(self.page.locator("main").inner_text(timeout=5000)[:4000]) if self.page.locator("main").count() else None
                    if m:displayed_total=int(m.group(1).replace(",",""))
                if n and len(found)==before:stable+=1
                else:stable=0
                if n and scroll_count%self.options.verify_every==0:
                    proof=self.verify_store()
                load_more=self.page.get_by_role("button",name=re.compile(r"^(?:load|show|view)\s+more",re.I))
                if load_more.count() and load_more.first.is_visible() and load_more.first.is_enabled():
                    load_more.first.click(timeout=6000)
                    self._pace();stable=0
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(650)
                scroll_count+=1
                if stable>=4:break
            else:
                raise CoverageGap(f"listing failed to settle after {self.options.max_listing_scrolls} scrolls for {url}")
            proof=self.verify_store()
            next_link=self.page.locator('main a[rel="next"], main nav[aria-label*="agination"] a[aria-label*="Next"], main a[aria-label="Next page"]')
            next_button=self.page.locator('main nav[aria-label*="agination"] button[aria-label*="Next"], main button[aria-label="Next page"]')
            if next_link.count() and next_link.first.is_visible():
                next_href=next_link.first.get_attribute("href")
                next_url=urljoin(self.page.url,next_href or "")
                if next_url==self.page.url or next_url in visited:
                    raise CoverageGap(f"pagination loop detected: {next_url}")
                if urlparse(next_url).hostname not in ("www.marianos.com","marianos.com"):
                    raise CoverageGap("pagination attempted an external link")
                visited.add(next_url)
                self._navigate(next_url)
                self.verify_store()
                continue
            if next_button.count() and next_button.first.is_visible() and next_button.first.is_enabled():
                before_url=self.page.url
                before_html=sha256(self.page.content().encode()).hexdigest()
                next_button.first.click(timeout=6000)
                self.page.wait_for_timeout(1000)
                after_html=sha256(self.page.content().encode()).hexdigest()
                if before_html==after_html:
                    raise CoverageGap("next page control did not change content")
                self.verify_store()
                continue
            break
        if not found:
            raise CoverageGap(f"zero products on {url}; blocked/empty not accepted")
        if displayed_total is not None and len(observed_card_urls)<max(1,math.ceil(displayed_total*0.90)):
            raise CoverageGap(f"silent truncation on {url}: {len(observed_card_urls)} observed product cards vs {displayed_total} displayed products (before approximate-weight exclusions)")
        proof=self.verify_store()
        items=[]
        for k,original in enumerate(found.values(),start=1):
            product=dict(original)
            if self.options.max_detail_pages and k<=self.options.max_detail_pages:
                if k%self.options.verify_every==0:
                    proof=self.verify_store()
                cached=self.detail_cache.get(product["url"])
                if cached is None and product.get("_fully_enriched"):
                    cached=product
                if cached is None:
                    self._navigate(product["url"])
                    self.verify_store()
                    details=self.page.content()
                    self._check_block()
                    cached=enrich_from_details(dict(product),details)
                    self.detail_cache[product["url"]]=cached
                product=dict(cached)
                # Detailed product parsing may exclude approximate-weight items.
                if not product:continue
            else:
                product=finalize_card(product)
            if product:
                product.pop("_fully_enriched",None)
                items.append(product)
        self.verify_store()
        LOG.info("listing_complete",extra={"category":category.name,"sub_category":sub_name,"url":url,"count":len(items),"displayed_total":displayed_total,"scrolls":scroll_count,"pages":page_count})
        return CrawlOutcome(items=items,proof=proof,observed_count=displayed_total,screenshots=[])

    def _check_block(self):
        text=self.page.locator("body").inner_text(timeout=6000)[:5000]
        if BLOCKING.search(text):
            raise Blocked("retailer denied request or challenge appeared")
        if urlparse(self.page.url).hostname not in ("www.marianos.com","marianos.com"):
            raise Blocked("retailer page redirected to unknown host")