param(
    [string]$ServicePattern = "memurai",
    [int]$RedisPort = 6379,
    [string]$PythonExe = ".\itds_env\Scripts\python.exe",
    [string]$WorkerScript = "run_worker.py"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[STEP] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-WarnText {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Fail {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

Write-Step "Locating Memurai service"
$service = Get-Service | Where-Object {
    $_.Name -match $ServicePattern -or $_.DisplayName -match $ServicePattern
} | Select-Object -First 1

if (-not $service) {
    Fail "Memurai service not found. Install Memurai Developer first: winget install --id Memurai.MemuraiDeveloper --accept-source-agreements --accept-package-agreements"
}

Write-Ok "Found service: $($service.Name) ($($service.Status))"

if ($service.Status -ne "Running") {
    Write-Step "Starting Memurai service"
    try {
        Start-Service -Name $service.Name
    }
    catch {
        Fail "Could not start service '$($service.Name)'. Try running PowerShell as Administrator. Details: $($_.Exception.Message)"
    }
}

Write-Step "Waiting for Redis port $RedisPort on localhost"
$maxAttempts = 15
$connected = $false
for ($i = 1; $i -le $maxAttempts; $i++) {
    try {
        $result = Test-NetConnection -ComputerName "localhost" -Port $RedisPort -WarningAction SilentlyContinue
        if ($result.TcpTestSucceeded) {
            $connected = $true
            break
        }
    }
    catch {
        # Ignore transient checks and keep retrying
    }
    Start-Sleep -Seconds 1
}

if (-not $connected) {
    Fail "Redis is not reachable on localhost:$RedisPort after $maxAttempts seconds. Check Memurai logs/service state."
}

Write-Ok "Redis is reachable on localhost:$RedisPort"

if (-not (Test-Path $PythonExe)) {
    Fail "Python executable not found at: $PythonExe"
}

if (-not (Test-Path $WorkerScript)) {
    Fail "Worker script not found at: $WorkerScript"
}

Write-Step "Launching worker: $PythonExe $WorkerScript"
& $PythonExe $WorkerScript
exit $LASTEXITCODE
