#!/usr/bin/env bash
# Azure Container Apps Job - twice weekly; FAILS CLOSED until collection rights are confirmed.
set -euo pipefail
: "${AZ_SUBSCRIPTION_ID:?Required}"
: "${AZ_RESOURCE_GROUP:?Required}"
: "${AZ_CONTAINERAPPS_ENV:?Required}"
: "${AZ_ACR_NAME:?Required}"
: "${AZ_STORAGE_ACCOUNT:?Required}"
: "${AZ_STORAGE_CONTAINER:?Required}"
: "${MARIANOS_APPROVAL_REFERENCE:?Written permission / licensed-feed reference required}"
: "${MARIANOS_AUTHORIZATION_METADATA_FILE:?Private signed-authorization metadata required}"
if [[ "${MARIANOS_AUTHORIZED:-false}" != "true" ]]; then
  echo 'No written approval for bulk collection; refusing deployment' >&2
  exit 12
fi
if [[ ! -f "$MARIANOS_AUTHORIZATION_METADATA_FILE" ]]; then
  echo 'Signed-authorization metadata JSON missing; refusing deployment' >&2
  exit 13
fi
if [[ ! -f config/stores.yaml ]]; then
  echo 'Fill in real config/stores.yaml first; see stores.yaml.example' >&2
  exit 13
fi
: "${AZ_JOB_NAME:=marianos-scraper}"
: "${AZ_IDENTITY_NAME:=marianos-scraper-identity}"
TAG="${SCRAPER_IMAGE_TAG:-v0.4.0}"
# All credential/document validation occurs before ANY cloud mutation.
# Validate original signed evidence before uploading it to a private Blob prefix.
# The agreement document itself is NOT copied into the Docker image.
AUTH_SIGNED_PATH="$(python - "$MARIANOS_AUTHORIZATION_METADATA_FILE" <<'PYCODE'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);doc=json.loads(p.read_text(encoding='utf-8'))
print(doc.get('signed_agreement_file',''))
PYCODE
)"
if [[ ! -f "$AUTH_SIGNED_PATH" ]]; then
  echo 'Signed authorization document missing; refusing deployment' >&2
  exit 15
fi
TMP_AUTH="$(mktemp)"
trap 'rm -f "$TMP_AUTH"' EXIT
python - "$MARIANOS_AUTHORIZATION_METADATA_FILE" "$AUTH_SIGNED_PATH" "$TMP_AUTH" "$MARIANOS_APPROVAL_REFERENCE" <<'PYCODE'
import hashlib,json,sys
from pathlib import Path
metadata,agreement,out,expected=sys.argv[1:]
obj=json.loads(Path(metadata).read_text(encoding='utf-8'))
original=Path(agreement).read_bytes()
if len(original)<100 or hashlib.sha256(original).hexdigest()!=obj.get('signed_agreement_sha256'):
    raise SystemExit('signed authorization checksum mismatch')
if obj.get('agreement_id')!=expected:
    raise SystemExit('signed authorization agreement ID mismatch')
if not any(w in str(obj.get('authorized_access_method','')).lower() for w in ('browser','website','web site')):
    raise SystemExit('signed authorization does not cover website/browser collection')
# Verify explicit collection, commercial rights and concrete store/category coverage.
import csv,datetime
import yaml
store_config=yaml.safe_load(Path('config/stores.yaml').read_text(encoding='utf-8')) or {}
store_ids={s['id'] for s in store_config.get('stores',[])}
with Path('config/Marianos_Category_URLs.csv').open(newline='',encoding='utf-8-sig') as f:
    required_categories={r['Category (Auto)'].strip() for r in csv.DictReader(f)}
if not store_ids or not store_ids.issubset(set(obj.get('store_ids') or [])):
    raise SystemExit('signed authorization does not cover all configured store IDs')
if len(required_categories)!=28 or not required_categories.issubset(set(obj.get('authorized_categories') or [])):
    raise SystemExit('signed authorization does not cover all 28 category names')
if obj.get('collection_frequency_per_week',0)<2:
    raise SystemExit('signed authorization does not permit twice-weekly collection')
for field in ('commercial_storage_permitted','historical_retention_permitted','promotion_and_coupon_collection_permitted'):
    if obj.get(field) is not True:raise SystemExit('signed authorization missing '+field)
today=datetime.date.today()
if not (datetime.date.fromisoformat(obj['effective_date'])<=today<=datetime.date.fromisoformat(obj['expiry_date'])):
    raise SystemExit('signed authorization outside effective dates')
