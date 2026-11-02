# Preserves original Python/Git/Node/system PATH and any preexisting ~/.azure data.
# Default: DRY RUN. -Execute removes only paths within this dedicated workspace.
[CmdletBinding()]
param([switch]$Execute,[switch]$IncludeProject)
$ErrorActionPreference='Stop'
$root=Join-Path $env:USERPROFILE 'MarianosAzureQualification'
$ledger=Join-Path $root 'installation-ledger.json'
if (!(Test-Path $ledger)) {throw 'Refusing cleanup without installation ledger'}
$state=Get-Content -Raw $ledger | ConvertFrom-Json
if ($state.workspace -ne $root) {throw 'Workspace mismatch, refusing cleanup'}
$targets=@('tools\azure-cli','downloads\azure-cli.zip','downloads\source-v03.b64',
           'downloads\source-v03.tar.xz','project\.venv','tools\browsers',
           'evidence\azure-config','evidence\pytest-tmp')
if ($IncludeProject) {$targets+=@('project')}
foreach($relative in $targets) {
  $full=Join-Path $root $relative
  if (!($full.StartsWith(($root+'\'),[StringComparison]::OrdinalIgnoreCase))) {throw 'Unsafe cleanup path'}
  if (Test-Path -LiteralPath $full) {
    if ($Execute) {Remove-Item -LiteralPath $full -Recurse -Force; Write-Output ('REMOVED '+$full)}
    else {Write-Output ('PLAN_REMOVE '+$full)}
  } else {Write-Output ('NOT_PRESENT '+$full)}
}
if ($Execute) {
  $state | Add-Member -NotePropertyName temporary_components_removed_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
  $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ledger -Encoding UTF8
  Write-Output 'CLEANUP_COMPLETE; audit ledger and scripts kept'
} else {Write-Output 'DRY_RUN_ONLY. Add -Execute to remove toolchain. Add -IncludeProject to remove project source.'}