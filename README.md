# Mariano's Azure catalog collector

**v0.5.1 client-review amendment build — cross-platform offline-tested; NOT retailer-qualified or Azure-deployed.**

This is runnable source code with a Playwright browser collector, category discovery from the client's *entire* 28-category CSV, location guardrails, exact JSON schema, checkpoints, a two-days-per-week Azure Container Apps Job recipe, Azure Blob immutable exports, and last-known-good publication. It has offline automated tests, including a real Chromium/Playwright DOM integration test. It is **not** a retailer-observed 500-record contest submission or evidence of live retailer or Azure qualification.

## November 4 independent evidence-boundary checkpoint

See [the GitHub source/CI audit and separate production evidence tracks](docs/CLIENT_EVIDENCE_BOUNDARIES_20261104.md)
and the [machine-readable present-state register](release/evidence-register-20261104.json).
Three GitHub jobs were rechecked directly: 82 offline tests and source/wheel
builds passed on each runner. This does **not** establish observed Vernon
Hills/PICKUP source prices, full category/coupon collection, live recovery,
Azure execution, contest entry or award eligibility. The `release-check`
output now includes separate `evidence_domains`. Production status remains
**NO_GO** while client-side authorization/access is pending.

## v0.5.1 - client review amendments (2026-11-03)

See [detailed client review amendment and release status](docs/CLIENT_REVIEW_20261103.md).
Five client findings were addressed in source and synthetic regression tests:
(1) permanent previous-catalog retention with a SHA-256-checked historical
lineage sidecar, first/last observation dates, and fresh-vs-carried counts;
(2) valid partial checkpoints with subcategory and fresh re-observation;
(3) same-session first-party store-ref/fulfillment/product-price source
binding plus canonical product-specific detail fields; (4) uncapped detail
traversal with fail-closed optional safety limits; and (5) identity-bound
detail patch caching, coupon term aggregation and independent category
coverage evidence without manufactured duplicate products.

**Acquisition:** direct permission-gated Playwright Chromium, NOT Walmart
Classic Oxylabs API. The new typed price-source evidence parser is an
**unqualified integration contract**: the real first-party JSON schema,
approved response paths, selected store ID and fulfillment must be established
from an authorized observed source session. Until then the live browser
stops before collection rather than guessing IDs or accepting prices.

The client's demo location is **1720 N Milwaukee Ave, Vernon Hills, IL
60061**. Public retailer directory URL:
https://www.marianos.com/stores/grocery/il/vernon-hills/marianos-vernon-hills/531/00502
The directory's `531/00502` path is NOT a verified source-pricing
session ID. `release/store-vernon-hills-directory-candidate.json` records
its unverified status. No actual Mariano's contest entry number is known.

The scraper is still **NO_GO for live production acceptance** without
written rights, observed price-source adapter, genuine 500+ records,
coupon coverage, Azure run, independent client review and walkthrough.

## v0.5.0 positive-coverage and coupon safeguards (2026-11-02)

See [the v0.5.0 evidence and acceptance runbook](docs/V050_POSITIVE_COVERAGE_AND_RELEASE.md).
The collector now requires a **retailer-observed positive end-of-results signal**
before a browser unit can be checkpointed or published: exact source-displayed
counts or explicit retailer terminal control, plus settled bottom-of-page
navigation and full source-card reconciliation. No more 90% count tolerance.
Coupon pages require directly linked products with a stable offer identity
and full digital activation terms; otherwise the job fails. Observed
promotion strings longer than 400 characters are no longer discarded.
The selected-store picker now distinguishes individual result rows from the
global picker. Authorized walkthrough recording can be opted into using
`MARIANOS_ACCEPTANCE_VIDEO_DIR` on a private writable disk.

This remains **NO_GO** for live/contest acceptance without signed website
collection authorization, assigned store selection, authentic 500+ product
data, complete category/coupon proof, actual Azure execution, independent
review and a genuine walkthrough. Offline tests DO NOT fill those gaps.

## Important permission boundary

As of September 9, 2026, Kroger/Mariano's website terms explicitly prohibit automated site collection, including scrapers, crawlers and bots, and attempts to circumvent restrictions. Kroger Public Products API access **does not itself** grant permission to systematically harvest products into a historical price database; review the API's separate acceptable-use rules. Obtain affirmative written authorization, partner/licensed dataset rights or another approved commercial contract covering automated extraction, storage and intended downstream use **before enabling live collection**. This code stops on challenges and access denials; it contains no bypasses, impersonation, stealth plugin or proxy rotation. The CLI refuses live operation unless both `MARIANOS_AUTHORIZED=true` and `MARIANOS_APPROVAL_REFERENCE=<written authorization reference>` are present. Setting these values is an operator attestation, *not* a substitute for actual rights.

Official terms: https://www.marianos.com/i/terms/website-and-app
Official API policy: https://developer.kroger.com/documentation/public/getting-started/acceptable-use

## What runs today

