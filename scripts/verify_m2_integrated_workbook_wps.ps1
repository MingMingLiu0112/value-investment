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
    throw 'M2 integrated candidate changed before WPS verification.'
}
if (-not $Published) {
    $sourceHash = (Get-FileHash -LiteralPath $source).Hash.ToLowerInvariant()
    if ($sourceHash -ne $package.source_sha256) {
        throw 'Original workbook changed before WPS verification.'
    }
}
$expectedM2 = @(
    '00_M2总览'
    '01_候选池'
    '02_质量候选'
    '03_现金回报候选'
    '04_价值候选'
    '05_周期候选'
    '06_数据健康'
    '07_不支持与缺失'
    '08_Legacy对比'
    '09_证据清单'
    '10_逐通道覆盖'
    '11_研究报告'
    '12_研究证据'
)
$expectedApplication = @(
    '00_M1应用总览'
    '01_估值与价格'
    '02_股利评估'
    '03_反向估值'
    '04_阻断与证据'
    '05_研究样本'
)
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
            throw 'M2 integrated candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M2 integrated candidate must open read-only.'
    }
    $expectedSheets = $expectedM2.Count + $expectedApplication.Count + $expectedOriginal.Count
    if ($book.Worksheets.Count -ne $expectedSheets) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $firstChecks = @{}
    for ($i = 0; $i -lt $expectedM2.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedM2[$i]) {
            throw "M2 sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M2 sheet hidden: $($sheet.Name)"
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
                action = [string]$sheet.Range('B4').Text
            }
        }
        if ($sheet.Name -eq '11_研究报告') {
            $firstChecks.report_title = [string]$sheet.Range('A1').Text
            $firstChecks.report_rows = [int]$sheet.UsedRange.Rows.Count
        }
        if ($sheet.Name -eq '12_研究证据') {
            $firstChecks.evidence_rows = [int]$sheet.UsedRange.Rows.Count
            $firstChecks.evidence_hyperlinks = [int]$sheet.Hyperlinks.Count
        }
    }
    if ($firstChecks.title -ne 'M2 多通道机会发现') {
        throw "Unexpected M2 overview title: $($firstChecks.title)"
    }
    if ($firstChecks.report_title -ne 'AC8 实质研究与通道否决') {
        throw "Unexpected AC8 report title: $($firstChecks.report_title)"
    }
    if ($firstChecks.report_rows -lt 21) {
        throw "AC8 report rows are unexpectedly short: $($firstChecks.report_rows)"
    }
    if ($firstChecks.evidence_rows -lt 20 -or $firstChecks.evidence_hyperlinks -lt 10) {
        throw 'AC8 evidence links are unexpectedly incomplete.'
    }
    for ($i = 0; $i -lt $expectedApplication.Count; $i++) {
        $sheet = $book.Worksheets.Item($expectedM2.Count + $i + 1)
        if ($sheet.Name -ne $expectedApplication[$i]) {
            throw "M1 application sheet order differs at $($sheet.Name)"
        }
    }
    for ($i = 0; $i -lt $expectedOriginal.Count; $i++) {
        $sheet = $book.Worksheets.Item($expectedM2.Count + $expectedApplication.Count + $i + 1)
        if ($sheet.Name -ne $expectedOriginal[$i]) {
            throw "Original frontend sheet order differs at $($sheet.Name)"
        }
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M2 integrated candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = if ($Published) { 'published' } else { 'pre_publication' }
        source = $source
        workbook = $path
        source_sha256 = $sourceHash
        sha256 = $before
        read_only = $true
        m2_frontend_sheets = $expectedM2.Count
        m1_application_sheets = $expectedApplication.Count
        original_sheets = $expectedOriginal.Count
        sheets = $expectedSheets
        original_sheet_xml_byte_identical = $package.original_sheets_preserved
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $firstChecks
        source_unchanged = if ($Published) { $null } else { $true }
        check_scope = 'WPS read-only open/read/calculate, formula-error scan, sheet order and evidence-link count; no visual click verification'
    }
    $receipt | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    if (-not $SkipChecksOutput) {
        $checks = @{
            status = 'passed'
            candidate_sha256 = $before
            source_sha256 = $sourceHash
            original_sheet_xml_byte_identical = $package.original_sheets_preserved
            m2_frontend_sheets = $expectedM2.Count
            m1_application_sheets = $expectedApplication.Count
            original_sheets = $expectedOriginal.Count
            sheets = $expectedSheets
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
