<#
P9 bounded acceptance preflight. Default: read published local evidence and write
one receipt under .tmp. -RunTests explicitly opts into isolated tests/build.
No quote capture, private journal read/write, Excel publication, approval or order.
Exit 0 = checked engineering evidence passed; 1 = integrity/test failure;
3 = -FullAcceptance needs actual external/user/browser evidence.
#>
param([switch]$RunTests, [switch]$FullAcceptance)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required' }
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $root
$started = [DateTimeOffset]::Now
$failures = [System.Collections.Generic.List[string]]::new()
$checks = [System.Collections.Generic.List[object]]::new()

function Check-Hash {
    param([string]$RelativePath, [string]$Expected, [string]$Label)
    $target = Join-Path $root $RelativePath
    $present = Test-Path -LiteralPath $target -PathType Leaf
    $actual = if ($present) { (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant() } else { $null }
    $passed = ($present -and $Expected -and $actual -eq $Expected.ToLowerInvariant())
    $checks.Add([pscustomobject]@{ label = $Label; path = $RelativePath; status = $(if ($passed) { 'PASS' } else { 'FAIL' }); sha256 = $actual })
    if (-not $passed) { $failures.Add("$Label`: $RelativePath") }
}

try {
    $head = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Git HEAD unavailable' }
    $branch = (& git branch --show-current).Trim()
    $python = (Get-Command python -ErrorAction Stop).Source
    $node = (Get-Command node -ErrorAction Stop).Source
    $pointer = Get-Content -LiteralPath 'config/current-daily-public-snapshot.json' -Raw -Encoding utf8 | ConvertFrom-Json
    if ($pointer.status -ne 'VERIFIED' -or $pointer.action -ne 'no_order') { throw 'Current public pointer is not verified no_order' }
    Check-Hash $pointer.packet_path $pointer.packet_sha256 'public_packet'
    $packet = Get-Content -LiteralPath $pointer.packet_path -Raw -Encoding utf8 | ConvertFrom-Json
    if ($packet.publication_id -ne $pointer.publication_id -or $packet.content_sha256 -ne $pointer.content_sha256 -or -not $packet.source_bindings_verified -or $packet.action -ne 'no_order') {
        $failures.Add('public_packet_contract')
    }
    $receipt = Get-Content -LiteralPath $pointer.receipt_path -Raw -Encoding utf8 | ConvertFrom-Json
    if ($receipt.publication_id -ne $pointer.publication_id -or
        $receipt.packet_path -ne $pointer.packet_path -or
        $receipt.packet_sha256 -ne $pointer.packet_sha256 -or
        $receipt.content_sha256 -ne $pointer.content_sha256 -or
        $receipt.research_version -ne $pointer.research_version -or
        $receipt.action -ne 'no_order') {
        $failures.Add('immutable_publication_receipt_mismatch')
    }
    foreach ($binding in @($packet.source_bindings)) {
        Check-Hash $binding.path $binding.sha256 "packet_binding:$($binding.role)"
    }
    $registry = Get-Content -LiteralPath 'config/current-company-research-registry.json' -Raw -Encoding utf8 | ConvertFrom-Json
    foreach ($company in $registry.companies.PSObject.Properties) {
        foreach ($evidence in @($company.Value.evidence)) {
            Check-Hash $evidence.path $evidence.sha256 "registry:$($company.Name)"
        }
    }
    $quotes = Get-Content -LiteralPath 'config/current-quote-bridge.json' -Raw -Encoding utf8 | ConvertFrom-Json
    foreach ($quote in $quotes.quotes.PSObject.Properties) {
        Check-Hash $quote.Value.quote_bundle $quote.Value.quote_bundle_sha256 "quote:$($quote.Name)"
    }
    $prices = Get-Content -LiteralPath 'config/current-price-conditions.json' -Raw -Encoding utf8 | ConvertFrom-Json
    Check-Hash $prices.watch_source_binding.path $prices.watch_source_binding.sha256 'hotspot_selection'
    foreach ($item in @($prices.items)) {
        Check-Hash $item.case_path $item.case_sha256 "price:$($item.symbol)"
    }
    $testStatus = 'NOT_RUN'
    if ($RunTests) {
        $env:PYTHONPATH = Join-Path $root 'src'
        $env:PYTHONIOENCODING = 'utf-8'
        $env:TEMP = Join-Path $root '.tmp'
        $env:TMP = $env:TEMP
        & $python -B -m pytest -q -p no:cacheprovider --basetemp=.tmp/p9-audit-tests tests/web_api tests/test_hotspot_price_action_case.py tests/test_daily_public_packet_identity.py tests/test_private_risk_held_marks.py
        if ($LASTEXITCODE -ne 0) { $failures.Add('python_tests') }
        & npm run format --prefix web
        if ($LASTEXITCODE -ne 0) { $failures.Add('web_format') }
        & npm test --prefix web -- --run
        if ($LASTEXITCODE -ne 0) { $failures.Add('web_tests') }
        & npm run build --prefix web
        if ($LASTEXITCODE -ne 0) { $failures.Add('web_build') }
        $testStatus = $(if ($failures.Count -eq 0) { 'PASS' } else { 'FAIL' })
    }
    $status = if ($failures.Count -gt 0) { 'FAIL' } elseif ($FullAcceptance) { 'BLOCKED_EXTERNAL' } else { 'PASS_ENGINEERING_PRECHECK' }
    $exitCode = if ($failures.Count -gt 0) { 1 } elseif ($FullAcceptance) { 3 } else { 0 }
    $receipt = [ordered]@{
        schema_version = 'p9-readonly-preflight-v1'; action = 'no_order'
        started_at = $started.ToString('o'); finished_at = [DateTimeOffset]::Now.ToString('o')
        head = $head; branch = $branch; python = $python; node = $node
        publication_id = $pointer.publication_id; research_version = $pointer.research_version
        quote_trade_date = $packet.dates.quote_trade_date
        latest_completed_session = $packet.dates.latest_completed_trade_session
        formal_admission_count = $packet.formal_admission_count
        research_counts = $packet.research_counts
        hotspot_case_count = @($prices.items).Count; source_checks = @($checks)
        tests = $testStatus; browser = 'NOT_RUN_BY_SCRIPT_REQUIRES_ACTUAL_UI'
        private_account = 'NOT_READ_REQUIRES_USER_CONFIRMATION'
        human_review = 'NOT_SIGNED_BY_SCRIPT'
        excel = 'NOT_WRITTEN'; full_acceptance = $(if ($FullAcceptance) { 'BLOCKED_EXTERNAL' } else { 'NOT_ASSESSED' })
        failures = @($failures); status = $status; exit_code = $exitCode
    }
} catch {
    $exitCode = 1
    $receipt = [ordered]@{
        schema_version = 'p9-readonly-preflight-v1'; action = 'no_order'
        started_at = $started.ToString('o'); finished_at = [DateTimeOffset]::Now.ToString('o')
        status = 'FAIL'; exit_code = 1; failures = @($_.Exception.Message)
        browser = 'NOT_RUN_BY_SCRIPT'; private_account = 'NOT_READ'; excel = 'NOT_WRITTEN'
    }
}
$directory = Join-Path $root '.tmp'
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$receiptPath = Join-Path $directory 'p9-readonly-preflight.json'
$receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding utf8
Write-Host "P9 $($receipt.status) | HEAD $($receipt.head) | publication $($receipt.publication_id) | checks $($checks.Count) | tests $($receipt.tests)"
Write-Host "Receipt: $receiptPath"
exit $exitCode