obj['signed_agreement_file']='blob:authorization/signed-agreement'
Path(out).write_text(json.dumps(obj,separators=(',',':')),encoding='utf-8')
PYCODE
az account set --subscription "$AZ_SUBSCRIPTION_ID"
if az containerapp job show -n "$AZ_JOB_NAME" -g "$AZ_RESOURCE_GROUP" >/dev/null 2>&1; then
  echo 'Job already exists. Require change-management approval before deployment.' >&2
  exit 14
fi
# Existing group, registry, environment and account are reused rather than replaced.
if [[ -z "$(az identity list -g "$AZ_RESOURCE_GROUP" --query "[?name=='$AZ_IDENTITY_NAME'].id | [0]" -o tsv)" ]]; then
  az identity create -n "$AZ_IDENTITY_NAME" -g "$AZ_RESOURCE_GROUP" >/dev/null
fi
IDENTITY_ID="$(az identity show -n "$AZ_IDENTITY_NAME" -g "$AZ_RESOURCE_GROUP" --query id -o tsv)"
PRINCIPAL_ID="$(az identity show -n "$AZ_IDENTITY_NAME" -g "$AZ_RESOURCE_GROUP" --query principalId -o tsv)"
CLIENT_ID="$(az identity show -n "$AZ_IDENTITY_NAME" -g "$AZ_RESOURCE_GROUP" --query clientId -o tsv)"
ACR_ID="$(az acr show -n "$AZ_ACR_NAME" --query id -o tsv)"
STORAGE_ID="$(az storage account show -n "$AZ_STORAGE_ACCOUNT" -g "$AZ_RESOURCE_GROUP" --query id -o tsv)"
# Role assignment commands are idempotent only if role isn't already present.
if [[ -z "$(az role assignment list --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" --query '[0].id' -o tsv)" ]]; then
  az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID" >/dev/null
fi
if [[ -z "$(az role assignment list --assignee "$PRINCIPAL_ID" --role 'Storage Blob Data Contributor' --scope "$STORAGE_ID" --query '[0].id' -o tsv)" ]]; then
  az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role 'Storage Blob Data Contributor' --scope "$STORAGE_ID" >/dev/null
fi
az storage container create --account-name "$AZ_STORAGE_ACCOUNT" --name "$AZ_STORAGE_CONTAINER" --auth-mode login >/dev/null
# Identity-based storage access; no credential string is logged or embedded.
az storage blob upload --account-name "$AZ_STORAGE_ACCOUNT" --container-name "$AZ_STORAGE_CONTAINER" --name config/stores.yaml --file config/stores.yaml --overwrite true --auth-mode login >/dev/null
az storage blob upload --account-name "$AZ_STORAGE_ACCOUNT" --container-name "$AZ_STORAGE_CONTAINER" --name authorization/signed-agreement --file "$AUTH_SIGNED_PATH" --overwrite true --auth-mode login >/dev/null
az storage blob upload --account-name "$AZ_STORAGE_ACCOUNT" --container-name "$AZ_STORAGE_CONTAINER" --name authorization/metadata.json --file "$TMP_AUTH" --overwrite true --auth-mode login >/dev/null
az acr build -r "$AZ_ACR_NAME" -t "marianos-scraper:$TAG" .
IMAGE="$AZ_ACR_NAME.azurecr.io/marianos-scraper:$TAG"
# 16 UTC = 10:00/11:00 Chicago, Monday and Thursday, including across DST.
# One replica, Azure Blob lease prevents overlapping executions, even manual starts.
az containerapp job create \
  --name "$AZ_JOB_NAME" --resource-group "$AZ_RESOURCE_GROUP" --environment "$AZ_CONTAINERAPPS_ENV" \
  --trigger-type Schedule --cron-expression '0 16 * * 1,4' \
  --replica-timeout 21600 --replica-retry-limit 1 \
  --replica-completion-count 1 --parallelism 1 \
  --cpu 2.0 --memory 4.0Gi \
  --image "$IMAGE" --mi-user-assigned "$IDENTITY_ID" \
  --registry-server "$AZ_ACR_NAME.azurecr.io" --registry-identity "$IDENTITY_ID" \
  --env-vars "SCRAPER_STORAGE=azure" "AZURE_STORAGE_ACCOUNT=$AZ_STORAGE_ACCOUNT" \
             "AZURE_STORAGE_CONTAINER=$AZ_STORAGE_CONTAINER" \
             "MARIANOS_AUTHORIZED=true" "MARIANOS_APPROVAL_REFERENCE=$MARIANOS_APPROVAL_REFERENCE" "AZURE_CLIENT_ID=$CLIENT_ID" \
             "MARIANOS_AUTHORIZATION_FILE=blob:authorization/metadata.json"
echo "Created scheduled job $AZ_JOB_NAME. The live crawler still requires retailer-side observation and acceptance qualification."