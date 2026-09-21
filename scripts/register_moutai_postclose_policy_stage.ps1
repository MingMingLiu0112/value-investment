[CmdletBinding()]
param([string]$TaskName='ValueInvestmentAgent-MoutaiPostclosePolicyStage',[datetime]$At=(Get-Date '16:40'))
$ErrorActionPreference='Stop'
$pwsh='C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe'
$run=Join-Path $PSScriptRoot 'run_moutai_postclose_p1_refresh.ps1'
$action=New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -File `"$run`"" -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$trigger=New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $At
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'Rebuild and audit a research-only 600519 P1 model from a same-day verified pre-close receipt. Never authorizes orders.' -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State
