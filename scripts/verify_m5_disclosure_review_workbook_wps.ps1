param(
    [Parameter(Mandatory)][string]$WorkbookPath,
    [Parameter(Mandatory)][string]$ManifestPath,
    [Parameter(Mandatory)][string]$ReceiptPath,
    [Parameter(Mandatory)][string]$ExpectedSha256
)
$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$expected = $ExpectedSha256.ToLowerInvariant()
if ($before -ne $expected) {
    throw "M5 disclosure review workbook changed before WPS verification: $before"
}

$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$expectedSheets = @(
    "00_总览"
    "01_人工判定"
    "02_判定说明"
    "03_边界"
)
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
            throw "M5 disclosure review workbook already open; do not reuse or close it."
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw "M5 disclosure review workbook must open read-only."
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }
    $checks = @{}
    $allText = @()
    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M5 disclosure review sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M5 disclosure review sheet hidden: $($sheet.Name)"
        }
        $sheet.Calculate()
        foreach ($value in $sheet.UsedRange.Value2) {
            $allText += [string]$value
            if ($value -is [string] -and $value -match "^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$") {
                throw "Formula error on $($sheet.Name)"
            }
        }
        if ($i -eq 0) {
            $checks = @{
                title = [string]$sheet.Range("A1").Text
                queue_id = [string]$sheet.Range("B5").Text
                queue_sha256 = [string]$sheet.Range("B6").Text
                pending_count = [int]$sheet.Range("B10").Value2
                action = [string]$sheet.Range("B12").Text
                reviewed_at_blank = [string]$sheet.Range("B13").Text -eq ""
            }
        }
        if ($i -eq 1) {
            $checks.pending_rows = [int]$sheet.UsedRange.Rows.Count - 4
            for ($row = 5; $row -le $checks.pending_rows + 4; $row++) {
                if ([string]$sheet.Cells.Item($row, 7).Text) {
                    throw "M5 disclosure review decision is prefilled at row $row"
                }
                if ([string]$sheet.Cells.Item($row, 12).Text) {
                    throw "M5 disclosure review note is prefilled at row $row"
                }
            }
        }
        if ($i -eq 3) {
            $checks.boundary_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
    }
    if ($checks.title -ne "M5 真实披露人工复核回填") {
        throw "Unexpected M5 disclosure review title: $($checks.title)"
    }
    if ($checks.queue_id -ne [string]$manifest.queue_id) {
        throw "Unexpected queue id: $($checks.queue_id)"
    }
    if ($checks.queue_sha256 -ne [string]$manifest.queue_sha256) {
        throw "Unexpected queue hash: $($checks.queue_sha256)"
    }
    if ($checks.pending_count -ne [int]$manifest.pending_candidate_count) {
        throw "Unexpected pending count: $($checks.pending_count)"
    }
    if ($checks.action -ne "no_order") {
        throw "M5 disclosure review action is not no_order: $($checks.action)"
    }
    if (-not $checks.reviewed_at_blank) {
        throw "M5 disclosure review reviewed_at must start blank."
    }
    if ($checks.pending_rows -ne [Math]::Max(1, [int]$manifest.pending_candidate_count)) {
        throw "Unexpected pending row count: $($checks.pending_rows)"
    }
    if ($checks.boundary_rows -ne 9) {
        throw "Unexpected boundary row count: $($checks.boundary_rows)"
    }
    foreach ($forbidden in @("自动交易", "自动下单", "目标仓位")) {
        if ($allText -contains $forbidden) {
            throw "M5 disclosure review contains forbidden text: $forbidden"
        }
    }
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw "Read-only check changed the M5 disclosure review workbook."
    }
    $receipt = @{
        status = "passed"
        mode = "blank_m5_disclosure_review_intake"
        workbook = $path
        manifest = $ManifestPath
        sha256 = $before
        read_only = $true
        sheets = $expectedSheets.Count
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        checks = $checks
        check_scope = "WPS read-only open/read/calculate, formula-error scan, sheet order, blank decisions, queue fingerprint and no-order boundary"
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
