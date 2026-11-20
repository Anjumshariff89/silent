<#
.SYNOPSIS
  One-command launcher (Windows 11 / PowerShell): backend API, log agent, dashboard.

.EXAMPLE
  .\start.ps1                 # set up on first run, then start backend + agent + frontend
  .\start.ps1 -WithVerifier   # also start the standalone verifier/anchoring process
  .\start.ps1 -Stop           # stop everything started by this script
  .\start.ps1 -Rebuild        # force reinstall of dependencies and a fresh frontend build

  If scripts are blocked:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$WithVerifier,
    [switch]$Rebuild,
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$Root    = $PSScriptRoot
$DataDir = Join-Path $Root "data"
$LogDir  = Join-Path $DataDir "runtime_logs"
$PidFile = Join-Path $DataDir "pids.json"
$Py      = Join-Path $Root ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Stop-All {
    if (Test-Path $PidFile) {
        $pids = Get-Content $PidFile | ConvertFrom-Json
        foreach ($p in $pids.PSObject.Properties) {
            $proc = Get-Process -Id $p.Value -ErrorAction SilentlyContinue
            if ($proc) {
                # /T kills the whole process tree (npm -> node -> next-server)
                & taskkill.exe /PID $p.Value /T /F | Out-Null
                Write-Host "stopped $($p.Name) (pid $($p.Value))"
            }
        }
        Remove-Item $PidFile -Force
    } else {
        Write-Host "nothing to stop (no $PidFile)"
    }
}

function Wait-Http($url, $seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Milliseconds 700 }
    }
    return $false
}

if ($Stop) { Stop-All; exit 0 }
if (Test-Path $PidFile) { Write-Step "Previous run found, stopping it first"; Stop-All }

# ---------------------------------------------------------------- prerequisites
Write-Step "Checking prerequisites"
foreach ($port in @($ApiPort, $WebPort)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use by another process. Stop it first (.\start.ps1 -Stop)."
    }
}
& py -3.12 --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 not found. Install it from python.org (tick 'py launcher')." }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Node.js not found. Install Node.js 20 LTS or newer." }

# ---------------------------------------------------------------- python venv
$stamp = Join-Path $DataDir ".requirements.sha256"
$reqHash = (Get-FileHash (Join-Path $Root "requirements.txt") -Algorithm SHA256).Hash
if ($Rebuild -or -not (Test-Path $Py)) {
    Write-Step "Creating virtual environment (.venv) with Python 3.12"
    & py -3.12 -m venv .venv
}
if ($Rebuild -or -not (Test-Path $stamp) -or (Get-Content $stamp) -ne $reqHash) {
    Write-Step "Installing pinned Python dependencies"
    & $Py -m pip install --upgrade pip --quiet
    & $Py -m pip install -r requirements.txt --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    Set-Content -Path $stamp -Value $reqHash
}

# ---------------------------------------------------------------- .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example (all integrations SIMULATED). Edit .env yourself to add keys." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- frontend
Push-Location frontend
if ($Rebuild -or -not (Test-Path "node_modules")) { Write-Step "Installing frontend dependencies (npm ci)"; & npm ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw "npm ci failed" } }
if ($Rebuild -or -not (Test-Path ".next\BUILD_ID")) { Write-Step "Building dashboard"; & npm run build; if ($LASTEXITCODE -ne 0) { throw "frontend build failed" } }
Pop-Location

# ---------------------------------------------------------------- start services
$pids = [ordered]@{}

Write-Step "Starting backend on http://127.0.0.1:$ApiPort"
$backend = Start-Process -FilePath $Py -PassThru -WindowStyle Hidden `
    -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "$ApiPort" `
    -RedirectStandardOutput (Join-Path $LogDir "backend.out.log") -RedirectStandardError (Join-Path $LogDir "backend.err.log")
$pids.backend = $backend.Id
if (-not (Wait-Http "http://127.0.0.1:$ApiPort/api/health" 60)) { $pids | ConvertTo-Json | Set-Content $PidFile; throw "backend did not become healthy; see $LogDir\backend.err.log" }

Write-Step "Starting log agent (Windows Event Log if available, else simulator)"
$agent = Start-Process -FilePath $Py -PassThru -WindowStyle Hidden `
    -ArgumentList "-m", "backend.agent.agent", "--server", "http://127.0.0.1:$ApiPort", "--collector", "auto" `
    -RedirectStandardOutput (Join-Path $LogDir "agent.out.log") -RedirectStandardError (Join-Path $LogDir "agent.err.log")
$pids.agent = $agent.Id

if ($WithVerifier) {
    Write-Step "Starting standalone verifier/anchoring process"
    $verifier = Start-Process -FilePath $Py -PassThru -WindowStyle Hidden `
        -ArgumentList "-m", "backend.verifier_service", "--interval", "60" `
        -RedirectStandardOutput (Join-Path $LogDir "verifier.out.log") -RedirectStandardError (Join-Path $LogDir "verifier.err.log")
    $pids.verifier = $verifier.Id
}

Write-Step "Starting dashboard on http://127.0.0.1:$WebPort"
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:$ApiPort"
$web = Start-Process -FilePath "cmd.exe" -PassThru -WindowStyle Hidden -WorkingDirectory (Join-Path $Root "frontend") `
    -ArgumentList "/c", "npx", "next", "start", "-p", "$WebPort" `
    -RedirectStandardOutput (Join-Path $LogDir "frontend.out.log") -RedirectStandardError (Join-Path $LogDir "frontend.err.log")
$pids.frontend = $web.Id
$pids | ConvertTo-Json | Set-Content $PidFile
if (-not (Wait-Http "http://127.0.0.1:$WebPort/login" 60)) { throw "dashboard did not start; see $LogDir\frontend.err.log" }

# ---------------------------------------------------------------- summary
$health = Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/health"
Write-Host ""
Write-Host "All services running:" -ForegroundColor Green
Write-Host ("  Backend   http://127.0.0.1:{0}/docs   status={1}  db={2}" -f $ApiPort, $health.status, $health.database.backend)
Write-Host ("  Agent     pid {0}  (logs: data\runtime_logs\agent.out.log)" -f $agent.Id)
Write-Host ("  Dashboard http://127.0.0.1:{0}" -f $WebPort)
Write-Host ("  Integrations: blockchain={0} database={1} telegram={2} windows_event_log={3}" -f `
    $health.integrations.blockchain, $health.integrations.database, $health.integrations.telegram, $health.integrations.windows_event_log)
if ($health.dev_api_key_in_use) { Write-Host "  Login: admin / dev-local-api-key (simulator dev key - set API_KEY in .env for real use)" -ForegroundColor Yellow }
else { Write-Host "  Login: admin / <your API_KEY from .env>" }
Write-Host "Stop everything with: .\start.ps1 -Stop"
