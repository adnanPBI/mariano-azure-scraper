#!/usr/bin/env bash
set -euo pipefail
: "${AZ_RESOURCE_GROUP:?}"; : "${AZ_JOB_NAME:?}"
az containerapp job execution list -n "$AZ_JOB_NAME" -g "$AZ_RESOURCE_GROUP" -o table
# Example: inspect the immutable run report without downloading arbitrary data publicly:
# az storage blob download --account-name "$AZ_STORAGE_ACCOUNT" --container-name "$AZ_STORAGE_CONTAINER" --name published/<store_id>/latest.json --file latest.json --auth-mode login