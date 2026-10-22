<#
TL9 MVP-2 / TL10-RC: one daily entry for the local investment workbench.

READ_ONLY (default)
  Compose the one daily public decision packet from the already registered
  artifacts, publish it as the current verified snapshot (a display
  publication only, never a research or trade approval), print the result in
  plain language, then start the Web workbench. No network calls, no quote
  registration, no private writes.

SAFE_REFRESH
  READ_ONLY plus the authorized dual-source quote collection, archiving and
  close registration, bounded current price observation, then a packet rebuild:
  re-running research, the human event review and the G3 valuation gate stay
  explicit human/engineering steps and are listed as pending actions, never
  signed here.

RESEARCH DISCOVERY (optional, Mock/TEST_ONLY only)
  -AutoDiscoverResearchContexts exports a bounded Mock batch from existing
  server-owned event, financial, hotspot and optional confirmed TEST_ONLY
  retrospective contexts, then runs that exact hash-pinned batch. A manually
  supplied -ResearchMockPlan pair remains the override. No live provider path,
  research approval, position size or order is reachable here.

The entry stays action=no_order: it reports what the existing gates decided,
and price triggers never waive formal gates or create a position size or order.

Exit codes (update result first, Web result second):
  0  update SUCCESS, Web ran or was skipped
  2  update BLOCKED (chain unavailable, identity conflict, refresh failed)
  3  update PARTIAL (succeeded with recorded notes)
  4  Web failed to start while the update itself succeeded
#>
param(
    [ValidateSet('READ_ONLY', 'SAFE_REFRESH')][string]$Mode = 'READ_ONLY',
    [ValidateSet(8001)][int]$Port = 8001,
    [switch]$Open,
    [switch]$NoServer,
    [switch]$Reauthorize,
    [string]$Symbols = '',
    [string]$ResearchMockPlan = '',
    [string]$ResearchMockPlanSha256 = '',
    [switch]$AutoDiscoverResearchContexts,
    [string]$ResearchTestOnlyRetrospective = '',
    [string]$ResearchTestOnlyRetrospectiveSha256 = '',
    [switch]$RegisterResearchDrafts,
    [switch]$BuildValueResearchPriority,
    [switch]$ExecuteValueEnrichment
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    & 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe' -NoProfile -File $PSCommandPath `
        -Mode $Mode -Port $Port -Open:$Open -NoServer:$NoServer -Reauthorize:$Reauthorize -Symbols $Symbols `
        -ResearchMockPlan $ResearchMockPlan -ResearchMockPlanSha256 $ResearchMockPlanSha256 `
        -AutoDiscoverResearchContexts:$AutoDiscoverResearchContexts `
        -ResearchTestOnlyRetrospective $ResearchTestOnlyRetrospective `
        -ResearchTestOnlyRetrospectiveSha256 $ResearchTestOnlyRetrospectiveSha256 `
        -RegisterResearchDrafts:$RegisterResearchDrafts -BuildValueResearchPriority:$BuildValueResearchPriority `
        -ExecuteValueEnrichment:$ExecuteValueEnrichment
    exit $LASTEXITCODE
}
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
if ($BuildValueResearchPriority -and $Mode -ne 'SAFE_REFRESH') {
    throw 'Value research priority requires explicit SAFE_REFRESH; READ_ONLY never starts research work.'
}
if ($ExecuteValueEnrichment -and (-not $BuildValueResearchPriority -or $Mode -ne 'SAFE_REFRESH')) {
    throw 'Financial enrichment requires SAFE_REFRESH and BuildValueResearchPriority.'
}
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $root
$env:PYTHONPATH = Join-Path $root 'src'
$env:PYTHONIOENCODING = 'utf-8'
$env:TEMP = Join-Path $root '.tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

