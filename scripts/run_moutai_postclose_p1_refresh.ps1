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
Start-Transcript -LiteralPath (Join-Path $logDirectory "moutai-postclose-p1-$timestamp.log") -Append | Out-Null

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
    Set-Location $root
    $python = Get-Python
    $receipt = Get-ChildItem (Join-Path $runtime 'company-research') -Directory -Filter '600519-preclose-capital-receipt-*' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $receipt) { throw 'No same-day pre-close capital receipt exists; refusing to rebuild the current P1 model.' }
    $receiptPath = Join-Path $receipt.FullName 'evidence.json'
    $receiptData = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    $today = (Get-Date).ToString('yyyy-MM-dd')
    if ($receiptData.through -ne $today -or -not $receiptData.preclose_complete) {
        throw 'Latest pre-close receipt is not complete for today; refusing cross-date P1 refresh.'
    }

    $policy = Invoke-AgentJson $python @('scripts/stage_moutai_postclose_policy.py', '--receipt', $receiptPath, '--registered-at', (Get-Date).ToString('o')) 'Policy stage'
    $model = Invoke-AgentJson $python @('scripts/value_moutai_consolidated_parent_equity.py', '--current-policy', $policy.output) 'Current model'
    $bridge = Invoke-AgentJson $python @('scripts/assess_moutai_current_capital_bridge.py') 'Capital bridge'
    $cost = Invoke-AgentJson $python @('scripts/assess_moutai_current_cost_of_equity_policy.py') 'Cost-policy review'
    $assumptions = Invoke-AgentJson $python @('scripts/assess_moutai_current_forward_assumptions.py') 'Forward-assumption review'
    $contract = Invoke-AgentJson $python @('scripts/freeze_moutai_current_p1_model_contract.py') 'P1 contract freeze'
    $admission = Invoke-AgentJson $python @('scripts/audit_moutai_current_valuation_admission.py') 'P1 admission audit'
    $scope = Invoke-AgentJson $python @('scripts/assess_moutai_current_equity_scope.py') 'Scope review'
    $thesis = Invoke-AgentJson $python @('scripts/assess_moutai_current_thesis.py') 'Thesis review'
    if ($admission.blocking_gate_ids.Count -ne 0 -or -not $admission.p1_current_model_admitted) {
        throw 'P1 admission remains blocked; the 16:50 paper cycle must fail closed.'
    }
    [PSCustomObject]@{
        status = 'succeeded'; date = $today; policy = $policy.output; model = $model.output; bridge = $bridge.output
        p1_contract = $contract.output; admission = $admission.output; scope = $scope.output; thesis = $thesis.output
        trade_approved = $false; live_eligible = $false
    } | ConvertTo-Json -Compress
}
catch {
    [PSCustomObject]@{ status = 'failed'; at = (Get-Date).ToString('o'); error = $_.Exception.Message; trade_approved = $false } |
        ConvertTo-Json -Compress
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
