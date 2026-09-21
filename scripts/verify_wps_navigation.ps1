param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$candidatePath = (Resolve-Path -LiteralPath $WorkbookPath).Path
$application = $null
$book = $null
$previousBook = $null
$previousSheet = $null
$initialCount = -1
$checks = [Collections.Generic.List[object]]::new()
try {
    $application = New-Object -ComObject 'ket.Application'
    $initialCount = $application.Workbooks.Count
    if ($initialCount -gt 0) {
        $previousBook = $application.ActiveWorkbook
        $previousSheet = $application.ActiveSheet
        foreach ($openBook in $application.Workbooks) {
            if ([string]$openBook.FullName -eq $candidatePath) {
                throw 'This workbook is already open; verification will not close or reuse the existing workbook.'
            }
        }
    }
    $book = $application.Workbooks.Open($candidatePath, 0, $true)
    if (-not $book.ReadOnly) {
        $book = $null
        throw 'WPS verification must use a read-only candidate; an existing editable workbook will not be closed.'
    }
    $samples = @(
        @('00_首页Dashboard', 'A4'), @('00_首页Dashboard', 'D4'),
        @('00_首页Dashboard', 'G8'), @('00_首页Dashboard', 'G9'),
        @('00_首页Dashboard', 'G18'), @('00_首页Dashboard', 'G19'),
        @('00_首页Dashboard', 'G21'), @('00_首页Dashboard', 'G23'), @('00_公司总览', 'F4'),
        @('00_公司总览', 'G4'), @('00_公司总览', 'H4'),
        @('00_待完成公司', 'G4')
    )
    foreach ($sample in $samples) {
        $sheet = $book.Worksheets.Item($sample[0])
        $sheet.Activate()
        $link = $sheet.Range($sample[1]).Hyperlinks.Item(1)
        if ($link.Address) { throw ('Internal navigation has an external address: ' + $link.Address) }
        $location = [string]$link.SubAddress
        if ($location -notmatch "^'(.+)'!([A-Z]+)([0-9]+)$") { throw ('Invalid SubAddress: ' + $location) }
        $expectedSheet = $Matches[1].Replace("''", "'")
        $expectedRow = [int]$Matches[3]
        $link.Follow()
        $actualSheet = [string]$application.ActiveSheet.Name
        $actualRow = [int]$application.ActiveCell.Row
        if ($actualSheet -ne $expectedSheet -or $actualRow -ne $expectedRow) {
            throw "WPS did not follow $location (observed $actualSheet row $actualRow)"
        }
        $checks.Add(@{ source = ($sample -join '!'); destination = $location; followed = $true })
    }
    $positions = $book.Worksheets.Item('05_仓位管理')
    $brief = $book.Worksheets.Item('00_公司总览')
    if ([string]$brief.Range('A1').Value2 -eq '贵州茅台 | 单公司研究卡') {
        $brief.Calculate()
        $labels = @{}
        for ($row = 1; $row -le $brief.UsedRange.Rows.Count; $row++) {
            $label = [string]$brief.Cells.Item($row, 1).Value2
            if ($label) { $labels[$label] = $row }
        }
        $requiredLabels = @('归母权益（元）', '扣非TTM（元）', '已披露股数（股）', '归档价格（元）', '每股扣非TTM（元）', '参考市盈率（倍）', '账面权益/股（元）', '主模型 / 价格要求', '资本配置 / 治理', '现金 / 低谷韧性')
        foreach ($label in $requiredLabels) {
            if (-not $labels.ContainsKey($label)) { throw "Research-card label missing: $label" }
        }
        $equity = [double]$brief.Cells.Item($labels['归母权益（元）'], 3).Value2
        $profit = [double]$brief.Cells.Item($labels['扣非TTM（元）'], 3).Value2
        $shares = [double]$brief.Cells.Item($labels['已披露股数（股）'], 3).Value2
        $price = [double]$brief.Cells.Item($labels['归档价格（元）'], 3).Value2
        if ($shares -le 0 -or $profit -le 0 -or $price -le 0) { throw 'Invalid research-card inputs' }
        $expected = @{
            $brief.Cells.Item($labels['每股扣非TTM（元）'], 3).Address($false, $false) = ($profit / $shares)
            $brief.Cells.Item($labels['参考市盈率（倍）'], 3).Address($false, $false) = ($price / ($profit / $shares))
            $brief.Cells.Item($labels['账面权益/股（元）'], 3).Address($false, $false) = ($equity / $shares)
        }
        foreach ($address in $expected.Keys) {
            $actual = $brief.Range($address).Value2
            if ($actual -isnot [double] -or [Math]::Abs($actual - $expected[$address]) -gt 0.000001) {
                throw "Research-card formula mismatch at $address"
            }
            $checks.Add(@{ source = "00_公司总览!$address"; calculated_value = $actual; formula_verified = $true })
        }
        $coverQuote = [string]$book.Worksheets.Item('00_首页Dashboard').Range('C7').Value2
        $briefQuote = [string]$brief.Cells.Item($labels['主模型 / 价格要求'], 3).Value2
        $coverDate = $coverQuote.Substring(0, 10)
        if ($briefQuote -notmatch [regex]::Escape($coverDate)) { throw 'Research quote dates disagree' }
        $capitalText = [string]$brief.Cells.Item($labels['资本配置 / 治理'], 3).Value2
        if ($capitalText -notmatch '3,927,585' -or $capitalText -notmatch '92.06亿元' -or $capitalText -notmatch '不证明实际价格公允') {
            throw 'Research-card capital-allocation conclusion is incomplete'
        }
        $resilienceText = [string]$brief.Cells.Item($labels['现金 / 低谷韧性'], 3).Value2
        if ($resilienceText -notmatch '469.54亿元' -or $resilienceText -notmatch '254.26亿元' -or $resilienceText -notmatch '不称无债或低谷安全') {
            throw 'Research-card resilience conclusion is incomplete'
        }
        if (-not $labels.ContainsKey('当前交付边界')) { throw 'Research-card delivery-boundary label is missing' }
        $deliveryText = [string]$brief.Cells.Item($labels['当前交付边界'], 3).Value2
        if ($deliveryText -ne 'R0研究卡与P1研究日条件估值准入已通过；正式合理价、模拟准入和实盘指令仍未通过。') {
            throw 'Research-card R0 delivery boundary is incomplete'
        }
        $checks.Add(@{ source = '00_公司总览!当前交付边界'; r0_delivery_boundary_verified = $true })
    }
    $positions.Calculate()
    $formula = [string]$positions.Range('B5').Formula
    $value = $positions.Range('B5').Value2
    if ($formula -ne '=SUM(G10:G100)' -or $value -isnot [double]) {
        throw 'WPS did not calculate the retained holdings summary as a numeric value'
    }
    $visible = @()
    foreach ($sheet in $book.Worksheets) {
        if ($sheet.Visible -eq -1) { $visible += [string]$sheet.Name }
    }
    $receipt = @{
        status = 'passed'; application = [string]$application.Name; automation_progid = 'ket.Application'
        wps_process_paths = @(Get-Process -Name et -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Path -Unique)
        checked_at = [DateTimeOffset]::UtcNow.ToString('o'); workbook = $candidatePath
        read_only = $true; checks = $checks; visible_sheets = $visible
        retained_formula = $formula; calculated_value = $value
        note = 'Actual WPS COM navigation and calculation; the candidate was not saved.'
    }
    $receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReceiptPath -Encoding utf8
    $receipt | ConvertTo-Json -Depth 6 -Compress
}
finally {
    if ($null -ne $book) { $book.Close($false) }
    if ($null -ne $previousBook) {
        try { $previousBook.Activate(); $previousSheet.Activate() } catch { }
    }
    if ($null -ne $application -and $initialCount -eq 0 -and $application.Workbooks.Count -eq 0) {
        $application.Quit()
    }
}
