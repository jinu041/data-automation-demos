# Exports cell ranges of a workbook to PDF with Excel (for screenshots). The workbook is opened read-only and not saved.
# Usage: pwsh -File export_ranges.ps1 <xlsx> <outdir> "Sheet!A1:N13" "Dashboard!A1:F18" ...
param([Parameter(Mandatory)][string]$Xlsx, [Parameter(Mandatory)][string]$Out, [Parameter(ValueFromRemainingArguments)][string[]]$Ranges)
$ErrorActionPreference = 'Stop'
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false
$xl.DisplayAlerts = $false
try {
    $wb = $xl.Workbooks.Open((Resolve-Path $Xlsx).Path, 0, $true)
    foreach ($r in $Ranges) {
        $sheet, $addr = $r.Split('!')
        $ws = $wb.Worksheets.Item($sheet)
        $ws.PageSetup.Orientation = 2          # landscape
        $ws.PageSetup.Zoom = $false
        $ws.PageSetup.FitToPagesWide = 1
        $ws.PageSetup.FitToPagesTall = 1
        $ws.PageSetup.PrintArea = $addr
        $pdf = Join-Path (Resolve-Path $Out).Path ($sheet + '.pdf')
        $ws.ExportAsFixedFormat(0, $pdf)
        "exported $sheet $addr"
    }
    $wb.Close($false)
}
finally {
    $xl.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
