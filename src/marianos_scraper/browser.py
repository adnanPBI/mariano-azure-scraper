"""Playwright collection engine. Execute only with explicit written permission.

No CAPTCHA solving, stealth/evasion, shadow API access, proxy rotation, or
credentials embedded in the code. Incomplete listings are rejected.
"""
from __future__ import annotations
import logging
import os
from hashlib import sha256
import math
from bs4 import BeautifulSoup
import random
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse,urljoin,parse_qs
from playwright.sync_api import Page, sync_playwright, Error as PlaywrightError
from .config import Category,Store,Options,require_source_context_config
from .extract import extract_cards, extract_detail_fields, apply_detail_fields, finalize_card, approximate_excluded_urls, DetailIdentityError
from .source_context import SourceResponseLedger, SourceContextError
from .coverage import Completion, EXPLICIT_END, verify_completion, IncompleteListing
from .coupons import scan_coupon_cards

LOG=logging.getLogger(__name__)
BLOCKING=re.compile(r"(?:verify\s+(?:that\s+)?you\s+are\s+human|captcha|access\s+denied|automated\s+requests|unusual\s+traffic|temporarily\s+blocked|bot\s+challenge|request\s+blocked)", re.I)
PRODUCT_COUNT=re.compile(r"\b([\d,]+)\s+(?:products|results|items)\b",re.I)
COUPON_COUNT=re.compile(r"\b([\d,]+)\s+(?:coupons|offers)\b",re.I)

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
    coverage: dict | None = None
    source_evidence: dict | None = None

