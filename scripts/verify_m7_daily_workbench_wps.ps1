param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $true)][string]$PackagePath,
    [Parameter(Mandatory = $true)][string]$CanonicalPath,
    [Parameter(Mandatory = $true)][string]$ExpectedCanonicalSha256,
    [switch]$PostCheckpointA,
    [switch]$ActualEventReadModel
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$canonicalPath = (Resolve-Path -LiteralPath $CanonicalPath).Path
$packagePath = (Resolve-Path -LiteralPath $PackagePath).Path
$package = Get-Content -Raw -LiteralPath $packagePath | ConvertFrom-Json
$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$canonicalBefore = (Get-FileHash -LiteralPath $canonicalPath).Hash.ToLowerInvariant()
$expected = $ExpectedSha256.ToLowerInvariant()
$expectedCanonical = $ExpectedCanonicalSha256.ToLowerInvariant()

if ($before -ne $expected) {
    throw "M7 daily candidate changed before WPS verification: $before"
}
if ($canonicalBefore -ne $expectedCanonical) {
    throw "Canonical workbook changed before WPS verification: $canonicalBefore"
}
if ($package.workbook_sha256 -ne $expected) {
    throw 'M7 daily manifest does not bind the candidate hash.'
}
if ($package.action -ne 'no_order') {
    throw 'M7 daily candidate is not no_order.'
}

$visibleSheets = @(
    '00_今日总览'
    '01_全市场与数据健康'
    '02_候选与重点关注'
    '03_决策复核'
    '04_当前持仓与仓位'
    '05_股息现金流'
    '06_事件与预警'
    '07_公司研究'
    '08_买卖逻辑与历史'
    '09_审计与证据'
)
$hiddenSheets = @(
    '_模块状态矩阵'
    '_审计明细索引'
)

