# Ask the model that Power BI Desktop has open for the dashboard numbers, and compare them with
# data/expected.json (computed in Python from the same CSV by make_data.py).
#
#   1. Open SalesDemo.pbip in Power BI Desktop and refresh it.
#   2. powershell -ExecutionPolicy Bypass -File check_model.ps1
#
# Uses Windows PowerShell 5.1 and the query client that ships with Power BI Desktop. Read-only.
$ErrorActionPreference = 'Stop'
[void][Reflection.Assembly]::LoadFrom('C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll')

$portFile = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces" -Recurse -Filter msmdsrv.port.txt |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $portFile) { throw 'Power BI Desktop is not running with a model open.' }
$port = (Get-Content $portFile.FullName -Encoding Unicode | Out-String).Trim()
$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection "Data Source=localhost:$port"
$conn.Open()

function Query([string]$dax) {
    $cmd = $conn.CreateCommand(); $cmd.CommandText = $dax
    $r = $cmd.ExecuteReader(); $rows = @()
    while ($r.Read()) { $row = @(); for ($i = 0; $i -lt $r.FieldCount; $i++) { $row += $r.GetValue($i) }; $rows += , $row }
    $r.Close(); return , $rows
}

$exp = Get-Content (Join-Path $PSScriptRoot 'data\expected.json') -Raw | ConvertFrom-Json
$script:fails = 0; $script:checks = 0
function Check([string]$what, $got, $want) {
    $script:checks++
    if ([math]::Abs([double]$got - [double]$want) -gt 0.005) { $script:fails++; Write-Output "FAIL $what  model=$got  expected=$want" }
}

$t = (Query 'EVALUATE ROW("rev", [Total Revenue], "m", [Gross Margin %], "o", [Orders], "aov", [Avg Order Value], "rows", COUNTROWS(sales))')[0]
Check 'Total Revenue' ([math]::Round($t[0], 2)) $exp.revenue
Check 'Gross Margin %' ([math]::Round(100 * $t[1], 1)) $exp.gross_margin_pct
Check 'Orders' $t[2] $exp.orders
Check 'Avg Order Value' ([math]::Round($t[3], 2)) $exp.avg_order_value
Check 'Rows' $t[4] $exp.rows

foreach ($pair in @(@('Region', 'revenue_by_region'), @('Channel', 'revenue_by_channel'), @('Category', 'revenue_by_category'))) {
    foreach ($row in (Query "EVALUATE SUMMARIZECOLUMNS(sales[$($pair[0])], ""r"", [Total Revenue])")) {
        Check "$($pair[0]) $($row[0])" ([math]::Round($row[1], 2)) $exp.($pair[1]).($row[0])
    }
}
foreach ($row in (Query 'EVALUATE SUMMARIZECOLUMNS(sales[Month], "r", [Total Revenue])')) {
    $key = ([datetime]$row[0]).ToString('yyyy-MM')
    Check "Month $key" ([math]::Round($row[1], 2)) $exp.revenue_by_month.$key
}
$conn.Close()
Write-Output "$($script:checks - $script:fails) of $($script:checks) checks match data/expected.json"
if ($script:fails) { exit 1 }
