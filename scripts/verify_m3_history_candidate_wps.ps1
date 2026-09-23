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
    throw "M3 history candidate changed before WPS verification: $before"
}

$expectedSheets = @(
    '00_历史链'
    '01_原Entry'
    '02_决策日志'
    '03_一致性复核'
    '04_来源哈希'
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
            throw 'M3 history candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M3 history candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $checks = @{}
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M3 history sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M3 history sheet hidden: $($sheet.Name)"
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
                symbol = [string]$sheet.Range('A5').Text
                latest_human_decision = [string]$sheet.Range('G5').Text
                latest_consistency = [string]$sheet.Range('H5').Text
                action = [string]$sheet.Range('I5').Text
            }
        }
        if ($i -eq 2) {
            $checks.journal_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 3) {
            $checks.consistency_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 4) {
            $checks.source_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
    }
    if ($checks.title -ne 'M3 论点连续性历史链') {
        throw "Unexpected M3 history overview title: $($checks.title)"
    }
    if ($checks.symbol -ne '600887') {
        throw "Unexpected M3 history symbol: $($checks.symbol)"
    }
    if ($checks.latest_human_decision -ne '确认减仓') {
        throw "Unexpected latest decision: $($checks.latest_human_decision)"
    }
    if ($checks.latest_consistency -ne '已破坏') {
        throw "Unexpected latest consistency: $($checks.latest_consistency)"
    }
    if ($checks.action -ne 'no_order') {
        throw "M3 history action is not no_order: $($checks.action)"
    }
    if ($checks.journal_rows -ne 3) {
        throw "Unexpected journal row count: $($checks.journal_rows)"
    }
    if ($checks.consistency_rows -lt 3) {
        throw "Unexpected consistency row count: $($checks.consistency_rows)"
    }
    if ($checks.source_rows -ne 6) {
        throw "Unexpected source row count: $($checks.source_rows)"
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M3 history candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = 'standalone_simulated_history_candidate'
        workbook = $path
        sha256 = $before
        read_only = $true
        sheets = $expectedSheets.Count
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $checks
        check_scope = 'WPS read-only open/read/calculate, formula-error scan, sheet order, history rows and action; no visual click verification'
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
