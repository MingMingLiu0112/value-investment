param(
    [Parameter(Mandatory=$true)][string]$WorkbookPath,
    [Parameter(Mandatory=$true)][string]$ReceiptPath,
    [Parameter(Mandatory=$false)][string]$PackagePath,
    [Parameter(Mandatory=$false)][string]$ExpectedSha256
)
$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$packagePath = if ([string]::IsNullOrWhiteSpace($PackagePath)) {
    [IO.Path]::ChangeExtension($path, "candidate.manifest.json")
} else {
    (Resolve-Path -LiteralPath $PackagePath).Path
}
if (-not (Test-Path -LiteralPath $packagePath)) {
    throw "Package manifest missing: $packagePath"
}
$package = Get-Content -Raw -LiteralPath $packagePath | ConvertFrom-Json
$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$expected = if ([string]::IsNullOrWhiteSpace($ExpectedSha256)) {
    $package.candidate_sha256
} else {
    $ExpectedSha256.ToLowerInvariant()
}
if ($before -ne $expected) {
    throw "M3 integrated candidate changed before WPS verification."
}

$target = "00_决策复核"
$app = $null
$book = $null
$initialCount = -1
try {
    $app = New-Object -ComObject ket.Application
    $applicationPath = [string]$app.Path
    if ($applicationPath -notmatch "WPS") {
        throw "Unexpected document engine: $applicationPath"
    }
    $initialCount = $app.Workbooks.Count
    foreach ($existing in $app.Workbooks) {
        if ([string]$existing.FullName -eq $path) {
            throw "M3 integrated candidate already open; do not reuse or close it."
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        throw "M3 integrated candidate must open read-only."
    }
    if ($book.Worksheets.Count -ne 55) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $sheet = $null
    foreach ($candidate in $book.Worksheets) {
        if ([string]$candidate.Name -eq $target) {
            $sheet = $candidate
            break
        }
    }
    if ($null -eq $sheet) {
        throw "Decision review sheet missing: $target"
    }
    if ($sheet.Visible -ne -1) {
        throw "Decision review sheet is hidden: $target"
    }
    $sheet.Calculate()
    foreach ($value in $sheet.UsedRange.Value2) {
        if ($value -is [string] -and $value -match "^(#REF!|#DIV/0!|#VALUE!|#NAME\?|#N/A)$") {
            throw "Formula error on $target"
        }
    }
    $checks = @{
        title = [string]$sheet.Range("A1").Text
        subtitle = [string]$sheet.Range("A2").Text
        first_symbol = [string]$sheet.Range("A6").Text
        first_name = [string]$sheet.Range("B6").Text
        first_status = [string]$sheet.Range("D6").Text
        first_intent = [string]$sheet.Range("F6").Text
        first_portfolio = [string]$sheet.Range("G6").Text
        first_entry = [string]$sheet.Range("H6").Text
        row_count = [int]$sheet.UsedRange.Rows.Count
    }
    if ($checks.title -ne "决策复核（M3 非个人化负向卡）") {
        throw "Unexpected decision review title: $($checks.title)"
    }
    if ($checks.subtitle -notmatch "action=no_order") {
        throw "Decision review subtitle does not preserve no_order."
    }
    if ($checks.first_symbol -ne "000651" -or $checks.first_status -ne "研究证据不足") {
        throw "Unexpected first M3 decision card."
    }
    if ($checks.first_intent -ne "未提交" -or $checks.first_portfolio -ne "缺失" -or $checks.first_entry -ne "本卡不需要") {
        throw "Unexpected fail-closed decision card fields."
    }
    $forbidden = @("买入", "加仓", "减仓", "目标仓位", "BUY", "ADD")
    foreach ($row in $sheet.UsedRange.Rows) {
        foreach ($cell in $row.Cells) {
            $text = [string]$cell.Text
            foreach ($item in $forbidden) {
                if ($text -match $item) {
                    throw "Forbidden signal text on $target : $item"
                }
            }
        }
    }
    $sheetCount = $book.Worksheets.Count
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw "Read-only check changed the M3 integrated candidate."
    }
    $receipt = @{
        status = "passed"
        mode = "pre_publication"
        workbook = $path
        sha256 = $before
        read_only = $true
        sheets = $sheetCount
        target_sheet = $target
        original_sheets_preserved = $package.original_sheets_preserved
        derived_sheets_replaced = $package.derived_sheets_replaced
        original_parts_unchanged = $package.original_parts_unchanged
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        checks = $checks
        action = "no_order"
        check_scope = "WPS read-only open/read/calculate, formula scan, 55-sheet count, M3 fail-closed fields and forbidden signal scan"
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
