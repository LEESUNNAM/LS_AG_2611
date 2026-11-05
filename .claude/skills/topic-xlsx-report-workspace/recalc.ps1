param([string]$In, [string]$Out)
# Open a workbook in Excel, recalculate everything and save a copy with stored results.
# Exit code 0 = Excel opened the file; the copy at $Out then holds computed formula values.
$ErrorActionPreference = 'Stop'
try {
  Copy-Item -LiteralPath $In -Destination $Out -Force
  $x = New-Object -ComObject Excel.Application
  $x.Visible = $false; $x.DisplayAlerts = $false
  $wb = $x.Workbooks.Open($Out)
  $wb.Application.CalculateFull()
  $wb.Save()
  $wb.Close($false)
  $x.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($x) | Out-Null
  exit 0
} catch {
  Write-Output ("ERR: " + $_.Exception.Message)
  try { $x.Quit() } catch {}
  exit 1
}