$app = $null
$book = $null
$initialCount = -1
try {
    $app = New-Object -ComObject ket.Application
    $applicationPath = [string]$app.Path
    if ($applicationPath -notmatch 'WPS') {
        throw "Unexpected document engine: $applicationPath"
    }
    $initialCount = $app.Workbooks.Count
    foreach ($existing in $app.Workbooks) {
        if ([string]$existing.FullName -eq $path) {
            throw 'M7 daily candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M7 daily candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne 12) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }

    $allText = @()
    for ($i = 0; $i -lt $visibleSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $visibleSheets[$i]) {
            throw "M7 daily visible sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M7 daily presentation sheet hidden: $($sheet.Name)"
        }
        $sheet.Calculate()
        foreach ($value in $sheet.UsedRange.Value2) {
            $allText += [string]$value
            if ($value -is [string] -and $value -match '^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$') {
                throw "Formula error on $($sheet.Name)"
            }
        }
    }
    for ($i = 0; $i -lt $hiddenSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($visibleSheets.Count + $i + 1)
        if ($sheet.Name -ne $hiddenSheets[$i]) {
            throw "M7 daily hidden sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne 0) {
            throw "M7 daily technical sheet is not hidden: $($sheet.Name)"
        }
    }

    $overview = $book.Worksheets.Item('00_今日总览')
    # UsedRange.Text is unreliable through WPS COM. The values loop above has
    # already collected every visible cell, so scan that materialized text.
    $visibleText = $allText -join [Environment]::NewLine
    if ([string]::IsNullOrWhiteSpace($visibleText)) {
        throw 'M7 daily visible-cell text could not be materialized.'
    }
    $conclusion = [string]$overview.Range('B15').Text
    if ($conclusion -notmatch [regex]::Escape('当前无任何可用订单')) {
        throw "M7 daily overview conclusion is not fail-closed: $conclusion"
    }
    $expectedM2HumanStatus = if ($PostCheckpointA) { 'HUMAN_PASS' } else { 'PENDING_HUMAN_REVIEW' }
    if ($package.stage_statuses.m2[3] -ne $expectedM2HumanStatus) {
        throw "M7 daily manifest lost the M2 human-review status: $($package.stage_statuses.m2[3])"
    }
    if ($package.summary.m4_private_input_status -ne 'PENDING_USER_PRIVATE_INPUT') {
        throw 'M7 daily manifest lost the M4 private-input status.'
    }
    if ($package.summary.m6_operational_status -ne 'NOT_STARTED') {
        throw 'M7 daily manifest lost the M6 operational status.'
    }
    # WPS COM can return an empty string for UsedRange.Text, so read the
    # contracted cells directly instead of weakening the boundary assertion.
    $decisionText = [string]$book.Worksheets.Item('03_决策复核').Range('B11').Text
    $researchText = [string]$book.Worksheets.Item('07_公司研究').Range('B11').Text
    $historicalBoundaryText = $decisionText + [Environment]::NewLine + $researchText
    if ($historicalBoundaryText -notmatch [regex]::Escape('规则时点 PIT=NOT CLAIMED')) {
        throw 'M7 daily candidate lost the non-contemporaneous-rule PIT boundary.'
    }
    if ($historicalBoundaryText -notmatch [regex]::Escape('future_rule_version_used=True')) {
        throw 'M7 daily candidate lost the future-rule-version marker.'
    }
    foreach ($misleading in @('真实 PIT 历史重放', '当时规则')) {
        if ($historicalBoundaryText -match [regex]::Escape($misleading)) {
            throw "M7 daily candidate contains misleading historical PIT wording: $misleading"
        }
    }
    if ($PostCheckpointA) {
        if ($visibleText -notmatch [regex]::Escape('M3 重建证据连续性')) {
            throw 'Post-Checkpoint A M7 candidate is missing the reconstructed M3 evidence layer.'
        }
        $expectedEventLabel = if ($ActualEventReadModel) { '600519 实际事件闭环' } else { '600519 新增真实披露待复核队列' }
        if ($visibleText -notmatch [regex]::Escape($expectedEventLabel)) {
            throw 'Post-Checkpoint A M7 candidate is missing the required 600519 event layer.'
        }
        if ($visibleText -notmatch [regex]::Escape('strict PIT=NOT_PROVEN')) {
            throw 'Post-Checkpoint A M7 candidate lost the strict-PIT NOT_PROVEN boundary.'
        }
        $expectedPending = if ($ActualEventReadModel) { 0 } else { 9 }
        if ($package.summary.m5_600519_pending_reviews -ne $expectedPending) {
            throw 'Post-Checkpoint A M7 candidate lost the 600519 pending-review count.'
        }
        if ($ActualEventReadModel) {
            if ($visibleText -notmatch [regex]::Escape('STILL_NOT_READY') -or
                $visibleText -notmatch [regex]::Escape('missing_dependency_node:valuation_inputs')) {
                throw 'Actual M5 workbench lost the bounded-recalculation blocker.'
            }
        }
        if ($package.summary.m3_reconstructed_continuity_status -ne 'RECONSTRUCTED_EVIDENCE_ONLY') {
            throw 'Post-Checkpoint A M7 candidate lost the reconstructed-evidence status.'
        }
    }
    foreach ($forbidden in @('建议买入', '建议加仓', '目标仓位', '下单')) {
        if ($visibleText -match $forbidden) {
            throw "M7 daily visible sheets contain forbidden recommendation text: $forbidden"
        }
    }
    $checks = @{
        title = [string]$overview.Range('A1').Text
        boundary = [string]$overview.Range('A2').Text
        conclusion = $conclusion
        action = [string]$package.action
        forbidden_recommendation_scan = @{
            checked = $true
            scope = 'all visible sheets'
        }
        historical_replay_boundary = @{
            facts_quote_pit = $true
            contemporaneous_rule_pit = $false
            future_rule_version_used = $true
            checked = $true
        }
    }

    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M7 daily candidate.'
    }
    if ((Get-FileHash -LiteralPath $canonicalPath).Hash.ToLowerInvariant() -ne $canonicalBefore) {
        throw 'Read-only check changed the canonical workbook.'
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReceiptPath) | Out-Null

    $receipt = @{
        status = 'passed'
        mode = 'm7_daily_workbench_read_only_candidate'
        workbook = $path
        sha256 = $before
        canonical = $canonicalPath
        canonical_sha256 = $canonicalBefore
        read_only = $true
        visible_sheets = $visibleSheets.Count
        hidden_sheets = $hiddenSheets.Count
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $checks
        action = 'no_order'
        post_checkpoint_a = [bool]$PostCheckpointA
        check_scope = 'WPS read-only open/read/calculate, formula-error scan, visible/hidden sheet contract, fail-closed status text, all-visible-sheet recommendation scan, M3 replay PIT wording boundary, optional post-Checkpoint A evidence layers and no_order boundary'
    }
    $receipt | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    $receipt | ConvertTo-Json -Depth 6 -Compress
}
finally {
    if ($null -ne $book) {
        $book.Close($false)
    }
    if ($null -ne $app -and $initialCount -eq 0 -and $app.Workbooks.Count -eq 0) {
        $app.Quit()
    }
}
