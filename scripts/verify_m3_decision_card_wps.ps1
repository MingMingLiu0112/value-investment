param(
    [Parameter(Mandatory)][string]$WorkbookPath,
    [Parameter(Mandatory)][string]$ReceiptPath,
    [Parameter(Mandatory)][string]$ExpectedSha256
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$expected = $ExpectedSha256.ToLowerInvariant()
if ($before -ne $expected) {
    throw "M3 decision-card candidate changed before WPS verification: $before"
}

$expectedSheets = @(
    '00_决策卡'
    '01_缺失与阻断'
    '02_来源哈希'
    '03_证据引用'
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
            throw 'M3 decision-card candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M3 decision-card candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $checks = @{}
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M3 sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M3 sheet hidden: $($sheet.Name)"
        }
        $sheet.Calculate()
        foreach ($value in $sheet.UsedRange.Value2) {
            if ($value -is [string] -and $value -match '^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$') {
                throw "Formula error on $($sheet.Name)"
            }
        }
        if ($i -eq 0) {
            $checks = @{
                title = [string]$sheet.Range('A1').Text
                subtitle = [string]$sheet.Range('A2').Text
                first_symbol = [string]$sheet.Range('A5').Text
                third_symbol = [string]$sheet.Range('A7').Text
                action = [string]$sheet.Range('A2').Text
            }
        }
        if ($i -eq 2) {
            $checks.source_hash_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 3) {
            $checks.evidence_hyperlinks = [int]$sheet.Hyperlinks.Count
        }
    }
    if ($checks.title -ne 'M3 非个人化失败关闭决策卡候选') {
        throw "Unexpected M3 overview title: $($checks.title)"
    }
    if ($checks.first_symbol -ne '000651' -or $checks.third_symbol -ne '600887') {
        throw 'M3 card symbol order is unexpected.'
    }
    if ($checks.source_hash_rows -ne 9) {
        throw "Unexpected source-hash row count: $($checks.source_hash_rows)"
    }
    if ($checks.evidence_hyperlinks -lt 20) {
        throw "M3 evidence links are unexpectedly incomplete: $($checks.evidence_hyperlinks)"
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M3 decision-card candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = 'standalone_candidate'
        workbook = $path
        sha256 = $before
        read_only = $true
        sheets = $expectedSheets.Count
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $checks
        check_scope = 'WPS read-only open/read/calculate, formula-error scan, sheet order, symbol rows and evidence-link count; no visual click verification'
    }
    $receipt | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    $receipt | ConvertTo-Json -Depth 5 -Compress
}
finally {
    if ($null -ne $book) {
        $book.Close($false)
    }
    if ($null -ne $app -and $initialCount -eq 0 -and $app.Workbooks.Count -eq 0) {
        $app.Quit()
    }
}
