<#
P10 read-only acceptance. No capture, approval, private-account access, Excel
publication, scheduler or order. -RunTests opts into isolated engineering checks.
Exit 0: integrity precheck passed; 1: engineering failure; 3: full assisted-use
acceptance still needs independent market, research, human and private evidence.
#>
param(
    [switch]$RunTests,
    [switch]$FullAcceptance,
    [string]$OutputPath = '.tmp/p10/acceptance.json'
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required' }
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $root
$safeRoot = [System.IO.Path]::GetFullPath((Join-Path $root '.tmp/p10'))
$output = [System.IO.Path]::GetFullPath((Join-Path $root $OutputPath))
if (-not [System.IO.Path]::GetDirectoryName($output).Equals($safeRoot,
        [StringComparison]::OrdinalIgnoreCase) -or [System.IO.Path]::GetExtension($output) -ne '.json') {
    throw 'OutputPath must be a JSON file inside .tmp/p10'
}
New-Item -ItemType Directory -Force -Path $safeRoot | Out-Null
$head = (& git rev-parse HEAD).Trim()
$branch = (& git branch --show-current).Trim()
$dirty = @(& git status --porcelain)
$failures = [System.Collections.Generic.List[string]]::new()
& (Join-Path $PSScriptRoot 'audit_p9_readonly.ps1')
$p9Exit = $LASTEXITCODE
$p9 = Get-Content -LiteralPath '.tmp/p9-readonly-preflight.json' -Raw -Encoding utf8 | ConvertFrom-Json
if ($p9Exit -ne 0 -or $p9.status -ne 'PASS_ENGINEERING_PRECHECK' -or $p9.head -ne $head) {
    $failures.Add('P9_SOURCE_OR_PUBLICATION_INTEGRITY')
}
$pointer = Get-Content -LiteralPath 'config/current-daily-public-snapshot.json' -Raw -Encoding utf8 | ConvertFrom-Json
$packet = Get-Content -LiteralPath $pointer.packet_path -Raw -Encoding utf8 | ConvertFrom-Json
$registry = Get-Content -LiteralPath 'config/current-company-research-registry.json' -Raw -Encoding utf8 | ConvertFrom-Json
$value = @{}
foreach ($symbol in @('600887', '600519')) {
    $company = $packet.company_statuses.$symbol
    $registered = $registry.companies.$symbol
    $value[$symbol] = [ordered]@{
        research_status = $company.research_status.code
        valuation_status = $company.valuation_status.code
        economic_reliability = $(if ($registered.status -eq 'PENDING_RESEARCH') { 'NOT_PROVEN' } else { 'RECHECK_REQUIRED' })
        b1_price_admitted = ($company.price_bridge.price_admitted -eq $true)
        quote_date = $company.price_bridge.quote_date
        observed_at = $company.price_bridge.quote_observed_at
        missing_inputs = @($registered.missing_inputs)
        formal_qualification = 'NOT_PROVEN'
    }
}
$b1 = if (@($value.Values | Where-Object b1_price_admitted -eq $true).Count -eq 2) {
    'NOT_PROVEN_REQUIRES_INDEPENDENT_SAME_DAY_SOURCE_REPLAY'
} else { 'BLOCKED_EXTERNAL' }
$tests = 'NOT_RUN'
$fullCore = 'NOT_RUN'
if ($RunTests) {
    $env:PYTHONPATH = Join-Path $root 'src'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:TEMP = Join-Path $root '.tmp'
    $env:TMP = $env:TEMP
    $python = (Get-Command python -ErrorAction Stop).Source
    & $python -B -m pytest -q -p no:cacheprovider --basetemp=.tmp/p10-tests `
        tests/test_quote_b1_acquisition.py tests/test_quote_session_conversion.py `
        tests/test_quote_bridge_execution.py tests/test_daily_quote_binding.py `
        tests/test_hotspot_opportunity_quality.py tests/test_private_risk_held_marks.py `
        tests/web_api
    if ($LASTEXITCODE -ne 0) { $failures.Add('P10_TARGETED_TESTS') }
    & npm run build --prefix web
    if ($LASTEXITCODE -ne 0) { $failures.Add('WEB_BUILD') }
    if ($FullAcceptance) {
        & $python -B -m pytest -q -p no:cacheprovider --basetemp=.tmp/p10-full-acceptance-core
        $fullCore = if ($LASTEXITCODE -eq 0) { 'ENGINEERING_PASS' } else { 'ENGINEERING_FAIL' }
        if ($fullCore -eq 'ENGINEERING_FAIL') { $failures.Add('FULL_CORE_TESTS') }
    }
    $tests = if ($failures.Count -eq 0) { 'ENGINEERING_PASS' } else { 'ENGINEERING_FAIL' }
}
$headAfter = (& git rev-parse HEAD).Trim()
if ($headAfter -ne $head) { $failures.Add('HEAD_CHANGED_DURING_ACCEPTANCE') }
$status = if ($failures.Count -gt 0) { 'ENGINEERING_FAIL' }
          elseif ($FullAcceptance) { 'BLOCKED_EXTERNAL' }
          else { 'NOT_PROVEN' }
$exitCode = if ($failures.Count -gt 0) { 1 } elseif ($FullAcceptance) { 3 } else { 0 }
$receipt = [ordered]@{
    schema_version = 'p10-assisted-use-acceptance-v1'; action = 'no_order'
    checked_at = [DateTimeOffset]::UtcNow.ToString('o')
    head = $head; branch = $branch; worktree_dirty = ($dirty.Count -gt 0)
    head_after_tests = $headAfter
    publication_id = $pointer.publication_id; packet_sha256 = $pointer.packet_sha256
    source_checks = @($p9.source_checks).Count; source_integrity = $(if ($p9Exit -eq 0) { 'ENGINEERING_PASS' } else { 'ENGINEERING_FAIL' })
    b1_price_state = $b1; value_companies = $value
    hotspot_observations = @($packet.price_conditions.items).Count
    hotspot_strategy_quality = 'NOT_PROVEN'
    held_continuity_real_account = 'BLOCKED_EXTERNAL'
    isolated_private_continuity = $(if ($RunTests -and $tests -eq 'ENGINEERING_PASS') { 'ENGINEERING_PASS' } else { 'NOT_RUN' })
    isolated_private_full_dual_sleeve_flow = 'NOT_PROVEN'
    full_core_tests = $fullCore
    browser = 'NOT_RUN_BY_SCRIPT_REQUIRES_INTERACTIVE_EVIDENCE'
    canonical_excel = 'NOT_WRITTEN'
    formal_admission_count = $packet.formal_admission_count
    human_g3_and_materiality = 'BLOCKED_EXTERNAL'
    personal_ips_and_account = 'BLOCKED_EXTERNAL'
    tests = $tests; failures = @($failures); status = $status; exit_code = $exitCode
}
$receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $output -Encoding utf8
Write-Host "P10 $status | HEAD $head | publication $($pointer.publication_id) | B1 $b1 | tests $tests"
Write-Host "Receipt: $output"
exit $exitCode
