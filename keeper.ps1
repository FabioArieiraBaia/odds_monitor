$root = "C:\xampp\htdocs\odds_monitor"
$python = "C:\Program Files\Python311\python.exe"
$log = Join-Path $root "watchdog.log"
function W([string]$m) {
  $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $m"
  try { Add-Content -LiteralPath $log -Value $line -Encoding UTF8 } catch {}
}
W "keeper started pid=$PID"
while ($true) {
  Start-Sleep -Seconds 12
  $up = $false
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8005/" -UseBasicParsing -TimeoutSec 4
    if ($r.StatusCode -eq 200) { $up = $true }
  } catch {}
  if ($up) { continue }
  W "server DOWN — restarting main.py"
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'app\\main\.py|app/main\.py' } |
    ForEach-Object { taskkill /PID $_.ProcessId /T /F 2>$null }
  Start-Sleep -Seconds 3
  Start-Process -FilePath $python -ArgumentList @("-u","app\main.py") -WorkingDirectory $root `
    -RedirectStandardOutput (Join-Path $root "python_log.txt") `
    -RedirectStandardError (Join-Path $root "python_err.txt") `
    -WindowStyle Hidden
  W "start issued"
  Start-Sleep -Seconds 15
}
