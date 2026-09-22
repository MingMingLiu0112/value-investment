[CmdletBinding()]
param(
    [string]$ExpectedDate = (Get-Date).ToString('yyyy-MM-dd')
)

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root 'runtime'
$logs = Join-Path $runtime 'logs'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
Start-Transcript -LiteralPath (Join-Path $logs "moutai-b1-excel-publish-$stamp.log") -Append | Out-Null

try {
    Set-Location $root
    if ($ExpectedDate -notmatch '^\d{4}-\d{2}-\d{2}$') { throw 'ExpectedDate must be an ISO calendar date.' }
    $pointerPath = Join-Path $runtime 'valuation-results\600519-current-equity-stage-b-latest.json'
    if (-not (Test-Path -LiteralPath $pointerPath)) { throw 'Current Moutai B1 valuation pointer is missing.' }
    $pointer = Get-Content -LiteralPath $pointerPath -Raw | ConvertFrom-Json
    $evidencePath = Join-Path $root ([string]$pointer.path)
    if (Test-Path -LiteralPath $evidencePath -PathType Container) {
        $evidencePath = Join-Path $evidencePath 'evidence.json'
    }
    if (-not (Test-Path -LiteralPath $evidencePath)) { throw 'Current Moutai B1 valuation evidence is missing.' }
    $evidenceHash = (Get-FileHash -LiteralPath $evidencePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($evidenceHash -ne ([string]$pointer.sha256).ToLowerInvariant()) { throw 'Current Moutai B1 valuation evidence hash changed.' }
    $payload = Get-Content -LiteralPath $evidencePath -Raw | ConvertFrom-Json
    $value = $payload.result
    $bridge = $payload.price_bridge
    $validity = $payload.model_validity
    if ($payload.version -ne 'moutai-stage-b-valuation-result-v2' -or $value.symbol -ne '600519' -or
        $value.status -ne 'conditional_research_only' -or $value.confidence -ne '低' -or
        $payload.trade_approved -ne $false -or $payload.live_eligible -ne $false -or
        $validity.status -ne 'VALID' -or $bridge.bridge_status -ne 'READY' -or
        $bridge.quote_date -ne $ExpectedDate -or $null -eq $bridge.current_price -or
        $null -eq $bridge.margin_to_bear -or $null -eq $bridge.margin_to_base) {
        throw 'Current Moutai B1 result does not have a valid model and verified current price bridge eligible for Excel publication.'
    }
    foreach ($number in @($bridge.current_price, $bridge.margin_to_bear, $bridge.margin_to_base)) {
        $parsed = [decimal]::Parse([string]$number, [Globalization.CultureInfo]::InvariantCulture)
        if ($parsed -ne $parsed) { throw 'Current Moutai B1 result contains a non-finite numeric value.' }
    }
    $publication = & (Join-Path $PSScriptRoot 'run_excel_mvp_publication.ps1') -Publish
    if ($LASTEXITCODE -ne 0) { throw 'Excel MVP atomic publication failed.' }
    [PSCustomObject]@{
        status = 'published_same_date_conditional_research'; expected_date = $ExpectedDate
        valuation_evidence = $evidencePath; valuation_sha256 = $evidenceHash
        publication = ($publication | Select-Object -Last 1); trade_approved = $false
    } | ConvertTo-Json -Compress
}
catch {
    [PSCustomObject]@{ status = 'not_published'; expected_date = $ExpectedDate; error = $_.Exception.Message; trade_approved = $false } |
        ConvertTo-Json -Compress
    exit 1
}
finally { Stop-Transcript | Out-Null }
