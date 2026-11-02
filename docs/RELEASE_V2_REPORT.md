# Mariano's scraper v0.2.0 - independently scoped release report

Date: 2026-10-18

## Implemented and tested
- Original 28-row manifest preserved without editing; all 22 output fields retained.
- Authorization evidence checker demands effective dates, store/category/collection/deal scope, affirmative retention rights, signed-document path and SHA-256 correspondence. Authenticity and permission require human/contractual verification.
- Publicly documented store candidates maintained separately from active store settings. No store declared validated without live checkout/pickup-context evidence.
- Export audit checks 500-record minimum, all 28 top-level category names, duplicate IDs, required fields, retailer URL domain, same-store context and PPM/digital/volume completeness.
- Read-only Azure preflight reports subscription/resource availability without mutating the user's environment.
- Offline regression tests: 20 passed in this session. No observed Mariano's product dataset generated.

## Blocking external evidence
1. Signed rights for retailer site/API collection, coupon terms, repeated twice-weekly capture, retention and intended downstream use. Metadata alone is insufficient.
2. A store assigned by the client, verified through a live selected-store display and local product-price checks. Public store page references do not prove store selection.
3. Azure subscription, accessible resource group, Container Apps environment, ACR and storage; RND workstation has no Azure CLI, and none was deployed.
4. Observed authorized end-to-end run >= 500 records, every required category and subcategory, coupon/UPC mapping, representative price/PPM/deal comparisons, screenshots, error injection and recovery, repeat run, actual Azure costs and recorded walkthrough.

## Status
**NO-GO for production and contest submission.** The code and safety checks are real; public retailer authorization and cloud operation cannot be fabricated.