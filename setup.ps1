<#
.SYNOPSIS
  Prepare the Sylva environment on Windows (Python venv, PyTorch, backend and frontend dependencies, database).

.DESCRIPTION
  Run once from the repository root:
      powershell -ExecutionPolicy Bypass -File .\setup.ps1

  Options:
      -Cpu                Force the CPU build of PyTorch even if an NVIDIA GPU is present.
      -Cuda               Force a CUDA build of PyTorch (requires an NVIDIA GPU + recent driver).
      -WithSampleData     Download two real Sentinel-2 observations of the default AOI (~80 MB).
      -WithTrainingData   Download the training regions (real Sentinel-2 + reference labels, ~1 GB).
      -SkipFrontend       Do not install frontend packages.

  The script never starts model training and never downloads whole satellite scenes.
#>
[CmdletBinding()]
param(
    [switch]$Cpu,
    [switch]$Cuda,
    [switch]$WithSampleData,
    [switch]$WithTrainingData,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPy = Join-Path $Backend ".venv\Scripts\python.exe"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Green }
function Info($msg) { Write-Host "    $msg" -ForegroundColor Gray }
function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- Python
Step "Checking Python (3.11 - 3.13 required)"
$PyCmd = $null
foreach ($v in @("3.12", "3.13", "3.11")) {
    try {
        $out = & py "-$v" --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { $PyCmd = @("py", "-$v"); Info "Found $out via py launcher"; break }
    } catch { }
}
if (-not $PyCmd) {
    try {
        $out = & python --version 2>$null
        if ($out -match "Python 3\.(11|12|13)\.") { $PyCmd = @("python"); Info "Found $out" }
    } catch { }
}
if (-not $PyCmd) {
    Fail "Python 3.11-3.13 not found. Install it with:  winget install Python.Python.3.12   (then reopen PowerShell)"
}

# ---------------------------------------------------------------- Node.js
if (-not $SkipFrontend) {
    Step "Checking Node.js (20 or newer required)"
    try { $nodeV = (& node --version) 2>$null } catch { $nodeV = $null }
    if (-not $nodeV) { Fail "Node.js not found. Install it with:  winget install OpenJS.NodeJS.LTS   (then reopen PowerShell)" }
    $major = [int]($nodeV.TrimStart("v").Split(".")[0])
    if ($major -lt 20) { Fail "Node.js $nodeV is too old; install Node 20+ (winget install OpenJS.NodeJS.LTS)" }
    Info "Found Node.js $nodeV"
}

# ---------------------------------------------------------------- venv
Step "Creating Python virtual environment (backend\.venv)"
if (-not (Test-Path $VenvPy)) {
    $exe = $PyCmd[0]
    $pyArgs = @()
    if ($PyCmd.Count -gt 1) { $pyArgs += $PyCmd[1] }
    & $exe @pyArgs -m venv (Join-Path $Backend ".venv")
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment" }
} else { Info "Already exists" }
& $VenvPy -m pip install --upgrade pip wheel --quiet
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed (check internet/proxy settings)" }

# ---------------------------------------------------------------- PyTorch
Step "Installing PyTorch"
$hasNvidia = $false
try { & nvidia-smi -L 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $hasNvidia = $true } } catch { }
$wantCuda = $Cuda -or ($hasNvidia -and -not $Cpu)
$torchOk = $false
if ($wantCuda) {
    foreach ($cu in @("cu132", "cu126")) {
        Info "Trying CUDA build ($cu)..."
        & $VenvPy -m pip install torch --index-url "https://download.pytorch.org/whl/$cu" --quiet
        if ($LASTEXITCODE -eq 0) {
            $ok = & $VenvPy -c "import torch; print(torch.cuda.is_available())"
            if ($ok -match "True") { $torchOk = $true; Info "CUDA PyTorch installed and a GPU is usable"; break }
            Info "CUDA build installed but no usable GPU/driver; trying next option"
        }
    }
    if (-not $torchOk) { Info "Falling back to the CPU build" }
}
if (-not $torchOk) {
    & $VenvPy -m pip install torch --index-url "https://download.pytorch.org/whl/cpu" --quiet --force-reinstall
    if ($LASTEXITCODE -ne 0) { Fail "PyTorch installation failed" }
    Info "CPU PyTorch installed"
}

# ---------------------------------------------------------------- backend deps
Step "Installing backend dependencies (GDAL is bundled with the rasterio wheel)"
& $VenvPy -m pip install -r (Join-Path $Backend "requirements-dev.txt") --quiet
if ($LASTEXITCODE -ne 0) { Fail "Backend dependency installation failed" }

# ---------------------------------------------------------------- frontend deps
if (-not $SkipFrontend) {
    Step "Installing frontend dependencies (npm ci)"
    Push-Location $Frontend
    try {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { Fail "npm ci failed" }
    } finally { Pop-Location }
}

# ---------------------------------------------------------------- config + database
Step "Configuration and database"
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root ".env.example") $envFile
    Info "Created .env from .env.example (edit it to add optional CDSE credentials)"
} else { Info ".env already exists (left unchanged)" }
New-Item -ItemType Directory -Force -Path (Join-Path $Root "data"), (Join-Path $Root "logs"), (Join-Path $Root ".run") | Out-Null
Push-Location $Backend
try {
    & $VenvPy -c "from app.db.init import init_db; init_db(); print('database ready')"
    if ($LASTEXITCODE -ne 0) { Fail "Database initialisation failed" }

    # ------------------------------------------------------------ smoke check
    Step "Smoke check"
    & $VenvPy -m forestwatch.cli doctor
    if ($LASTEXITCODE -ne 0) { Fail "Smoke check failed" }

    if ($WithSampleData) {
        Step "Downloading sample observations for the default AOI (AOI window only)"
        & $VenvPy -m forestwatch.cli sample-data
        if ($LASTEXITCODE -ne 0) { Write-Host "Sample data download failed; you can add observations later in the Image Explorer." -ForegroundColor Yellow }
    }
    if ($WithTrainingData) {
        Step "Building training regions (real Sentinel-2 + WorldCover/Hansen labels)"
        & $VenvPy -m forestwatch.cli build-regions
    }
} finally { Pop-Location }

Step "Setup complete"
Write-Host "    Start Sylva with:   powershell -ExecutionPolicy Bypass -File .\start.ps1" -ForegroundColor Cyan
Write-Host "    Training is never started automatically: use the Model Laboratory page." -ForegroundColor Gray
