[CmdletBinding()]
param(
    [string]$TaskName = 'ValueInvestmentAgent-MoutaiB1ExcelPublish',
    [datetime]$At = (Get-Date '17:30')
)

$ErrorActionPreference = 'Stop'
$runScript = Join-Path $PSScriptRoot 'run_moutai_b1_excel_publish.ps1'
if (-not (Test-Path -LiteralPath $runScript)) { throw "Startup script was not found: $runScript" }
$pwsh = 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe'
if (-not (Test-Path -LiteralPath $pwsh)) { throw "PowerShell 7 was not found: $pwsh" }

$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -File `"$runScript`"" -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'Publishes only a same-date, low-confidence Moutai B1 conditional-research result after candidate and WPS verification. Never publishes orders or trading approval.' -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
