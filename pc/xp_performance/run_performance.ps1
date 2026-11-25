# XP Strategy - Performance Overview weekly pull (MerchantSpring API, no Claude tokens).
# Run by Windows Task Scheduler every Tuesday morning, or by hand:
#   powershell -ExecutionPolicy Bypass -File C:\XP\xp_performance\run_performance.ps1
#   powershell -ExecutionPolicy Bypass -File C:\XP\xp_performance\run_performance.ps1 -Check
# Output: C:\XP\xp_performance\output\<run date>\ (ms\*.json, manifest.json, pull.log) and a zip of it.
param([switch]$Check, [string]$Only = "", [string]$Today = "")

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
New-Item -ItemType Directory -Force -Path "$here\logs" | Out-Null
$log = "$here\logs\run_$(Get-Date -Format yyyy-MM-dd_HHmm).log"

# API key: user environment variable MS_API_KEY (set once with:
#   [Environment]::SetEnvironmentVariable("MS_API_KEY", "<key>", "User")  )
if (-not $env:MS_API_KEY) { $env:MS_API_KEY = [Environment]::GetEnvironmentVariable("MS_API_KEY", "User") }

$py = (Get-Command py -ErrorAction SilentlyContinue)
$pyArgs = @()
if ($py) { $exe = "py"; $pyArgs += "-3" } else { $exe = "python" }
$pyArgs += @("-u", "perf_pull.py")
if ($Check) { $pyArgs += "--check" }
if ($Only)  { $pyArgs += @("--only", $Only) }
if ($Today) { $pyArgs += @("--today", $Today) }

& $exe @pyArgs 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
if ($Check) { exit $code }

# Zip the newest run folder so it is one file to hand over (or for the publish step to pick up).
$run = Get-ChildItem "$here\output" -Directory | Sort-Object Name -Descending | Select-Object -First 1
if ($run) {
  $zip = "$here\output\perf_bundle_$($run.Name).zip"
  if (Test-Path $zip) { Remove-Item $zip }
  Compress-Archive -Path "$($run.FullName)\*" -DestinationPath $zip
  "Bundle: $zip" | Tee-Object -FilePath $log -Append
}
exit $code
