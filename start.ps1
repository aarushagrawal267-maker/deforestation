<#
.SYNOPSIS
  Start Sylva: backend API (http://localhost:8000), job worker, and frontend (http://localhost:5173).

.DESCRIPTION
      powershell -ExecutionPolicy Bypass -File .\start.ps1 [-NoBrowser] [-Preview]

  -Preview serves the production build (npm run build) instead of the Vite dev server.
  Process IDs are recorded in .run\pids.json so stop.ps1 can stop exactly these processes.
  Logs are written to logs\.
#>
[CmdletBinding()]
param([switch]$NoBrowser, [switch]$Preview)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPy = Join-Path $Backend ".venv\Scripts\python.exe"
$Logs = Join-Path $Root "logs"
$RunDir = Join-Path $Root ".run"
$PidFile = Join-Path $RunDir "pids.json"
New-Item -ItemType Directory -Force -Path $Logs, $RunDir | Out-Null

if (-not (Test-Path $VenvPy)) { Write-Host "Run setup.ps1 first (backend\.venv not found)." -ForegroundColor Red; exit 1 }
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) { Write-Host "Run setup.ps1 first (frontend\node_modules not found)." -ForegroundColor Red; exit 1 }

if (Test-Path $PidFile) {
    $old = Get-Content $PidFile -Raw | ConvertFrom-Json
    $alive = @($old.PSObject.Properties | Where-Object { Get-Process -Id $_.Value -ErrorAction SilentlyContinue })
    if ($alive.Count -gt 0) { Write-Host "Sylva appears to be running already (see .run\pids.json). Run stop.ps1 first." -ForegroundColor Yellow; exit 1 }
}

function Test-PortBusy([int]$port) {
    try { return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) } catch { return $false }
}
foreach ($p in 8000, 5173) {
    if (Test-PortBusy $p) { Write-Host "Port $p is already in use. Stop the program using it (or run stop.ps1) and retry." -ForegroundColor Red; exit 1 }
}

$env:PYTHONUNBUFFERED = "1"
Write-Host "Starting backend API on http://localhost:8000 ..." -ForegroundColor Green
$api = Start-Process -FilePath $VenvPy -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $Backend -RedirectStandardOutput (Join-Path $Logs "backend.log") -RedirectStandardError (Join-Path $Logs "backend.err.log") `
    -WindowStyle Hidden -PassThru

Write-Host "Starting job worker ..." -ForegroundColor Green
$worker = Start-Process -FilePath $VenvPy -ArgumentList "-m", "app.jobs.worker" `
    -WorkingDirectory $Backend -RedirectStandardOutput (Join-Path $Logs "worker.log") -RedirectStandardError (Join-Path $Logs "worker.err.log") `
    -WindowStyle Hidden -PassThru

$vite = Join-Path $Frontend "node_modules\vite\bin\vite.js"
$viteArgs = @($vite, "--port", "5173", "--strictPort", "--host", "127.0.0.1")
if ($Preview) {
    Write-Host "Building frontend ..." -ForegroundColor Green
    Push-Location $Frontend; & npm.cmd run build; Pop-Location
    $viteArgs = @($vite, "preview", "--port", "5173", "--strictPort", "--host", "127.0.0.1")
}
Write-Host "Starting frontend on http://localhost:5173 ..." -ForegroundColor Green
$web = Start-Process -FilePath "node" -ArgumentList $viteArgs -WorkingDirectory $Frontend `
    -RedirectStandardOutput (Join-Path $Logs "frontend.log") -RedirectStandardError (Join-Path $Logs "frontend.err.log") `
    -WindowStyle Hidden -PassThru

@{ backend = $api.Id; worker = $worker.Id; frontend = $web.Id } | ConvertTo-Json | Set-Content -Encoding UTF8 $PidFile

function Wait-Url([string]$url, [int]$timeoutSec) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try { $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { return $true } } catch { }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

if (-not (Wait-Url "http://127.0.0.1:8000/api/health" 90)) {
    Write-Host "Backend did not become healthy. See logs\backend.err.log" -ForegroundColor Red
    & (Join-Path $Root "stop.ps1"); exit 1
}
if (-not (Wait-Url "http://127.0.0.1:5173/" 90)) {
    Write-Host "Frontend did not start. See logs\frontend.err.log" -ForegroundColor Red
    & (Join-Path $Root "stop.ps1"); exit 1
}

Write-Host ""
Write-Host "Sylva is running:" -ForegroundColor Cyan
Write-Host "   Frontend   http://localhost:5173"
Write-Host "   Backend    http://localhost:8000"
Write-Host "   API docs   http://localhost:8000/docs"
Write-Host "   Logs       $Logs"
Write-Host "Stop with:  powershell -ExecutionPolicy Bypass -File .\stop.ps1" -ForegroundColor Gray
if (-not $NoBrowser) { Start-Process "http://localhost:5173" }
