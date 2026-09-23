param(
    [Parameter(Mandatory)][string]$WorkbookPath,
    [Parameter(Mandatory)][string]$ManifestPath,
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
    throw "M5 disclosure queue candidate changed before WPS verification: $before"
}

$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$expectedSheets = @(
    '00_总览'
    '01_待复核公告'
    '02_来源覆盖'
    '03_输入与边界'
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
            throw 'M5 disclosure queue candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M5 disclosure queue candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $checks = @{}
    $allText = @()
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M5 disclosure queue sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M5 disclosure queue sheet hidden: $($sheet.Name)"
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
                source = [string]$sheet.Range('B6').Text
                company_count = [int]$sheet.Range('B9').Value2
                pending_count = [int]$sheet.Range('B10').Value2
                unavailable_count = [int]$sheet.Range('B11').Value2
                action = [string]$sheet.Range('B14').Text
            }
        }
        if ($i -eq 1) {
            $checks.pending_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 2) {
            $checks.coverage_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 3) {
            $checks.boundary_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
    }
    if ($checks.title -ne 'M5 真实披露待复核队列') {
        throw "Unexpected M5 disclosure queue title: $($checks.title)"
    }
    if ($checks.source -ne 'CNINFO statutory disclosure') {
        throw "Unexpected disclosure source: $($checks.source)"
    }
    if ($checks.company_count -ne [int]$manifest.company_count) {
        throw "Unexpected company count: $($checks.company_count)"
    }
    if ($checks.pending_count -ne [int]$manifest.pending_candidate_count) {
        throw "Unexpected pending count: $($checks.pending_count)"
    }
    if ($checks.unavailable_count -ne [int]$manifest.source_unavailable_count) {
        throw "Unexpected unavailable count: $($checks.unavailable_count)"
    }
    if ($checks.action -ne 'no_order') {
        throw "M5 disclosure queue action is not no_order: $($checks.action)"
    }
    $expectedPendingRows = [Math]::Max(1, [int]$manifest.pending_candidate_count)
    if ($checks.pending_rows -ne $expectedPendingRows) {
        throw "Unexpected pending row count: $($checks.pending_rows)"
    }
    if ($checks.coverage_rows -ne [int]$manifest.company_count) {
        throw "Unexpected coverage row count: $($checks.coverage_rows)"
    }
    if ($checks.boundary_rows -ne 9) {
        throw "Unexpected boundary row count: $($checks.boundary_rows)"
    }
    if ($allText -contains '自动交易' -or $allText -contains '下单' -or $allText -contains '目标仓位') {
        throw 'M5 disclosure queue contains forbidden trading or position text.'
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M5 disclosure queue candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = 'standalone_real_cninfo_m5_disclosure_review_queue'
        workbook = $path
        manifest = $ManifestPath
        sha256 = $before
        read_only = $true
        sheets = $expectedSheets.Count
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $checks
        check_scope = 'WPS read-only open/read/calculate, formula-error scan, sheet order, queue counts and no-order boundary'
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
