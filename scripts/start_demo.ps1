<#
.SYNOPSIS
    Start the Kratos Intelligence Platform demo — FastAPI backend + Vite dashboard.

.DESCRIPTION
    Launches three processes:
      1. uvicorn serving src/demo_api.py on $env:DEMO_API_PORT      (default 8002)
      2. uvicorn serving src/obs_api.py  on $env:OBS_API_PORT       (default 8003)
      3. npm run dev  inside dashboard/                              (default port 5173)

    Both processes run in separate windows.  Press Ctrl+C in this window (or
    close either child window) to stop.

.EXAMPLE
    .\scripts\start_demo.ps1
    .\scripts\start_demo.ps1 -ApiPort 8003 -DashPort 5174
#>

param (
    [int]    $ApiPort   = if ($env:DEMO_API_PORT) { [int]$env:DEMO_API_PORT } else { 8002 },
    [int]    $ObsPort   = if ($env:OBS_API_PORT)  { [int]$env:OBS_API_PORT  } else { 8003 },
    [int]    $DashPort  = 5173,
    [string] $VenvDir   = "venv311",
    [switch] $NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
$Root       = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root "$VenvDir\Scripts\python.exe"
$DashDir    = Join-Path $Root "dashboard"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Python venv not found at: $VenvPython`nRun 'python -m venv $VenvDir && pip install -r requirements.txt' first."
    exit 1
}
if (-not (Test-Path (Join-Path $DashDir "package.json"))) {
    Write-Error "Dashboard package.json not found at: $DashDir"
    exit 1
}

# ---------------------------------------------------------------------------
# Start Demo API (uvicorn)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Starting Demo API on port $ApiPort ..." -ForegroundColor Cyan

$ApiArgs = @(
    "-m", "uvicorn",
    "src.demo_api:app",
    "--host", "127.0.0.1",
    "--port", "$ApiPort",
    "--reload",
    "--log-level", "info"
)

$ApiProc = Start-Process `
    -FilePath $VenvPython `
    -ArgumentList $ApiArgs `
    -WorkingDirectory $Root `
    -PassThru `
    -WindowStyle Normal

Write-Host "  Demo API PID: $($ApiProc.Id)" -ForegroundColor Green
Write-Host "  URL: http://localhost:$ApiPort/demo/health" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Start Observability API (uvicorn)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Starting Observability API on port $ObsPort ..." -ForegroundColor Cyan

$ObsArgs = @(
    "-m", "uvicorn",
    "src.obs_api:app",
    "--host", "127.0.0.1",
    "--port", "$ObsPort",
    "--reload",
    "--log-level", "info"
)

$ObsProc = Start-Process `
    -FilePath $VenvPython `
    -ArgumentList $ObsArgs `
    -WorkingDirectory $Root `
    -PassThru `
    -WindowStyle Normal

Write-Host "  Observability API PID: $($ObsProc.Id)" -ForegroundColor Green
Write-Host "  URL: http://localhost:$ObsPort/obs/health" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Start Vite dashboard (npm run dev)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Starting Dashboard on port $DashPort ..." -ForegroundColor Cyan

# Resolve npm executable (works with npm installed via nvm or global installer)
$NpmExe = (Get-Command npm -ErrorAction SilentlyContinue)?.Source
if (-not $NpmExe) {
    Write-Error "npm not found in PATH.  Install Node.js first."
    $ApiProc | Stop-Process -Force
    exit 1
}

$DashEnv = [System.Environment]::GetEnvironmentVariables()
$DashEnv["VITE_PORT"] = "$DashPort"

$DashProc = Start-Process `
    -FilePath $NpmExe `
    -ArgumentList "run", "dev" `
    -WorkingDirectory $DashDir `
    -PassThru `
    -WindowStyle Normal

Write-Host "  Dashboard PID: $($DashProc.Id)" -ForegroundColor Green
Write-Host "  URL: http://localhost:$DashPort" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Open browser (unless suppressed)
# ---------------------------------------------------------------------------
if (-not $NoBrowser) {
    Start-Sleep -Seconds 3
    Start-Process "http://localhost:$DashPort"
}

# ---------------------------------------------------------------------------
# Wait / cleanup
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Both services are running.  Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

try {
    # Block until either process exits, then clean up both.
    $null = Wait-Process -Id $ApiProc.Id, $ObsProc.Id, $DashProc.Id -ErrorAction SilentlyContinue
} finally {
    Write-Host ""
    Write-Host "Stopping services..." -ForegroundColor Yellow

    foreach ($proc in @($ApiProc, $ObsProc, $DashProc)) {
        if (-not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped PID $($proc.Id)" -ForegroundColor DarkGray
        }
    }

    Write-Host "Done." -ForegroundColor Green
}
