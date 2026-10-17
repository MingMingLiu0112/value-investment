$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$root = 'D:/GPTProject/value-investment'
Set-Location -LiteralPath $root
$destination = Join-Path $root 'artifacts/current/tl11-p61-20261015'
$pwsh = 'C:/Users/we/AppData/Local/Programs/PowerShell/7/pwsh.exe'
foreach ($name in @('safe-refresh-live-probe.log', 'safe-refresh-recovery.log')) {
    if (Test-Path (Join-Path $destination $name)) { throw "Evidence already exists: $name" }
}
Copy-Item config/current-daily-public-snapshot.json (Join-Path $destination 'pointer-before-live-probe.json')
& $pwsh -NoProfile -File scripts/current/run_daily_workbench.ps1 -Mode SAFE_REFRESH -NoServer -Symbols '600887,000333' *>&1 |
    Tee-Object -FilePath (Join-Path $destination 'safe-refresh-live-probe.log')
$probeExit = $LASTEXITCODE
Copy-Item .tmp/daily-workbench-latest-run.json (Join-Path $destination 'live-probe-run-receipt.json')
Copy-Item config/current-daily-public-snapshot.json (Join-Path $destination 'pointer-after-live-probe.json')
& $pwsh -NoProfile -File scripts/current/run_daily_workbench.ps1 -Mode SAFE_REFRESH -NoServer *>&1 |
    Tee-Object -FilePath (Join-Path $destination 'safe-refresh-recovery.log')
$recoveryExit = $LASTEXITCODE
Copy-Item .tmp/daily-workbench-latest-run.json (Join-Path $destination 'recovery-run-receipt.json')
Copy-Item config/current-daily-public-snapshot.json (Join-Path $destination 'pointer-after-recovery.json')
@{ probe_exit_code=$probeExit; recovery_exit_code=$recoveryExit; ps_version=$PSVersionTable.PSVersion.ToString(); finished_at=[DateTimeOffset]::Now.ToString('o') } |
    ConvertTo-Json | Set-Content (Join-Path $destination 'actual-entry-results.json') -Encoding utf8
