param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $false)][string]$PackagePath,
    [Parameter(Mandatory = $true)][string]$CanonicalPath,
    [Parameter(Mandatory = $true)][string]$ExpectedCanonicalSha256
)
$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$canonicalPath = (Resolve-Path -LiteralPath $CanonicalPath).Path
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
$canonicalBefore = (Get-FileHash -LiteralPath $canonicalPath).Hash.ToLowerInvariant()
$expected = $ExpectedSha256.ToLowerInvariant()
$expectedCanonical = $ExpectedCanonicalSha256.ToLowerInvariant()
if ($before -ne $expected) {
    throw "M7 candidate changed before WPS verification: $before"
}
if ($canonicalBefore -ne $expectedCanonical) {
    throw "Canonical workbook changed before WPS verification: $canonicalBefore"
}
if ($package.candidate_sha256 -ne $expected) {
    throw "M7 manifest does not bind the candidate hash."
}
if ($package.canonical_sha256 -ne $expectedCanonical) {
    throw "M7 manifest does not bind the canonical hash."
}
if ($package.action -ne "no_order") {
    throw "M7 candidate is not no_order."
}

$expectedSheets = @(
    "00_M7总览",
    "M4风险_00_组合风险",
    "M4风险_01_持仓与集中度",
    "M4风险_02_风险发现",
    "M4风险_03_输入与边界",
    "M4仓位_00_总览",
    "M4仓位_01_仓位分层",
    "M4仓位_02_共同预算",
    "M4仓位_03_股息收入",
    "M4仓位_04_输入与边界",
    "M5事件_00_总览",
    "M5事件_01_事件账",
    "M5事件_02_水位与检查点",
    "M5事件_03_依赖失效与重算",
    "M5事件_04_Outbox",
    "M5事件_05_输入与边界",
    "M5材料性_00_总览",
    "M5材料性_01_材料性映射",
    "M5材料性_02_事件账",
    "M5材料性_03_依赖失效与重算",
    "M5材料性_04_Outbox",
    "M5材料性_05_输入与边界",
    "M5披露队列_00_总览",
    "M5披露队列_01_待复核公告",
    "M5披露队列_02_来源覆盖",
    "M5披露队列_03_输入与边界",
    "M5披露复核_00_总览",
    "M5披露复核_01_人工判定",
    "M5披露复核_02_判定说明",
    "M5披露复核_03_边界",
    "00_历史链"
)
$navigationTargets = @(
    "M4风险_00_组合风险",
    "M4仓位_00_总览",
    "M5事件_00_总览",
    "M5材料性_00_总览",
    "M5披露队列_00_总览",
    "M5披露复核_00_总览",
    "00_历史链",
    "00_决策复核",
    "00_投资工作台"
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
            throw "M7 candidate already open; do not reuse or close it."
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        throw "M7 candidate must open read-only."
    }
    if ($book.Worksheets.Count -ne 90) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }

    for ($i = 0; $i -lt $expectedSheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $expectedSheets[$i]) {
            throw "M7 sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M7 presentation sheet hidden: $($sheet.Name)"
        }
        $sheet.Calculate()
        foreach ($value in $sheet.UsedRange.Value2) {
            if ($value -is [string] -and $value -match "^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$") {
                throw "Formula error on $($sheet.Name)"
            }
        }
    }

    $overview = $book.Worksheets.Item("00_M7总览")
    $overviewChecks = @{
        title = [string]$overview.Range("A1").Text
        boundary = [string]$overview.Range("A2").Text
        m2_status = [string]$overview.Range("C6").Text
        m6_status = [string]$overview.Range("C10").Text
        action = [string]$overview.Range("C12").Text
    }
    if ($overviewChecks.title -ne "M7 统一工作台候选（只读展示准备）") {
        throw "Unexpected M7 overview title: $($overviewChecks.title)"
    }
    if ($overviewChecks.boundary -notmatch "simulated/no_order") {
        throw "M7 overview does not preserve the read-only boundary."
    }
    if ($overviewChecks.m2_status -ne "PENDING_HUMAN_REVIEW") {
        throw "Unexpected M2 status: $($overviewChecks.m2_status)"
    }
    if ($overviewChecks.m6_status -ne "NOT_STARTED") {
        throw "M6 must remain NOT_STARTED in this display candidate."
    }
    if ($overviewChecks.action -ne "no_order") {
        throw "M7 overview action is not no_order."
    }
    for ($i = 0; $i -lt $navigationTargets.Count; $i++) {
        $cell = $overview.Range("A$($i + 16)")
        if ($cell.Hyperlinks.Count -lt 1) {
            throw "Missing M7 navigation hyperlink at $($cell.Address())"
        }
        $address = [string]$cell.Hyperlinks.Item(1).Address
        if ($address -notmatch [regex]::Escape($navigationTargets[$i])) {
            throw "Unexpected M7 hyperlink target at $($cell.Address()): $address"
        }
    }

    $overviewText = [string]$overview.UsedRange.Text
    foreach ($forbidden in @("买入", "加仓", "减仓", "目标仓位", "BUY", "ADD")) {
        if ($overviewText -match $forbidden) {
            throw "Forbidden decision text on M7 overview: $forbidden"
        }
    }

    $sheetCount = $book.Worksheets.Count
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw "Read-only check changed the M7 candidate."
    }
    if ((Get-FileHash -LiteralPath $canonicalPath).Hash.ToLowerInvariant() -ne $canonicalBefore) {
        throw "Read-only check changed the canonical workbook."
    }
    $receipt = @{
        status = "passed"
        mode = "protected_m7_workbench_display_candidate"
        workbook = $path
        sha256 = $before
        canonical = $canonicalPath
        canonical_sha256 = $canonicalBefore
        read_only = $true
        sheets = $sheetCount
        presentation_sheets_checked = $expectedSheets.Count
        navigation_targets = $navigationTargets
        source_sheets_preserved = $package.final_original_sheets_preserved
        original_parts_unchanged = $package.final_original_parts_unchanged
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        checks = @{
            overview = $overviewChecks
        }
        action = "no_order"
        check_scope = "WPS read-only open/read/calculate, formula-error scan, presentation sheet order, navigation targets, no_order text and canonical hash; no visual click verification"
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
