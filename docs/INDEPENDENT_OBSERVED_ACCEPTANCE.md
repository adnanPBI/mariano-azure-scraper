# Independent observed acceptance - cannot be fabricated from fixtures

1. Verify written permission for the exact website collection method and rights; supply private `authorization/metadata.json` plus signed agreement.
2. Witness a collection at each assigned location. Record store selection before/after every category, URLs/screenshots, full eligible catalog and coupon-to-product relationships. Independently compare at least **30 randomly selected genuine records** for source UPC, price, PPM units, deals and store. Show every required category/subcategory; a category may be empty legitimately only if client explicitly accepts an exception, which current scraper treats as NO-GO.
3. Record a genuine Azure execution ID, subscription ID, successful blob publication, schedule, immutable dataset SHA-256 and a failed-run non-overwrite demonstration.
4. Complete `release/observed_acceptance.example.json` with only actually observed true assertions. The reviewer must hold an **out-of-band trusted Ed25519 private key** (never in this repository). Save the signed JSON at a private path; ensure `signature_base64` is computed over UTF-8 JSON with sorted keys and separators `(',',':')`, excluding signature itself. Do not set flags using fake data.
5. Provide the paired **trusted public key** separately, verify identity of signer/authority and execute:

```
marianos-scrape release-check --settings /secure/stores.yaml --authorization-file /secure/auth.json \
  --file /secure/observed-real-export.json --azure-proof-file /secure/azure-job-proof.json \
  --acceptance-file /secure/observed-acceptance.json --reviewer-public-key /secure/reviewer_ed25519_public.pem
```

The cryptographic key only establishes which trusted reviewer signed the assertion; it does not prove that data is true. Verify all real evidence manually before sharing GO. No sample private key, fake live proof, or claimed production run is included.