# Mariano's v0.5.1 - Client five-point review and release decision

Reference: client review of v0.5.0 commit
`17eee0374becd578a708a547e1f6d798769ce944`, supplied
2026-11-03.

**Current evidence is offline only; source adapter remains unqualified.**
All products used in automated tests are synthetic fixture records. There is
no actual 500-product Mariano's crawl, live coupon-to-UPC audit or Azure job.

## 1. Permanent historical retention and source observation dates

- New `history.py` loads the previous immutable dataset through
  `published/<store>/latest.json`, verifies store/ZIP/address and SHA-256
  before every new publication, and refuses corrupted/missing previous data.
- Every authentic old product not re-observed remains in the new export,
  including missing, temporarily unavailable and blank-priced products.
- Source-observed products get current observed prices and crawl date;
  carried records keep their original scraped row and crawl date.
- A separate immutable `history-<digest>.json` lineage sidecar records
  first_seen, last_seen, original_crawl_date, observation_count and
  fresh_observed / fresh_observed_unpriced / carried_forward_unobserved.
- The 22-field JSON contract is unchanged. Reports break down fresh,
  new, refreshed, carried, carried unpriced and historical totals.
- Source yield checks run before history union; old rows cannot hide failed
  or unexpectedly thin category collection. No delete/prune operation exists.

## 2. Partial checkpoint recovery

- Partial `on_progress` checkpoints now include exact `subcategory`.
- Restart validates store/category/subcategory/URL, passes checkpoint
  items as restart hints, then reobserves current listing cards. Old
  prices and offers do not survive merely because a URL matches.
- Completed source units require positive pagination proof and source
  context before they can be reused. Synthetic interrupted-listing and
  updated-price tests are included.
- A failed run cannot advance the last-good publication pointer.

## 3. Store ID/fulfillment and product-specific source binding

- Public location page: Mariano's Vernon Hills at 1720 N Milwaukee Ave,
  IL 60061, with directory path `531/00502`:
  https://www.marianos.com/stores/grocery/il/vernon-hills/marianos-vernon-hills/531/00502
- This is a *directory candidate*, not a verified shopping-session
  store ID. No session trace has been provided.
- New `source_context.py` checks source-returned division/number,
  fulfillment mode, exact product URL, and explicitly returned product
  prices/UPC from the SAME first-party XHR/fetch response observed by
  the Playwright session. Headers/config labels are not sufficient.
- The current typed schema `retailer-price-source-v1` is a STRICT
  normalized adapter contract used only by synthetic tests. It is
  NOT claimed to be Mariano's actual response schema. Authorized
  source discovery must map and qualify a true first-party response
  and approved response path before enabling production. Otherwise
  BrowserSource fails closed, so no invented store ID or prices pass.
- Detail extraction now binds to the requested canonical product URL
  or verified matching detail container; rejects mismatched JSON-LD,
  recommendation products, page-global UPC/PPM/offers and redirects.

## 4. Complete details

- `max_detail_pages=0` means **uncapped full product-detail visits**,
  not disabled detail browsing.
- A positive finite ceiling causes an explicit `CoverageGap` if
  observed product count exceeds it. All eligible products must be
  detail-checked before success.
- Identity-bound detail records are scoped to one exact product; the
  page is never enriched from unrelated recommended product JSON-LD.
- The existing store/price evidence gate still blocks publication if
  any genuine product lacks bound context and source values.

## 5. Coupon caching and global deduplication

- Product detail cache holds ONLY exact product-bound detail patches,
  keyed by (store, fulfillment, canonical product URL). It cannot
  overwrite fresh category assignment or newly observed coupon terms.
- Product appearing in catalog + many coupon filters gets a single
  canonical export record, with complete nonconflicting coupon terms
  merged from source observations.
- Report retains independent source category and coupon listing evidence
  even when all coupons overlap catalog products; it never manufactures
  an extra duplicate export row simply to populate the Coupons category.
- A prior synthetic test that expected a duplicate-only unrelated
  category to fail continues to fail unless independently source-proven.
- New `coverage_audit.py` validates a REAL observed export/report pair,
  including 500 **fresh** records (carried history does not substitute),
  source count/category proof, location/price context, and exact
  dataset SHA-256. `release-check` gains
  `--source-coverage-file <real-validation-report>`.

## Acquisition route clarification

The currently implemented route is a **direct Playwright Chromium browser**
visiting authorized first-party Mariano's pages. Intercepted synthetic
Chromium tests demonstrate DOM behavior, not live website compatibility.
This code does NOT use the Walmart Oxylabs Classic Web Scraper API, and
the client's Walmart Oxylabs entitlement cannot be assumed to cover
Mariano's. A source-specific Classic or licensed feed adapter would be
a separately scoped integration, requiring approved credentials, scope,
cost/rates and observed response format.

No live website requests, credentials or paid Azure resources were used
to qualify this release. Kroger/Mariano's terms restrict automated
collection without appropriate permission:
https://www.marianos.com/i/terms/website-and-app

## Contest-entry status

A Mariano's contest entry number has NOT been provided or independently
verified. A GitHub repository, passing CI and an accepted MVP review are
NOT proof of a registered contest entry or award eligibility. Request
the actual contest submission URL/number from the entrant/platform.

## Acceptance blockers that the code cannot resolve without outside access

1. Written website/browser commercial collection authorization covering
   products, prices, coupon terms, historical retention and source scope.
2. Client-confirmed fulfillment mode and observed first-party Vernon Hills
   session store ID; independently qualified real price response mapping.
3. Authorized observed catalog and coupon capture, 500+ unique genuine
   fresh records, source PPM/offers and full department/subcategory proof.
4. Client Azure subscription, approved budget, attended job execution,
   actual logs, storage readbacks, interruption/repeat-run proof.
5. Independent client review, authentic walkthrough recording and an
   actual Mariano's contest entry number/eligibility confirmation.

**No production-GO certification** may be issued from fixture tests alone.