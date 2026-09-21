[CmdletBinding()]
param(
    [string]$TaskName = 'ValueInvestmentAgent-DailyUpdate',
    [datetime]$At = (Get-Date '16:50')
)

$ErrorActionPreference = 'Stop'
$runScript = Join-Path $PSScriptRoot 'run_server_excel_sync.ps1'
if (-not (Test-Path -LiteralPath $runScript)) {
    throw "Startup script was not found: $runScript"
}

$pwsh = 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe'
if (-not (Test-Path -LiteralPath $pwsh)) { throw "PowerShell 7 was not found: $pwsh" }
$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -File `"$runScript`"" -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'Refresh the local audited Moutai observation, then download the audited server export and atomically sync the local WPS Excel workbook.' -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
