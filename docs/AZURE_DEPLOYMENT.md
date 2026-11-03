# Azure installation and operations runbook

## Pre-deployment release gates

1. Confirm a signed written license/authorization **specifically allows** collection and retention of Mariano's catalogs, prices, offers and coupon terms at the proposed frequency. Kroger Public API registration is not sufficient by itself.
2. Confirm one real store ID, full address, ZIP and one address phrase that is visibly present in the store-selection indicator; repeat for each store.
3. Assign an operator with contributor rights on the **existing** Azure resource group, registry, Container Apps environment and storage account, plus `Microsoft.Authorization/roleAssignments/write` if the deployment script creates RBAC assignments.
4. Configure source_store_ref, fulfillment_mode and observed, approved first-party price_response_paths for each store. A public directory reference or header is not a price-source proof; live operation requires strict source-returned store/mode/product/price binding. Verify all 28 categories and subcategories with an authorized observed run. Most top-level `/d/` URLs are marketing/landing pages rather than guaranteed full catalog pagination endpoints. Coupon coverage must be proven through a defensible UPC/product mapping.
5. Confirm legal scope of any authentication, cookies, retailer membership, offers and stored images. Do not use anti-bot evasion, challenge solvers, unsupported private APIs or rotating proxies.

## Azure resources

- Existing resource group and subscription
- Existing Azure Container Apps managed environment
- Existing Azure Container Registry (ACR)
- Existing Azure Storage account / private Blob container
- User-assigned managed identity with `AcrPull` on registry and `Storage Blob Data Contributor` on storage
- Optional Azure Monitor / Log Analytics already wired to Container Apps environment
- Container Apps scheduled Job, 2 vCPU and 4 GiB RAM in starter manifest; adjust after measured runtime and bill

The job does not require a public ingress endpoint. Storage tokens are obtained through managed identity; approval reference is injected as an environment variable. The store list is uploaded to a private blob as YAML and is not part of the Docker image.

## Create the job

Run from the extracted project root using Bash and Azure CLI after `az login`:

```bash
cp config/stores.yaml.example config/stores.yaml
# Replace all placeholder values with real, verified Mariano's store details.
export AZ_SUBSCRIPTION_ID='REAL_SUBSCRIPTION_ID'
export AZ_RESOURCE_GROUP='EXISTING_RESOURCE_GROUP'
export AZ_CONTAINERAPPS_ENV='EXISTING_CONTAINER_APPS_ENVIRONMENT'
export AZ_ACR_NAME='EXISTING_ACR_NAME'
export AZ_STORAGE_ACCOUNT='EXISTING_STORAGE_ACCOUNT'
export AZ_STORAGE_CONTAINER='marianos-crawls'
export AZ_JOB_NAME='marianos-scraper'
export AZ_IDENTITY_NAME='marianos-scraper-identity'
export MARIANOS_AUTHORIZED='true'
export MARIANOS_APPROVAL_REFERENCE='SIGNATURE_OR_CONTRACT_REFERENCE'
export MARIANOS_AUTHORIZATION_METADATA_FILE='/secure/authorization.json'
# JSON must reference the signed agreement file, with its actual SHA256.
./azure/deploy.sh
```

Deploy script stops if authorization and filled store config are missing. It refuses to blindly replace a job that already exists; change-management approval is required for updates. It does not automatically open public network access or copy the private store settings into the image.

To run a **fresh observed acceptance job** after deployment:

```bash
az containerapp job start --name "$AZ_JOB_NAME" --resource-group "$AZ_RESOURCE_GROUP"
az containerapp job execution list --name "$AZ_JOB_NAME" --resource-group "$AZ_RESOURCE_GROUP" -o table
```

## Scheduling and concurrency

- Cron `0 16 * * 1,4` is evaluated in UTC: every **Monday and Thursday** at 16:00 UTC.
- Chicago local wall-clock time is 10:00 in daylight saving time and 11:00 in standard time.
- Each scheduled slot produces a deterministic local run slot (`YYYY-MM-DD`), allowing retries and exact recovery.
- Container Apps settings allow a single replica per execution; Azure Blob lease allows only one execution per store across scheduled and manual invocations.
- A background heartbeat renews the 60-second lease. If lost, the job fails without publishing.
- Container Apps jobs may time out for very large catalogs; adjust `--replica-timeout`, pacing, detail coverage and performance only after an approved monitored run. Do not bypass access restrictions to speed up collection.

## Recovery without data loss

A failed execution writes `runs/<id>/<slot>/FAILED.json` if storage remains available. Completed subcategory checkpoints are durable and reused on the next run of the **same slot**. Partial products are saved periodically, allowing a restarted unit to restore already observed items while replaying navigation; the unit is revalidated before completion. Manifests and exports are versioned; the latest-success pointer is only changed on a fully successful validation and conditional Blob update.

Do **not** manually edit or overwrite `published/<id>/latest.json` to force a failed dataset. The safe rollback is to point to a previous successfully validated version after verifying its SHA-256 and location.

## Inspect evidence

```bash
# Download the latest successful validation pointer for a confirmed store ID:
az storage blob download --auth-mode login \
 --account-name "$AZ_STORAGE_ACCOUNT" --container-name "$AZ_STORAGE_CONTAINER" \
 --name 'published/REAL_STORE_ID/latest.json' --file latest.json --overwrite
cat latest.json
```

Inspect `records`, `duplicates_removed`, `category_counts`, `subcategories_by_category`, `field_completeness`, `ppm_examples`, `digital_deal_examples`, `volume_deal_examples`, `location_proof_samples` and `location_proof_images`. Compare chosen examples with the currently displayed authorized site content. All category URLs must be accounted for, including Coupons.

Logs are newline-delimited structured JSON sent to stdout. Container Apps execution logs are available through Azure Monitor / Log Analytics if the existing environment is configured for collection.

## Cost model

**No actual Azure spend or time measurements exist for this build.** Monthly resource cost approximately equals `(measured hours/run) × (8-10 runs/month) × (two vCPU job rate + four GiB memory rate)` plus blob storage, transactions, registry and monitoring costs, per your Azure region and plan. Per-store prices, image downloads, retries, page-enrichment intensity and large category counts affect runtime. Use the Azure Pricing Calculator and a real observed full crawl before quoting a fixed monthly budget.

Useful Microsoft docs:
- https://learn.microsoft.com/azure/container-apps/jobs
- https://learn.microsoft.com/en-us/cli/azure/containerapp/job
- https://learn.microsoft.com/azure/container-apps/manage-secrets

## Signed authorization runtime enforcement (v0.4)

A production job must download the signed authorization metadata and signed agreement from private Azure Blob storage through its managed identity before opening any retailer browser. `MARIANOS_AUTHORIZATION_FILE=blob:authorization/metadata.json` is injected by `azure/deploy.sh`. The metadata must explicitly permit the selected stores, all CSV categories, twice-weekly runs, commercial/historical storage and coupons, and the authorized method must include browser/website collection. A valid SHA-256 only proves document bytes match the metadata; a human must verify the authority of the signer and the grant scope. The deployment script uploads the document and metadata to private Blob storage; neither is baked into the container image.