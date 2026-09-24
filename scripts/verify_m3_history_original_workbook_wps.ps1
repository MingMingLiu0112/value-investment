param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $false)][string]$PackagePath
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
$expected = $ExpectedSha256.ToLowerInvariant()
if ($before -ne $expected) {
    throw "M3 history overlay changed before WPS verification: $before"
}
if ($package.candidate_sha256 -ne $expected) {
    throw "M3 history overlay manifest does not bind the candidate hash."
}

$historySheets = @(
    "00_历史链",
    "01_原Entry",
    "02_决策日志",
    "03_一致性复核",
    "04_来源哈希"
)
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
            throw "M3 history overlay already open; do not reuse or close it."
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        throw "M3 history overlay must open read-only."
    }
    if ($book.Worksheets.Count -ne 60) {
        throw "Unexpected worksheet count: $($book.Worksheets.Count)"
    }

    $historyChecks = @{}
    for ($i = 0; $i -lt $historySheets.Count; $i++) {
        $sheet = $book.Worksheets.Item($i + 1)
        if ($sheet.Name -ne $historySheets[$i]) {
            throw "M3 history sheet order differs at $($sheet.Name)"
        }
        if ($sheet.Visible -ne -1) {
            throw "M3 history sheet hidden: $($sheet.Name)"
        }
        $sheet.Calculate()
        foreach ($value in $sheet.UsedRange.Value2) {
            if ($value -is [string] -and $value -match "^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$") {
                throw "Formula error on $($sheet.Name)"
            }
        }
        if ($i -eq 0) {
            $historyChecks = @{
                title = [string]$sheet.Range("A1").Text
                subtitle = [string]$sheet.Range("A2").Text
                symbol = [string]$sheet.Range("A5").Text
                namespace = [string]$sheet.Range("C5").Text
                entry_type = [string]$sheet.Range("D5").Text
                latest_human_decision = [string]$sheet.Range("G5").Text
                latest_consistency = [string]$sheet.Range("H5").Text
                action = [string]$sheet.Range("I5").Text
            }
        }
        if ($i -eq 2) {
            $historyChecks.journal_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 3) {
            $historyChecks.consistency_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
        if ($i -eq 4) {
            $historyChecks.source_rows = [int]$sheet.UsedRange.Rows.Count - 4
        }
    }
    if ($historyChecks.title -ne "M3 论点连续性历史链") {
        throw "Unexpected M3 history overlay title: $($historyChecks.title)"
    }
    if ($historyChecks.subtitle -notmatch "模拟演示链路") {
        throw "M3 history overlay does not preserve the simulated boundary."
    }
    if ($historyChecks.symbol -ne "600887" -or $historyChecks.namespace -ne "模拟") {
        throw "Unexpected M3 history namespace or symbol."
    }
    if ($historyChecks.entry_type -ne "模拟") {
        throw "M3 history overlay does not use simulated entry type."
    }
    if ($historyChecks.latest_human_decision -ne "确认减仓") {
        throw "Unexpected latest decision: $($historyChecks.latest_human_decision)"
    }
    if ($historyChecks.latest_consistency -ne "已破坏") {
        throw "Unexpected latest consistency: $($historyChecks.latest_consistency)"
    }
    if ($historyChecks.action -ne "no_order") {
        throw "M3 history overlay action is not no_order: $($historyChecks.action)"
    }
    if ($historyChecks.journal_rows -ne 3) {
        throw "Unexpected journal row count: $($historyChecks.journal_rows)"
    }
    if ($historyChecks.consistency_rows -lt 3) {
        throw "Unexpected consistency row count: $($historyChecks.consistency_rows)"
    }
    if ($historyChecks.source_rows -ne 6) {
        throw "Unexpected source row count: $($historyChecks.source_rows)"
    }

    # UsedRange.Text is unreliable through WPS COM. Materialize the values so
    # forbidden presentation text cannot pass through an empty scan.
    $historyText = ""
    foreach ($historyName in $historySheets) {
        foreach ($value in $book.Worksheets.Item($historyName).UsedRange.Value2) {
            $historyText += [string]$value
        }
    }
    foreach ($forbidden in @("目标仓位", "下单", "自动卖出")) {
        if ($historyText -match $forbidden) {
            throw "Forbidden presentation text on M3 history pages: $forbidden"
        }
    }

    $decision = $null
    foreach ($candidate in $book.Worksheets) {
        if ([string]$candidate.Name -eq $target) {
            $decision = $candidate
            break
        }
    }
    if ($null -eq $decision) {
        throw "Decision review sheet missing: $target"
    }
    if ($decision.Visible -ne -1) {
        throw "Decision review sheet is hidden: $target"
    }
    $decision.Calculate()
    foreach ($value in $decision.UsedRange.Value2) {
        if ($value -is [string] -and $value -match "^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$") {
            throw "Formula error on $target"
        }
    }
    $decisionChecks = @{
        title = [string]$decision.Range("A1").Text
        subtitle = [string]$decision.Range("A2").Text
        first_symbol = [string]$decision.Range("A6").Text
        first_status = [string]$decision.Range("D6").Text
        first_intent = [string]$decision.Range("F6").Text
        first_portfolio = [string]$decision.Range("G6").Text
        first_entry = [string]$decision.Range("H6").Text
    }
    if ($decisionChecks.title -ne "决策复核（M3 非个人化负向卡）") {
        throw "Unexpected decision review title: $($decisionChecks.title)"
    }
    if ($decisionChecks.subtitle -notmatch "action=no_order") {
        throw "Decision review subtitle does not preserve no_order."
    }
    if ($decisionChecks.first_symbol -ne "000651" -or $decisionChecks.first_status -ne "研究证据不足") {
        throw "Unexpected first M3 decision card."
    }
    if ($decisionChecks.first_intent -ne "未提交" -or $decisionChecks.first_portfolio -ne "缺失" -or $decisionChecks.first_entry -ne "本卡不需要") {
        throw "Unexpected fail-closed decision card fields."
    }
    $forbiddenDecision = @("买入", "加仓", "减仓", "目标仓位", "BUY", "ADD")
    foreach ($row in $decision.UsedRange.Rows) {
        foreach ($cell in $row.Cells) {
            $text = [string]$cell.Text
            foreach ($item in $forbiddenDecision) {
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
        throw "Read-only check changed the M3 history overlay."
    }
    $receipt = @{
        status = "passed"
        mode = "protected_history_overlay_candidate"
        workbook = $path
        sha256 = $before
        read_only = $true
        sheets = $sheetCount
        history_sheets = $historySheets
        target_sheet = $target
        source_sheets_preserved = $package.original_sheets_preserved
        new_sheets = $historySheets.Count
        original_parts_unchanged = $package.original_parts_unchanged
        namespace = "simulated"
        application = [string]$app.Name
        application_path = $applicationPath
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        checks = @{
            history = $historyChecks
            decision = $decisionChecks
        }
        action = "no_order"
        check_scope = "WPS read-only open/read/calculate, formula-error scan, sheet order, simulated history boundary and decision fail-closed fields; no visual click verification"
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
