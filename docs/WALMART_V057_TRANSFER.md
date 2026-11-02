# Mariano's v0.4.1 - Walmart v0.5.7 adaptation checkpoint

Reference: [Walmart authoritative v0.5.7 commit](https://github.com/adnanPBI/walmart-azure-scraper/commit/4c62e387447c80fc506c918e981a2f0fe07c483c).

## Applied cross-retailer reliability concepts

1. Positive publication belongs to the synchronous caller and only a **qualified**
   `status=passed, published=true` manifest with a valid SHA-256 and immutable,
   store/slot-bound export key may replace `published/<store>/latest.json`.
2. Staged, incomplete, blocked, thin, permission-denied, or failed collection
   records **must never** advance the last-good pointer. The existing Azure
   conditional ETag write and local atomic rename remain intact.
3. Local filesystem fault-injection tests cover failures before rename, deliberate
   stalls before rename and stalls after the actual rename. No late daemon
   publisher or provider worker is introduced by this change.
4. The synchronous OS filesystem rename and Azure service write have **no
   unconditional caller wall-clock bound**. A blocked filesystem can block
   the caller; a crash between remote success and caller receipt may leave
   an uncertain result requiring independent readback. This limitation is
   disclosed rather than disguised as a 90-second promise.
5. Cross-platform CI exercises Linux Python 3.11/3.12 and Windows Python 3.12
   with real localhost Chromium fixture tests, source build and JUnit evidence.
6. The original 28-row Mariano's CSV and 22 ordered string-valued output
   fields remain unchanged; GUPC and unit_price always blank, PPM directly
   observed, volume/digital deals classified by clipping requirement.

## Not carried over from Walmart

- The **Classic Oxylabs** diagnostic, authenticated paid request ledger,
  Waukegan #3891/PICKUP locale, Walmart product IDs, marketplace/fulfillment
  semantics, and `.supervisor.tmp` source API receipts are Walmart-specific.
- Mariano's has no approved paid provider workflow in this implementation.
  No attempt, credit reservation, provider cost or false 90-second deadline
  is introduced.
- No claim of live page compatibility, selected-store prices, coupon-to-product
  mapping, at least 500 genuine products, actual Azure job execution or
  independently observed source acceptance is made.

## Reproduce offline

```sh
python -m pip install -e ".[test]"
python -m playwright install chromium
python -m pytest -q tests
python -m pytest -q tests/test_walmart_v057_publication_port.py
```

All test products are synthetic/local fixtures. Authorization metadata and
store config must be populated **privately** before any live operation.

## Important release boundary

**Engineering gate and production gate are distinct.** Passing local tests
does not override Mariano's collection terms or grant a cloud subscription.
`release-check` remains NO_GO without written access permission, verified
assigned stores, 28-category/subcategory and coupon completeness, actual
500-record source, independently reviewed PPM/deals/store evidence and
Azure execution/signoff.