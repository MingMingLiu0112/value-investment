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
    throw "M4 guidance candidate changed before WPS verification: $before"
}

$expectedSheets = @(
    '00_总览'
    '01_仓位分层'
    '02_共同预算'
    '03_股息收入'
    '04_输入与边界'
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
            throw 'M4 guidance candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'M4 guidance candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $checks = @{}
    $allText = @()
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M4 guidance sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M4 guidance sheet hidden: $($sheet.Name)"
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
                guidance_status = [string]$sheet.Range('B6').Text
                dividend_status = [string]$sheet.Range('B7').Text
                action = [string]$sheet.Range('B12').Text
            }
        }
        if ($i -eq 1) {
            $checks.position_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 2) {
            $checks.budget_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 3) {
            $checks.income_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 4) {
            $checks.boundary_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
    }
    if ($checks.title -ne 'M4 仓位边界与股息收入（模拟演示）') {
        throw "Unexpected M4 guidance title: $($checks.title)"
    }
    if ($checks.namespace -ne 'SIMULATED') {
        throw "M4 guidance candidate is not simulated: $($checks.namespace)"
    }
    if ($checks.guidance_status -ne '共同预算冲突') {
        throw "Unexpected M4 guidance status: $($checks.guidance_status)"
    }
    if ($checks.dividend_status -ne 'READY') {
        throw "Unexpected M4 dividend status: $($checks.dividend_status)"
    }
    if ($checks.action -ne 'no_order') {
        throw "M4 guidance action is not no_order: $($checks.action)"
    }
    if ($checks.position_rows -ne 4) {
        throw "Unexpected M4 position row count: $($checks.position_rows)"
    }
    if ($checks.budget_rows -ne 6) {
        throw "Unexpected M4 budget row count: $($checks.budget_rows)"
    }
    if ($checks.income_rows -ne 4) {
        throw "Unexpected M4 income row count: $($checks.income_rows)"
    }
    if ($checks.boundary_rows -lt 10) {
        throw "Unexpected M4 boundary row count: $($checks.boundary_rows)"
    }
    if ($allText -contains '目标仓位' -or $allText -contains '下单') {
        throw 'M4 guidance candidate contains forbidden position or order text.'
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw 'Read-only check changed the M4 guidance candidate.'
    }
    $receipt = @{
        status = 'passed'
        mode = 'standalone_simulated_m4_guidance_income_candidate'
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
