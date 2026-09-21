[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root 'runtime'
$logs = Join-Path $runtime 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Start-Transcript -LiteralPath (Join-Path $logs "moutai-b1-after-close-$stamp.log") -Append | Out-Null

function Get-Python {
    foreach ($candidate in @(
        (Join-Path $runtime 'venv\Scripts\python.exe'),
        (Join-Path $runtime 'test-venv\Scripts\python.exe')
    )) { if (Test-Path -LiteralPath $candidate) { return $candidate } }
    throw 'Project Python runtime is missing.'
}

function Invoke-Json([string]$Python, [string[]]$Arguments, [string]$Name) {
    $lines = @(& $Python -X utf8 @Arguments)
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE." }
    $line = @($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)
    if ($line.Count -ne 1) { throw "$Name did not emit a final JSON line." }
    return $line[0] | ConvertFrom-Json -ErrorAction Stop
}

try {
    Set-Location $root
    $python = Get-Python
    $collection = Invoke-Json $python @('scripts/collect_quote_sessions.py', '--symbols', '600519') 'Quote collection'
    $report = Join-Path ([string]$collection.path) 'report.json'
    $observation = @($collection.observations | Where-Object { $_.symbol -eq '600519' })
    if ($observation.Count -ne 1 -or $observation[0].result.passed -ne $true) {
        [PSCustomObject]@{
            status = 'quote_rejected_no_model_rebuild'; at = (Get-Date).ToString('o'); quote_report = $report
            quote_status = if ($observation.Count -eq 1) { $observation[0].result.status } else { 'missing_observation' }
            trade_approved = $false; workbook_changed = $false
        } | ConvertTo-Json -Compress
        exit 0
    }
    # The model is constructed after the accepted close, using only the same-day
    # pre-close receipt. This task never writes orders or the canonical workbook.
    $refreshLines = @(& (Join-Path $PSScriptRoot 'run_moutai_postclose_p1_refresh.ps1'))
    if ($LASTEXITCODE -ne 0) { throw 'Post-close P1 refresh failed.' }
    $refreshLine = @($refreshLines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)
    if ($refreshLine.Count -ne 1) { throw 'Post-close P1 refresh did not emit a final JSON result.' }
    try { $refresh = $refreshLine[0] | ConvertFrom-Json -ErrorAction Stop }
    catch { throw "Post-close P1 refresh emitted invalid JSON: $($_.Exception.Message)" }
    if ($refresh.status -notin @('p1_simulation_admitted', 'model_staged_simulation_blocked')) {
        throw "Unexpected post-close P1 refresh status: $($refresh.status)"
    }
    $diagnostic = Invoke-Json $python @('scripts/review_moutai_parent_equity_assumptions.py', '--current-quote-report', $report) 'Reverse valuation review'
    $valuation = Invoke-Json $python @('scripts/build_moutai_valuation_result.py', '--diagnostic', (Join-Path ([string]$diagnostic.output) 'evidence.json')) 'Valuation result export'
    [PSCustomObject]@{
        status = 'model_and_reverse_valuation_staged'; at = (Get-Date).ToString('o'); quote_report = $report
        refresh = $refresh; diagnostic = $diagnostic.output; valuation = $valuation.output
        trade_approved = $false; workbook_changed = $false
    } | ConvertTo-Json -Compress
}
catch {
    [PSCustomObject]@{ status = 'failed'; at = (Get-Date).ToString('o'); error = $_.Exception.Message
        trade_approved = $false; workbook_changed = $false } | ConvertTo-Json -Compress
    exit 1
}
finally { Stop-Transcript | Out-Null }
