# One-time setup: run the pull every Tuesday at 5:00 (PC local time), before the hub publish step.
# Run in PowerShell as the user who owns C:\XP:  powershell -ExecutionPolicy Bypass -File C:\XP\xp_performance\register_task.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$here\run_ads.ps1`"" -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 5:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName "XP Performance Overview ads pull" -Action $action -Trigger $trigger -Settings $settings -Description "Amazon Ads API pull (ad columns) for hub/performance.html" -Force
