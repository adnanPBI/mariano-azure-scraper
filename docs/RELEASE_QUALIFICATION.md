# Release qualification and contest acceptance gates

**Status: BLOCKED FOR PRODUCTION / NOT A CONTEST-PASSING LIVE SCRAPE.**

Source implementation and offline tests are real. Live retail extraction, permission, 500-record observed output, Azure deployment and full coverage proof have not occurred.

| Requirement | Current evidence | Gate |
|---|---|---|
| 28 input category URLs | Client CSV embedded unchanged; parser test asserts 28 | Implemented locally |
| Full dynamic subcategory inventory | Landing page link discovery, subcategory checkpointing, scroll and next-page logic | Not verified live |
| Store accuracy | Verified address phrase at pickup header, repeated checks; fails closed | Not verified live |
| Product/price/UPC/PPM | DOM extraction, product detail enrichment and tests | Actual site fields unverified |
| Volume vs digital coupons | Conservative rule-based classifier with explicit prices and blank calculated fields | Deal examples require real observation |
| 22 ordered fields | Automated schema validator and unit tests | Passed offline |
| Exclude approximate weight | HTML extraction and validation tests | Passed offline |
| Duplication across categories | Store-level UPC/product URL dedup + duplicate metric | Passed offline |
| Multiple stores | Store YAML and independent lease/output namespaces | Unverified on Azure |
| Twice weekly | Azure Job creation cron Mon/Thu at 16:00 UTC | Script not run in Azure |
| Safe resume | Durable discovery/unit/partial state, restart test | Passed offline |
| Last-good dataset | Versioned exports and conditional publication pointer, failure tests | Passed local backend |
| Silent blocking & thin results | HTTP challenge checks, zero/low-yield gates, canaries, displayed-count checks | Block behavior not site-qualified |
| Actual 500+ live records | No retailer authorization or store provided | BLOCKED |
| Real runtime and cloud costs | No approved observed run | BLOCKED |
| Recorded walkthrough | Not captured | BLOCKED |
| Legal/contractual authorization | Kroger terms prohibit ordinary automated site collection | BLOCKED |
| Azure environment acceptance | No subscription or environment access supplied | BLOCKED |

## Required observed release acceptance

After rights and environment access are supplied, the release must pass all of these with retained evidence:

1. Store-specific picker selects *only* the assigned address/ZIP and retains it across all categories and after detail-page navigation. Test two locations with different prices, where available.
2. Each CSV category is covered, along with every live subcategory. Map coupon offers to product records only when supported by explicit retailer identifiers; never synthesize a product.
3. Collect at least 500 real valid products from one assigned store across multiple categories. Retain timestamped JSON, per-category counts, duplicate/completeness report, real PPM examples, volume/deal wording/price examples, and proof screenshots.
4. Compare random samples of product titles, URLs, UPC, weights, prices, PPM and both deal types to an authorized manual browser session at the same store.
5. Inject interruption during a high-yield category, restart same slot and prove no missing pages; perform a repeated authorized run and compare counts.
6. Trigger blocked, 429, empty category, missing subcategory and store mismatch cases; prove `published/<store>/latest.json` stays on the previous passing catalog.
7. Deploy into target Azure subscription, validate managed identity, private container, scheduling, no overlap, structured logs and real measured runtime/spend.
8. Record a full run walkthrough and obtain client confirmation before calling this a production-ready deliverable.