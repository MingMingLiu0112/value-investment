[CmdletBinding()]
param(
    [string]$TaskName = 'ValueInvestmentAgent-DailyUpdate',
    [datetime]$At = (Get-Date '16:30')
)

$ErrorActionPreference = 'Stop'
$runScript = Join-Path $PSScriptRoot 'run_daily_update.ps1'
if (-not (Test-Path -LiteralPath $runScript)) {
    throw "Startup script was not found: $runScript"
}

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'Fetch audited results from the central database and sync the local Excel copy.' -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
