# start.ps1 — Start the Kratos RCA Agent (API + Dashboard)
# Usage: .\start.ps1 [-Port 8001] [-FrontendPort 5173] [-Reload] [-ApiOnly] [-FrontendOnly]

param(
    [int]$Port         = 8001,
    [int]$FrontendPort = 5173,
    [switch]$Reload,
    [switch]$ApiOnly,
    [switch]$FrontendOnly
)

$Root      = $PSScriptRoot
$Dashboard = Join-Path $Root "dashboard"

# ---------------------------------------------------------------------------
# 1. Activate venv311 (skip if frontend-only)
# ---------------------------------------------------------------------------
if (-not $FrontendOnly) {
    $Activate = Join-Path $Root "venv311\Scripts\Activate.ps1"
    if (-not (Test-Path $Activate)) {
        Write-Error "venv311 not found at $Activate. Run: python -m venv venv311"
        exit 1
    }
    . $Activate
    $env:PYTHONPATH = $Root
}

# ---------------------------------------------------------------------------
# 2. Banner
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  Kratos RCA Platform" -ForegroundColor Cyan
if (-not $FrontendOnly) {
    Write-Host "  API      : http://127.0.0.1:$Port"      -ForegroundColor Gray
    Write-Host "  API Docs : http://127.0.0.1:$Port/docs" -ForegroundColor Green
}
if (-not $ApiOnly) {
    Write-Host "  Dashboard: http://127.0.0.1:$FrontendPort" -ForegroundColor Green
}
Write-Host ""

# ---------------------------------------------------------------------------
# 2b. Check My_Bank pipeline availability
# ---------------------------------------------------------------------------
$BankUrl = "http://localhost:8080"
try {
    $null = Invoke-WebRequest -Uri "$BankUrl/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    Write-Host "  My_Bank  : $BankUrl (connected)" -ForegroundColor Green
}
catch {
    Write-Host "  My_Bank  : $BankUrl (offline - using synthetic data)" -ForegroundColor Yellow
    Write-Host "  To start : cd ..\My_Bank\bank-pipeline-api; docker compose up -d" -ForegroundColor DarkGray
}
Write-Host ""

# ---------------------------------------------------------------------------
# 3. Load .env into the current PowerShell session so child processes inherit it
# ---------------------------------------------------------------------------
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
            $name  = $Matches[1].Trim()
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            if (-not [System.Environment]::GetEnvironmentVariable($name)) {
                [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
                Write-Host "  .env: loaded $name" -ForegroundColor DarkGray
            }
        }
    }
}

# ---------------------------------------------------------------------------
# 4. Start backend API as a background process (unless -FrontendOnly)
#    Uses Start-Process instead of Start-Job so the child inherits the
#    current process's environment variables (PYTHONPATH, OPENAI_API_KEY, etc.)
# ---------------------------------------------------------------------------
$ApiProcess = $null
if (-not $FrontendOnly) {
    $UvicornExe  = Join-Path $Root "venv311\Scripts\uvicorn.exe"
    $UvicornArgs = @("server:app", "--host", "0.0.0.0", "--port", "$Port", "--log-level", "info", "--ws-ping-interval", "300", "--ws-ping-timeout", "300")
    if ($Reload) { $UvicornArgs += "--reload" }

    $ApiProcess = Start-Process -FilePath $UvicornExe `
        -ArgumentList $UvicornArgs `
        -WorkingDirectory $Root `
        -PassThru `
        -NoNewWindow

    # Wait briefly and verify the process is still alive
    Start-Sleep -Seconds 2
    if ($ApiProcess.HasExited) {
        Write-Error "API failed to start (exit code $($ApiProcess.ExitCode)). Check server.py for errors."
        exit 1
    }
    Write-Host "  API started (PID $($ApiProcess.Id))" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# 5. Start frontend — foreground so Ctrl+C stops everything
# ---------------------------------------------------------------------------
if (-not $ApiOnly) {
    if (-not (Test-Path $Dashboard)) {
        Write-Error "dashboard/ folder not found at $Dashboard"
        if ($ApiProcess -and -not $ApiProcess.HasExited) { Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue }
        exit 1
    }

    try {
        Push-Location $Dashboard
        npm run dev -- --port $FrontendPort
    } finally {
        Pop-Location
        # Clean up backend process when frontend exits
        if ($ApiProcess -and -not $ApiProcess.HasExited) {
            Write-Host "`n  Stopping API (PID $($ApiProcess.Id))..." -ForegroundColor DarkGray
            Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    # API-only mode: just run uvicorn in the foreground
    $UvicornArgs = @("server:app", "--host", "0.0.0.0", "--port", "$Port", "--log-level", "info", "--ws-ping-interval", "300", "--ws-ping-timeout", "300")
    if ($Reload) { $UvicornArgs += "--reload" }
    & $UvicornExe @UvicornArgs
}
