param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $true)][string]$PackagePath
)
$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$packagePath = (Resolve-Path -LiteralPath $PackagePath).Path
$package = Get-Content -Raw -LiteralPath $packagePath | ConvertFrom-Json
$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$expected = $ExpectedSha256.ToLowerInvariant()
if ($before -ne $expected) {
    throw "M7 product candidate changed before WPS verification: $before"
}
if ($package.workbook_sha256 -ne $expected) {
    throw "M7 product manifest does not bind the workbook hash."
}
if ($package.action -ne "no_order") {
    throw "M7 product candidate is not no_order."
}
if ($package.schema_version -ne "m7-product-workbench-candidate-v1") {
    throw "Unexpected M7 product manifest schema: $($package.schema_version)"
}

$expectedSheets = @(
    "01_今日",
    "02_机会",
    "03_公司",
    "04_我的组合",
    "05_事件",
    "06_系统与审计"
)
$userSheets = $expectedSheets[0..4]
$forbiddenDecision = @("建议买入", "建议加仓", "目标仓位", "下单", "买入", "加仓", "减仓", "BUY", "ADD")
$forbiddenToken = "\b(DONE|PARTIAL|NOT_STARTED|BLOCKED|PENDING_[A-Z_]+|ENGINEERING_[A-Z_]+|PREFLIGHT_[A-Z_]+|VERIFIED|REJECTED|INSUFFICIENT)\b"

$app = $null
$book = $null
$initialCount = -1
$sheetChecks = [ordered]@{}
try {
    $app = New-Object -ComObject ket.Application
    $app.DisplayAlerts = $false
    $applicationPath = [string]$app.Path
    if ($applicationPath -notmatch "WPS") {
        throw "Unexpected document engine: $applicationPath"
    }
    $initialCount = $app.Workbooks.Count
    foreach ($existing in $app.Workbooks) {
        if ([string]$existing.FullName -eq $path) {
            throw "M7 product candidate already open; do not reuse or close it."
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        throw "M7 product candidate must open read-only."
    }
    if ($book.Worksheets.Count -ne $expectedSheets.Count) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }

    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        $name = [string]$sheet.Name
        if ($name -ne $expectedSheets[$i]) {
            throw "Sheet order differs at $name"
        }
        if ($sheet.Visible -ne -1) {
            throw "Product sheet hidden: $name"
        }
        $sheet.Calculate()
        $values = @()
        foreach ($value in $sheet.UsedRange.Value2) {
            $text = [string]$value
            if ($text -match "^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$") {
                throw "Formula error on $name"
            }
            $values += $text
        }
        $joined = $values -join [Environment]::NewLine
        if ([string]::IsNullOrWhiteSpace($joined)) {
            throw "Sheet $name produced no materialized text."
        }
        $sheet.Activate()
        $window = $app.ActiveWindow
        $freezeOk = [bool]$window.FreezePanes -and
            ([int]$window.SplitRow -eq 3) -and
            ([int]$window.SplitColumn -eq 1)
        if (-not $freezeOk) {
            throw "Sheet $name does not freeze the first column and the title rows."
        }
        if ($userSheets -contains $name) {
            if ($joined -match $forbiddenToken) {
                throw "Engineering stage token leaked onto user page $name : $($Matches[0])"
            }
            foreach ($word in $forbiddenDecision) {
                if ($joined -match [regex]::Escape($word)) {
                    throw "Forbidden decision text on $name : $word"
                }
            }
        }
        $sheetChecks[$name] = @{
            materialized_characters = $joined.Length
            freeze_panes_first_column = $freezeOk
        }
    }

    $emptyState = $book.Worksheets.Item("04_我的组合")
    $emptyText = @()
    foreach ($value in $emptyState.UsedRange.Value2) { $emptyText += [string]$value }
    $emptyJoined = $emptyText -join [Environment]::NewLine
    if ($emptyJoined -notmatch "尚未接入真实组合") {
        throw "Absent portfolio page lost its required empty state."
    }
    $company = $book.Worksheets.Item("03_公司")
    $companyText = @()
    foreach ($value in $company.UsedRange.Value2) { $companyText += [string]$value }
    $companyJoined = $companyText -join [Environment]::NewLine
    foreach ($required in @("暂不可评估", "原因：", "需要：")) {
        if ($companyJoined -notmatch [regex]::Escape($required)) {
            throw "Company page lost required blocked-valuation wording: $required"
        }
    }

    $sheetCount = $book.Worksheets.Count
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw "Read-only check changed the M7 product candidate."
    }
    $receipt = @{
        status = "passed"
        mode = "m7_product_ux_read_only_candidate"
        workbook = $path
        sha256 = $before
        read_only = $true
        sheets = $sheetCount
        visible_sheets = $sheetCount
        hidden_sheets = 0
        user_sheets = $userSheets
        secondary_sheets = @("06_系统与审计")
        sheet_checks = $sheetChecks
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        action = "no_order"
        final_user_acceptance = "NOT_PASSED"
        canonical_pointer_modified = $false
        check_scope = "WPS read-only open/read/calculate, sheet contract, per-sheet frozen first column, formula-error scan, engineering-token scan and forbidden-decision scan on the five user pages, required empty-state and blocked-valuation wording, workbook hash stability"
    }
    $receipt | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    $receipt | ConvertTo-Json -Depth 6 -Compress
}
finally {
    if ($null -ne $book) {
        $book.Close($false)
    }
    if ($null -ne $app -and $initialCount -eq 0 -and $app.Workbooks.Count -eq 0) {
        $app.Quit()
    }
}