class BrowserSource:
    requires_positive_coverage = True
    requires_source_price_binding = True
    def __init__(self,store:Store, options:Options):
        self.store=store
        self.options=options
        self._playwright=None
        self.browser=None
        self.context=None
        self.page:Page|None=None
        self.detail_cache:dict[tuple[str,str,str],dict]={}
        self.source_ledger:SourceResponseLedger|None=None
        self.logo_url=""
        self._requests=0
        self._failures=0

    def __enter__(self):
        # A public directory URL or local header label does NOT prove that
        # product prices belong to the selected retailer ID/fulfillment.
        require_source_context_config(self.store)
        self.source_ledger=SourceResponseLedger(self.store)
        self._playwright=sync_playwright().start()
        self.browser=self._playwright.chromium.launch(headless=self.options.browser_headless, args=["--disable-dev-shm-usage"])
        context_args={"locale":"en-US","timezone_id":"America/Chicago",
                      "viewport":{"width":1480,"height":920}}
        video_dir=os.getenv("MARIANOS_ACCEPTANCE_VIDEO_DIR","").strip()
        if video_dir:
            # Explicit opt-in only. Browser footage can contain private store
            # and login data; keep output outside the public repository.
            os.makedirs(video_dir,exist_ok=True)
            context_args["record_video_dir"]=video_dir
            context_args["record_video_size"]={"width":1280,"height":800}
        self.context=self.browser.new_context(**context_args)
        self.page=self.context.new_page()
        self.page.set_default_timeout(self.options.timeout_ms)
        # Observe existing authorized browsing responses only. No shadow
        # APIs, independent replay or paid provider requests are made.
        self.context.on("requestfinished",self._capture_source_response)
        self._navigate("https://www.marianos.com/")
        self._select_store()
        self.verify_store()
        return self

    def __exit__(self,*exc):
        # Explicitly close the context before the browser: Playwright writes
        # requested recording evidence only when the context is closed.
        if self.context:self.context.close()
        if self.browser:self.browser.close()
        if self._playwright:self._playwright.stop()

    def _capture_source_response(self, request):
        """Inspect only completed, allowlisted first-party requests in this session.

        The typed observation schema is a contract awaiting real authorized
        Mariano's source qualification. Missing/mismatched responses block
        publication; the source path is NOT guessed from Walmart/Oxylabs.
        """
        ledger=self.source_ledger
        if ledger is None or request.resource_type not in ("xhr","fetch"):
            return
        if not ledger.accepts_response_url(request.url):
            return
        try:
            response=request.response()
            if response is None or response.status!=200:
                raise SourceContextError("configured price source response was unsuccessful")
            ctype=response.header_value("content-type") or ""
            if "json" not in ctype.lower():
                raise SourceContextError("configured price source returned non-JSON data")
            ledger.ingest(response.url,response.json())
        except Exception as exc:
            ledger.mark_rejected(type(exc).__name__ + ": " + str(exc))
            LOG.error("source_price_response_rejected",extra={
                "store":self.store.id,"error":type(exc).__name__,
            })

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
                # Do not match the global header picker against body-wide text.
                # Constrain the address to the nearest visible result card.
                nearby=opt.locator("xpath=..").inner_text(timeout=3000).casefold()
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
        if self.source_ledger and self.source_ledger._rejected:
            raise StoreMismatch(
                "source response contradicted store/fulfillment/price binding: "
                + self.source_ledger._rejected[0]
            )
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

    def _discover_coupon_units(self, category: Category) -> list[tuple[str, str]]:
        """Traverse navigable coupon filters; require direct coupon/product proof.

        A coupon page containing only generic clipping buttons or opaque
        product membership is NOT a qualified product category.
        """
        root_path = urlparse(category.url).path.rstrip("/")
        queue = [(category.url, 0)]
        visited = set()
        units = {category.url: (category.name + " / All Coupons", category.url)}
        saw_source_coupon = False
        while queue:
            landing, depth = queue.pop(0)
            if landing in visited:
                continue
            visited.add(landing)
            if len(visited) + len(queue) > self.options.category_hard_limit:
                raise CoverageGap("coupon filter discovery exceeded configured safety cap")
            self._navigate(landing)
            self.verify_store()
            html = self.page.content() if callable(getattr(self.page, "content", None)) else ""
            scan = scan_coupon_cards(html)
            if scan.unresolved:
                raise CoverageGap("coupons without verified product mapping: " + "; ".join(scan.unresolved[:4]))
            if scan.mappings:
                saw_source_coupon = True
            links = self.page.eval_on_selector_all(
                'main a[href], [role="main"] a[href]',
                """els => els.map(a => ({href:a.href,text:(a.innerText||a.getAttribute('aria-label')||'').trim()}))"""
            )
            for entry in links:
                url = str(entry.get("href") or "")
                parsed = urlparse(url)
                if parsed.hostname not in ("marianos.com", "www.marianos.com"):
                    continue
                path = parsed.path.rstrip("/")
                parameters = parse_qs(parsed.query)
                is_filter = path == root_path and bool({"category", "department", "filter", "cat"} & set(parameters))
                is_child = path.startswith(root_path + "/")
                if not (is_filter or is_child):
                    continue
                if url in visited or url == category.url:
                    continue
                if depth >= self.options.max_subcategory_depth:
                    raise CoverageGap("coupon discovery bound reached with additional filter pages")
                name = " ".join(str(entry.get("text") or "").split())[:120] or "Coupon filter"
                units.setdefault(url, (name, url))
                if not any(p == url for p, _ in queue):
                    queue.append((url, depth + 1))
        if not saw_source_coupon:
            raise CoverageGap(
                "no product-listing subcategories or coupon-to-product mappings found; "
                "opaque coupon landing is NOT coverage"
            )
        return list(units.values())

    def discover_units(self,category:Category) -> list[tuple[str,str]]:
        """Conservatively walk subdepartment landing pages to configured depth.

        Only child /d/ paths of the configured root can be recursively visited.
        /pl/ and /q/ listings are work units, never off-domain URLs.
        Failure to discover a listing is a coverage gap, not an empty category.
        """
        root_path=urlparse(category.url).path.rstrip("/")
        if category.name.casefold()=="coupons" and root_path.startswith("/savings/cl/coupons"):
            return self._discover_coupon_units(category)
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
                elif root_path.startswith("/d/") and path.startswith(root_path+"/"):
                    if depth >= max_depth:
                        raise CoverageGap(f"unvisited child beyond category discovery depth for {category.name}: {href}")
                    if href not in visited and all(href!=x[0] for x in to_visit):
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
        # A partial checkpoint is a restart hint, not fresh source evidence.
        # Reobserve each URL and replace every stale price/offer/field.
        resumed_urls={p["url"] for p in (resume_items or []) if p.get("url")}
        found:dict[str,dict]={}
        LOG.info("partial_recovery_reobserve",extra={"store":self.store.id,
            "items":len(resumed_urls)})
        # Resumed partial products do NOT count as fresh source observations.
        observed_card_urls=set()
        approximate_card_urls=set()
        coupon_mode=category.name.casefold()=="coupons"
        coupon_mappings={}
        coupon_ids=set()
        displayed_total=None
        terminal_seen=False
        disabled_terminal=False
        bottom_confirmed=False
        scroll_count=0
        page_count=0
        visited={self.page.url}
        # Many categories use infinite loading, some use explicit pagination.
        # Both must complete before the unit is durably committed.
        while True:
            page_count+=1
            if page_count>self.options.max_listing_pages:
                raise CoverageGap(f"pagination exceeded configured page safety cap ({self.options.max_listing_pages}): {url}")
            stable=0
            for n in range(self.options.max_listing_scrolls):
                self._check_block()
                html=self.page.content()
                before=len(found) + len(coupon_mappings) + len(observed_card_urls)
                # Count retailer-linked products, including legitimate approximate-
                # weight exclusions. Reject any other unparseable product link.
                scope=BeautifulSoup(html,"html.parser").select_one("main")
                if scope:
                    for link in scope.select('a[href*="/p/"]'):
                        candidate=urljoin("https://www.marianos.com",str(link.get("href") or ""))
                        if urlparse(candidate).hostname in ("www.marianos.com","marianos.com"):
                            observed_card_urls.add(candidate.split("?",1)[0])
                approximate_card_urls.update(approximate_excluded_urls(html))
                if coupon_mode:
                    scan=scan_coupon_cards(html)
                    if scan.unresolved:
                        raise CoverageGap("unmapped or ambiguous coupon cards: " + "; ".join(scan.unresolved[:5]))
                    coupon_ids.update(scan.identities)
                    for mapping in scan.mappings:
                        previous=coupon_mappings.get(mapping.identity)
                        if previous and previous.terms != mapping.terms:
                            raise CoverageGap("coupon terms changed across observed pages: " + mapping.identity)
                        if previous and previous.product_urls != mapping.product_urls:
                            raise CoverageGap("coupon-to-product membership changed during traversal: " + mapping.identity)
                        coupon_mappings[mapping.identity]=mapping
                for item in extract_cards(html,category.name,sub_name):
                    # The newest observed card replaces any prior card fields,
                    # including prices and offer terms. Never reuse stale
                    # partial data solely because its URL reappeared.
                    found[item["url"]]=item
                if progress and len(found)>0 and n%5==0:
                    progress([finalize_card(x) for x in found.values()])
                main_text=self.page.locator("main").inner_text(timeout=5000) if self.page.locator("main").count() else ""
                if displayed_total is None:
                    pattern=COUPON_COUNT if coupon_mode else PRODUCT_COUNT
                    m=pattern.search(main_text[:4000])
                    if m:displayed_total=int(m.group(1).replace(",",""))
                terminal_seen=bool(EXPLICIT_END.search(main_text[-5000:]))
                if n and len(found)+len(coupon_mappings)+len(observed_card_urls)==before:stable+=1
                else:stable=0
                if n and scroll_count%self.options.verify_every==0:
                    proof=self.verify_store()
                load_more=self.page.get_by_role("button",name=re.compile(r"^(?:load|show|view)\s+more",re.I))
                if load_more.count() and load_more.first.is_visible():
                    if load_more.first.is_enabled():
                        load_more.first.click(timeout=6000)
                        self._pace();stable=0
                    else:
                        disabled_terminal=True
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(650)
                at_bottom=self.page.evaluate(
                    "Math.ceil(window.scrollY + window.innerHeight) >= document.documentElement.scrollHeight - 4"
                )
                scroll_count+=1
                if stable>=4 and at_bottom:
                    bottom_confirmed=True
                    break
            else:
                raise CoverageGap(f"listing failed to settle after {self.options.max_listing_scrolls} scrolls for {url}")
            proof=self.verify_store()
            next_link=self.page.locator('main a[rel="next"], main nav[aria-label*="agination"] a[aria-label*="Next"], main a[aria-label="Next page"]')
            next_button=self.page.locator('main nav[aria-label*="agination"] button[aria-label*="Next"], main button[aria-label="Next page"]')
            if next_link.count() and next_link.first.is_visible():
                next_href=next_link.first.get_attribute("href")
                if next_link.first.get_attribute("aria-disabled")=="true" or not next_href:
                    disabled_terminal=True
                else:
                    next_url=urljoin(self.page.url,next_href)
                    if next_url==self.page.url or next_url in visited:
                        raise CoverageGap(f"pagination loop detected: {next_url}")
                    if urlparse(next_url).hostname not in ("www.marianos.com","marianos.com"):
                        raise CoverageGap("pagination attempted an external link")
                    visited.add(next_url)
                    self._navigate(next_url)
                    self.verify_store()
                    bottom_confirmed=False
                    disabled_terminal=False
                    continue
            if next_button.count() and next_button.first.is_visible():
                if next_button.first.is_enabled():
                    before_html=sha256(self.page.content().encode()).hexdigest()
                    next_button.first.click(timeout=6000)
                    self.page.wait_for_timeout(1000)
                    after_html=sha256(self.page.content().encode()).hexdigest()
                    if before_html==after_html:
                        raise CoverageGap("next page control did not change content")
                    self.verify_store()
                    bottom_confirmed=False
                    disabled_terminal=False
                    continue
                disabled_terminal=True
            break
        if coupon_mode:
            if not coupon_mappings or set(coupon_mappings)!=coupon_ids:
                raise CoverageGap("coupon list had no complete coupon-to-product mappings")
            authorized_products={}
            for mapping in coupon_mappings.values():
                for product_url in mapping.product_urls:
                    item=dict(authorized_products.get(product_url) or found.get(product_url) or {
                        "category":category.name,"sub_category":sub_name,
                        "product_title":"","weight":"","regular_price":"","sale_price":"",
                        "volume_deals_description":"","volume_deals_price":"",
                        "digital_deals_description":"","digital_deals_price":"",
                        "image_url":"","url":product_url,"upc":"","ppm":"","store_brand":"no"
                    })
                    # The coupon card heading is NOT sufficient evidence of
                    # the linked product's actual name: read its detail page.
                    item["product_title"]=""
                    # Coupon mapping terms replace incidental card-offer text
                    # to avoid inserting the same coupon twice.
                    offers=list(authorized_products.get(product_url,{}).get("_offers",[]))
                    if (mapping.terms,"") not in offers:
                        offers.append((mapping.terms,""))
                    item["_offers"]=offers
                    authorized_products[product_url]=item
            found=authorized_products
            observed_identity_count=len(coupon_ids)
            resolved_identity_count=len(coupon_mappings)
        else:
            parsed_urls={k.split("?",1)[0] for k in found}
            stale=parsed_urls-observed_card_urls
            unresolved=observed_card_urls-parsed_urls-approximate_card_urls
            if stale:
                raise CoverageGap(f"resume has products absent from freshly observed listing: {sorted(stale)[:4]}")
            if unresolved:
                raise CoverageGap(f"unparseable product identities, not legitimate weight exclusions: {sorted(unresolved)[:4]}")
            observed_identity_count=len(observed_card_urls)
            resolved_identity_count=len(observed_card_urls & (parsed_urls|approximate_card_urls))
        try:
            coverage=verify_completion(Completion(
                source_total=displayed_total,
                observed_identities=observed_identity_count,
                resolved_identities=resolved_identity_count,
                explicit_end=terminal_seen,
                disabled_terminal_control=disabled_terminal,
                stable_at_bottom=bottom_confirmed,
                pages=page_count,
                listing_kind="coupons" if coupon_mode else "products",
            ))
        except IncompleteListing as exc:
            raise CoverageGap(f"no positive end-of-list proof for {url}: {exc}") from exc
        proof=self.verify_store()
        if self.options.max_detail_pages and len(found)>self.options.max_detail_pages:
            raise CoverageGap(
                f"detail-page cap {self.options.max_detail_pages} is insufficient "
                f"for {len(found)} products; refusing partial enrichment"
            )
        items=[]
        for k,original in enumerate(found.values(),start=1):
            product=dict(original)
            if k%self.options.verify_every==0:
                proof=self.verify_store()
            # Cache ONLY product-identity-bound detail facts. Never cache the
            # whole category-specific dict or coupon terms: these must come
            # from the fresh work unit, including multiple coupon filters.
            cache_key=(self.store.id,self.store.fulfillment_mode,
                       product["url"].split("?",1)[0])
            detail_patch=self.detail_cache.get(cache_key)
            if detail_patch is None:
                self._navigate(product["url"])
                if urlparse(self.page.url).hostname in ("marianos.com","www.marianos.com"):
                    if urlparse(self.page.url).path.rstrip("/") != urlparse(product["url"]).path.rstrip("/"):
                        raise CoverageGap("product-detail redirect changed canonical identity")
                self.verify_store()
                details=self.page.content()
                self._check_block()
                detail_patch=extract_detail_fields(details,product["url"])
                self.detail_cache[cache_key]=detail_patch
            product=apply_detail_fields(product,detail_patch)
            if product:
                product.pop("_fully_enriched",None)
                items.append(product)
        self.verify_store()
        source_proof=self.source_ledger.audit_unit(items) if self.source_ledger else None
        LOG.info("listing_complete",extra={"category":category.name,"sub_category":sub_name,"url":url,"count":len(items),"displayed_total":displayed_total,"scrolls":scroll_count,"pages":page_count})
        return CrawlOutcome(items=items,proof=proof,observed_count=displayed_total,
                            screenshots=[],coverage=coverage,source_evidence=source_proof)

    def _check_block(self):
        text=self.page.locator("body").inner_text(timeout=6000)[:5000]
        if BLOCKING.search(text):
            raise Blocked("retailer denied request or challenge appeared")
        if urlparse(self.page.url).hostname not in ("www.marianos.com","marianos.com"):
            raise Blocked("retailer page redirected to unknown host")