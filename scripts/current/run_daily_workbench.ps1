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
  close registration, then a packet rebuild. It refreshes quotes only:
  re-running research, the human event review and the G3 valuation gate stay
  explicit human/engineering steps and are listed as pending actions, never
  signed here.

The entry stays action=no_order: it reports what the existing gates decided,
and it cannot create a buy/sell signal, a position size or an order.

Exit codes (update result first, Web result second):
  0  update SUCCESS, Web ran or was skipped
  2  update BLOCKED (chain unavailable, identity conflict, refresh failed)
  3  update PARTIAL (succeeded with recorded notes)
  4  Web failed to start while the update itself succeeded
#>
param(
    [ValidateSet('READ_ONLY', 'SAFE_REFRESH')][string]$Mode = 'READ_ONLY',
    [ValidateRange(1024, 65535)][int]$Port = 8001,
    [switch]$Open,
    [switch]$NoServer,
    [string]$Symbols = '600887,000333,601088,600519'
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    & 'C:\Users\we\AppData\Local\Programs\PowerShell\7\pwsh.exe' -NoProfile -File $PSCommandPath `
        -Mode $Mode -Port $Port -Open:$Open -NoServer:$NoServer -Symbols $Symbols
    exit $LASTEXITCODE
}
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $root
$env:PYTHONPATH = Join-Path $root 'src'
$env:PYTHONIOENCODING = 'utf-8'
$env:TEMP = Join-Path $root '.tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

$notes = [System.Collections.Generic.List[string]]::new()

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

Write-Host '================ TL9 每日工作台 ================'
Write-Host "运行模式 : $Mode"

$python = Resolve-Python
if (-not $python) {
    Write-Host '运行结果 : BLOCKED - 未找到 Python 解释器（python 或 D:\APP\Python313\python.exe）。'
    exit 2
}
$importCheck = & $python -X utf8 -B -c 'import value_investment_agent' 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host '运行结果 : BLOCKED - Python 环境无法导入 value_investment_agent。'; Write-Host $importCheck.Trim(); exit 2
}
Write-Host "Python   : $python"

# The pre-run packet records what is registered right now; SAFE_REFRESH also
# uses it so that re-running the same close stays idempotent. The formal
# workbook is only ever compared read-only (never written, never rebuilt).
$excelArgs = @()
$workbookCheck = Invoke-PythonJson @('scripts/open_current_trial_workbook.py')
if ($workbookCheck.ExitCode -eq 0 -and $workbookCheck.Json -and $workbookCheck.Json.workbook) {
    $excelArgs = @('--excel', [string]$workbookCheck.Json.workbook)
}
else {
    $notes.Add('正式 Excel 路径未解析或未通过只读校验；本次不做 Excel 版本对照（NOT_VERIFIED）。')
}
$build = Invoke-PythonJson (@('scripts/current/build_daily_public_packet.py') + $excelArgs)
if (-not $build.Json) {
    Write-Host '运行结果 : BLOCKED - 每日公开数据包生成失败（无法解析输出）。'
    if ($build.Text) { Write-Host $build.Text }
    exit 2
}
$packet = $build.Json
$buildExit = $build.ExitCode

if ($Mode -eq 'SAFE_REFRESH') {
    Write-Host '[SAFE_REFRESH] 采集已授权的公开行情来源（腾讯/新浪，只读页面）...'
    $collect = Invoke-PythonJson @('scripts/collect_quote_sessions.py', '--symbols', $Symbols)
    if ($collect.ExitCode -ne 0 -or -not $collect.Json) {
        $notes.Add('行情采集未完成（网络或来源不可用）；本次继续使用已登记行情。')
        Write-Host '  行情采集未完成，采集器最后输出：'
        ($collect.Text -split "`n" | Select-Object -Last 12) | ForEach-Object { Write-Host "    $_" }
    }
    else {
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
                Write-Host "  ${symbol}: 未形成可登记的双源收盘（$($observation.result.status)：$($observation.result.reason)）"
                continue
            }
            $session = [string]$observation.result.expected_session
            $registeredDate = $null
            if ($packet.bridge_quote_dates -and
                ($packet.bridge_quote_dates.PSObject.Properties.Name -contains $symbol)) {
                $registeredDate = [string]$packet.bridge_quote_dates.$symbol
            }
            if ($registeredDate -eq $session) {
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
            $pin = Invoke-PythonJson @('scripts/current/pin_current_quote_bridge.py',
                '--symbol', $symbol, '--quote-bundle', $bundlePath,
                '--research-package', [string]$entry.research_package)
            if ($pin.ExitCode -ne 0) {
                $notes.Add("$symbol 的新收盘登记失败；保留原登记，未写入部分结果。")
                Write-Host "  ${symbol}: 登记失败，保留原登记。"
                ($pin.Text -split "`n" | Select-Object -Last 6) | ForEach-Object { Write-Host "    $_" }
            }
            else {
                Write-Host "  ${symbol}: 已登记 $session 双源收盘（登记不构成估值或交易批准）。"
            }
        }
        # Rebuild so the printed summary reflects the new registration.
        $rebuild = Invoke-PythonJson (@('scripts/current/build_daily_public_packet.py') + $excelArgs)
        if ($rebuild.Json) { $packet = $rebuild.Json; $buildExit = $rebuild.ExitCode }
    }
}

