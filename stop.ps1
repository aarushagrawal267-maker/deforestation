<#
.SYNOPSIS
  Stop the Sylva processes started by start.ps1 (backend, worker, frontend).

.DESCRIPTION
      powershell -ExecutionPolicy Bypass -File .\stop.ps1

  Stops the process trees recorded in .run\pids.json. As a fallback it looks for
  processes listening on ports 8000/5173 or running the Sylva worker, and only stops
  them if their command line belongs to Sylva (uvicorn app.main, app.jobs.worker, vite).
  A running training job is interrupted; its last completed epoch checkpoint is kept.
#>
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root ".run\pids.json"
$stopped = 0

function Stop-Tree([int]$procId, [string]$label) {
    if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
        & taskkill.exe /PID $procId /T /F 2>&1 | Out-Null
        Write-Host "Stopped $label (PID $procId)"
        $script:stopped++
    }
}

if (Test-Path $PidFile) {
    $pids = Get-Content $PidFile -Raw | ConvertFrom-Json
    foreach ($prop in $pids.PSObject.Properties) { Stop-Tree ([int]$prop.Value) $prop.Name }
    Remove-Item $PidFile -Force
}

# Fallback: only processes whose command line is clearly Sylva's
$patterns = @("uvicorn app.main:app", "app.jobs.worker", "vite.js")
try {
    $procs = Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $cl = $_.CommandLine
        $cl -and ($patterns | Where-Object { $cl -like "*$_*" }) -and ($cl -like "*$Root*" -or $cl -like "*app.main:app*" -or $cl -like "*app.jobs.worker*")
    }
    foreach ($p in $procs) { Stop-Tree ([int]$p.ProcessId) $p.Name }
} catch { }

foreach ($port in 8000, 5173) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
            if ($proc -and ($patterns | Where-Object { $proc.CommandLine -like "*$_*" })) { Stop-Tree ([int]$c.OwningProcess) "port $port" }
            elseif ($proc) { Write-Host "Port $port is used by another program ($($proc.Name)); not stopping it." -ForegroundColor Yellow }
        }
    } catch { }
}

if ($stopped -eq 0) { Write-Host "No running Sylva processes found." } else { Write-Host "Sylva stopped." -ForegroundColor Green }
