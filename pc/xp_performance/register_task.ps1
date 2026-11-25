# One-time setup: run the pull every Tuesday at 6:00 (PC local time), before the hub publish step.
# Run in PowerShell as the user who owns C:\XP:  powershell -ExecutionPolicy Bypass -File C:\XP\xp_performance\register_task.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$here\run_performance.ps1`"" -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 6:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "XP Performance Overview pull" -Action $action -Trigger $trigger -Settings $settings -Description "MerchantSpring API pull for hub/performance.html" -Force
