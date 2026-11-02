# RND workstation: independent Windows toolchain qualification

Date (UTC): 2026-10-18. Machine: RND. Local path: `C:\Users\NHTML\MarianosAzureQualification`.

## Verified

- Python 3.12.9 preexisting; new isolated venv has Playwright 1.56.0, Chromium 141 (build 1194), headless Chromium, Azure Storage Blob SDK 12.31.0, Azure Identity 1.26.0, pytest 9.1.1, and Windows timezone database `tzdata` 2026.5.
- v0.3.1 source installed editable in the project-only venv and browser test ran successfully on Windows: **20 passed in 8.49s**, no failures, via `windows/Run-Offline-QA.ps1`.
- Azure CLI 2.91.0 and the Container Apps extension `1.3.0b5` installed and verified; `az containerapp job create --help` recognizes the required managed identity, registry identity, schedule, concurrency and replica arguments.
- Azure Bash deployment script syntax passed `bash -n`; without authorization metadata/environment the script failed closed before cloud changes.
- Install inventory, SHA-256 of original transfer/archive, test logs, JSON release preflight and dry-run cleanup exist on RND.
- User-scoped installs only. Existing Python, Node, Git and PATH have not been replaced.

## Not accepted as production

- Azure `account list` returned `[]` on RND: there is no authenticated subscription available through the tested configurations.
- No signed written retailer bulk-collection authorization, client-assigned store/session proof, real catalog/coupon crawl, >=500 genuine records, or observed production Azure execution was supplied.
- No new Azure infrastructure, registry builds, scheduled jobs, storage writes, or actual retailer sessions were performed.

## Removal

On RND, open PowerShell:

```powershell
& "$env:USERPROFILE\MarianosAzureQualification\Remove-Temporary-Components.ps1" # preview only
& "$env:USERPROFILE\MarianosAzureQualification\Remove-Temporary-Components.ps1" -Execute # remove tracked temporary toolchain
# Add -IncludeProject only when ready to delete source folder as well.
```

Original Python/Git/Node, any preexisting user `.azure`, and Windows/system variables are out of the cleanup scope. Cleanup retains audit scripts and installation ledger. Preexisting global pip cache is not purged since it may contain unrelated packages.