# Windows 11; non-admin, per-user project dependencies only.
# The source package should be located at $env:USERPROFILE\MarianosAzureQualification\project\marianos_azure_scraper.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root=Join-Path $env:USERPROFILE 'MarianosAzureQualification'
foreach($folder in @('tools','downloads','evidence','project')) {New-Item -ItemType Directory -Force -Path (Join-Path $root $folder) | Out-Null}
$ledger=Join-Path $root 'installation-ledger.json'
if (!(Test-Path $ledger)) {
 $state=[ordered]@{workspace=$root;created_utc=[DateTime]::UtcNow.ToString('o');previous_az=(Get-Command az -ErrorAction SilentlyContinue).Source;previous_python=(Get-Command python -ErrorAction SilentlyContinue).Source;user_path_changed=$false;machine_path_changed=$false;registry_changed=$false}
 $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ledger -Encoding UTF8
}
$state=Get-Content -LiteralPath $ledger -Raw | ConvertFrom-Json
$az=Join-Path $root 'tools\azure-cli\bin\az.cmd'
$zip=Join-Path $root 'downloads\azure-cli.zip'
if (!(Test-Path $az)) {
  if ($state.previous_az) {throw 'Azure CLI previously installed; refusing to replace it'}
  Invoke-WebRequest 'https://aka.ms/installazurecliwindowszipx64' -OutFile $zip -TimeoutSec 900 -MaximumRedirection 8
  if ((Get-Item $zip).Length -lt 10000000) {throw 'Bad Azure CLI archive size'}
  $hash=(Get-FileHash $zip -Algorithm SHA256).Hash
  Write-Output ('Downloaded Microsoft Azure CLI archive SHA256='+$hash)
  Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $root 'tools\azure-cli') -Force
}
if (!(Test-Path $az)) {throw 'Azure CLI installation incomplete'}
$env:AZURE_CONFIG_DIR=Join-Path $root 'evidence\azure-config'
$env:AZURE_CORE_COLLECT_TELEMETRY='no'
& $az version --only-show-errors
if ($LASTEXITCODE -ne 0) {throw 'Azure CLI verification failed'}
& $az extension add --name containerapp --upgrade --yes --only-show-errors
if ($LASTEXITCODE -ne 0) {throw 'Azure Container Apps extension failed'}
$venv=Join-Path $root 'project\.venv'
$py=Join-Path $venv 'Scripts\python.exe'
if (!(Test-Path $py)) {& python -m venv $venv; if($LASTEXITCODE -ne 0){throw 'venv failed'}}
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $root 'tools\browsers'
$deps=@('playwright==1.56.0','beautifulsoup4>=4.12,<5','PyYAML>=6,<7','azure-storage-blob>=12.22,<13','azure-identity>=1.19,<2','pytest>=8,<10','tzdata>=2025.2')
& $py -m pip install --disable-pip-version-check --no-input @deps
if ($LASTEXITCODE -ne 0) {throw 'Dependency installation failed'}
& $py -m playwright install chromium
if ($LASTEXITCODE -ne 0) {throw 'Chromium installation failed'}
$state=Get-Content -Raw $ledger | ConvertFrom-Json
foreach($kv in @(@('azure_cli_cmd',$az),@('python_venv',$venv),@('playwright_browsers',$env:PLAYWRIGHT_BROWSERS_PATH))) {$state | Add-Member -NotePropertyName $kv[0] -NotePropertyValue $kv[1] -Force}
$state | Add-Member -NotePropertyName scoped_install_verified_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
$state | ConvertTo-Json -Depth 8 | Set-Content $ledger -Encoding UTF8
Write-Output 'SCOPED_TOOLCHAIN_READY. No system-wide PATH changes; Azure login and retailer authorization not performed.'