$status = if ($buildExit -eq 0) { 'SUCCESS' } else { 'BLOCKED' }
if ($status -eq 'SUCCESS' -and $notes.Count -gt 0) { $status = 'PARTIAL' }
$updateExit = if ($status -eq 'SUCCESS') { 0 } elseif ($status -eq 'PARTIAL') { 3 } else { 2 }

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
if ($packet.next_steps) { Write-Host '下一步   :'; foreach ($step in @($packet.next_steps)) { if ($step) { Write-Host "  - $step" } } }
if ($packet.blockers) { Write-Host "阻止事项 : $(@($packet.blockers) -join '; ')" }
Write-Host "来源绑定 : $(if ($packet.source_bindings_verified) { '全部哈希校验通过' } else { '存在未通过校验的来源（见数据包）' })"
if ($packet.excel_sync) { Write-Host "Excel对照 : $($packet.excel_sync.status)（只读校验，不覆盖正式工作簿）" }
if ($packet.path) { Write-Host "产物     : $($packet.path)" }
if ($packet.sha256) { Write-Host "产物哈希 : $($packet.sha256)" }
if ($Mode -eq 'SAFE_REFRESH') { Write-Host '能力边界 : SAFE_REFRESH 只刷新行情并重建公开快照；重跑研究、事件复核与 G3 估值门仍是人工/工程步骤。' }
Write-Host '说明     : 本次运行不修改正式发布指针；正式 Excel 与私人数据均未被触碰（action=no_order）。'
foreach ($note in $notes) { Write-Host "提醒     : $note" }

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
if ($listening) {
    Write-Host "Web 服务 : 端口 $Port 已有工作台在监听，本次不重复启动；直接打开 http://127.0.0.1:$Port 。"
    Write-Host "整体结果 : 退出码 $updateExit（已运行的工作台会读取本次发布的最新快照）"; exit $updateExit
}
Write-Host '正在启动本地工作台（Ctrl+C 停止）...'
& (Join-Path $PSScriptRoot 'start_web_workbench.ps1') -Port $Port -Open:$Open
$webExit = $LASTEXITCODE
$webStatus = if ($webExit -eq 0) { "已退出（退出码 0）" } else { "已退出（退出码 $webExit）" }
Write-Host "Web 服务 : $webStatus"
$overallExit = if ($updateExit -ne 0) { $updateExit } elseif ($webExit -ne 0) { 4 } else { 0 }
Write-Host "整体结果 : 退出码 $overallExit（数据更新 $status；Web 退出码 $webExit）"
exit $overallExit
