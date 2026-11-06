# Mariano's — Focused source-price role binding correction

**Client finding:** `SourceResponseLedger.require_price` accepted regular
and sale values as an unordered set, allowing reversed roles such as output
regular=3.00/sale=5.00 against a source regular=5.00/sale=3.00.

**Scope:** A small source fix plus focused regression tests; the existing
exact-commit d09b749 review ZIP is intentionally unchanged. This note
is a *new subsequent correction*, not a claim that the older source was
already free of this bug.

## Source changes

- `src/marianos_scraper/source_context.py`
  - Replaced `extracted_prices.issubset(actual_prices)` with a direct
    field-by-field comparison. Populated output `regular_price` must
    equal source `regular_price`; populated output `sale_price` must
    equal source `sale_price`. Source price strings are normalized only
    to their decimal price format, never reassigned between roles.
  - A populated output price fails if its same-named source field is
    absent or blank, even if the opposite source slot has the same amount.
  - Rejects malformed nonempty source price values before storing a
    binding, so invalid inputs are not silently reinterpreted as missing.
  - Rejects malformed nonempty output prices. The validator never
    overwrites, swaps, or populates missing output values.
  - Retains the existing policy: a completely unpriced output needs the
    explicit `unpriced: true` source flag. A blank output slot remains
    blank even when a corresponding source slot has a value; completeness
    must be independently evaluated.

## New tests — `tests/test_source_price_role_binding.py`

| Scenario | Expected |
| --- | --- |
| Same-session source 5.00 regular/3.00 sale, matching output | PASS |
| Same source, output 3.00 regular/5.00 sale | REJECT, wrong regular slot |
| Source regular missing or explicitly blank, output regular populated from sale | REJECT |
| Source sale missing or explicitly blank, output sale populated from regular | REJECT |
| Actual numeric mismatch in either slot | REJECT |
| Sale-only source and matching sale-only output | PASS |
| Explicit unpriced source and blank output | PASS |
| Entirely blank output without explicit unpriced source | REJECT |
| Nonempty malformed source/output price in either role | REJECT |
| Source has sale but output sale remains empty | PASS without inventing a sale price |
| Intercepted Chromium product crawl with correct 5.00/3.00 | PASS |
| Intercepted Chromium product crawl with swapped 3.00/5.00 | REJECT before `CrawlOutcome` returns |

Run only the focused tests (requires project test dependencies and
Playwright Chromium):

```bash
python -m pytest -q tests/test_source_price_role_binding.py
```

Test fixtures are synthetic and only exercise the typed
`retailer-price-source-v1` contract. They do **not** qualify real Mariano's
first-party response mappings, Vernon Hills PICKUP pricing, genuine 500+
products, full coupon/category coverage, real retention/recovery, Azure
jobs, or contest eligibility.

## Decision

The **specific unordered-set price-role bug** may be closed once the
client independently reviews the focused diff and confirms the new
negative/positive tests. All previously stated live-source and Azure
acceptance gates remain **NO_GO**.
