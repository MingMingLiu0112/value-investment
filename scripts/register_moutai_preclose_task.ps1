[CmdletBinding()]
param(
    [string]$TaskName = 'ValueInvestmentAgent-MoutaiPrecloseCapitalRefresh',
    [datetime]$At = (Get-Date '14:45')
)

$ErrorActionPreference = 'Stop'
$runScript = Join-Path $PSScriptRoot 'run_moutai_preclose_capital_refresh.ps1'
$pwsh = 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe'
if (-not (Test-Path -LiteralPath $runScript)) { throw "Startup script was not found: $runScript" }
if (-not (Test-Path -LiteralPath $pwsh)) { throw "PowerShell 7 was not found: $pwsh" }

$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -File `"$runScript`"" -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 12) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'Before-close CNINFO capital-event receipt for 600519. Fails closed on late, incomplete or non-empty results; never authorizes an order.' -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
