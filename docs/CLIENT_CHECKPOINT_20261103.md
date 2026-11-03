# Mariano's — November 3, 2026 independent checkpoint

## Source and offline results

- Source HEAD verified before this documentation change: `5c6d9060dd95680b6a558a8b0b4d080325835e0b` (v0.5.1).
- Baseline GitHub Actions run: `41634406120`, success.
- Independent RND Windows Python 3.12 offline run on November 3: **82 passed, 0 failed** in 36.11 seconds. The full run uses local/Chromium fixtures, not live retailer collection.
- Existing fixes: historical unavailable/later-missing retention with source dates and integrity hashes; partial subcategory restart and fresh reobservation; explicit store/fulfillment/product-specific source binding; uncapped detail visits; complete coupon deduplication and terms.
- Original 28 required category rows and ordered 22-field output schema remain unchanged.

## Independent production gates

1. Written Mariano's collection and historical retention authorization. Walmart's Classic Oxylabs credentials and entitlement do not grant Mariano's access.
2. Verified store-shopping session/fulfillment, genuinely observed first-party product price and coupon context. The public Vernon Hills directory number `531/00502` is not session proof.
3. Complete uncapped 28-category/subcategory and coupon traversal; at least **500 fresh genuine distinct** store-bound records (carried history is separate).
4. Real offer/PPM evidence, actual interruption/recovery and independent review.
5. Separately approved Azure execution with retained evidence, logs, storage readbacks and cleanup.
6. Mariano's contest entry number and submission link remain unverified.

No paid provider request, live Mariano's scrape, billable Azure deployment or schedule was run for this checkpoint.

## Dated conditional milestones — Asia/Dhaka (UTC+06:00)

| Date | Milestone | Dependency |
| --- | --- | --- |
| November 3, after 18:00 | Offline 82-pass checkpoint and explicit NO-GO blockers | Completed locally; GitHub CI for this doc-only change separate |
| November 5, 18:00 | Authorized retailer/store/session specification or blocker report | Client's written source permissions and valid store identification |
| November 6, 18:00 | First-party source-specific adapter mapping candidate and field audit, or blocker | Approved observed site/source response |
| November 10, 18:00 | 28-category/subcategory/coupon coverage audit or blocker | Genuine authorized collection |
| November 12–17 | Conditional planning window for 500-product, source proof and recovery evidence | Source and complete coverage qualify sufficiently early |
| After qualification and separate approval | Manual Azure execution with retained evidence and acceptance | Client Azure scope, budget and execution approval |

Do not treat these conditional dates as guaranteed acceptance dates. The Walmart 5–7-working-day estimate is not automatically a Mariano's promise. Production status remains NO_GO until independent real-source and Azure evidence exists.
