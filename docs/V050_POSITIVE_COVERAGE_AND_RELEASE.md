# Mariano's Azure scraper v0.5.0 - strict coverage and acceptance checkpoint

**Status: offline software qualification only, NOT client production GO.**
No retailer data was collected, no paid provider was called, and no Azure
subscription was authenticated during this checkpoint. A synthetic fixture
cannot be substituted for a real 500-product export.

## Exact defects addressed

1. **Linux CI:** pin Ubuntu to 24.04 rather than the moving 26.04 image
   unsupported by Playwright 1.56 Chromium. Confirm all jobs against the
   precise versioned commit SHA.
2. **Listing completeness:** remove the previous 90% count tolerance.
   Every raw /p/ link must be either parsed into a product or explicitly
   excluded for source approximate-weight wording. A previously checkpointed
   product absent from fresh listing evidence is not retained silently.
3. **Positive end of listing:** require an exact retailer-displayed count,
   a retailer-visible terminal phrase, or a disabled final pagination
   control; additionally require four settled iterations at the bottom
   and no enabled Next/Load More control. Do not treat mere lack of products
   or a blocked response as completion.
4. **Category expansion:** increase depth limit from 3 to 12 (operator cap
   <=24); discovering child departments beyond the configured cap fails
   explicitly rather than omitting their products.
5. **Coupon mapping:** recursively examine URL-addressable coupon filters.
   Every recognized source coupon tile requires a unique first-party ID,
   clear clipping/activation terms, and at least one first-party /p/ link.
   Opaque offers block publication. Linked products are checked through
   the page with the assigned store header. Coupon count and mapping count
   must reconcile; a mere coupon landing page does NOT qualify.
6. **Complete promotion text:** remove the silent 400-character fallback
   cutoff; preserve observed terms and limits. A missing digital deal
   price remains empty; never calculate PPM or a coupon final price.
7. **Store picker bug:** exclude the global 'Select Store' button from
   the result selector and match unique address only within each result row.
   An ambiguous match fails closed.
8. **Durable validation:** real BrowserSource checkpoints must have a
   `coverage.passed` manifest before being reused or committed. Every
   published run records positive evidence per category/unit. Existing
   atomic last-good pointer protection is unchanged.
9. **Walkthrough capture:** when explicitly set, the local
   `MARIANOS_ACCEPTANCE_VIDEO_DIR` records the authorized browser session
   to a private folder. The browser context closes before returning so
   the Playwright video can be finalized. Never upload unredacted private
   account footage to a public repository.

## Limitations that cannot be determined from offline fixtures

- Exact live website selector shape; coupon tile identities and whether
  the retailer exposes product /p/ links for every offer; hidden/JavaScript
  coupon filters or eligibility details; source-specific pagination
  signals. Failures here require an *authorized observed source assessment*
  and possible further code work; they are NOT automatically solved.
- A headline count may include off-card links/recommendations; the strict
  raw-vs-declared reconciliation intentionally refuses uncertain results.
- The client must verify that each applicable subcategory is included, even
  when an online page exposes a partial navigation tree.
- The OS and cloud operations do not have an unconditional wall-clock
  guarantee. A blocked synchronous final filesystem or Azure write may
  outlive any nominal scrape worker timeout.

## Acceptance recipe (not yet executed)

Before any live request or charge:
- Obtain a signed grant identifying Mariano's browser/website collection,
  historical commercial storage, store IDs, all required categories, coupons,
  twice-weekly collection and permitted account context. Human-verify grantor.
- Confirm client-assigned store IDs/ZIPs and the exact address phrase rendered
  by the selected store. Populate **private** `config/stores.yaml`; never
  commit it. Configure independent, meaningful canary products.
- Confirm an Azure subscription and permission to create the existing ACR,
  Blob, managed identity and Container Apps Job components. Approve cloud
  spend separately. Do NOT use `az login` in public or CI.

After authorization and attended setup:

```bash
marianos-scrape check-config --settings config/stores.yaml
# MARIANOS_AUTHORIZED=true and MARIANOS_APPROVAL_REFERENCE=<actual agreement id>
# MARIANOS_AUTHORIZATION_FILE=<private metadata> with original signed-file hash
export MARIANOS_ACCEPTANCE_VIDEO_DIR=/private/retailer-observation
marianos-scrape run --settings config/stores.yaml --authorization-file /private/auth.json
marianos-scrape verify-export --file /private/exports/actual-catalog.json
# Observe and record a full run with 500+ distinct genuine products,
# coupon-to-UPC/product mapping, category/subcategory coverage, prices,
# original PPM, complete volume/digital terms, and location screenshots.
# Re-run with injected interruption and compare the previous published pointer.
# Deploy only with permitted Azure account and approved resource/spend plan.
az containerapp job execution list -g REAL_RG -n REAL_JOB -o table
marianos-scrape release-check --settings config/stores.yaml \
  --authorization-file /private/auth.json \
  --file /private/exports/actual-catalog.json \
  --azure-proof-file /private/azure_execution.json \
  --acceptance-file /private/client_signed_review.json \
  --reviewer-public-key /private/client_public.pem
```

The final submission must include real product JSON, actual run times and
cost, 28 category/subcategory source maps, coupon/PPM/deal spot checks,
original screenshots, valid Azure execution IDs, interruption and repeat
run evidence, and a signed client review plus sanitized walkthrough recording.
Until those exist, `release-check` must remain NO_GO.