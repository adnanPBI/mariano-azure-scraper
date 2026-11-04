# Mariano's — source/CI inspection and evidence boundaries (November 4, 2026)

**Decision: engineering source + offline CI verified; production release NO_GO.**
This is a supplement to the November 3 checkpoint, not a replacement for
the client's independent acceptance process. The code is still v0.5.1.

## Direct GitHub inspection (not merely repeating the author summary)

- Examined the exact versioned source commit
  [\`5c6d9060dd95680b6a558a8b0b4d080325835e0b\`](https://github.com/adnanPBI/mariano-azure-scraper/commit/5c6d9060dd95680b6a558a8b0b4d080325835e0b).
  Its changes address historical retention, partial resume metadata,
  canonical product-detail extraction, full-detail traversal and
  coupon-safe merging. These are code-level changes and synthetic test cases.
- Independently inspected GitHub workflow run
  [\`41634406120\`](https://github.com/adnanPBI/mariano-azure-scraper/actions/runs/41634406120):
  Ubuntu 24.04 / Python 3.11, Ubuntu 24.04 / Python 3.12, and Windows /
  Python 3.12 each report **82 tests passed and v0.5.1 wheel + sdist built**.
- Repository HEAD on inspection was
  [\`313bf6995aa57fe07946383d2910dbade47aa75a\`](https://github.com/adnanPBI/mariano-azure-scraper/commit/313bf6995aa57fe07946383d2910dbade47aa75a).
  That later commit adds only \`docs/CLIENT_CHECKPOINT_20261103.md\`,
  not changed scraper logic. Its matching
  [\`41664946302\` workflow run](https://github.com/adnanPBI/mariano-azure-scraper/actions/runs/41664946302)
  also has **82 passed and a successful build on each of the three jobs**;
  job IDs: \`126017644125\`, \`126017644505\`, \`126017644554\`.
- This is **direct GitHub job-log inspection**, independent of the earlier
  conversational claim. It is **not an independent client's rerun of live
  retailer collection**. The RND workstation was offline at this review,
  so no new RND execution is claimed.
- GitHub tests exercise locally intercepted Chromium/fixtures and file
  state, not retail network products or actual Azure resources.

## Strictly separate verification tracks

| Domain | Current status | Evidence needed for the next decision |
| --- | --- | --- |
| Offline source and CI | VERIFIED FOR v0.5.1 SOURCE | Exact SHA, three job logs and build artifacts listed above |
| Source acquisition permission | NOT VERIFIED | Written rights covering collection, coupons, history and stores |
| Vernon Hills PICKUP price binding | NOT VERIFIED | Authorized same-session source-returned **store ID, fulfillment, product, price, UPC**, response path/digest and spot checks |
| Full 28-category / subcategory / coupon scope | NOT VERIFIED | Real visited URL tree, complete page-end proofs, coupon links and terms, **500+ fresh genuine distinct** products, not carried rows |
| Actual recovery and history continuity | NOT VERIFIED | Witnessed interruption, same-slot recovery, changed-price reobservation, later missing/unpriced retention and last-good readbacks |
| Azure production execution | NOT VERIFIED | Owner-authorized account/budget, actual job execution ID, logs, storage hash readback, schedule and cost |
| Independent client acceptance | NOT VERIFIED | Witnessed real evidence, redacted walkthrough and owner-approved acceptance record |
| Contest entry / award | SEPARATE AND UNVERIFIED | Existing Mariano's contest entry number + link and platform eligibility; **no new entry or award commitment** |

### Vernon Hills store-directory limitation

The target is **Mariano's, 1720 N Milwaukee Ave, Vernon Hills, IL 60061,
fulfillment PICKUP**. The \`531/00502\` directory URL reference is
**not a returned shopping-session store ID**, and neither it nor the
configured address qualifies any source-specific price. The current
\`retailer-price-source-v1\` interface is a **synthetic normalized adapter
contract**, not a verified Mariano's first-party payload schema. Direct
Playwright Chromium is the current source route; **Walmart Classic Oxylabs
credentials and entitlement do not automatically apply**. Do not begin
commercial collection without rights and verified source mapping.

### Release-check semantics

\`marianos-scrape release-check\` now emits \`evidence_domains\`
alongside its existing checks. These labels separate offline CI from
source-bound prices, complete scope, actual recovery, Azure, and contest
entry. **Self-authored JSON or a cryptographic attestation records a claim,
not proof that a retailer/Azure observation physically occurred.**
A signed review still requires external corroboration.

## Handling while owner-side dependencies are resolved

- Do not invent or fill in a store session ID, observed product price,
  coupon scope, Azure execution ID, or Mariano's entry number.
- Keep \`MARIANOS_AUTHORIZED\` disabled; do not run live collection,
  billable provider calls, cloud deployments or schedules on the
  strength of this checkpoint.
- After owner authorization, record private, timestamped and hashed
  response evidence; use source-observed IDs/fulfillment, independent
  sample comparisons, complete navigation and recovery readbacks.
  Keep HAR/network bodies and tokens out of this public repository.
- Azure may be executed only after separate scope and spend approval;
  record job IDs, readbacks and cost as a new evidence domain.
- Milestones remain conditional on owner-side rights and access; no
  deadline for live source qualification or acceptance is promised here.

Machine-readable present-state register:
[\`release/evidence-register-20261104.json\`](../release/evidence-register-20261104.json).
