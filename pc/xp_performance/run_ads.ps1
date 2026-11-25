# XP Strategy - Performance Overview: Amazon Ads API pull for the ad columns (no Claude tokens).
# Run by Windows Task Scheduler every Tuesday morning, or by hand:
#   powershell -ExecutionPolicy Bypass -File C:\XP\xp_performance\run_ads.ps1 -Profiles   # list profiles to fill config_ads.json
#   powershell -ExecutionPolicy Bypass -File C:\XP\xp_performance\run_ads.ps1 -Check      # token + one small report
#   powershell -ExecutionPolicy Bypass -File C:\XP\xp_performance\run_ads.ps1             # full pull
# Output: output\<run date>\ads_daily.json (+ log), history\ads_daily.json, output\ads_bundle_<run date>.zip
param([switch]$Profiles, [switch]$Check, [string]$Only = "", [int]$Days = 0, [string]$Today = "")

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
New-Item -ItemType Directory -Force -Path "$here\logs" | Out-Null
$log = "$here\logs\ads_$(Get-Date -Format yyyy-MM-dd_HHmm).log"

# Optional overrides; normally the credentials come from the budget bot config.
foreach ($v in "ADS_CLIENT_ID", "ADS_CLIENT_SECRET", "ADS_REFRESH_TOKEN") {
  if (-not (Get-Item "env:$v" -ErrorAction SilentlyContinue)) {
    $u = [Environment]::GetEnvironmentVariable($v, "User"); if ($u) { Set-Item "env:$v" $u }
  }
}

$exe = "python"; $pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $exe = "py"; $pyArgs += "-3" }
$pyArgs += "ads_pull.py"
if ($Profiles) { $pyArgs += "--profiles" }
if ($Check)    { $pyArgs += "--check" }
if ($Only)     { $pyArgs += @("--only", $Only) }
if ($Days)     { $pyArgs += @("--days", $Days) }
if ($Today)    { $pyArgs += @("--today", $Today) }

& $exe @pyArgs 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
if ($Profiles -or $Check) { exit $code }

$run = Get-ChildItem "$here\output" -Directory | Sort-Object Name -Descending | Select-Object -First 1
if ($run -and (Test-Path "$($run.FullName)\ads_daily.json")) {
  $zip = "$here\output\ads_bundle_$($run.Name).zip"
  if (Test-Path $zip) { Remove-Item $zip }
  Compress-Archive -Path "$($run.FullName)\ads_daily.json", "$($run.FullName)\ads_pull.log" -DestinationPath $zip
  "Bundle: $zip" | Tee-Object -FilePath $log -Append
}
exit $code
