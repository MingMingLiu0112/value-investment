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
    throw "M5 event candidate changed before WPS verification: $before"
}

$expectedSheets = @(
    '00_总览'
    '01_事件账'
    '02_水位与检查点'
    '03_依赖失效与重算'
    '04_Outbox'
    '05_输入与边界'
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
            throw 'M5 event candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M5 event candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $checks = @{}
    $allText = @()
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M5 event sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M5 event sheet hidden: $($sheet.Name)"
        }
        $sheet.Calculate()
        foreach ($value in $sheet.UsedRange.Value2) {
            $allText += [string]$value
            if ($value -is [string] -and $value -match '^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$') {
                throw "Formula error on $($sheet.Name)"
            }
        }
        if ($i -eq 0) {
            $checks = @{
                title = [string]$sheet.Range('A1').Text
                subtitle = [string]$sheet.Range('A2').Text
                namespace = [string]$sheet.Range('B5').Text
                health = [string]$sheet.Range('B6').Text
                input_count = [int]$sheet.Range('B7').Value2
                active_count = [int]$sheet.Range('B9').Value2
                action = [string]$sheet.Range('B17').Text
            }
        }
        if ($i -eq 1) {
            $checks.event_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 2) {
            $checks.watermark_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 3) {
            $checks.invalidation_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 4) {
            $checks.outbox_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 5) {
            $checks.boundary_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
    }
    if ($checks.title -ne 'M5 事件监控基础设施（模拟演示）') {
        throw "Unexpected M5 event title: $($checks.title)"
    }
    if ($checks.namespace -ne 'SIMULATED') {
        throw "M5 event candidate is not simulated: $($checks.namespace)"
    }
    if ($checks.health -ne '需关注') {
        throw "Unexpected M5 run health: $($checks.health)"
    }
    if ($checks.input_count -ne 7 -or $checks.active_count -ne 6) {
        throw "Unexpected M5 event counts: $($checks.input_count)/$($checks.active_count)"
    }
    if ($checks.action -ne 'no_order') {
        throw "M5 event action is not no_order: $($checks.action)"
    }
    if ($checks.event_rows -ne 7) {
        throw "Unexpected M5 event row count: $($checks.event_rows)"
    }
    if ($checks.watermark_rows -ne 10) {
        throw "Unexpected M5 watermark row count: $($checks.watermark_rows)"
    }
    if ($checks.invalidation_rows -ne 20) {
        throw "Unexpected M5 invalidation row count: $($checks.invalidation_rows)"
    }
    if ($checks.outbox_rows -ne 6) {
        throw "Unexpected M5 outbox row count: $($checks.outbox_rows)"
    }
    if ($checks.boundary_rows -ne 11) {
        throw "Unexpected M5 boundary row count: $($checks.boundary_rows)"
    }
    if ($allText -contains '自动交易' -or $allText -contains '下单' -or $allText -contains '目标仓位') {
        throw 'M5 event candidate contains forbidden trading or position text.'
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M5 event candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = 'standalone_simulated_m5_event_infrastructure_candidate'
        workbook = $path
        sha256 = $before
        read_only = $true
        sheets = $expectedSheets.Count
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $checks
        check_scope = 'WPS read-only open/read/calculate, formula-error scan, sheet order, simulated labels, row counts and no-order boundary'
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
