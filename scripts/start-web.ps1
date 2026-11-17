param(
    [string]$Environment = "torchcode",
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000,
    [switch]$NoBrowser,
    [switch]$CheckOnly,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $projectRoot "web"
$ownedProcesses = New-Object System.Collections.ArrayList
$previousApiUrl = $env:TORCHCODE_API_URL
$previousTelemetry = $env:NEXT_TELEMETRY_DISABLED

function Find-Conda {
    $command = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue
    $candidates = @($env:TORCHCODE_CONDA_EXE, $env:CONDA_EXE)
    if ($command) { $candidates += $command.Source }
    foreach ($name in @("anaconda3", "miniconda3", "Anaconda3", "Miniconda3")) {
        $candidates += Join-Path $env:USERPROFILE "$name\Scripts\conda.exe"
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
    }
    throw "Conda was not found. Open this launcher from Anaconda Prompt, or set TORCHCODE_CONDA_EXE to conda.exe."
}

function Quote-ProcessArgument([string]$Value) {
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Start-OwnedProcess([string]$Executable, [string[]]$Arguments, [string]$Directory, [string]$Name) {
    $argumentString = ($Arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join " "
    $process = Start-Process -FilePath $Executable -ArgumentList $argumentString -WorkingDirectory $Directory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory "$Name.log") -RedirectStandardError (Join-Path $logDirectory "$Name.error.log")
    [void]$process.Handle
    [void]$ownedProcesses.Add($process)
    return $process
}

function Read-Health([string]$Url) {
    try { return Invoke-RestMethod -Uri $Url -TimeoutSec 2 -UseBasicParsing }
    catch { return $null }
}

function Test-PortInUse([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.ConnectAsync("127.0.0.1", $Port)
        if (-not $connection.Wait(500)) { return $false }
        return $client.Connected
    }
    catch { return $false }
    finally { $client.Dispose() }
}

function Test-ProjectHealth($Health) {
    return $Health -and $Health.service -eq "torchcode" -and $Health.project_root -eq $projectRoot
}

function Wait-ProjectHealth([string]$Url, $Process, [string]$Name) {
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        if ($Process) {
            $Process.Refresh()
            if ($Process.HasExited) { throw "$Name exited. See logs in $logDirectory" }
        }
        $health = Read-Health $Url
        if (Test-ProjectHealth $health) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not become ready within 120 seconds. See logs in $logDirectory"
}

try {
    if ($BackendPort -lt 1024 -or $BackendPort -gt 65535 -or $FrontendPort -lt 1024 -or $FrontendPort -gt 65535 -or $BackendPort -eq $FrontendPort) {
        throw "Choose two different ports between 1024 and 65535."
    }
    if ($env:TORCHCODE_BACKEND_ENV) { $Environment = $env:TORCHCODE_BACKEND_ENV }
    $conda = Find-Conda
    $node = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue
    if (-not $node) { throw "Node.js was not found. Install Node.js and reopen this launcher." }
    $next = Join-Path $webRoot "node_modules\next\dist\bin\next"
    if (-not (Test-Path -LiteralPath $next -PathType Leaf)) { throw "Frontend dependencies are missing. Run npm install in the web directory once." }
    $logDirectory = Join-Path $projectRoot ("data\startup-logs\" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-$PID")
    [void](New-Item -ItemType Directory -Path $logDirectory -Force)
    $backendExecutable = $conda
    $backendArguments = @("run", "--no-capture-output", "--name", $Environment, "--cwd", $projectRoot, "python")
    $backendSettings = Join-Path $projectRoot "data\startup-backend.json"
    if (Test-Path -LiteralPath $backendSettings) {
        $savedBackend = Get-Content -LiteralPath $backendSettings -Raw | ConvertFrom-Json
        if ($savedBackend.environment -eq $Environment -and (Test-Path -LiteralPath $savedBackend.python -PathType Leaf)) {
            $backendExecutable = $savedBackend.python
            $backendArguments = @()
            $savedPrefix = Split-Path -Parent $savedBackend.python
            if (Test-Path -LiteralPath (Join-Path $savedPrefix "conda-meta")) {
                $backendExecutable = $conda
                $backendArguments = @("run", "--no-capture-output", "--prefix", $savedPrefix, "--cwd", $projectRoot, $savedBackend.python)
            }
        }
    }
    Write-Host "TorchCode - checking backend Python (initial environment: '$Environment')..." -ForegroundColor Cyan
    $checkArguments = $backendArguments + @("-B", "-c", "import sys,fastapi,uvicorn,pydantic; print('Backend Python: '+sys.executable); print('TORCHCODE_PYTHON='+sys.executable)")
    $preflight = Start-OwnedProcess $backendExecutable $checkArguments $projectRoot "check"
    if (-not $preflight.WaitForExit(60000)) { throw "Python dependency check timed out. See $logDirectory" }
    if ($preflight.ExitCode -ne 0) { throw "Cannot start the backend in '$Environment'. Check environment name and api/requirements.txt. See $logDirectory" }
    $checkOutput = @(Get-Content -LiteralPath (Join-Path $logDirectory "check.log"))
    $checkOutput | Where-Object { -not $_.StartsWith("TORCHCODE_PYTHON=") } | Write-Host
    $pythonLine = $checkOutput | Where-Object { $_.StartsWith("TORCHCODE_PYTHON=") } | Select-Object -Last 1
    if (-not $pythonLine) { throw "Cannot identify the backend Python. See $logDirectory" }
    $actualPython = $pythonLine.Substring("TORCHCODE_PYTHON=".Length)
    @{ environment = $Environment; python = $actualPython } | ConvertTo-Json | Set-Content -LiteralPath $backendSettings -Encoding UTF8
    Write-Host "Node.js: $($node.Source)"
    if ($CheckOnly) { Write-Host "Startup checks passed." -ForegroundColor Green; exit 0 }

    $apiUrl = "http://127.0.0.1:$BackendPort"
    $siteUrl = "http://127.0.0.1:$FrontendPort"
    $env:TORCHCODE_API_URL = $apiUrl
    $env:NEXT_TELEMETRY_DISABLED = "1"
    $backend = $null
    $frontend = $null
    if (Test-PortInUse $BackendPort) {
        if (-not (Test-ProjectHealth (Read-Health "$apiUrl/api/health"))) { throw "Port $BackendPort is occupied. Close the old server, or choose -BackendPort with another port." }
        Write-Host "Reusing this project's existing backend on $BackendPort."
    }
    if (-not (Test-PortInUse $BackendPort)) {
        Write-Host "Starting backend..."
        $serverArguments = $backendArguments + @("-B", "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "$BackendPort")
        $backend = Start-OwnedProcess $backendExecutable $serverArguments $projectRoot "backend"
    }
    Wait-ProjectHealth "$apiUrl/api/health" $backend "Backend"
    if (Test-PortInUse $FrontendPort) {
        if (-not (Test-ProjectHealth (Read-Health "$siteUrl/api/health"))) { throw "Port $FrontendPort is occupied. Close the old server, or choose -FrontendPort with another port." }
        Write-Host "Reusing this project's existing frontend on $FrontendPort."
    }
    if (-not (Test-PortInUse $FrontendPort)) {
        Write-Host "Starting frontend..."
        $frontend = Start-OwnedProcess $node.Source @($next, "dev", "--webpack", "--hostname", "127.0.0.1", "--port", "$FrontendPort") $webRoot "frontend"
    }
    Wait-ProjectHealth "$siteUrl/api/health" $frontend "Frontend"
    Write-Host ""
    Write-Host "TorchCode is ready: $siteUrl/problems" -ForegroundColor Green
    Write-Host "Logs: $logDirectory"
    if (-not $NoBrowser -and -not $SmokeTest) { Start-Process "$siteUrl/problems" }
    if ($SmokeTest) { Write-Host "Startup smoke test passed." -ForegroundColor Green; exit 0 }
    Write-Host "Keep this window open. Press Enter to stop processes started by this launcher."
    [void](Read-Host)
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($logDirectory -and (Test-Path -LiteralPath $logDirectory)) {
        Get-ChildItem -LiteralPath $logDirectory -Filter "*.log" | ForEach-Object {
            if ($_.Length) { Write-Host "--- $($_.Name) ---"; Get-Content -LiteralPath $_.FullName -Tail 15 | Write-Host }
        }
    }
    exit 1
}
finally {
    foreach ($process in $ownedProcesses) {
        try {
            $process.Refresh()
            if (-not $process.HasExited) {
                & taskkill.exe /PID $process.Id /T /F *> $null
            }
        }
        catch { Write-Host "Could not stop PID $($process.Id). Close that server manually." -ForegroundColor Yellow }
    }
    $env:TORCHCODE_API_URL = $previousApiUrl
    $env:NEXT_TELEMETRY_DISABLED = $previousTelemetry
}
