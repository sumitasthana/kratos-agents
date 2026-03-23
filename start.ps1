# start.ps1 — Launch all Kratos services in separate windows
# Run from project root:  .\start.ps1
# Requires: venv311 created, dashboard/node_modules installed

$root = $PSScriptRoot

# -- 1. CauseLink FastAPI -- port 8001 -----------------------------------------------
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root'; `
     Write-Host '[CauseLink API] Starting on http://127.0.0.1:8001' -ForegroundColor Cyan; `
     & '$root\venv311\Scripts\Activate.ps1'; `
     `$env:PYTHONPATH = 'src'; `
     uvicorn src.causelink_api:app --host 0.0.0.0 --port 8001 --reload"
) -WindowStyle Normal

# -- 2. Express artifact server -- port 4173 -----------------------------------------
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\dashboard'; `
     Write-Host '[Express Server] Starting on http://127.0.0.1:4173' -ForegroundColor Green; `
     npm run server"
) -WindowStyle Normal

# -- 3. Vite dev server -- port 5173 -----------------------------------------
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root\dashboard'; `
     Write-Host '[Vite Dev] Starting on http://localhost:5173' -ForegroundColor Yellow; `
     npm run dev"
) -WindowStyle Normal

# -- 4. Kratos RCA API -- port 8000 -------------------------------------------
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root'; `
     Write-Host '[Kratos API] Starting on http://127.0.0.1:8000' -ForegroundColor Magenta; `
     & '$root\venv311\Scripts\Activate.ps1'; `
     `$env:PYTHONPATH = 'src'; `
     uvicorn src.rca_api:app --host 0.0.0.0 --port 8000 --reload"
) -WindowStyle Normal

# -- 5. Demo API -- port 8002 -------------------------------------------------
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$root'; `
     Write-Host '[Demo API] Starting on http://127.0.0.1:8002' -ForegroundColor Blue; `
     & '$root\venv311\Scripts\Activate.ps1'; `
     `$env:PYTHONPATH = 'src'; `
     uvicorn src.demo_api:app --host 0.0.0.0 --port 8002 --reload"
) -WindowStyle Normal

Write-Host ""
Write-Host "All services launching in separate windows:" -ForegroundColor White
Write-Host "  CauseLink API   -> http://localhost:8001   (FastAPI + chat RCA)" -ForegroundColor Cyan
Write-Host "  Express Server  -> http://localhost:4173   (run history / artifacts)" -ForegroundColor Green
Write-Host "  Dashboard       -> http://localhost:5173   (React UI)" -ForegroundColor Yellow
Write-Host "  Kratos API      -> http://localhost:8000   (Spark/Airflow log RCA)" -ForegroundColor Magenta
Write-Host "  Demo API        -> http://localhost:8002   (FDIC scenario RCA demo)" -ForegroundColor Blue
Write-Host ""
Write-Host "Available log files for Spark analysis:" -ForegroundColor Gray
Write-Host "  logs/test_fixtures/spark/spark_failure_spill.jsonl" -ForegroundColor Gray
Write-Host "  logs/raw/spark_events/local-* (10 event logs)" -ForegroundColor Gray
