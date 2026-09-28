param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $true)][string]$M5ProjectionPath,
    [Parameter(Mandatory = $true)][string]$M5ProjectionSha256
)
$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$before = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$expected = $ExpectedSha256.ToLowerInvariant()
if ($before -ne $expected) {
    throw "M7 product candidate changed before WPS verification: $before"
}
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "../..")).Path
$projectionPath = (Resolve-Path -LiteralPath $M5ProjectionPath).Path
$projectionHash = (Get-FileHash -LiteralPath $projectionPath).Hash.ToLowerInvariant()
if ($projectionHash -ne $M5ProjectionSha256.ToLowerInvariant()) {
    throw "M5 projection changed before WPS verification: $projectionHash"
}
$projectionDocument = Get-Content -LiteralPath $projectionPath -Raw -Encoding utf8 | ConvertFrom-Json
if (
    $projectionDocument.action -ne "no_order" -or
    $projectionDocument.report.schema_version -ne "registered-public-event-projection-v5" -or
    $projectionDocument.report.public_event_observation_as_of -ne "2026-09-28" -or
    $projectionDocument.report.strict_pit_proven -ne $false
) {
    throw "M5 projection does not prove the expected bounded non-strict as-of state."
}
$exclusions = @($projectionDocument.report.as_of_exclusions)
$quarantined = @($projectionDocument.projection.as_of_excluded_evidence)
if ($exclusions.Count -ne 1 -or $quarantined.Count -ne 1) {
    throw "M5 projection must bind one bounded as-of exclusion."
}
$exclusion = $exclusions[0]
$quarantinedRecord = $quarantined[0]
$excludedSource = $quarantinedRecord.evidence
if (
    $quarantinedRecord.reason -ne $exclusion.reason -or
    $exclusion.reason -ne "SOURCE_NOT_AVAILABLE_AS_OF_CUTOFF" -or
    $excludedSource.evidence_id -ne $exclusion.evidence_id -or
    $excludedSource.available_at -ne $exclusion.available_at -or
    $excludedSource.available_at -ne "2026-09-29" -or
    $quarantinedRecord.related_event_ids.Count -ne 1 -or
    $quarantinedRecord.related_event_ids[0] -ne $exclusion.event_ids[0]
) {
    throw "M5 as-of exclusion does not match its hash-bound source record."
}
$activeEvidenceIds = @($projectionDocument.projection.audit_evidence | ForEach-Object { $_.evidence_id })
$activeEventIds = @($projectionDocument.projection.events | ForEach-Object { $_.event_id })
$activeDecisionIds = @($projectionDocument.projection.audit_decisions | ForEach-Object { $_.event_id })
if (
    $activeEvidenceIds -contains $excludedSource.evidence_id -or
    $activeEventIds -contains $exclusion.event_ids[0] -or
    $activeDecisionIds -contains $exclusion.event_ids[0]
) {
    throw "Future-available source remains in active M5 evidence, events or decisions."
}
$sourcePath = Join-Path $projectRoot $excludedSource.path
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Hash-bound excluded source file is missing: $($excludedSource.path)"
}
$sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sourceHash -ne $excludedSource.sha256.ToLowerInvariant()) {
    throw "Hash-bound excluded source file changed: $($excludedSource.path)"
}
$forbiddenAsOfContent = @(
    $excludedSource.evidence_id,
    $excludedSource.title,
    $excludedSource.path,
    $excludedSource.sha256
) + @($exclusion.event_ids)

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
    if ($book.Worksheets.Count -lt $expectedSheets.Count) {
        throw "Canonical workbook has fewer than six product worksheets."
    }

    $visibleSheetNames = @($book.Worksheets | Where-Object { $_.Visible -eq -1 } | ForEach-Object { [string]$_.Name })
    if (($visibleSheetNames -join "|") -ne ($expectedSheets -join "|")) {
        throw "Default workbook navigation must expose exactly the six product pages."
    }
    if ([string]$book.Worksheets.Item(1).Name -ne "01_今日") {
        throw "The product home page must be the first worksheet."
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
        foreach ($needle in $forbiddenAsOfContent) {
            if ($joined -match [regex]::Escape([string]$needle)) {
                throw "Future-available evidence is visible on canonical product sheet $name."
            }
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
                $pattern = if ($word -match '^[A-Z]+$') {
                    '\b' + [regex]::Escape($word) + '\b'
                } else {
                    [regex]::Escape($word)
                }
                if ($joined -match $pattern) {
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
    if ($emptyJoined -notmatch "个性化组合分析已暂停" -or
        $emptyJoined -match "查看接入说明|尚未收到真实个人组合输入") {
        throw "Absent portfolio state must be parked without an onboarding prompt."
    }
    $visibleProductText = @()
    foreach ($name in $expectedSheets) {
        foreach ($value in $book.Worksheets.Item($name).UsedRange.Value2) {
            $visibleProductText += [string]$value
        }
    }
    $visibleProductJoined = $visibleProductText -join [Environment]::NewLine
    if ($visibleProductJoined -match "查看接入说明|后续准入所需的个人信息|尚未收到真实个人组合输入|通过受保护的私密入口") {
        throw "Visible product pages contain a private-portfolio onboarding prompt."
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
    $requiredCompanyContent = @(
        "2026H1 营业收入：260042490 千元；可用日 2026-08-30T00:00:00+08:00",
        "2026H1 归母净利润：26446037 千元；可用日 2026-08-30T00:00:00+08:00",
        "2026H1 经营活动现金流净额：37552090 千元；可用日 2026-08-30T00:00:00+08:00",
        "2026H1 营业收入：189338 百万元",
        "2026H1 归母净利润：28715 百万元",
        "2026H1 经营活动现金流净额：54664 百万元",
        "2026-08-30T00:00:00+08:00",
        "未经审计；注册会计师实施有限审阅，未发表审计意见。"
    )
    foreach ($required in $requiredCompanyContent) {
        if ($companyJoined -notmatch [regex]::Escape($required)) {
            throw "Company page is missing newly admitted public fact or its assurance boundary: $required"
        }
    }

    $sheetCount = $book.Worksheets.Count
    $visibleCount = @($book.Worksheets | Where-Object { $_.Visible -eq -1 }).Count
    $hiddenCount = @($book.Worksheets | Where-Object { $_.Visible -ne -1 }).Count
    $book.Close($false)
    $book = $null
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $before) {
        throw "Read-only check changed the M7 product candidate."
    }
    $receipt = @{
        status = "passed"
        mode = "m7_product_ux_read_only_canonical"
        workbook = $path
        sha256 = $before
        read_only = $true
        sheets = $sheetCount
        visible_sheets = $visibleCount
        hidden_sheets = $hiddenCount
        user_sheets = $userSheets
        secondary_sheets = @("06_系统与审计")
        sheet_checks = $sheetChecks
        application = "WPS Office"
        application_com_name = [string]$app.Name
        application_path = $applicationPath
        company_content_assertions = $requiredCompanyContent
        m5_projection = @{
            path = $projectionPath
            sha256 = $projectionHash
            schema_version = $projectionDocument.report.schema_version
            observation_as_of = $projectionDocument.report.public_event_observation_as_of
            strict_pit_proven = $projectionDocument.report.strict_pit_proven
        }
        as_of_exclusion_assertion = @{
            evidence_id = $excludedSource.evidence_id
            conservative_available_at = $excludedSource.available_at
            source_sha256 = $sourceHash
            reason = $exclusion.reason
            related_event_ids = @($exclusion.event_ids)
            absent_from_all_six_visible_product_sheets = $true
        }
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        action = "no_order"
        final_user_acceptance = "NOT_PASSED"
        canonical_workbook = $true
        check_scope = "WPS read-only open/read/calculate of canonical workbook; exactly six visible product tabs with product home active, retained legacy tabs hidden without content changes, per-product-sheet frozen first column, formula-error scan, engineering-token scan and forbidden-decision scan on the five user pages, hash-bound M5 as-of exclusion closure, excluded future evidence absent from all six visible product sheets, parked portfolio state, blocked-valuation wording, admitted H1 values and assurance boundaries, workbook hash stability"
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
