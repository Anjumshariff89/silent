<#
.SYNOPSIS
  One-command launcher (Windows 11 / PowerShell 7): quai-service, backend API, log agent, dashboard.

.EXAMPLE
  .\start.ps1                 # set up on first run, then start quai-service + backend + agent + frontend
  .\start.ps1 -WithVerifier   # also start the standalone verifier/anchoring process
  .\start.ps1 -AllowBroadcast # let the quai-service send Quai transactions (ONLY after you approved them)
  .\start.ps1 -Stop           # stop everything started by this script (and nothing else)
  .\start.ps1 -Restart        # stop the previous run of this script, then start again
  .\start.ps1 -Rebuild        # force reinstall of dependencies and a fresh frontend build

  Run it from PowerShell, not from Git Bash / WSL / cmd:
    pwsh -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
  From a Unix shell (Git Bash, WSL, CI) always use -File and never wrap it in -Command "...":
    pwsh -NoProfile -File ./start.ps1
  (Passing PowerShell code through /bin/sh as  -Command "..."  with inner double quotes is what produces
   "/bin/sh: -c: line 1: unexpected EOF while looking for matching `"'".)

  If scripts are blocked:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Restart,
    [switch]$WithVerifier,
    [switch]$Rebuild,
    [switch]$AllowBroadcast,
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000,
    [int]$QuaiPort = 8787
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$Root    = $PSScriptRoot
$DataDir = Join-Path $Root "data"
$LogDir  = Join-Path $DataDir "runtime_logs"
$PidFile = Join-Path $DataDir "pids.json"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Windows PowerShell 5.1 has no $IsWindows; PowerShell 7 has it on every platform.
$OnWindows = if (Test-Path variable:IsWindows) { $IsWindows } else { $env:OS -eq "Windows_NT" }
$Py  = if ($OnWindows) { Join-Path $Root ".venv\Scripts\python.exe" } else { Join-Path $Root ".venv/bin/python" }
# npm.cmd avoids "npm.ps1 cannot be loaded because running scripts is disabled" on locked-down Windows.
$Npm = if ($OnWindows) { "npm.cmd" } else { "npm" }

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

# ---------------------------------------------------------------- process bookkeeping
# pids.json records pid + process name + start time, so a PID that Windows has re-used for another program
# (e.g. after a reboot) is never killed by -Stop / -Restart.
function Get-RecordedProcesses {
    if (-not (Test-Path $PidFile)) { return @() }
    try { $entries = @(Get-Content $PidFile -Raw | ConvertFrom-Json) } catch { return @() }
    $alive = @()
    foreach ($e in $entries) {
        if ($null -eq $e.pid) { continue }   # old-format file: no identity to check, never kill blindly
        $p = Get-Process -Id $e.pid -ErrorAction SilentlyContinue
        if (-not $p) { continue }
        # Identity = start time (within 2 s; it is read with slightly different precision by different
        # processes). The process name is not compared: Next.js renames itself to "next-server (vX)".
        try {
            $delta = [math]::Abs(($p.StartTime.ToUniversalTime() - [datetime]::Parse($e.started).ToUniversalTime()).TotalSeconds)
        } catch { continue }
        if ($delta -le 2) { $alive += $e }
    }
    return $alive
}

function Stop-Tree([int]$ProcessId) {
    if ($OnWindows) {
        # /T: whole tree (node -> next-server, python -> workers)
        & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
    } else {
        & pkill -TERM -P $ProcessId 2>$null
        Stop-Process -Id $ProcessId -ErrorAction SilentlyContinue
    }
}

function Stop-All {
    $alive = Get-RecordedProcesses
    foreach ($e in $alive) { Stop-Tree $e.pid; Write-Host "stopped $($e.name) (pid $($e.pid))" }
    if (-not $alive.Count) { Write-Host "nothing to stop (no running processes from a previous start.ps1 run)" }
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
}

$script:Started = @()
function Save-Pids { ConvertTo-Json -InputObject @($script:Started) | Set-Content -Path $PidFile }

function Start-Svc([string]$Name, [string]$File, [string[]]$Arguments, [string]$WorkDir) {
    $out = Join-Path $LogDir "$Name.out.log"
    $err = Join-Path $LogDir "$Name.err.log"
    if ($OnWindows) {
        # Windows: Start-Process hands the child real file handles, so services outlive this window.
        $p = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru -WorkingDirectory $WorkDir `
             -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
    } else {
        # Linux/macOS: Start-Process -Redirect* pipes output through this PowerShell process, so services die
        # with "broken pipe" once start.ps1 exits. Let /bin/sh redirect to the log files and exec the command.
        # The sh script is a fixed literal and every argument is passed separately (no quote nesting).
        $psi = [System.Diagnostics.ProcessStartInfo]::new("/bin/sh")
        $psi.WorkingDirectory = $WorkDir
        $psi.UseShellExecute = $false
        foreach ($a in @("-c", 'exec "$@" >>"$SVC_OUT" 2>>"$SVC_ERR" </dev/null', "sh", $File) + $Arguments) {
            $psi.ArgumentList.Add($a)
        }
        $psi.Environment["SVC_OUT"] = $out
        $psi.Environment["SVC_ERR"] = $err
        $p = [System.Diagnostics.Process]::Start($psi)
    }
    $script:Started += [pscustomobject]@{ name = $Name; pid = $p.Id; process = $p.ProcessName
                                          started = $p.StartTime.ToUniversalTime().ToString("o") }
    Save-Pids
    return $p
}

function Test-PortInUse([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { return $client.ConnectAsync("127.0.0.1", $Port).Wait(500) -and $client.Connected }
    catch { return $false }
    finally { $client.Dispose() }
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

function Find-Python312 {
    # py launcher first (python.org installer), then python3.12 / python on PATH (winget, Store, Linux).
    $candidates = if ($OnWindows) { @(@("py", "-3.12"), @("python3.12"), @("python")) }
                  else { @(@("python3.12"), @("python3")) }
    foreach ($c in $candidates) {
        if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
        $extra = @($c | Select-Object -Skip 1)
        $ver = (& $c[0] @extra --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $ver -match '^Python 3\.12\.') { return , $c }
    }
    return $null
}

# ---------------------------------------------------------------- stop / previous run
if ($Stop) { Stop-All; exit 0 }
$running = Get-RecordedProcesses
if ($running.Count) {
    if ($Restart) {
        Write-Step "Restart requested: stopping the previous run of start.ps1"
        Stop-All
    } else {
        $list = ($running | ForEach-Object { "$($_.name) (pid $($_.pid))" }) -join ", "
        Write-Host "start.ps1 is already running: $list" -ForegroundColor Yellow
        Write-Host "Nothing was stopped. Use .\start.ps1 -Restart to restart, or .\start.ps1 -Stop to stop." -ForegroundColor Yellow
        exit 1
    }
} elseif (Test-Path $PidFile) {
    Remove-Item $PidFile -Force   # stale file from a run that already ended; its PIDs are not ours any more
}

# ---------------------------------------------------------------- prerequisites
Write-Step "Checking prerequisites"
foreach ($port in @($ApiPort, $WebPort, $QuaiPort)) {
    # allow up to 10 s for a just-stopped previous run to release the port
    for ($i = 0; $i -lt 10 -and (Test-PortInUse $port); $i++) { Start-Sleep -Seconds 1 }
    if (Test-PortInUse $port) {
        throw "Port $port is already in use by another program. start.ps1 does not stop programs it did not start; " +
              "close that program or choose another port (-ApiPort / -WebPort / -QuaiPort)."
    }
}
$PySys = Find-Python312
if (-not $PySys) {
    throw "Python 3.12 not found. Install Python 3.12 from python.org (tick 'Add python.exe to PATH' and 'py launcher'), then reopen PowerShell."
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Node.js not found. Install Node.js 20 LTS or newer." }
if (-not (Get-Command $Npm -ErrorAction SilentlyContinue)) { throw "npm not found. Reinstall Node.js (npm is included)." }
Write-Host ("  Python: {0}   Node: {1}" -f ((& $PySys[0] @($PySys | Select-Object -Skip 1) --version 2>&1 | Out-String).Trim()), (& node --version))

# ---------------------------------------------------------------- python venv
$stamp = Join-Path $DataDir ".requirements.sha256"
$reqHash = (Get-FileHash (Join-Path $Root "requirements.txt") -Algorithm SHA256).Hash
if ($Rebuild -or -not (Test-Path $Py)) {
    Write-Step "Creating virtual environment (.venv) with Python 3.12"
    & $PySys[0] @($PySys | Select-Object -Skip 1) -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Py)) { throw "creating .venv failed" }
}
if ($Rebuild -or -not (Test-Path $stamp) -or (Get-Content $stamp) -ne $reqHash) {
    Write-Step "Installing pinned Python dependencies"
    & $Py -m pip install --upgrade pip --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
    & $Py -m pip install -r requirements.txt --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    Set-Content -Path $stamp -Value $reqHash
}

# ---------------------------------------------------------------- .env (never overwritten)
if (-not (Test-Path ".env")) {
    # First run only: create .env from the template with fresh random API_KEY and JWT_SECRET (never printed).
    # An existing .env is never modified.
    function New-Secret([int]$Bytes) {
        $b = New-Object byte[] $Bytes
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
        return ([Convert]::ToBase64String($b)).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    }
    $lines = Get-Content ".env.example" | ForEach-Object {
        if ($_ -match '^API_KEY=$') { "API_KEY=$(New-Secret 32)" }
        elseif ($_ -match '^JWT_SECRET=$') { "JWT_SECRET=$(New-Secret 48)" }
        else { $_ }
    }
    Set-Content -Path ".env" -Value $lines
    Write-Host "Created .env with freshly generated API_KEY and JWT_SECRET (values not shown)." -ForegroundColor Yellow
    Write-Host "Dashboard login: admin / the API_KEY value in .env. Add Quai/Telegram/Supabase keys to .env yourself." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- quai-service (Node.js + quais)
Push-Location (Join-Path $Root "backend/blockchain/quai-service")
try {
    if ($Rebuild -or -not (Test-Path "node_modules")) {
        Write-Step "Installing quai-service dependencies (npm ci)"
        & $Npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "npm ci (quai-service) failed" }
    }
} finally { Pop-Location }

# ---------------------------------------------------------------- frontend
# NEXT_PUBLIC_* values are compiled into the dashboard at build time, so the API URL must be set before
# `next build`, and the dashboard is rebuilt when -ApiPort changes.
$apiUrl = "http://127.0.0.1:$ApiPort"
$builtFor = Join-Path $DataDir ".frontend-api-url"
Push-Location (Join-Path $Root "frontend")
try {
    if ($Rebuild -or -not (Test-Path "node_modules")) {
        Write-Step "Installing frontend dependencies (npm ci)"
        & $Npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "npm ci (frontend) failed" }
    }
    $buildId = Join-Path ".next" "BUILD_ID"
    $needBuild = $Rebuild -or -not (Test-Path $buildId) -or
                 -not (Test-Path $builtFor) -or ((Get-Content $builtFor) -ne $apiUrl)
    if (-not $needBuild) {
        # Rebuild when the dashboard source changed since the last build (e.g. after git pull).
        $builtAt = (Get-Item $buildId).LastWriteTimeUtc
        $newer = Get-ChildItem -Path "src", "public", "package-lock.json", "next.config.mjs", "tailwind.config.ts" `
                     -Recurse -File -ErrorAction SilentlyContinue |
                 Where-Object { $_.LastWriteTimeUtc -gt $builtAt } | Select-Object -First 1
        if ($newer) { $needBuild = $true }
    }
    if ($needBuild) {
        Write-Step "Building dashboard for API $apiUrl"
        $env:NEXT_PUBLIC_API_URL = $apiUrl
        $env:NEXT_TELEMETRY_DISABLED = "1"
        & $Npm run build
        if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
        Set-Content -Path $builtFor -Value $apiUrl
    }
} finally { Pop-Location }
$NextBin = Join-Path $Root "frontend/node_modules/next/dist/bin/next"
if (-not (Test-Path $NextBin)) { throw "Next.js not installed in frontend/node_modules; run .\start.ps1 -Rebuild" }

# ---------------------------------------------------------------- start services
$mode = if ($AllowBroadcast) { "BROADCAST ALLOWED" } else { "read-only" }
Write-Step "Starting quai-service on http://127.0.0.1:$QuaiPort ($mode)"
$env:QUAI_SERVICE_PORT = "$QuaiPort"                       # read by the quai-service
$env:QUAI_SERVICE_URL  = "http://127.0.0.1:$QuaiPort"      # read by the backend (QuaiServiceAnchorer)
$qArgs = @("server.js"); if ($AllowBroadcast) { $qArgs += "--allow-broadcast" }
$quai = Start-Svc "quai-service" "node" $qArgs (Join-Path $Root "backend/blockchain/quai-service")
if (-not (Wait-Http "http://127.0.0.1:$QuaiPort/status" 30)) { throw "quai-service did not start; see $LogDir\quai-service.err.log (stop with .\start.ps1 -Stop)" }

Write-Step "Starting backend on http://127.0.0.1:$ApiPort"
$backend = Start-Svc "backend" $Py @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") $Root
if (-not (Wait-Http "http://127.0.0.1:$ApiPort/api/health" 60)) { throw "backend did not become healthy; see $LogDir\backend.err.log (stop with .\start.ps1 -Stop)" }

Write-Step "Starting log agent (real Windows Security events; needs Windows + an elevated PowerShell)"
$agent = Start-Svc "agent" $Py @("-m", "backend.agent.agent", "--server", $apiUrl, "--collector", "auto") $Root
Start-Sleep -Seconds 3
$agentRunning = [bool](Get-Process -Id $agent.Id -ErrorAction SilentlyContinue)
if (-not $agentRunning) {
    $agentWhy = (Get-Content (Join-Path $LogDir "agent.out.log") -Tail 1 -ErrorAction SilentlyContinue)
}

if ($WithVerifier) {
    Write-Step "Starting standalone verifier/anchoring process"
    $verifier = Start-Svc "verifier" $Py @("-m", "backend.verifier_service", "--interval", "60") $Root
}

Write-Step "Starting dashboard on http://127.0.0.1:$WebPort"
$env:NEXT_TELEMETRY_DISABLED = "1"
$web = Start-Svc "frontend" "node" @($NextBin, "start", "-p", "$WebPort") (Join-Path $Root "frontend")
if (-not (Wait-Http "http://127.0.0.1:$WebPort/login" 60)) { throw "dashboard did not start; see $LogDir\frontend.err.log (stop with .\start.ps1 -Stop)" }

# ---------------------------------------------------------------- summary
$health = Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/health"
$quaiStatus = Invoke-RestMethod "http://127.0.0.1:$QuaiPort/status"
Write-Host ""
Write-Host "All services running:" -ForegroundColor Green
Write-Host ("  Backend   http://127.0.0.1:{0}/docs   status={1}  db={2}" -f $ApiPort, $health.status, $health.database.backend)
Write-Host ("  Quai svc  http://127.0.0.1:{0}/status mode={1} chain={2} broadcast_allowed={3}" -f $QuaiPort, $quaiStatus.mode, $quaiStatus.chain_id, $quaiStatus.broadcast_allowed)
if ($agentRunning) { Write-Host ("  Agent     pid {0}  (logs: data/runtime_logs/agent.out.log)" -f $agent.Id) }
else { Write-Host ("  Agent     not running: {0}" -f $agentWhy) -ForegroundColor Yellow
       Write-Host "            Logs can still be sent through the API: .\.venv\Scripts\python.exe scripts\seed_logs.py" -ForegroundColor Yellow }
Write-Host ("  Dashboard http://127.0.0.1:{0}" -f $WebPort)
Write-Host ("  Integrations: blockchain={0} database={1} telegram={2} windows_event_log={3}" -f `
    $health.integrations.blockchain, $health.integrations.database, $health.integrations.telegram, $health.integrations.windows_event_log)
if ($health.dev_api_key_in_use) { Write-Host "  Login: admin / dev-local-api-key (dev key - set API_KEY in .env)" -ForegroundColor Yellow }
else { Write-Host "  Login: admin / <your API_KEY from .env>" }
Write-Host "Stop everything with: .\start.ps1 -Stop"
