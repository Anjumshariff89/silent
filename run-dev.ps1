<#
.SYNOPSIS
  Start backend + frontend (and the quai-service + agent) together, then check that they answer.

.EXAMPLE
  .\run-dev.ps1               # start everything (first run installs dependencies and builds the dashboard)
  .\run-dev.ps1 -Seed         # ... then insert 20 test logs through the API, verify the chain, build a Merkle batch
  .\run-dev.ps1 -Restart      # restart a previous run of this project (only processes it started)
  .\run-dev.ps1 -Stop         # stop everything it started
  .\run-dev.ps1 -ApiPort 8100 -WebPort 3100   # other ports if 8000/3000 are taken

  Run from PowerShell (not Git Bash / cmd):  pwsh -NoProfile -ExecutionPolicy Bypass -File .\run-dev.ps1
  This is a thin wrapper around start.ps1 (one code path); see README "Troubleshooting".
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Rebuild,
    [switch]$Seed,
    [switch]$AllowBroadcast,
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000,
    [int]$QuaiPort = 8787
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$OnWindows = if (Test-Path variable:IsWindows) { $IsWindows } else { $env:OS -eq "Windows_NT" }
$Py = if ($OnWindows) { Join-Path $PSScriptRoot ".venv\Scripts\python.exe" } else { Join-Path $PSScriptRoot ".venv/bin/python" }

function Show-Troubleshooting([string]$Problem) {
    Write-Host ""
    Write-Host "Troubleshooting ($Problem):" -ForegroundColor Yellow
    Write-Host "  * Port in use: find the program -> Get-NetTCPConnection -LocalPort $ApiPort,$WebPort,$QuaiPort -State Listen | Select LocalPort,OwningProcess"
    Write-Host "      then Get-Process -Id <OwningProcess>. If it is an old run of this project: .\run-dev.ps1 -Stop"
    Write-Host "      otherwise close that program or use other ports: .\run-dev.ps1 -ApiPort 8100 -WebPort 3100"
    Write-Host "  * ERR_CONNECTION_REFUSED: nothing is listening. Read data\runtime_logs\<service>.err.log"
    Write-Host "      (backend.err.log, frontend.err.log, quai-service.err.log) for the real error, fix it, run again."
    Write-Host "  * Python 3.12 missing: install from python.org (tick 'py launcher' + 'Add to PATH'), reopen PowerShell."
    Write-Host "  * Scripts blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"
    Write-Host "  * Corrupt install: .\run-dev.ps1 -Rebuild"
}

$startArgs = @{ ApiPort = $ApiPort; WebPort = $WebPort; QuaiPort = $QuaiPort }
if ($Stop) { $startArgs.Stop = $true }
if ($Restart) { $startArgs.Restart = $true }
if ($Rebuild) { $startArgs.Rebuild = $true }
if ($AllowBroadcast) { $startArgs.AllowBroadcast = $true }

try {
    & (Join-Path $PSScriptRoot "start.ps1") @startArgs
} catch {
    Write-Host "start.ps1 failed: $($_.Exception.Message)" -ForegroundColor Red
    Show-Troubleshooting "startup failed"
    exit 1
}
if ($Stop) { exit 0 }
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    Show-Troubleshooting "start.ps1 exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# ---------------------------------------------------------------- health checks
$checks = [ordered]@{
    "backend  /health"        = "http://127.0.0.1:$ApiPort/health"
    "quai-service /status"    = "http://127.0.0.1:$QuaiPort/status"
    "frontend /login"         = "http://127.0.0.1:$WebPort/login"
}
$failed = @()
Write-Host ""
foreach ($name in $checks.Keys) {
    try {
        $r = Invoke-WebRequest -Uri $checks[$name] -UseBasicParsing -TimeoutSec 5
        Write-Host ("  OK   {0,-22} HTTP {1}" -f $name, $r.StatusCode) -ForegroundColor Green
    } catch {
        Write-Host ("  FAIL {0,-22} {1}" -f $name, $_.Exception.Message) -ForegroundColor Red
        $failed += $name
    }
}
if ($failed.Count) { Show-Troubleshooting "health check failed"; exit 1 }

if ($Seed) {
    Write-Host ""
    Write-Host "Seeding test logs through the API ..." -ForegroundColor Cyan
    & $Py (Join-Path $PSScriptRoot "scripts/seed_logs.py") --server "http://127.0.0.1:$ApiPort" --count 20 --verify --build-merkle
    if ($LASTEXITCODE -ne 0) { Write-Host "seeding failed (see message above)" -ForegroundColor Red; exit 1 }
}

Write-Host ""
Write-Host "Open:" -ForegroundColor Green
Write-Host "  Dashboard   http://127.0.0.1:$WebPort"
Write-Host "  API docs    http://127.0.0.1:$ApiPort/docs"
Write-Host "  Health      http://127.0.0.1:$ApiPort/health"