# Serialize data updates and receipts, independently of the Web service lifetime.
try {
    $dailyRunLock = [System.IO.File]::Open((Join-Path $env:TEMP 'daily-workbench.lock'),
        [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None)
} catch [System.IO.IOException] {
    Write-Host '运行结果 : BUSY - 已有每日工作台任务正在运行；未修改其回执。'
    exit 2
}
try {

$notes = [System.Collections.Generic.List[string]]::new()
$startedAt = [DateTimeOffset]::UtcNow.ToString('o')
$receiptPath = Join-Path $env:TEMP 'daily-workbench-latest-run.json'
# An interrupted/failed invocation must not leave yesterday's SUCCESS as its result.
$initialReceipt = @{
    schema_version = 'daily-workbench-run-v1'; action = 'no_order'; mode = $Mode
    started_at = $startedAt; finished_at = $null; status = 'BLOCKED'; exit_code = 2
    published = $false; notes = @('本次更新尚未完成；继续显示历史已验证快照。')
}
$priorPointer = Join-Path $root 'config/current-daily-public-snapshot.json'
if (Test-Path -LiteralPath $priorPointer) {
    try { $initialReceipt.retained_publication_id = (Get-Content -LiteralPath $priorPointer -Raw -Encoding utf8 | ConvertFrom-Json).publication_id } catch { }
}
$initialReceipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$receiptPath.pending" -Encoding utf8
Move-Item -LiteralPath "$receiptPath.pending" -Destination $receiptPath -Force
trap {
    if ($null -eq $dailyRunLock) {
        Write-Host 'Web 服务 : 启动失败；保留已完成的数据更新回执。'
        exit 4
    }
    $failedReceipt = @{
        schema_version = 'daily-workbench-run-v1'; action = 'no_order'; mode = $Mode
        started_at = $startedAt; finished_at = [DateTimeOffset]::UtcNow.ToString('o')
        status = 'BLOCKED'; exit_code = 2; published = $false
        retained_publication_id = $initialReceipt.retained_publication_id
        notes = @('刷新后快照生成失败，Web 保留上一验证版本。')
    }
    $failedReceipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$receiptPath.pending" -Encoding utf8
    Move-Item -LiteralPath "$receiptPath.pending" -Destination $receiptPath -Force
    Write-Host "运行结果 : BLOCKED - $($_.Exception.Message)"
    exit 2
}
if (-not $Symbols) {
    $quoteRegistry = Get-Content -LiteralPath (Join-Path $root 'config/current-quote-bridge.json') -Raw -Encoding utf8 | ConvertFrom-Json
    $Symbols = @($quoteRegistry.quotes.PSObject.Properties.Name) -join ','
}

function Resolve-Python {
    $command = Get-Command python -ErrorAction SilentlyContinue
    foreach ($candidate in @($command.Source, 'D:\APP\Python313\python.exe')) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    return $null
}

function Invoke-PythonJson {
    param([string[]]$PythonArgs)
    $raw = & $script:python -X utf8 -B @PythonArgs 2>&1 | Out-String
    $code = $LASTEXITCODE
    $text = $raw.Trim()
    $parsed = $null
    $start = $text.IndexOf('{')
    if ($start -ge 0) {
        try { $parsed = $text.Substring($start) | ConvertFrom-Json } catch { $parsed = $null }
    }
    [pscustomobject]@{ ExitCode = $code; Text = $text; Json = $parsed }
}

function Write-ResearchReceipt {
    param([hashtable]$Value)
    $path = Join-Path $env:TEMP 'daily-workbench-research-latest.json'
    $Value | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath "$path.pending" -Encoding utf8
    Move-Item -LiteralPath "$path.pending" -Destination $path -Force
}

Write-Host '================ TL9 每日工作台 ================'
Write-Host "运行模式 : $Mode"

$python = Resolve-Python
if (-not $python) {
    Write-Host '运行结果 : BLOCKED - 未找到 Python 解释器（python 或 D:\APP\Python313\python.exe）。'
    throw 'Python interpreter unavailable'
}
$importCheck = & $python -X utf8 -B -c 'import value_investment_agent' 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host '运行结果 : BLOCKED - Python 环境无法导入 value_investment_agent。'; Write-Host $importCheck.Trim(); throw 'Python import failed'
}
Write-Host "Python   : $python"

# Explicit offline drafts are independent of quote refresh and public publication.
# Discovery is opt-in and only exports bounded Mock/TEST_ONLY inputs. A pinned
# manual batch remains the override, and no live provider path is reachable here.
if ($AutoDiscoverResearchContexts -or $ResearchMockPlan -or $ResearchMockPlanSha256 `
        -or $ResearchTestOnlyRetrospective -or $ResearchTestOnlyRetrospectiveSha256 `
        -or $RegisterResearchDrafts) {
    $researchResult = @{
        action = 'no_order'; mode = 'MOCK'; scope = 'TEST_ONLY_ENGINEERING'
        exit_code = 2; status = 'BLOCKED'; source = $null; discovery = $null; result = $null
    }
    try {
        $planPath = $null
        $planSha256 = $null
        if ($ResearchMockPlan -or $ResearchMockPlanSha256) {
            if (-not $ResearchMockPlan -or -not $ResearchMockPlanSha256) {
                throw 'Research Mock plan requires both path and SHA-256.'
            }
            $planPath = $ResearchMockPlan
            $planSha256 = $ResearchMockPlanSha256
            $researchResult.source = 'PINNED_MOCK_PLAN'
        } elseif ($AutoDiscoverResearchContexts) {
            $discoveryArgs = @('scripts/current/run_agent_research_pilot.py',
                '--mode', 'mock', '--discover-contexts')
            if ($ResearchTestOnlyRetrospective -or $ResearchTestOnlyRetrospectiveSha256) {
                if (-not $ResearchTestOnlyRetrospective -or -not $ResearchTestOnlyRetrospectiveSha256) {
                    throw 'TEST_ONLY retrospective discovery requires both path and SHA-256.'
                }
                $discoveryArgs += @('--test-only-retrospective', $ResearchTestOnlyRetrospective,
                    '--test-only-retrospective-sha256', $ResearchTestOnlyRetrospectiveSha256)
            }
            $discovery = Invoke-PythonJson $discoveryArgs
            $researchResult.discovery = $discovery.Json
            $researchResult.source = 'AUTO_DISCOVERY'
            if (-not $discovery.Json) {
                throw 'Research context discovery returned no readable result.'
            }
            if ($discovery.Json.action -ne 'no_order' -or $discovery.Json.mode -ne 'MOCK' `
                    -or $discovery.Json.approval_count -ne 0 -or
                    $discovery.Json.registered_or_published -ne $false) {
                throw 'Research context discovery violated the Mock/no-order boundary.'
            }
            if ($discovery.ExitCode -eq 2 -or $discovery.Json.status -eq 'BLOCKED' `
                    -or -not $discovery.Json.batch_plan) {
                $researchResult.exit_code = if ($discovery.ExitCode -ne 0) { $discovery.ExitCode } else { 2 }
                $researchResult.status = 'BLOCKED'
                Write-ResearchReceipt $researchResult
                $notes.Add('自动上下文发现未产生可用研究批次；未登记任何研究；继续其他更新。')
                Write-Host '研究草案 : BLOCKED（未发现可用上下文；未登记研究）'
                $planPath = $null
            } else {
                $planPath = [string]$discovery.Json.batch_plan.path
                $planSha256 = [string]$discovery.Json.batch_plan.sha256
                if (-not $planPath -or $planSha256 -notmatch '^[0-9a-f]{64}$') {
                    throw 'Research context discovery returned an invalid batch plan pin.'
                }
            }
        } else {
            throw 'Explicit -AutoDiscoverResearchContexts or a pinned Research Mock plan is required.'
        }
        if ($planPath) {
            $researchArgs = @('scripts/current/run_agent_research_pilot.py',
                '--mode', 'mock', '--batch-plan', $planPath,
                '--batch-plan-sha256', $planSha256)
            if ($RegisterResearchDrafts) { $researchArgs += '--register-drafts' }
            $research = Invoke-PythonJson $researchArgs
            $researchResult.exit_code = $research.ExitCode
            $researchResult.result = $research.Json
            $researchResult.status = if ($research.Json) { [string]$research.Json.status } else { 'FAILED' }
            Write-ResearchReceipt $researchResult
            Write-Host "研究草案 : $($researchResult.status)（MOCK；不批准研究或交易）"
            if ($research.Json.display_registration) {
                Write-Host "草案展示登记 : $($research.Json.display_registration.status)（仅供已认证 Web 阅读）"
            }
            if ($research.ExitCode -ne 0) {
                $notes.Add('部分离线研究草案未完成；详见 .tmp/daily-workbench-research-latest.json；继续其他更新。')
            }
        }
    } catch {
        $researchResult.exit_code = 2
        $researchResult.status = 'BLOCKED'
        $researchResult.error = $_.Exception.Message
        Write-ResearchReceipt $researchResult
        $notes.Add('离线研究批次运行失败；其他行情及公开快照更新继续，未自动登记研究。')
        Write-Host '研究草案 : BLOCKED（独立失败；未授予研究或交易资格）'
    }
}

# The pre-run packet records what is registered right now; SAFE_REFRESH also
# uses it so that re-running the same close stays idempotent. The formal
# workbook is only ever compared read-only (never written, never rebuilt).
$excelArgs = @()
$build = Invoke-PythonJson @('scripts/current/build_daily_public_packet.py', '--no-publish')
if (-not $build.Json) {
    Write-Host '运行结果 : BLOCKED - 每日公开数据包生成失败（无法解析输出）。'
    if ($build.Text) { Write-Host $build.Text }
    throw 'Daily packet output unavailable'
}
$packet = $build.Json
$buildExit = $build.ExitCode
$coreBlocked = ($buildExit -ne 0 -or -not $packet.source_bindings_verified)
$verified = $null
$marketwideScreen = $null
$valueResearchPriority = $null

if ($Mode -eq 'SAFE_REFRESH') {
    $marketwideDirectory = 'runtime/daily-marketwide/' + [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
    Write-Host '[SAFE_REFRESH] M2 全市场年度财务证据重筛（研究线索，不授予正式资格）...'
    $marketwide = Invoke-PythonJson @('scripts/run_m2_opportunity_discovery.py', '--no-wps', '--no-workbook', '--output-dir', $marketwideDirectory)
    $marketwideScreen = @{
        exit_code = $marketwide.ExitCode; output_dir = $marketwideDirectory
        manifest_path = $marketwideDirectory + '/manifest.json'
        current_publication_eligible = $false; status = 'BLOCKED'
    }
    if ($marketwide.ExitCode -eq 0 -and $marketwide.Json -and
        $marketwide.Json.action -eq 'no_order' -and
        $marketwide.Json.input_mode -eq 'LIVE_COLLECTION' -and
        $marketwide.Json.rule_version -eq 'm2-evidence-screen-v3') {
        $marketwideScreen.status = 'RESEARCH_ONLY'
        $marketwideScreen.rule_version = $marketwide.Json.rule_version
        $marketwideScreen.financial_input = $marketwide.Json.financial_input
        $marketwideScreen.data_health = $marketwide.Json.data_health
        $marketwideScreen.coverage_counts = $marketwide.Json.coverage_counts
        $marketwideScreen.receipt_path = $marketwide.Json.receipt_path
        try {
            $marketwideScreen.manifest_sha256 = (Get-FileHash -LiteralPath (Join-Path $root $marketwideScreen.manifest_path) -Algorithm SHA256).Hash.ToLowerInvariant()
        } catch {
            $marketwideScreen.status = 'BLOCKED'
            $notes.Add('M2 重筛清单无法绑定哈希；不展示为本次可信筛选，其他行情更新继续。')
        }
        Write-Host "  M2 输出 : $marketwideDirectory（保留数据时点和缺口，不自动登记为当前发布）"
    } else {
        $notes.Add('M2 全市场重筛未完成；不得将历史研究线索称为本次已刷新。')
    }
    if ($BuildValueResearchPriority -and $marketwideScreen.status -eq 'RESEARCH_ONLY') {
        try {
            $scanManifest = Get-Content -LiteralPath (Join-Path $root $marketwideScreen.manifest_path) -Raw -Encoding utf8 | ConvertFrom-Json
            $queuePath = $marketwideDirectory + '/research-priority-v2.json'
            $executionArgs = if ($ExecuteValueEnrichment) { @('--execute-enrichment', '--allow-public-evidence-downloads', '--execution-budget', '2') } else { @() }
            $queue = Invoke-PythonJson (@('scripts/current/build_value_research_queue.py',
                '--priority-version', 'v2', '--report', $scanManifest.files.lead_report.path,
                '--report-sha256', $scanManifest.files.lead_report.sha256,
                '--receipt', $scanManifest.files.receipt.path, '--receipt-sha256', $scanManifest.files.receipt.sha256,
                '--financial-export', $scanManifest.files.financial.path, '--financial-export-sha256', $scanManifest.files.financial.sha256,
                '--budget', '10', '--enrichment-budget', '10', '--output', $queuePath) + $executionArgs)
            if ($queue.ExitCode -ne 0 -or $queue.Json.action -ne 'no_order') { throw 'Research priority build failed' }
            $valueResearchPriority = @{ status = 'RESEARCH_QUEUE_ONLY'; path = $queuePath
                sha256 = (Get-FileHash -LiteralPath (Join-Path $root $queuePath) -Algorithm SHA256).Hash.ToLowerInvariant()
                selected_deep_research_count = $queue.Json.selected_deep_research_count
                selected_enrichment_count = $queue.Json.selected_enrichment_count }
            if ($queue.Json.enrichment_execution) {
                $valueResearchPriority.execution = $queue.Json.enrichment_execution
                if ($queue.Json.enrichment_execution.status -ne 'COMPLETED') {
                    $notes.Add('财务补证已执行但仍有来源或口径缺口；未授予财务事实、估值或交易准入。')
                }
            }
        } catch {
            $valueResearchPriority = @{ status = 'BLOCKED' }
            $notes.Add('研究排序未完成；不影响独立行情核验，不将线索升级为正式研究。')
        }
    }
    $reuse = Invoke-PythonJson @('scripts/current/refresh_current_price_conditions.py', '--check-reuse', '--symbols', $Symbols)
    if ($reuse.ExitCode -eq 0 -and $reuse.Json.prices_ready -and $reuse.Json.continuity_ready) {
        Write-Host "  价格结构 : 复用已核验最近完成交易日 $($reuse.Json.market_trade_dates -join ',') 的完整已选候选；未重新采集。"
        $priceRefresh = [pscustomobject]@{ ExitCode = 0; Json = [pscustomobject]@{ status = 'UNCHANGED'; items = @(); failures = @() } }
    } else {
    Write-Host '[SAFE_REFRESH] 按当日行业相对强度与成交额筛选五只真实观察候选，再核验价格结构...'
    $priceRefresh = Invoke-PythonJson @('scripts/current/refresh_current_price_conditions.py')
    }
    if ($priceRefresh.Json) {
        Write-Host "  价格结构状态 : $($priceRefresh.Json.status)"
        foreach ($item in @($priceRefresh.Json.items)) { Write-Host "  已计算 : $($item.symbol) $($item.company_name)" }
        foreach ($failure in @($priceRefresh.Json.failures)) { Write-Host "  未升级 : $($failure.symbol) $($failure.reason)" }
    }
    if ($priceRefresh.ExitCode -ne 0 -or -not $priceRefresh.Json -or @($priceRefresh.Json.failures).Count -gt 0) {
        $notes.Add('当前价格条件采集存在缺项；未通过验证的证券不会升级为当前触发。')
    }
    Write-Host '[SAFE_REFRESH] 采集已授权的公开行情来源（腾讯/新浪，只读页面）...'
    if ($reuse.ExitCode -eq 0 -and $reuse.Json.quotes_ready) {
        Write-Host '  行情 : 复用已核验最近完成交易日的登记；未重新采集。'
        $collect = [pscustomobject]@{ ExitCode = 0; Json = [pscustomobject]@{ observations = @(); status = 'UNCHANGED' } }
    } else {
        $collect = Invoke-PythonJson @('scripts/collect_quote_sessions.py', '--symbols', $Symbols)
    }
    if ($collect.ExitCode -ne 0 -or -not $collect.Json) {
        $notes.Add('行情采集未完成（网络或来源不可用）；本次继续使用已登记行情。')
        Write-Host '  行情采集未完成，采集器最后输出：'
        ($collect.Text -split "`n" | Select-Object -Last 12) | ForEach-Object { Write-Host "    $_" }
    }
    elseif ($collect.Json.status -ne 'UNCHANGED') {
        $bundleDir = [string]$collect.Json.path
        $bundlePath = Join-Path $bundleDir 'bundle.json'
        $bundleSha = [string]$collect.Json.bundle_sha256
        Write-Host "  已归档行情包 : $bundleDir"
        Write-Host "  采集状态     : $($collect.Json.status)"
        $pointerFile = Join-Path $root 'config/current-quote-bridge.json'
        $pointer = $null
        if (Test-Path -LiteralPath $pointerFile) {
            $pointer = Get-Content -LiteralPath $pointerFile -Raw -Encoding utf8 | ConvertFrom-Json
        }
        foreach ($observation in @($collect.Json.observations)) {
            $symbol = [string]$observation.symbol
            if ($observation.result.status -ne 'matched_close' -or -not $observation.result.passed) {
                $notes.Add("$symbol 的最新收盘未通过验证；不升级该证券。")
                Write-Host "  ${symbol}: 未形成可登记的双源收盘（$($observation.result.status)：$($observation.result.reason)）"
                continue
            }
            if (-not $observation.b1_acquisition.eligible) {
                Write-Host "  ${symbol}: 双源收盘仅供展示；B1 时点不合格（$($observation.b1_acquisition.status)），不形成正式价格资格。"
            }
            $session = [string]$observation.result.expected_session
            $registeredDate = $null
            if ($packet.bridge_quote_dates -and
                ($packet.bridge_quote_dates.PSObject.Properties.Name -contains $symbol)) {
                $registeredDate = [string]$packet.bridge_quote_dates.$symbol
            }
            if ($registeredDate -eq $session -and $reuse.Json.quotes_ready) {
                Write-Host "  ${symbol}: $session 的双源收盘已登记，跳过重复登记（幂等）。"
                continue
            }
            $entry = $null
            if ($pointer -and $pointer.quotes -and
                ($pointer.quotes.PSObject.Properties.Name -contains $symbol)) {
                $entry = $pointer.quotes.$symbol
            }
            if (-not $entry) {
                Write-Host "  ${symbol}: 无已登记研究包，仅归档（不生成价格比较资格）。"
                continue
            }
            if ([string]$entry.quote_bundle_sha256 -eq $bundleSha) {
                Write-Host "  ${symbol}: 已登记同一份行情，跳过重复登记（幂等）。"
                continue
            }
            $pinArgs = @('scripts/current/pin_current_quote_bridge.py',
                '--symbol', $symbol, '--quote-bundle', $bundlePath)
            if ($entry.registration_scope -eq 'QUOTE_OBSERVATION_ONLY') { $pinArgs += '--observation-only' }
            else { $pinArgs += @('--research-package', [string]$entry.research_package) }
            $pin = Invoke-PythonJson $pinArgs
            if ($pin.ExitCode -ne 0) {
                $notes.Add("$symbol 的新收盘登记失败；保留原登记，未写入部分结果。")
                Write-Host "  ${symbol}: 登记失败，保留原登记。"
                ($pin.Text -split "`n" | Select-Object -Last 6) | ForEach-Object { Write-Host "    $_" }
            }
            else {
                Write-Host "  ${symbol}: 已登记 $session 双源收盘（登记不构成估值或交易批准）。"
            }
        }
        foreach ($expectedSymbol in ($Symbols -split ',')) {
            if ($expectedSymbol -notin @($collect.Json.observations | ForEach-Object { $_.symbol })) {
                $notes.Add("$expectedSymbol 未返回逐证券采集结果；保留原登记。")
            }
        }
        # Rebuild so the printed summary reflects the new registration.
    }
}

if ($Mode -eq 'SAFE_REFRESH') {
    $verified = Invoke-PythonJson @('scripts/current/refresh_current_price_conditions.py', '--check-reuse', '--symbols', $Symbols)
    $reviewDates = @($verified.Json.market_trade_dates) + @($verified.Json.quote_securities | ForEach-Object { $_.latest_completed_session })
    $reviewCutoff = $reviewDates | Where-Object { $_ -match '^\d{4}-\d{2}-\d{2}$' } | Sort-Object -Unique | Select-Object -Last 1
    if ($reviewCutoff) {
        $reviewArgs = @('scripts/current/review_registered_research_validity.py', '--review-cutoff', $reviewCutoff)
        $quoteRegistry = $null
        try { $quoteRegistry = Get-Content -LiteralPath (Join-Path $root 'config/current-quote-bridge.json') -Raw -Encoding utf8 | ConvertFrom-Json }
        catch { Write-Host '  公告增量登记不可读；保留原研究门禁。'; $notes.Add('公告增量采集或复核未完成；保留研究门禁，其他已核验证券继续。') }
        foreach ($registeredQuote in $quoteRegistry.quotes.PSObject.Properties) {
            if ($registeredQuote.Value.registration_scope -eq 'QUOTE_OBSERVATION_ONLY') { continue }
            $scanSymbol = $registeredQuote.Name
            $scanStamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
            $scanDirectory = "runtime/incremental-validity/$scanSymbol/$reviewCutoff-$scanStamp"
            $newScanDirectory = $scanDirectory
            $existingBinding = $registeredQuote.Value.incremental_validity_binding
            try { if ($existingBinding -and $existingBinding.path) {
                $boundPath = [System.IO.Path]::GetFullPath((Join-Path $root ([string]$existingBinding.path)))
                if ($boundPath.StartsWith((Join-Path $root 'runtime') + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $boundPath)) {
                    $boundScan = Get-Content -LiteralPath $boundPath -Raw -Encoding utf8 | ConvertFrom-Json
                    if ($boundScan.review_cutoff -eq $reviewCutoff -and
                        (Get-FileHash -LiteralPath $boundPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $existingBinding.sha256) {
                        $scanDirectory = Split-Path ([string]$existingBinding.path) -Parent
                    }
                }
            } } catch { Write-Host "  ${scanSymbol}: 原增量绑定无法复用，尝试独立新采集。" }
            $scan = Invoke-PythonJson @('scripts/current/collect_registered_validity_scan.py', '--symbol', $scanSymbol, '--review-cutoff', $reviewCutoff, '--output-dir', $scanDirectory, '--register')
            if ($scan.ExitCode -ne 0 -and $scanDirectory -ne $newScanDirectory) {
                Write-Host "  ${scanSymbol}: 旧扫描原件无法核验，保留旧证据并独立重采一次。"
                $scan = Invoke-PythonJson @('scripts/current/collect_registered_validity_scan.py', '--symbol', $scanSymbol, '--review-cutoff', $reviewCutoff, '--output-dir', $newScanDirectory, '--register')
            }
            if ($scan.ExitCode -eq 0 -and $scan.Json.binding_ref) {
                $reviewArgs += @('--incremental-binding', [string]$scan.Json.binding_ref.path, [string]$scan.Json.binding_ref.sha256)
                Write-Host "  ${scanSymbol}: 正式公告增量证据已绑定；未授予材料性或估值批准。"
            } else {
                $notes.Add('公告增量采集或复核未完成；保留研究门禁，其他已核验证券继续。')
                Write-Host "  ${scanSymbol}: 公告增量采集未完成，保留原研究限制；其他证券继续。"
            }
        }
        $reviewOutput = 'runtime/research-validity-reviews/registered-' + [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '.json'
        $validityReview = Invoke-PythonJson ($reviewArgs + @('--output', $reviewOutput))
        if ($validityReview.ExitCode -eq 0 -and $validityReview.Json) {
            Write-Host '  增量有效性 : 已写入逐证券审计；未改研究截止日或授予任何批准。'
            foreach ($item in @($validityReview.Json.reviews)) {
                Write-Host "  $($item.symbol) : $($item.model_validity_status) / $($item.status) $($item.reason)"
                if ($item.reason -and $item.status -ne 'NO_REGISTERED_RESEARCH') {
                    $notes.Add('公告增量采集或复核未完成；保留研究门禁，其他已核验证券继续。')
                }
            }
        } else {
            $notes.Add('公告增量采集或复核未完成；保留研究门禁，其他已核验证券继续。')
            Write-Host '  增量有效性 : 本次复核未完成，保留原研究门禁；其他已核验行情继续。'
        }
    }
    # Recompute after incremental registration so the published packet consumes
    # the same revalidated inputs as the current price bridge.
    $verified = Invoke-PythonJson @('scripts/current/refresh_current_price_conditions.py', '--check-reuse', '--symbols', $Symbols)
    $postBuild = Invoke-PythonJson @('scripts/current/build_daily_public_packet.py', '--no-publish')
    $coreBlocked = ($postBuild.ExitCode -ne 0 -or -not $postBuild.Json -or -not $postBuild.Json.source_bindings_verified)
    if ($postBuild.Json) { $packet = $postBuild.Json; $buildExit = $postBuild.ExitCode }
    else { $buildExit = 2; $notes.Add('刷新后快照生成失败，Web 保留上一验证版本。') }
    if ($verified.ExitCode -ne 0 -or -not $verified.Json.publication_ready) {
        $coreBlocked = $true
        $notes.Add('刷新后完整输入未通过最近完成交易日及来源校验；不发布新快照。')
    }
    elseif (-not $verified.Json.prices_ready -or -not $verified.Json.quotes_ready) {
        $notes.Add('部分证券数据未能更新；已核验证券可用，缺项不代表今日已刷新。')
    }
}
if (-not $coreBlocked) {
    $rebuild = Invoke-PythonJson (@('scripts/current/build_daily_public_packet.py') + $excelArgs)
    if ($rebuild.Json) { $packet = $rebuild.Json; $buildExit = $rebuild.ExitCode }
    else { $buildExit = 2; $notes.Add('刷新后快照生成失败，Web 保留上一验证版本。') }
}
else { if ($buildExit -eq 0) { $buildExit = 2 }; $notes.Add('采集或登记不完整：未发布新快照，Web 保留上一验证版本，不能称为本次新数据。') }

$status = if ($buildExit -eq 0) { 'SUCCESS' } else { 'BLOCKED' }
if ($status -eq 'SUCCESS' -and $notes.Count -gt 0) { $status = 'PARTIAL' }
$updateExit = if ($status -eq 'SUCCESS') { 0 } elseif ($status -eq 'PARTIAL') { 3 } else { 2 }
$receipt = @{
    schema_version = 'daily-workbench-run-v1'; action = 'no_order'; mode = $Mode
    started_at = $startedAt; finished_at = [DateTimeOffset]::UtcNow.ToString('o')
    status = $status; exit_code = $updateExit; published = [bool]($packet.snapshot -and $buildExit -eq 0)
    publication_id = $packet.snapshot.publication_id; notes = @($notes.ToArray())
}
if ($marketwideScreen) { $receipt.marketwide_screen = $marketwideScreen }
if ($valueResearchPriority) { $receipt.value_research_priority = $valueResearchPriority }
if ($verified.Json) {
    $receipt.price_securities = @($verified.Json.price_securities)
    $receipt.quote_securities = @($verified.Json.quote_securities)
    $receipt.core_integrity_ok = [bool]$verified.Json.core_integrity_ok
}
$snapshotPointer = Join-Path $root 'config/current-daily-public-snapshot.json'
if (Test-Path -LiteralPath $snapshotPointer) {
    $retained = Get-Content -LiteralPath $snapshotPointer -Raw -Encoding utf8 | ConvertFrom-Json
    $receipt.retained_publication_id = $retained.publication_id
}
$receiptPath = Join-Path $env:TEMP 'daily-workbench-latest-run.json'
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$receiptPath.pending" -Encoding utf8
Move-Item -LiteralPath "$receiptPath.pending" -Destination $receiptPath -Force

Write-Host '---------------- 本次运行 ----------------'
Write-Host "运行结果 : $status$(if ($buildExit -eq 4) { '（同一版本出现不同内容，已失败关闭并写入冲突回执）' } elseif ($buildExit -eq 3) { '（既有记录不可读，已失败关闭，未覆盖）' } elseif ($buildExit -eq 2) { '（发布链不可用，未发布新快照）' })"
if ($packet.chain_error) { Write-Host "发布链问题 : $($packet.chain_error)" }
Write-Host "数据版本 : $(if ($packet.publication_id) { $packet.publication_id } else { '不可用（fail-closed，不沿用旧版本）' })"
Write-Host "研究版本 : $(if ($packet.research_version) { $packet.research_version } else { '未提供' })"
if ($packet.content_sha256) { Write-Host "内容摘要 : $($packet.content_sha256)" }
$snapshotLine = if ($packet.snapshot) { "$($packet.snapshot.status) - $($packet.snapshot.publication_id)（Web 只读这一份已校验快照）" }
    elseif ($buildExit -ne 0 -and $packet.publication_id) { '未更新（Web 仍读取上一份已验证快照）' }
    else { '本次未发布（无已校验快照）' }
Write-Host "公开快照 : $snapshotLine"
if ($packet.dates) {
    Write-Host ("日期边界 : 自然日 {0} | 最近完成交易日 {1} | 已登记行情 {2} | 研究截止 {3} | 决策发布 {4} | Excel 快照 {5}" -f `
        $packet.dates.current_natural_date, $packet.dates.latest_completed_trade_session, $packet.dates.quote_trade_date, `
        $packet.dates.research_as_of, $packet.dates.decision_published_on, $packet.dates.excel_published_as_of)
}
foreach ($name in @('quote', 'research')) {
    $freshness = $packet.data_freshness.$name
    if ($freshness) { Write-Host ("{0}新鲜度 : {1}{2}" -f $(if ($name -eq 'quote') { '行情' } else { '研究' }), $freshness.status, $(if ($freshness.reason) { " - $($freshness.reason)" } else { '' })) }
}
if ($packet.research_counts) {
    Write-Host ("准入计数 : 正式准入 {0} | 待人工复核 {1} | 需重新研究 {2} | 观察线索 {3}" -f `
            $packet.formal_admission_count, $packet.pending_review_count,
        $packet.research_counts.needs_re_research_count, $packet.research_counts.lead_count)
}
Write-Host "价格结构 : $($packet.price_condition_status)"
foreach ($row in @($packet.price_condition_rows)) {
    Write-Host "  $($row.symbol) $($row.company_name): 收盘 $($row.current_reference_price) | 突破观察 $($row.entry_trigger_price) | 失效 $($row.invalidation_price) | $($row.signal_state) | 正式资格 $($row.action_eligibility)"
}
if ($packet.next_steps) { Write-Host '下一步   :'; foreach ($step in @($packet.next_steps)) { if ($step) { Write-Host "  - $step" } } }
if ($packet.blockers) { Write-Host "阻止事项 : $(@($packet.blockers) -join '; ')" }
Write-Host "来源绑定 : $(if ($packet.source_bindings_verified) { '全部哈希校验通过' } else { '存在未通过校验的来源（见数据包）' })"
if ($packet.excel_sync) { Write-Host "Excel对照 : $($packet.excel_sync.status)（只读校验，不覆盖正式工作簿）" }
if ($packet.path) { Write-Host "产物     : $($packet.path)" }
if ($packet.sha256) { Write-Host "产物哈希 : $($packet.sha256)" }
if ($Mode -eq 'SAFE_REFRESH') { Write-Host '能力边界 : 已完成行情和价格结构计算不代表触发、研究批准或正式操作准入；事件、风险、G3 等门禁独立。' }
Write-Host '说明     : 仅按验证结果更新本地公开快照引用；正式 Excel 与私人数据均未被触碰（action=no_order）。'
foreach ($note in $notes) { Write-Host "提醒     : $note" }

$dailyRunLock.Dispose()
$dailyRunLock = $null
$webStatus = '未启动'
if ($NoServer) {
    Write-Host '已按 -NoServer 跳过 Web 启动。'
    Write-Host "Web 服务 : $webStatus"
    Write-Host "整体结果 : 退出码 $updateExit（仅代表数据更新结果）"
    exit $updateExit
}

if (-not (Test-Path -LiteralPath (Join-Path $root 'web/dist/index.html'))) {
    Write-Host 'Web 服务 : 启动失败 - 缺少 Web 构建。先执行：npm ci --prefix web; npm run build --prefix web'
    $exitCode = if ($updateExit -ne 0) { $updateExit } else { 4 }
    Write-Host "整体结果 : 退出码 $exitCode（数据更新优先）"
    exit $exitCode
}
$listening = if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) { Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue } else { $null }
# The starter owns listener identity and free loopback port selection.
Write-Host '正在启动本地工作台（Ctrl+C 停止）...'
& (Join-Path $PSScriptRoot 'start_web_workbench.ps1') -Port $Port -Open:$Open -Reauthorize:$Reauthorize
$webExit = $LASTEXITCODE
$webStatus = if ($webExit -eq 0) { "已退出（退出码 0）" } else { "已退出（退出码 $webExit）" }
Write-Host "Web 服务 : $webStatus"
$overallExit = if ($updateExit -ne 0) { $updateExit } elseif ($webExit -ne 0) { 4 } else { 0 }
Write-Host "整体结果 : 退出码 $overallExit（数据更新 $status；Web 退出码 $webExit）"
exit $overallExit
} finally {
    if ($null -ne $dailyRunLock) { $dailyRunLock.Dispose() }
}
