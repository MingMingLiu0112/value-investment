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
$projectionReport = $projectionDocument.report
if (
    $projectionDocument.action -ne "no_order" -or
    $null -eq $projectionReport -or
    $projectionReport.strict_pit_proven -ne $false
) {
    throw "M5 projection must remain a bounded, non-strict no_order view."
}
$projectionSchema = [string]$projectionReport.schema_version
$forbiddenAsOfContent = @()
$asOfExclusionAssertion = $null
$publicEventAssertion = $null

if ($projectionSchema -eq "registered-public-event-projection-v5") {
    if ($projectionReport.public_event_observation_as_of -ne "2026-09-28") {
        throw "Historical v5 projection must retain its 2026-09-28 cutoff."
    }
    $exclusions = @($projectionReport.as_of_exclusions)
    $quarantined = @($projectionDocument.projection.as_of_excluded_evidence)
    if ($exclusions.Count -ne 1 -or $quarantined.Count -ne 1) {
        throw "Historical v5 projection must bind one bounded as-of exclusion."
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
        throw "Historical v5 exclusion does not match its hash-bound source record."
    }
    $activeEvidenceIds = @($projectionDocument.projection.audit_evidence | ForEach-Object { $_.evidence_id })
    $activeEventIds = @($projectionDocument.projection.events | ForEach-Object { $_.event_id })
    $activeDecisionIds = @($projectionDocument.projection.audit_decisions | ForEach-Object { $_.event_id })
    if (
        $activeEvidenceIds -contains $excludedSource.evidence_id -or
        $activeEventIds -contains $exclusion.event_ids[0] -or
        $activeDecisionIds -contains $exclusion.event_ids[0]
    ) {
        throw "Future-available source remains in historical v5 evidence, events or decisions."
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
    $asOfExclusionAssertion = @{
        evidence_id = $excludedSource.evidence_id
        conservative_available_at = $excludedSource.available_at
        source_sha256 = $sourceHash
        reason = $exclusion.reason
        related_event_ids = @($exclusion.event_ids)
        absent_from_all_six_visible_product_sheets = $true
    }
} elseif ($projectionSchema -eq "registered-public-event-projection-v6") {
    $expectedPredecessorSha = "5e543f50690a71254a97ff5c39136cd2bb74d81d1e3c4d3600f023dc948487d6"
    $expectedSourceSha = "75f419502c1f5c646d15913e455889a0d8c3ff08829b12316251c747702a3781"
    $expectedWatermarkPath = "config/prospective-public-event-watermarks-v9.json"
    $expectedWatermarkSha = "fa42a7aeb365185451fd2402390b631defc01d70d6ae310b47f29ab8465c8c49"
    if (
        $projectionReport.public_event_observation_as_of -ne "2026-09-29" -or
        $projectionReport.successor_of -ne "registered-public-event-projection-v5" -or
        $projectionReport.predecessor_sha256 -ne $expectedPredecessorSha -or
        $projectionReport.source_evidence_sha256 -ne $expectedSourceSha -or
        $projectionReport.bounded_observation_watermark_path -ne $expectedWatermarkPath -or
        $projectionReport.bounded_observation_watermark_sha256 -ne $expectedWatermarkSha -or
        $projectionReport.formal_watermark_advanced -ne $false -or
        $projectionReport.valuation_or_trade_conclusion_changed -ne $false -or
        @($projectionReport.as_of_exclusions).Count -ne 0
    ) {
        throw "M5 v6 projection does not match the pinned 2026-09-29 bounded successor contract."
    }
    $watermarkPath = Join-Path $projectRoot $expectedWatermarkPath
    $watermarkSha = (Get-FileHash -LiteralPath $watermarkPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($watermarkSha -ne $expectedWatermarkSha) {
        throw "The v6 bounded observation watermark changed: $watermarkSha"
    }
    $watermarkDocument = Get-Content -LiteralPath $watermarkPath -Raw -Encoding utf8 | ConvertFrom-Json
    $observations = @($projectionReport.bounded_observations)
    $expectedSymbols = @("000333", "600887", "601088")
    if (
        $observations.Count -ne 3 -or
        (@($observations | ForEach-Object { [string]$_.symbol } | Sort-Object) -join "|") -ne
            (@($expectedSymbols | Sort-Object) -join "|")
    ) {
        throw "M5 v6 must bind exactly one current bounded observation per registered symbol."
    }
    foreach ($observation in $observations) {
        if (
            $observation.scan_from -ne "2026-09-28" -or
            $observation.scan_to -ne "2026-09-29" -or
            $observation.coverage_status -ne "SINGLE_DAY_SNAPSHOT_ONLY" -or
            $observation.retrieval_clock_attestation -ne "PROCESS_CLOCK_ONLY_UNATTESTED"
        ) {
            throw "M5 v6 observation scope/time assurance is invalid for $($observation.symbol)."
        }
        $watermarkRows = @($watermarkDocument.current_bounded_observations | Where-Object {
            $_.symbol -eq $observation.symbol -and $_.scan_to -eq "2026-09-29"
        })
        if ($watermarkRows.Count -ne 1) {
            throw "M5 v6 watermark row is missing or duplicated for $($observation.symbol)."
        }
        $watermarkRow = $watermarkRows[0]
        if (
            $watermarkRow.scan_receipt_path -ne $observation.scan_receipt_path -or
            $watermarkRow.scan_receipt_sha256 -ne $observation.scan_receipt_sha256 -or
            $watermarkRow.index_sha256 -ne $observation.index_sha256 -or
            $watermarkRow.raw_page_sha256 -ne $observation.raw_page_sha256 -or
            (@($watermarkRow.announcement_ids) -join "|") -ne (@($observation.announcement_ids) -join "|")
        ) {
            throw "M5 v6 observation does not reconcile to its pinned watermark row for $($observation.symbol)."
        }
        foreach ($boundFile in @(
            @{ path = $watermarkRow.scan_receipt_path; sha256 = $observation.scan_receipt_sha256 },
            @{ path = $watermarkRow.index_path; sha256 = $observation.index_sha256 },
            @{ path = $watermarkRow.raw_page_path; sha256 = $observation.raw_page_sha256 }
        )) {
            $boundPath = Join-Path $projectRoot $boundFile.path
            if (-not (Test-Path -LiteralPath $boundPath -PathType Leaf)) {
                throw "M5 v6 bounded evidence file is missing: $($boundFile.path)"
            }
            $boundSha = (Get-FileHash -LiteralPath $boundPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($boundSha -ne $boundFile.sha256.ToLowerInvariant()) {
                throw "M5 v6 bounded evidence hash mismatch: $($boundFile.path)"
            }
        }
        $scanReceiptPath = Join-Path $projectRoot $watermarkRow.scan_receipt_path
        $scanReceipt = Get-Content -LiteralPath $scanReceiptPath -Raw -Encoding utf8 | ConvertFrom-Json
        $pageRefs = @($scanReceipt.pagination.page_refs)
        if (
            $scanReceipt.schema_version -ne "cninfo-exact-issuer-single-day-receipt-v1" -or
            $scanReceipt.symbol -ne $observation.symbol -or
            $scanReceipt.exact_query_date_filter -ne "2026-09-28~2026-09-29" -or
            $scanReceipt.capture_status -ne "SNAPSHOT_CAPTURED_NOT_FULL_DAY_COMPLETENESS" -or
            $scanReceipt.action -ne "no_order" -or
            $pageRefs.Count -ne 1 -or
            $pageRefs[0].sha256 -ne $observation.raw_page_sha256
        ) {
            throw "M5 v6 scan receipt does not bind the exact bounded observation for $($observation.symbol)."
        }
    }
    $resolved = @($projectionReport.resolved_prior_exclusions)
    if (
        $resolved.Count -ne 1 -or
        $resolved[0].evidence_id -ne "cninfo-1225582141" -or
        $resolved[0].available_at -ne "2026-09-29" -or
        @($resolved[0].related_event_ids).Count -ne 1 -or
        $resolved[0].related_event_ids[0] -ne "midea-2026-egm-notice-1225582141"
    ) {
        throw "M5 v6 did not re-admit exactly the evidence available by its cutoff."
    }
    $mideaEvents = @($projectionDocument.projection.events | Where-Object {
        $_.event_id -eq "midea-2026-egm-notice-1225582141"
    })
    $mideaEvidenceRows = @($projectionDocument.projection.audit_evidence | Where-Object {
        $_.evidence_id -eq "cninfo-1225582141"
    })
    $mideaDecisions = @($projectionDocument.projection.audit_decisions | Where-Object {
        $_.event_id -eq "midea-2026-egm-notice-1225582141"
    })
    if (
        $mideaEvents.Count -ne 1 -or
        $mideaEvents[0].event_type -ne "MATERIAL_RISK_MONITOR" -or
        $mideaEvidenceRows.Count -ne 1 -or
        $mideaEvidenceRows[0].available_at -ne "2026-09-29" -or
        $mideaEvidenceRows[0].sha256 -ne "94629a0271834020e0a1efd417837bbd04677f226650d940b4a6d523a26e9686" -or
        $mideaDecisions.Count -ne 1 -or
        $mideaDecisions[0].visible -ne $true -or
        $mideaDecisions[0].disposition -ne "MATERIAL_RISK_MONITOR"
    ) {
        throw "M5 v6 Midea event/evidence/disposition is incomplete or upgraded unsafely."
    }
    $mideaSourcePath = Join-Path $projectRoot $mideaEvidenceRows[0].path
    if (-not (Test-Path -LiteralPath $mideaSourcePath -PathType Leaf)) {
        throw "M5 v6 hash-bound Midea original is missing: $($mideaEvidenceRows[0].path)"
    }
    $mideaSourceSha = (Get-FileHash -LiteralPath $mideaSourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($mideaSourceSha -ne $mideaEvidenceRows[0].sha256.ToLowerInvariant()) {
        throw "M5 v6 Midea original hash mismatch: $mideaSourceSha"
    }
    $activeProjectionText = $projectionDocument.projection | ConvertTo-Json -Depth 32 -Compress
    if ($activeProjectionText -match "1225584526") {
        throw "The Yili notice unavailable until 2026-09-30 leaked into the 2026-09-29 active projection."
    }
    $forbiddenAsOfContent = @("1225584526")
    $publicEventAssertion = @{
        event_id = $mideaEvents[0].event_id
        event_type = $mideaEvents[0].event_type
        evidence_id = $mideaEvidenceRows[0].evidence_id
        evidence_available_at = $mideaEvidenceRows[0].available_at
        source_url = $mideaEvidenceRows[0].source_url
        source_sha256 = $mideaSourceSha
        prior_exclusion_resolved_at_cutoff = $true
        yili_future_notice_absent_from_active_projection = $true
    }
} else {
    throw "Unsupported M5 projection schema: $projectionSchema"
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

    if ($null -ne $publicEventAssertion) {
        $eventSheet = $book.Worksheets.Item("05_事件")
        $eventHeaderRow = 0
        for ($row = 1; $row -le $eventSheet.UsedRange.Rows.Count; $row++) {
            if (
                [string]$eventSheet.Cells.Item($row, 1).Text -eq "需要持续跟踪的风险事项 | 美的集团" -and
                [string]$eventSheet.Cells.Item($row + 2, 1).Text -eq $mideaEvents[0].what_happened
            ) {
                $eventHeaderRow = $row
                break
            }
        }
        if ($eventHeaderRow -eq 0) {
            throw "The v6 Midea risk-monitor event is absent from the user-facing event page."
        }
        $eventValueRow = $eventHeaderRow + 2
        if (
            [string]$eventSheet.Cells.Item($eventValueRow, 1).Text -ne $mideaEvents[0].what_happened -or
            [string]$eventSheet.Cells.Item($eventValueRow, 2).Text -ne $mideaEvents[0].impact_area -or
            [string]$eventSheet.Cells.Item($eventValueRow, 3).Text -ne $mideaEvents[0].current_conclusion -or
            [string]$eventSheet.Cells.Item($eventValueRow, 4).Text -ne "继续观察"
        ) {
            throw "The visible Midea event card does not match its reviewed risk-monitor projection."
        }
        $evidenceCell = $eventSheet.Cells.Item($eventValueRow, 6)
        if ($evidenceCell.Hyperlinks.Count -ne 1) {
            throw "The visible Midea event card must link to exactly one audit evidence row."
        }
        $internalLink = $evidenceCell.Hyperlinks.Item(1)
        $internalTarget = [string]$internalLink.SubAddress
        if ([string]::IsNullOrWhiteSpace($internalTarget)) {
            $internalTarget = [string]$internalLink.Address
        }
        if ($internalTarget -notmatch "06_系统与审计.*!A(?<row>\d+)$") {
            throw "The Midea event evidence link must target its row in 06_系统与审计."
        }
        $auditRow = [int]$Matches["row"]
        $auditSheet = $book.Worksheets.Item("06_系统与审计")
        $auditRowValues = @()
        foreach ($value in $auditSheet.Range("A$($auditRow):P$($auditRow)").Value2) {
            $auditRowValues += [string]$value
        }
        $auditRowText = $auditRowValues -join " | "
        if (
            $auditRowText -notmatch [regex]::Escape($mideaEvidenceRows[0].evidence_id) -or
            $auditRowText -notmatch [regex]::Escape($mideaEvidenceRows[0].sha256)
        ) {
            throw "The Midea audit row does not contain the evidence identity and pinned original hash."
        }
        $cninfoLinkFound = $false
        for ($linkIndex = 1; $linkIndex -le $auditSheet.Hyperlinks.Count; $linkIndex++) {
            $sourceLink = $auditSheet.Hyperlinks.Item($linkIndex)
            if (
                [int]$sourceLink.Range.Row -eq $auditRow -and
                [string]$sourceLink.Address -eq [string]$mideaEvidenceRows[0].source_url
            ) {
                $cninfoLinkFound = $true
                break
            }
        }
        if (-not $cninfoLinkFound) {
            throw "The linked Midea audit row must expose the exact hash-verified CNINFO original URL."
        }
        $publicEventAssertion["visible_event_header"] = [string]$eventSheet.Cells.Item($eventHeaderRow, 1).Text
        $publicEventAssertion["audit_sheet_row"] = $auditRow
        $publicEventAssertion["internal_event_to_audit_link"] = $internalTarget
        $publicEventAssertion["cninfo_original_link_verified"] = $true
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
        as_of_exclusion_assertion = $asOfExclusionAssertion
        public_event_assertion = $publicEventAssertion
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        action = "no_order"
        final_user_acceptance = "NOT_PASSED"
        canonical_workbook = $true
        check_scope = "WPS read-only open/read/calculate of canonical workbook; exactly six visible product tabs with product home active, retained legacy tabs hidden without content changes, per-product-sheet frozen first column, formula-error scan, engineering-token scan and forbidden-decision scan on the five user pages, schema-specific hash-bound M5 v5 exclusion or v6 bounded-observation/event closure, future-available evidence absent from all six visible product sheets, v6 event-to-audit-to-CNINFO hyperlink verification, parked portfolio state, blocked-valuation wording, admitted H1 values and assurance boundaries, workbook hash stability"
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
