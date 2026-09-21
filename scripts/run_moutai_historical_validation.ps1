[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root 'runtime'
$logDirectory = Join-Path $runtime 'logs'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$transcript = Join-Path $logDirectory "moutai-historical-validation-$timestamp.log"

function Get-Python {
    foreach ($candidate in @(
        (Join-Path $runtime 'venv\Scripts\python.exe'),
        (Join-Path $runtime 'test-venv\Scripts\python.exe')
    )) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw 'Project Python runtime is missing.'
}

function Invoke-AgentJson([string]$Python, [string[]]$Arguments, [string]$Name) {
    $lines = @(& $Python -X utf8 @Arguments)
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE." }
    $line = @($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)
    if ($line.Count -ne 1) { throw "$Name did not produce a final JSON result." }
    try { return $line[0] | ConvertFrom-Json -ErrorAction Stop }
    catch { throw "$Name produced invalid final JSON: $($_.Exception.Message)" }
}

try {
    Start-Transcript -LiteralPath $transcript -Append | Out-Null
    Set-Location $root
    $python = Get-Python
    $range = Invoke-AgentJson $python @('scripts/replay_moutai_experimental_range_strategy.py') 'Historical range replay'
    $closure = Invoke-AgentJson $python @('scripts/run_moutai_simulation_closure.py') 'Historical execution closure'
    [PSCustomObject]@{
        status = 'succeeded'
        mode = 'offline_historical_validation'
        uses_live_quote = $false
        waits_for_next_trading_day = $false
        range_experiment = $range.output
        closure = $closure.output
        strategy_backtest_complete = $false
        trade_approved = $false
        live_eligible = $false
        note = 'Replays only pinned local historical evidence. It is a validation receipt, not an investment recommendation.'
    } | ConvertTo-Json -Compress
}
catch {
    [PSCustomObject]@{
        status = 'failed'
        mode = 'offline_historical_validation'
        at = (Get-Date).ToString('o')
        error = $_.Exception.Message
        trade_approved = $false
    } | ConvertTo-Json -Compress
    exit 1
}
finally {
    if ($null -ne $Host -and (Get-Variable -Name transcript -ErrorAction SilentlyContinue)) {
        try { Stop-Transcript | Out-Null } catch { }
    }
}
