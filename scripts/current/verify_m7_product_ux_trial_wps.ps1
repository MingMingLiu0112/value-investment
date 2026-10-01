param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256
)
$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$path = (Resolve-Path -LiteralPath $WorkbookPath).Path
$before = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
if ($before -ne $ExpectedSha256.ToLowerInvariant()) {
    throw "M7 product trial changed before WPS verification: $before"
}

$primarySheets = @("01_今日", "02_机会", "03_公司", "04_我的组合", "05_事件")
$userSheets = @("01_今日", "02_机会", "决策过程", "03_公司", "04_我的组合", "05_事件")
$allSheets = @($userSheets + @("06_系统与审计"))
$forbiddenTokens = @(
    "action=no_order",
    "BLOCKED",
    "NOT_READY",
    "UNKNOWN",
    "SHA256",
    "SHA-256",
    "TEXT_EXTRACTED_NOT_SEMANTICALLY_VERIFIED",
    "RESEARCH_",
    "估值批准为 false",
    "runtime/",
    "PIT",
    "unknown",
    "issuer-specific beta",
    "CNY",
    "false"
)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$outputRoot = (Resolve-Path -LiteralPath $OutputDirectory).Path
$receiptFullPath = if ([IO.Path]::IsPathRooted($ReceiptPath)) {
    $ReceiptPath
} else {
    Join-Path (Get-Location).Path $ReceiptPath
}

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
            throw "M7 product trial is already open; verification will not reuse it."
        }
    }
    $book = $app.Workbooks.Open($path, 0, $true)
    if (-not $book.ReadOnly) {
        throw "M7 product trial must open read-only."
    }

    $sheetChecks = [ordered]@{}
    foreach ($sheetName in $allSheets) {
        $sheet = $book.Worksheets.Item($sheetName)
        $sheet.Activate()
        $sheet.Calculate()
        $values = @($sheet.UsedRange.Value2)
        $visibleText = ($values | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
        foreach ($value in $values) {
            if ($value -is [string] -and $value -match "^#(REF!|DIV/0!|VALUE!|NAME\?|N/A)$") {
                throw "Formula error on $sheetName"
            }
        }
        if ($userSheets -contains $sheetName) {
            foreach ($token in $forbiddenTokens) {
                if ($visibleText.Contains($token)) {
                    throw "User page $sheetName exposes internal token $token"
                }
            }
        }
        $pdfPath = Join-Path $outputRoot ($sheetName + ".pdf")
        if (Test-Path -LiteralPath $pdfPath) {
            throw "WPS review output already exists: $pdfPath"
        }
        $sheet.ExportAsFixedFormat(0, $pdfPath)
        $sheetChecks[$sheetName] = @{
            used_range = [string]$sheet.UsedRange.Address($false, $false)
            pdf = $pdfPath
            pdf_sha256 = (Get-FileHash -LiteralPath $pdfPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }

    $after = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($after -ne $before) {
        throw "Read-only WPS verification changed the workbook hash."
    }
    $receipt = @{
        schema_version = "m7-product-ux-trial-wps-receipt-v1"
        status = "passed"
        mode = "m7_product_ux_read_only_trial"
        workbook = $path
        sha256 = $before
        workbook_sha256 = $before
        readonly_open = "PASS"
        read_only = $true
        application = "WPS Office"
        application_com_name = [string]$app.Name
        application_path = $applicationPath
        primary_sheets = $primarySheets
        user_facing_sheets = $userSheets
        secondary_sheets = @("06_系统与审计")
        sheets = $sheetChecks
        forbidden_tokens_checked_on_user_pages = $forbiddenTokens
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        canonical_written = $false
        action = "no_order"
        final_user_acceptance = "NOT_PASSED"
    }
    $receipt | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $receiptFullPath -Encoding utf8
    $receipt | ConvertTo-Json -Depth 6 -Compress
}
finally {
    if ($null -ne $book) { $book.Close($false) }
    if ($null -ne $app -and $initialCount -eq 0 -and $app.Workbooks.Count -eq 0) { $app.Quit() }
}
