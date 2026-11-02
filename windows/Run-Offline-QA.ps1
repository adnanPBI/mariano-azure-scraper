# Windows QA without retailer traffic or Azure provisioning.
param([string]$Workspace = "$env:USERPROFILE\MarianosAzureQualification")
$ErrorActionPreference='Stop'
$project=Join-Path $Workspace 'project\marianos_azure_scraper'
$py=Join-Path $Workspace 'project\.venv\Scripts\python.exe'
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $Workspace 'tools\browsers'
$env:MARIANOS_AUTHORIZED='false'
$env:SCRAPER_STORAGE='local'
if (!(Test-Path $py)) { throw 'Install-Python-Environment.ps1 first' }
if (!(Test-Path (Join-Path $project 'pyproject.toml'))) {throw 'Project source package is missing'}
Push-Location $project
try {
  & $py -m pip install --disable-pip-version-check --no-input -e '.[test]'
  if ($LASTEXITCODE -ne 0) {throw 'editable source install failed'}
  & $py -m pytest -q --basetemp (Join-Path $Workspace 'evidence\pytest-tmp')
  if ($LASTEXITCODE -ne 0) {throw 'pytest failed'}
  Write-Output 'OFFLINE_WINDOWS_QA_PASS'
} finally { Pop-Location }