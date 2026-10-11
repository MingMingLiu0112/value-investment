param([Parameter(Mandatory)][string]$WorkbookPath,[Parameter(Mandatory)][string]$ExpectedSha256,[Parameter(Mandatory)][string]$ReceiptPath)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new()
[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$OutputEncoding=[Console]::OutputEncoding
$before=(Get-FileHash -LiteralPath $WorkbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($before -ne $ExpectedSha256 -or (Test-Path -LiteralPath $ReceiptPath)) {throw 'Navigation source or output conflict'}
$application=$null; $workbook=$null; $previousBook=$null; $previousSheet=$null; $initialCount=0
$verified=[Collections.Generic.List[object]]::new()
try {
    $application=New-Object -ComObject ket.Application
    if ([string]$application.Path -notmatch 'WPS') {throw 'Expected WPS'}
    $initialCount=$application.Workbooks.Count
    if ($initialCount -gt 0) {$previousBook=$application.ActiveWorkbook; $previousSheet=$application.ActiveSheet}
    foreach ($existing in $application.Workbooks) {
        if ([string]$existing.FullName -eq [IO.Path]::GetFullPath($WorkbookPath)) {throw 'Workbook is already open; not closing user workbook'}
    }
    $workbook=$application.Workbooks.Open($WorkbookPath,0,$true)
    if (-not $workbook.ReadOnly) {throw 'Read-only verification required'}
    foreach ($name in @('01_今日','02_机会','决策过程','03_公司','04_我的组合','05_事件','06_系统与审计')) {
        $sheet=$workbook.Worksheets.Item($name)
        $sheet.Activate()
        foreach ($link in $sheet.Hyperlinks) {
            $target=[string]$link.SubAddress
            if (-not $target) {continue}
            if ($target -notmatch "^'?([^']+)'?!([A-Z]+)([0-9]+)$") {throw "Unsupported internal destination: $target"}
            $expectedSheet=$Matches[1]; $expectedCell=$Matches[2]+$Matches[3]
            $sheet.Activate(); $link.Follow()
            if ([string]$application.ActiveSheet.Name -ne $expectedSheet -or ([string]$application.ActiveCell.Address()).Replace('$','') -ne $expectedCell) {throw 'Internal navigation differs'}
            $verified.Add(@{sheet=$name; target=$target; followed=$true})
        }
    }
    if ($verified.Count -lt 7) {throw 'Expected navigation links missing'}
    if ((Get-FileHash -LiteralPath $WorkbookPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $before) {throw 'Workbook changed during read-only navigation'}
    @{action='no_order';status='PASS';workbook_sha256=$before;read_only=$true;links=$verified.ToArray()} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ReceiptPath -Encoding utf8
} finally {
    if ($null -ne $workbook) {$workbook.Close($false)}
    if ($null -ne $previousBook) {$previousBook.Activate();if ($null -ne $previousSheet) {$previousSheet.Activate()}}
    if ($null -ne $application -and $initialCount -eq 0 -and $application.Workbooks.Count -eq 0) {$application.Quit()}
}
