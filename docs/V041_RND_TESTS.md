# v0.4.1 Mariano's engineering checkpoint - November 2, 2026

Reference project: Walmart scraper v0.5.7 at
`4c62e387447c80fc506c918e981a2f0fe07c483c`.

- **RND Windows Python 3.12:** 43 offline tests passed, including real
  local Chromium Playwright DOM fixture and five new positive-publication /
  synchronous rename fault-injection tests.
- **28 categories** loaded unchanged from client-supplied CSV. Offline
  positive count and coupon-map checks are synthetic, **not** proof that
  live category navigation or coupon mapping works.
- **22 fields** exact schema; empty gupc and unit_price; observed-only PPM.
- Existing storage protects last successful pointer using local atomic rename
  or Azure conditional ETag. New positive-only manifest guard prevents
  pending/failed/empty/invalid-hash output from becoming the latest export.
- **No timeout guarantee across synchronous filesystem writes.** After
  an OS rename, caller return can be delayed by filesystem stall. The scraper
  does not claim otherwise or introduce a daemon positive publisher.
- New CI Linux 3.11/3.12 and Windows 3.12; GitHub Actions results must be
  independently inspected after commit before declaring CI green.

## NOT production GO

Written site collection license, actual store binding, 500 genuine product
records, positive end-of-pagination/category proofs, complete coupons, live
PPM and terms, authorized paid tests, Azure authenticated deployment, and
observed recovery/independent signoff are missing. No retailer/paid/Azure
network requests were made during this regression checkpoint.

This is a **source and offline QA** commit, not a retailer-live claim.