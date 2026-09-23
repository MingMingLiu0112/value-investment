param(
    [Parameter(Mandatory)][string]$WorkbookPath,
    [Parameter(Mandatory)][string]$ReceiptPath
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$before = (Get-FileHash -LiteralPath $path).Hash
$expected = @(
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
            throw 'Candidate already open; do not reuse or close it.'
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'Candidate must open read-only.'
    }
    if ($book.Worksheets.Count -ne $expected.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $firstChecks = @{}
    for ($i = 0; $i -lt $expected.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expected[$i]) {
            throw "Application workbook sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "Application workbook sheet hidden: $($sheet.Name)"
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
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash -ne $before) {
        throw 'Read-only check changed the application workbook.'
    }
    $receipt = @{
        status = 'passed'
        workbook = $path
        sha256 = $before.ToLowerInvariant()
        read_only = $true
        sheets = $expected
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        checks = $firstChecks
        source_unchanged = $true
        check_scope = 'WPS read-only open/read/calculate and formula-error scan; no visual click verification'
    }
    $receipt | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    $receipt | ConvertTo-Json -Depth 5 -Compress
}
finally {
    if ($null -ne $book) { $book.Close($false) }
    if ($null -ne $app -and $initialCount -eq 0 -and $app.Workbooks.Count -eq 0) {
        $app.Quit()
    }
}
