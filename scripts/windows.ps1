param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runDir = Join-Path $projectDir '.run'
$statePath = Join-Path $runDir 'processes.json'
$webUrl = 'http://127.0.0.1:3017'
$apiUrl = 'http://127.0.0.1:8017'
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$processes = @{}
if (Test-Path -LiteralPath $statePath) {
    $saved = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    foreach ($property in $saved.PSObject.Properties) { $processes[$property.Name] = $property.Value }
}
function Get-OwnedProcess($entry) {
    if (-not $entry) { return $null }
    $process = Get-Process -Id $entry.Id -ErrorAction SilentlyContinue
    if ($process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $entry.StartTicks) {
        return $process
    }
    return $null
}
function Save-State {
    $processes | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
}
if ($Action -eq 'stop') {
    foreach ($name in @('frontend', 'backend')) {
        $process = Get-OwnedProcess $processes[$name]
        if ($process) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F | Out-Null
        }
        $processes.Remove($name)
    }
    Save-State
    Write-Output 'Chess Review Coach stopped. Saved games are kept.'
    exit 0
}
if ($Action -eq 'status') {
    foreach ($name in @('backend', 'frontend')) {
        $process = Get-OwnedProcess $processes[$name]
        Write-Output ('{0}: {1}' -f $name, $(if ($process) { 'running (PID ' + $process.Id + ')' } else { 'stopped' }))
    }
    Write-Output $webUrl
    exit 0
}
function Start-ServiceProcess($name, $executable, $arguments, $directory, $port) {
    if (Get-OwnedProcess $processes[$name]) { return }
    $occupied = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
        Where-Object { $_.Port -eq $port }
    if ($occupied) { throw "Port $port is in use by another process. Close that app before starting the coach." }
    $process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $directory `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runDir "$name.log") `
        -RedirectStandardError (Join-Path $runDir "$name.err.log")
    $processes[$name] = @{ Id = $process.Id; StartTicks = $process.StartTime.ToUniversalTime().Ticks.ToString() }
    Save-State
}
function Wait-Ready($url, $name) {
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if (-not (Get-OwnedProcess $processes[$name])) {
            throw "$name stopped unexpectedly. See logs in $runDir"
        }
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Milliseconds 400
    }
    throw "Startup timed out for $name. See logs in $runDir"
}
$pythonPath = Join-Path $projectDir '.venv\Scripts\python.exe'
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$buildPath = Join-Path $projectDir 'frontend\.next\BUILD_ID'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python environment is missing.' }
if (-not (Test-Path -LiteralPath $buildPath)) { throw 'Frontend build is missing. Run npm run build in frontend first.' }
$env:NEXT_TELEMETRY_DISABLED = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:CORS_ORIGINS = 'http://127.0.0.1:3017,http://localhost:3017'
$env:PORT = '3017'
Start-ServiceProcess 'backend' $pythonPath @('-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', '8017') (Join-Path $projectDir 'backend') 8017
Wait-Ready "$apiUrl/api/health" 'backend'
Start-ServiceProcess 'frontend' $nodePath @('node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3017') (Join-Path $projectDir 'frontend') 3017
Wait-Ready $webUrl 'frontend'
Write-Output "Ready: $webUrl"
if (-not $NoBrowser) { Start-Process $webUrl }