- Parses all 28 required category URL rows in `config/Marianos_Category_URLs.csv` (copied exactly from client attachment); supports multiple configured stores.
- Chooses store from a ZIP-code search and checks a unique visible address, before and repeatedly during collection. Fails closed on ambiguous selection or drift.
- Discovers category landing-page shopping links; visits direct `/pl/` and `/q/` category URLs, scrolls lazy-loaded lists, supports explicit pagination, waits with bounded delays, retries transient navigation errors, stops on HTTP 401/403/429 and challenge text.
- Extracts product titles, displayed weights, regular/sale price, UPC when explicitly provided, displayed PPM with its unit, original product/image URLs, private-label status and distinctly classified volume/digital offers. Never calculates PPM, GUPC, unit price, BOGO per-unit prices or a final coupon price from savings wording.
- Excludes approximate-weight products and prevents duplication by original UPC or product URL within each store; captures category-level raw counts separately.
- Records per-subcategory durable checkpoints and resumes completed units without re-scraping them. Partial scroll-stage checkpoints are saved periodically. A failed run retains the latest successful pointer.
- Compares overall and category yield with the last successful run, requires every requested category to pass, detects disappeared subcategories, validates canary URLs when configured, and preserves store proof text + screenshot keys.
- Produces deterministic ordered JSON (22 string fields), validation JSON, SHA-256, structured stdout logs and slot status.
- Provides a once-per-store Azure Blob lease and conditionally updated latest pointer, plus Azure Container Apps Job twice-weekly schedule and Azure managed identity/RBAC deployment script.

## Not yet proven; production and contest signoff blocked

- **Written retailer authorization / licensed access** is not supplied. No live retailer scraping was performed.
- **Store identifiers and assignment** were not supplied. All configured stores must be verified before starting.
- **Actual page selector compatibility** (including the ZIP/store picker) is unobserved against Mariano's live DOM, and real subcategory traversal requires an authorized acceptance run. DOM changes will need selector adjustments.
- **Coupons** is a separate coupon promotion surface; if it does not provide a reliable mapping from coupon to product URL/UPC and store scope, coverage intentionally fails instead of inventing deals or falsely passing. All 28 categories must pass to publish.
- No Azure subscription/resource group/Container Apps environment/ACR/Blob account access was provided. Deployment script was built, but Azure deployment was not performed.
- No 500+ real product records, real store screenshots, offer comparison, real costs, production timing or repeat-run proof are claimed.

Do **not** present unit fixtures as scraped retailer data. They are created solely for functional testing. A pass on offline tests does not certify a production scraper.

## Local setup

Use Python 3.11+ and Chromium:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
python -m playwright install chromium
cp config/stores.yaml.example config/stores.yaml
# Edit: real ID, ZIP, full street, store name and unique header verification_text.
marianos-scrape check-config --settings config/stores.yaml
pytest -q
```

For an **authorized, controlled** local test (not allowed without permission):

```bash
export MARIANOS_AUTHORIZED=true
export MARIANOS_APPROVAL_REFERENCE='YOUR_SIGNED_APPROVAL_OR_PARTNER_AGREEMENT_ID'
export SCRAPER_STORAGE=local
export SCRAPER_DATA_DIR='./local-state'
marianos-scrape run --settings config/stores.yaml
```

Run a previous slot to resume interrupted units, using the exact original Monday/Thursday slot:

```bash
marianos-scrape run --settings config/stores.yaml --slot 2026-10-15
```

`--force` deliberately repeats the source collection for the same slot, and is intended for authorized acceptance/regression testing. It still uses validation and does not bypass publication gates.

Independently check a finished JSON artifact:

```bash
marianos-scrape verify-export --file local-state/exports/STORE/SLOT/catalog-HASH.json
```

## Azure deployment (existing environment)

See `docs/AZURE_DEPLOYMENT.md` and `azure/deploy.sh`. The script builds a versioned image in the existing ACR, uploads the validated store settings as a private Azure Blob object, assigns minimal managed-identity access and creates a scheduled job **only after approval**. It does not invent Azure credentials or environments. Cron is `0 16 * * 1,4` UTC = Monday and Thursday morning in Chicago (10/11 AM depending on DST). It runs one replica, with a separate per-store Azure Blob lease as the overlap barrier.

Output storage structure:

```text
config/stores.yaml                                        # private operator config
locks/<store-id>.lock                                    # server lease
runs/<store-id>/<slot>/discovery/<hash>.json             # identified work units
runs/<store-id>/<slot>/units/<hash>.json                 # resumable completed units
runs/<store-id>/<slot>/proof/store-{start,end}.png       # location proof screenshots
runs/<store-id>/<slot>/FAILED.json                       # optional failure audit
exports/<store-id>/<slot>/catalog-<hash>.json            # versioned immutable successful dataset
exports/<store-id>/<slot>/validation-<hash>.json         # evidence / validation
published/<store-id>/latest.json                         # atomic pointer, success only
```

Consumers must load `published/<store-id>/latest.json`, inspect `status=passed` and read `dataset_key`, *not* rely on a mutable `latest.json` dataset overwritten by any cron execution.

## Exact schema and downstream boundary

All 22 fields appear in the required order:

`zipcode; store_name; store_location; store_logo; store_brand; category; sub_category; product_title; weight; regular_price; sale_price; volume_deals_description; volume_deals_price; digital_deals_description; digital_deals_price; image_url; url; upc; gupc; ppm; unit_price; crawl_date`

All values are strings, missing values are `""`, prices (where explicit) are `N.NN`, `gupc` and `unit_price` always `""`, PPM keeps the retailer-displayed text and unit, UPC is never inferred from URLs, `crawl_date` is the collection date in Chicago, and there are no `remarks` or `gupc14` fields. No weight or product matching normalization is done: those are downstream responsibilities.

For deals, a `2 for $5` displayed bundle price is recorded as `5.00`, **not** a derived `$2.50` unit price; a BOGO without a displayed price has blank deal price; a clipped coupon stating only `Save $2` has blank digital deal price.

## Code ownership and maintainability

Everything in `src/`, `config/`, `azure/`, and `tests/` is readable source; no obfuscated code, remote kill switch, telemetry beacon, required third-party scraping subscription, or hard-coded secrets. The runtime uses public Python packages and Azure services already named in the deployment.

## Release qualification additions (v0.2.0, 2026-10-18)

`release-check` is a read-only operator tool. It checks the unchanged 28-category CSV, validated store YAML, private authorization metadata and signed-file SHA-256, actual JSON coverage and optional Azure execution evidence. **It always reports NO_GO until independent observed acceptance is signed off; do not treat its report as legal advice or retailer authorization.**

```bash
marianos-scrape release-check --settings config/stores.yaml \
  --authorization-file /secure/private/authorization.json \
  --file /secure/private/observed-export.json \
  --azure-proof-file /secure/private/azure-observed-execution.json
