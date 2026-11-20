# start.ps1 - one-command launcher (backend, agent, frontend).
# Placeholder created in Step 1; full implementation in Step 12.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating venv (.venv) with Python 3.12..."
    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}
if (-not (Test-Path ".\.env")) { Copy-Item ".env.example" ".env"; Write-Host "Created .env from .env.example (SIMULATED mode)." }
Write-Host "Starting backend on http://127.0.0.1:8000 ..."
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
