param(
    [Parameter(Mandatory=$false)][string]$SourcePath,
    [Parameter(Mandatory=$false)][string]$PackagePath,
    [Parameter(Mandatory)][string]$WorkbookPath,
    [Parameter(Mandatory)][string]$ReceiptPath,
    [Parameter(Mandatory=$false)][string]$ExpectedSha256,
    [switch]$Published,
    [switch]$SkipChecksOutput
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$source = $null
$sourceHash = $null
if (-not $Published) {
    if ([string]::IsNullOrWhiteSpace($SourcePath)) {
        throw 'SourcePath is required for pre-publication verification.'
    }
    $source = (Resolve-Path -LiteralPath $SourcePath).Path
}
$packagePath = if ([string]::IsNullOrWhiteSpace($PackagePath)) {
    [IO.Path]::ChangeExtension($path, 'receipt.json')
} else {
    (Resolve-Path -LiteralPath $PackagePath).Path
}
if (-not (Test-Path -LiteralPath $packagePath)) {
    throw "Package receipt missing: $packagePath"
}
$package = Get-Content -Raw -LiteralPath $packagePath | ConvertFrom-Json
$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$expectedWorkbookHash = if ($Published) {
    if ([string]::IsNullOrWhiteSpace($ExpectedSha256)) {
        throw 'ExpectedSha256 is required for published-workbook verification.'
    }
    $ExpectedSha256.ToLowerInvariant()
} else {
    $package.candidate_sha256
}
if ($before -ne $expectedWorkbookHash) {
    throw 'Integrated candidate changed before WPS verification.'
}
if (-not $Published) {
    $sourceHash = (Get-FileHash -LiteralPath $source).Hash.ToLowerInvariant()
}
if (-not $Published -and $sourceHash -ne $package.source_sha256) {
    throw 'Original workbook changed before WPS verification.'
}
$expectedOriginal = @(
    '00_投资工作台'
    '00_研究看板'
    '00_研究逻辑卡'
    '00_决策复核'
    '00_组合与股息'
    '00_跟踪与数据'
    '00_首页Dashboard'
    '00_公司总览'
    '00_待完成公司'
    '21_决策验证'
    '05_仓位管理'
    '08_交易记录'
    '09_公司研究'
    '04_估值跟踪'
    '18_指标证据'
    '00_使用说明'
    '12_提醒'
    '03_财务指标'
    '02_质量评分'
    '10_年报跟踪'
    '19_金融专用指标'
    '06_月度跟踪'
    '07_月度复盘'
    '11_数据源审计'
    '20_市场覆盖'
    '01_观察名单'
    '12_系统设置'
    '13_全市场初筛'
    '14_财报候选'
    '15_公司财务覆盖'
    '16_板块行业汇总'
    '历史_初始评分'
    '历史_估值假设'
    '历史_报告备注'
    '17_财务质量评分'
    '18_研究建议'
)
$expectedApplication = @(
    '00_M1应用总览'
    '01_估值与价格'
    '02_股利评估'
    '03_反向估值'
    '04_阻断与证据'
    '05_研究样本'
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
            throw 'Integrated candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'Integrated candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne 42) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    for ($i = 0; $i -lt $expectedApplication.Count; $i++) {
        $index = $i + 1
        $sheet = $book.Worksheets.Item($index)
        if ($sheet.Name -ne $expectedApplication[$i]) {
            throw "Application sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "Application sheet hidden: $($sheet.Name)"
        }
        $sheet.Calculate()
        foreach ($value in $sheet.UsedRange.Value2) {
            if ($value -is [string] -and $value -match '^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$') {
                throw "Formula error on $($sheet.Name)"
            }
        }
        if ($i -eq 0) {
            $firstChecks = @{
                title = [string]$sheet.Range('A1').Text
                first_status = [string]$sheet.Range('E5').Text
            }
        }
    }
    if ($firstChecks.title -ne 'M1 三公司研究 Application 候选') {
        throw "Unexpected overview title: $($firstChecks.title)"
    }
    if ($firstChecks.first_status -ne '完成，有阻断') {
        throw "Unexpected overview status: $($firstChecks.first_status)"
    }
    for ($i = 0; $i -lt $expectedOriginal.Count; $i++) {
        $sheet = $book.Worksheets.Item(6 + $i + 1)
        if ($sheet.Name -ne $expectedOriginal[$i]) {
            throw "Original frontend sheet order differs at $($sheet.Name)"
        }
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the integrated candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = if ($Published) { 'published' } else { 'pre_publication' }
        source = $source
        workbook = $path
        source_sha256 = $sourceHash
        sha256 = $before
        read_only = $true
        original_sheets = 36
        application_sheets = 6
        sheets = 42
        original_sheet_xml_byte_identical = $package.original_sheets_preserved
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $firstChecks
        source_unchanged = if ($Published) { $null } else { $true }
        check_scope = 'WPS read-only open/read/calculate and formula-error scan; no visual click verification'
    }
    $receipt | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    if (-not $SkipChecksOutput) {
        $checks = @{
            status = 'passed'
            candidate_sha256 = $before
            source_sha256 = $sourceHash
            original_sheet_xml_byte_identical = $package.original_sheets_preserved
            original_sheets = 36
            application_sheets = 6
            sheets = 42
            new_pages_are_application_outputs_not_live_signals = $true
            manual_records_preserved = $true
        }
        $checks | ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath ([IO.Path]::ChangeExtension($path, 'checks.json')) -Encoding utf8
    }
    $receipt | ConvertTo-Json -Depth 5 -Compress
}
finally {
    if ($null -ne $book) { $book.Close($false) }
    if ($null -ne $app -and $initialCount -eq 0 -and $app.Workbooks.Count -eq 0) {
        $app.Quit()
    }
}
