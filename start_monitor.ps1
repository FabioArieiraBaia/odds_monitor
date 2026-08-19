# Keep Odds Monitor server alive. Auto-restart on crash.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Program Files\Python311\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
$logOut = Join-Path $root "python_log.txt"
$logErr = Join-Path $root "python_err.txt"
$watchLog = Join-Path $root "watchdog.log"
$env:PYTHONUNBUFFERED = "1"

function Write-Watch([string]$msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    try { Add-Content -Path $watchLog -Value $line -Encoding UTF8 } catch {}
    Write-Host $line
}

Write-Watch "Odds Monitor watchdog root=$root python=$python"

while ($true) {
    try {
        $conns = Get-NetTCPConnection -LocalPort 8005 -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            Write-Watch "Killing leftover PID $($c.OwningProcess) on :8005"
            taskkill /PID $c.OwningProcess /T /F 2>$null | Out-Null
        }
    } catch {}

    Write-Watch "Starting app/main.py"
    $p = Start-Process -FilePath $python `
        -ArgumentList @("-u", "app\main.py") `
        -WorkingDirectory $root `
        -RedirectStandardOutput $logOut `
        -RedirectStandardError $logErr `
        -PassThru `
        -WindowStyle Hidden

    Write-Watch "PID=$($p.Id)"
    Wait-Process -Id $p.Id -ErrorAction SilentlyContinue
    $code = $p.ExitCode
    Write-Watch "Process exited code=$code - restarting in 5s"
    Start-Sleep -Seconds 5
}
