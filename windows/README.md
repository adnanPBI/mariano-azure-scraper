# Windows/RND scoped workstation qualification

The live scraper runs in Azure Container Apps, **not** on the RND workstation. Windows is an operator/qualification machine.

Installation is scoped to `%USERPROFILE%\MarianosAzureQualification`: portable Azure CLI ZIP (Microsoft official distribution), virtualenv under `project\.venv`, and Playwright Chromium under `tools\browsers`. Existing Python, Git, Node, environment variables and `C:\Users\NHTML\.azure` are preserved. Neither Docker Desktop nor administrative privileges are required to run the offline tests. Docker is optional only for a local container build; the Azure script uses ACR cloud builds.

The operator creates an `installation-ledger.json` **before** downloads and retains `Remove-Temporary-Components.ps1` to remove only tracked files (dry-run by default). Azure CLI sign-in must be done by the operator if needed; never paste subscription keys or passwords into source files. Do not copy existing `.azure` token caches into project folders.

After extracting this project into `%USERPROFILE%\MarianosAzureQualification\project\marianos_azure_scraper`, run `powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\Run-Offline-QA.ps1` from the source root. The script verifies Windows dependencies, all offline tests and cross-platform file locking. This is **not** a live retail acceptance test.

Only begin cloud deployment after written collection permission, complete store identifiers and Azure role access have been independently verified. See `docs/AZURE_DEPLOYMENT.md`.

## Verified RND results (October 18, 2026)

- Azure CLI 2.91.0 from Microsoft's official portable ZIP verified through `az version`.
- Azure Container Apps CLI extension `1.3.0b5` installed in `evidence\azure-config\cliextensions`.
- Isolated Python 3.12 venv; Playwright 1.56.0, Chromium 141 build 1194, headless shell, pytest, Azure Blob/Identity SDKs and `tzdata` installed.
- Windows-specific QA was adjusted to use `evidence\pytest-tmp` because the preexisting global `%TEMP%\pytest-of-NHTML` had access restrictions. All **20/20** offline tests passed on the connected RND workstation.
- Azure CLI subscription enumeration returned `[]` in both isolated and existing user configurations. No cloud deployment or live retailer collection occurred.
- The user's existing global Python, Git, Node, system PATH and preexisting `.azure` configuration were not replaced. `windows/Remove-Temporary-Components.ps1` is designed for reviewed deletion of the scoped toolchain; RND has a matching copy at the workspace root.