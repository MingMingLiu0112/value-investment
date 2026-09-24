param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $true)][string]$PackagePath,
    [Parameter(Mandatory = $true)][string]$CanonicalPath,
    [Parameter(Mandatory = $true)][string]$ExpectedCanonicalSha256
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
    $overviewText = [string]$overview.UsedRange.Text
    $conclusion = [string]$overview.Range('B15').Text
    if ($conclusion -notmatch [regex]::Escape('当前无任何可用订单')) {
        throw "M7 daily overview conclusion is not fail-closed: $conclusion"
    }
    if ($package.stage_statuses.m2[3] -ne 'PENDING_HUMAN_REVIEW') {
        throw 'M7 daily manifest lost the M2 human-review status.'
    }
    if ($package.summary.m4_private_input_status -ne 'PENDING_USER_PRIVATE_INPUT') {
        throw 'M7 daily manifest lost the M4 private-input status.'
    }
    if ($package.summary.m6_operational_status -ne 'NOT_STARTED') {
        throw 'M7 daily manifest lost the M6 operational status.'
    }
    foreach ($forbidden in @('建议买入', '建议加仓', '目标仓位', '下单')) {
        if ($overviewText -match $forbidden) {
            throw "M7 daily overview contains forbidden recommendation text: $forbidden"
        }
    }
    $checks = @{
        title = [string]$overview.Range('A1').Text
        boundary = [string]$overview.Range('A2').Text
        conclusion = $conclusion
        action = [string]$package.action
    }

    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M7 daily candidate.'
    }
    if ((Get-FileHash -LiteralPath $canonicalPath).Hash.ToLowerInvariant() -ne $canonicalBefore) {
        throw 'Read-only check changed the canonical workbook.'
    }

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
        check_scope = 'WPS read-only open/read/calculate, formula-error scan, visible/hidden sheet contract, fail-closed status text and no_order boundary'
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
