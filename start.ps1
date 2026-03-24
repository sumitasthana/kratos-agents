# start.ps1 — Launch all Kratos services in ONE terminal
# Run from project root:  .\start.ps1
# Press Q to stop all services and free ports.

$root = $PSScriptRoot
$venv = "$root\venv311\Scripts\Activate.ps1"

# ── Port map ──────────────────────────────────────────────────────────────────
$PORTS = @(8000, 8001, 8002, 4173, 5173)

function Stop-Port {
    param([int]$port)
    $pids = netstat -ano 2>$null |
        Select-String ":$port\s" |
        ForEach-Object { ($_ -split '\s+')[-1] } |
        Sort-Object -Unique
    foreach ($p in $pids) {
        if ($p -and $p -ne '0') {
            try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}

function Stop-AllPorts {
    Write-Host ""
    Write-Host " Stopping all services..." -ForegroundColor Yellow
    foreach ($port in $PORTS) { Stop-Port $port }
    Write-Host " Ports freed: $($PORTS -join ', ')" -ForegroundColor Green
}

# ── Kill any stale processes on those ports before starting ───────────────────
Write-Host " Clearing stale processes on ports $($PORTS -join ', ')..." -ForegroundColor DarkGray
foreach ($port in $PORTS) { Stop-Port $port }
Start-Sleep -Milliseconds 400

# ── Helper: write a colour-prefixed log line ──────────────────────────────────
# We use a synchronized hashtable so jobs can share a queue-like mechanism via
# temp files (PowerShell jobs can't write directly to parent console colours).

$logDir = "$root\.kratos_logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory $logDir | Out-Null }

# ── Define services ───────────────────────────────────────────────────────────
$services = @(
    @{
        Name   = 'CauseLink'
        Prefix = '[CauseLink  :8001]'
        Color  = 'Cyan'
        Log    = "$logDir\causelink.log"
        Script = {
            param($root, $venv)
            Set-Location $root
            & $venv | Out-Null
            $env:PYTHONPATH = 'src'
            uvicorn src.causelink_api:app --host 0.0.0.0 --port 8001 --reload 2>&1
        }
    },
    @{
        Name   = 'Express  '
        Prefix = '[Express   :4173]'
        Color  = 'Green'
        Log    = "$logDir\express.log"
        Script = {
            param($root, $venv)
            Set-Location "$root\dashboard"
            npm run server 2>&1
        }
    },
    @{
        Name   = 'Vite     '
        Prefix = '[Vite      :5173]'
        Color  = 'Yellow'
        Log    = "$logDir\vite.log"
        Script = {
            param($root, $venv)
            Set-Location "$root\dashboard"
            npm run dev 2>&1
        }
    },
    @{
        Name   = 'RCA API  '
        Prefix = '[RCA API   :8000]'
        Color  = 'Magenta'
        Log    = "$logDir\rca_api.log"
        Script = {
            param($root, $venv)
            Set-Location $root
            & $venv | Out-Null
            $env:PYTHONPATH = 'src'
            uvicorn src.rca_api:app --host 0.0.0.0 --port 8000 --reload 2>&1
        }
    },
    @{
        Name   = 'Demo API '
        Prefix = '[Demo API  :8002]'
        Color  = 'Blue'
        Log    = "$logDir\demo_api.log"
        Script = {
            param($root, $venv)
            Set-Location $root
            & $venv | Out-Null
            $env:PYTHONPATH = 'src'
            uvicorn src.demo_api:app --host 0.0.0.0 --port 8002 --reload 2>&1
        }
    }
)

# ── Start each service as a background job, redirecting output to a log file ──
$jobs = @()
foreach ($svc in $services) {
    # Truncate old log
    Set-Content -Path $svc.Log -Value '' -Encoding UTF8

    $job = Start-Job -ScriptBlock {
        param($scriptBlock, $root, $venv, $logFile)
        $sb = [ScriptBlock]::Create($scriptBlock)
        & $sb $root $venv 2>&1 | ForEach-Object {
            $_ | Out-File -FilePath $logFile -Append -Encoding UTF8
        }
    } -ArgumentList $svc.Script.ToString(), $root, $venv, $svc.Log

    $jobs += [PSCustomObject]@{ Job = $job; Service = $svc }
}

# ── Banner ────────────────────────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "  ██╗  ██╗██████╗  █████╗ ████████╗ ██████╗ ███████╗" -ForegroundColor Blue
Write-Host "  ██║ ██╔╝██╔══██╗██╔══██╗╚══██╔══╝██╔═══██╗██╔════╝" -ForegroundColor Blue
Write-Host "  █████╔╝ ██████╔╝███████║   ██║   ██║   ██║███████╗" -ForegroundColor Cyan
Write-Host "  ██╔═██╗ ██╔══██╗██╔══██║   ██║   ██║   ██║╚════██║" -ForegroundColor Cyan
Write-Host "  ██║  ██╗██║  ██║██║  ██║   ██║   ╚██████╔╝███████║" -ForegroundColor White
Write-Host "  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚══════╝" -ForegroundColor White
Write-Host ""
Write-Host "  Intelligence Platform — All services starting" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Service         URL" -ForegroundColor DarkGray
Write-Host "  ─────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  [CauseLink  :8001]   http://localhost:8001" -ForegroundColor Cyan
Write-Host "  [Express    :4173]   http://localhost:4173" -ForegroundColor Green
Write-Host "  [Vite       :5173]   http://localhost:5173" -ForegroundColor Yellow
Write-Host "  [RCA API    :8000]   http://localhost:8000" -ForegroundColor Magenta
Write-Host "  [Demo API   :8002]   http://localhost:8002" -ForegroundColor Blue
Write-Host ""
Write-Host "  Press  Q  to stop all services and exit." -ForegroundColor White
Write-Host "  ─────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# ── Log tail positions per file ───────────────────────────────────────────────
$tails = @{}
foreach ($entry in $jobs) { $tails[$entry.Service.Log] = 0 }

# ── Main loop: tail all log files, print colour-coded, check Q ───────────────
try {
    while ($true) {
        # Check for Q keypress (non-blocking)
        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq 'Q' -or $key.Key -eq 'q') { break }
        }

        # Tail all log files
        foreach ($entry in $jobs) {
            $svc  = $entry.Service
            $file = $svc.Log
            if (-not (Test-Path $file)) { continue }

            $lines = Get-Content $file -Encoding UTF8 -ErrorAction SilentlyContinue
            if (-not $lines) { continue }

            $pos = $tails[$file]
            if ($lines.Count -gt $pos) {
                $newLines = $lines[$pos..($lines.Count - 1)]
                foreach ($line in $newLines) {
                    if ($line.Trim() -eq '') { continue }
                    # Suppress noisy uvicorn reload/startup noise after the first line
                    Write-Host "$($svc.Prefix) " -ForegroundColor $svc.Color -NoNewline
                    Write-Host $line -ForegroundColor DarkGray
                }
                $tails[$file] = $lines.Count
            }
        }

        Start-Sleep -Milliseconds 300
    }
}
finally {
    # ── Cleanup on Q or Ctrl+C ────────────────────────────────────────────────
    Write-Host ""
    Write-Host "  Shutting down..." -ForegroundColor Yellow

    foreach ($entry in $jobs) {
        Stop-Job  $entry.Job -ErrorAction SilentlyContinue
        Remove-Job $entry.Job -Force -ErrorAction SilentlyContinue
    }

    Stop-AllPorts

    # Clean up log files
    Remove-Item $logDir -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "  All services stopped. Ports freed." -ForegroundColor Green
    Write-Host ""
}

