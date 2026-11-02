#!/usr/bin/env bash
# Read-only Azure discovery. Never provision resources or enable a live scrape.
set -euo pipefail
command -v az >/dev/null || { echo '{"status":"blocked","reason":"Azure CLI is not installed"}'; exit 3; }
az account show --query '{subscription:id,subscriptionName:name,tenant:tenantId,state:state}' -o json || { echo '{"status":"blocked","reason":"Azure authentication is unavailable"}'; exit 3; }
if [[ -n "${AZ_RESOURCE_GROUP:-}" ]]; then
 az group show -n "$AZ_RESOURCE_GROUP" --query '{name:name,location:location,id:id}' -o json
 az containerapp env list -g "$AZ_RESOURCE_GROUP" --query '[].{name:name,location:location}' -o json
 az acr list -g "$AZ_RESOURCE_GROUP" --query '[].{name:name,loginServer:loginServer}' -o json
 az storage account list -g "$AZ_RESOURCE_GROUP" --query '[].{name:name,location:location}' -o json
fi