./azure/preflight.sh # read-only Azure CLI discovery; fails if CLI/login absent
```

`release/authorization_metadata.example.json` is a **template only**, with intentionally false rights and no signed agreement. `release/stores.candidates.yaml` is public store-page discovery evidence, **not** confirmed live store selection; it is deliberately incompatible with the live `stores.yaml` schema to avoid accidental execution. Confirm physical address, store ID and price locality in an authorized real run.

The audit does not imply true coupon coverage: it checks rows and categories, but coupon-to-UPC mapping, clipping limits, all coupon pages, subcategory enumeration and rendered values must be manually compared with observed retailer evidence. It cannot obtain a vendor's written authorization. This is why final observed acceptance defaults to failure even with all other metadata present.

The connected RND Windows workstation had no Azure CLI installed during this session, and no existing authenticated Azure subscription was identified. No real Azure job was created or run. Tests use synthetic fixtures only and never constitute 500 retailer records.


## Walmart v0.5.7 reliability transfer (Mariano's v0.4.1)

See `docs/WALMART_V057_TRANSFER.md` and `tests/test_walmart_v057_publication_port.py` for source-specific differences, synchronous positive-publication safeguards, filesystem stall/failure regressions and the honest no-hard-wall-clock-deadline contract. CI now runs Linux 3.11/3.12 and Windows 3.12. Walmart Classic Oxylabs and fulfillment logic were not copied. This remains offline engineering evidence only.

## RND Windows qualification (v0.3)

The portable, removal-tracked Windows toolchain is documented in `windows/README.md`. v0.3 fixes Windows local-store file locking without adding global dependencies. CLI and Azure permissions are checked independently; passing offline tests cannot substitute for a real licensed run.

## v0.4.0 engineering qualification (2026-10-18)

- New regression suite: `qa/offline_pytest_v040.txt`, JUnit XML, and machine-readable `qa/acceptance_evidence_v040.json`. Current offline fixture suite: **38/38 passed**. A synthetic 560-record fixture across 28 configured categories is ONLY an engineering simulation, not a scraper result for contest submission.
- Tightened eligible and exported category counts after approximate-weight exclusion and cross-category deduplication. A category missing in the final export fails publication. Cached discovery and completed units must match current URLs. Nested `/d/` landing links are conservatively traversed to configurable depth.
- Live CLI requires signed authorization metadata matching the assigned stores, all required categories, agreement checksum, commercial storage, coupons, frequency and browser collection method. `MARIANOS_AUTHORIZED=true` by itself is no longer sufficient. Azure deployment checks approval evidence before cloud mutations and uploads the approval and metadata privately for managed-identity access.
- Production GO requires authentic observed retailer and Azure execution evidence plus an independently signed review. See `docs/INDEPENDENT_OBSERVED_ACCEPTANCE.md`. The authorizing agreement has not been supplied. The CLI continues to report NO_GO.
- Windows RND baseline was 20/20 on v0.3.1. RND v0.4.1 requalification passed 43/43 offline tests on November 2, 2026. This is not a retailer or Azure production test.