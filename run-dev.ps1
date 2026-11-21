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

function Read-EnvFile([string]$Path) {
    # KEY=VALUE lines -> hashtable. Values are only tested for empty/non-empty, never printed.
    $vars = @{}
    if (Test-Path $Path) {
        foreach ($line in Get-Content $Path) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $vars[$Matches[1]] = $Matches[2].Trim() }
        }
    }
    return $vars
}

function State([hashtable]$Vars, [string]$Name) { if ($Vars[$Name]) { "SET" } else { "empty" } }

# ---------------------------------------------------------------- .env checks (before starting anything)
if (-not $Stop) {
    $backendEnv = Join-Path $PSScriptRoot ".env"
    $frontendEnv = Join-Path $PSScriptRoot "frontend/.env.local"
    Write-Host "Checking configuration files ..." -ForegroundColor Cyan
    if (Test-Path $backendEnv) { Write-Host "  .env                found" }
    else { Write-Host "  .env                missing -> start.ps1 creates it from .env.example (new API_KEY/JWT_SECRET)" -ForegroundColor Yellow }
    if (Test-Path $frontendEnv) { Write-Host "  frontend\.env.local found" }
    else { Write-Host "  frontend\.env.local missing -> Supabase sign-in is off (copy frontend\.env.local.example to enable it)" -ForegroundColor Yellow }

    $be = Read-EnvFile $backendEnv
    $fe = Read-EnvFile $frontendEnv
    $backendSupabase = [bool]($be["SUPABASE_URL"] -or $be["SUPABASE_JWT_SECRET"])
    $frontendSupabase = [bool]($fe["NEXT_PUBLIC_SUPABASE_URL"] -and $fe["NEXT_PUBLIC_SUPABASE_ANON_KEY"])
    Write-Host ("  Supabase (backend):  SUPABASE_URL={0} SUPABASE_JWT_SECRET={1}" -f (State $be "SUPABASE_URL"), (State $be "SUPABASE_JWT_SECRET"))
    Write-Host ("  Supabase (frontend): NEXT_PUBLIC_SUPABASE_URL={0} NEXT_PUBLIC_SUPABASE_ANON_KEY={1}" -f (State $fe "NEXT_PUBLIC_SUPABASE_URL"), (State $fe "NEXT_PUBLIC_SUPABASE_ANON_KEY"))
    if ($backendSupabase -ne $frontendSupabase) {
        Write-Host "Supabase Auth is configured on only one side, so every dashboard request would fail (401/403)." -ForegroundColor Red
        Write-Host "  Set SUPABASE_URL (+ SUPABASE_JWT_SECRET for HS256 projects) in .env AND NEXT_PUBLIC_SUPABASE_URL +" -ForegroundColor Red
        Write-Host "  NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend\.env.local - or leave all of them empty for the local admin login." -ForegroundColor Red
        exit 1
    }
    if ($backendSupabase -and ($be["DATABASE_URL"] -notmatch '^postgres')) {
        Write-Host "  Note: DATABASE_URL is not Supabase Postgres, so logs are stored in local SQLite." -ForegroundColor Yellow
    }
    if ($fe["SUPABASE_SERVICE_KEY"] -or $fe["NEXT_PUBLIC_SUPABASE_SERVICE_KEY"] -or $fe["CYPRUS1_PK"] -or $fe["NEXT_PUBLIC_CYPRUS1_PK"]) {
        Write-Host "frontend\.env.local contains a secret (service key / private key). Remove it: it would be shipped to browsers." -ForegroundColor Red
        exit 1
    }
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
Write-Host "  Dashboard   http://127.0.0.1:$WebPort   (sign in: $(if ($frontendSupabase) { 'Supabase email + password' } else { 'admin + API_KEY from .env' }))"
Write-Host "  API docs    http://127.0.0.1:$ApiPort/docs"
Write-Host "  Health      http://127.0.0.1:$ApiPort/health"
