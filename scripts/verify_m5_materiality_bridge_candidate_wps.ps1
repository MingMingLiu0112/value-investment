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
    throw "M5 materiality candidate changed before WPS verification: $before"
}

$expectedSheets = @(
    '00_总览'
    '01_材料性映射'
    '02_事件账'
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
            throw 'M5 materiality candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M5 materiality candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $checks = @{}
    $allText = @()
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M5 materiality sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M5 materiality sheet hidden: $($sheet.Name)"
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
                health = [string]$sheet.Range('B9').Text
                materiality_count = [int]$sheet.Range('B10').Value2
                silent_count = [int]$sheet.Range('B11').Value2
                event_count = [int]$sheet.Range('B12').Value2
                invalidation_count = [int]$sheet.Range('B13').Value2
                alert_count = [int]$sheet.Range('B14').Value2
                action = [string]$sheet.Range('B15').Text
            }
        }
        if ($i -eq 1) {
            $checks.materiality_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 2) {
            $checks.event_rows = [int]$sheet.UsedRange.Rows.Count - 4
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
    if ($checks.title -ne 'M5 材料性判定接入（模拟演示）') {
        throw "Unexpected M5 materiality title: $($checks.title)"
    }
    if ($checks.namespace -ne 'SIMULATED') {
        throw "M5 materiality candidate is not simulated: $($checks.namespace)"
    }
    if ($checks.health -ne '需关注') {
        throw "Unexpected M5 materiality health: $($checks.health)"
    }
    if ($checks.materiality_count -ne 6 -or $checks.silent_count -ne 3) {
        throw "Unexpected materiality counts: $($checks.materiality_count)/$($checks.silent_count)"
    }
    if ($checks.event_count -ne 3 -or $checks.invalidation_count -ne 3 -or $checks.alert_count -ne 3) {
        throw "Unexpected M5 integration counts"
    }
    if ($checks.action -ne 'no_order') {
        throw "M5 materiality action is not no_order: $($checks.action)"
    }
    if ($checks.materiality_rows -ne 6) {
        throw "Unexpected materiality row count: $($checks.materiality_rows)"
    }
    if ($checks.event_rows -ne 3) {
        throw "Unexpected event row count: $($checks.event_rows)"
    }
    if ($checks.invalidation_rows -ne 13) {
        throw "Unexpected invalidation row count: $($checks.invalidation_rows)"
    }
    if ($checks.outbox_rows -ne 3) {
        throw "Unexpected outbox row count: $($checks.outbox_rows)"
    }
    if ($checks.boundary_rows -ne 8) {
        throw "Unexpected boundary row count: $($checks.boundary_rows)"
    }
    if ($allText -contains '自动交易' -or $allText -contains '下单' -or $allText -contains '目标仓位') {
        throw 'M5 materiality candidate contains forbidden trading or position text.'
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M5 materiality candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = 'standalone_simulated_m5_materiality_bridge_candidate'
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
