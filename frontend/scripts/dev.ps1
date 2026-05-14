# Launches FastAPI + Next.js dev servers concurrently.
$ErrorActionPreference = "Stop"

# Refresh PATH and add common tool locations that may not be in system PATH.
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + `
    [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + `
    "$env:USERPROFILE\.local\bin" + ";" + `
    "$env:USERPROFILE\.cargo\bin"

# Load .env
if (Test-Path "$PSScriptRoot/../.env") {
    Get-Content "$PSScriptRoot/../.env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
        }
    }
}

$apiHost = if ($env:UI_API_BIND_HOST) { $env:UI_API_BIND_HOST } else { "127.0.0.1" }
$apiPort = if ($env:UI_API_PORT) { $env:UI_API_PORT } else { "8000" }
$webPort = if ($env:UI_WEB_PORT) { $env:UI_WEB_PORT } else { "3000" }

$apiDir = (Resolve-Path "$PSScriptRoot\..\api").Path
$webDir = (Resolve-Path "$PSScriptRoot\..\web").Path

# Resolve uv.exe — may be in ~/.local/bin, ~/.cargo/bin, or on PATH.
$uvExe = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uvExe) {
    Write-Host "ERROR: uv not found. Install from https://docs.astral.sh/uv/"
    exit 1
}

# next.cmd is the .cmd shim that Start-Process can launch directly.
$nextCmd = Join-Path $webDir "node_modules\.bin\next.cmd"
if (-not (Test-Path $nextCmd)) {
    Write-Host "ERROR: next.cmd not found. Run 'pnpm install' in frontend/web/ first."
    exit 1
}

Write-Host "Starting FastAPI on ${apiHost}:${apiPort}..."
$api = Start-Process -NoNewWindow -PassThru -FilePath $uvExe `
    -ArgumentList "run","uvicorn","footy_ev_api.main:app","--reload","--host",$apiHost,"--port",$apiPort `
    -WorkingDirectory $apiDir

Write-Host "Starting Next.js on localhost:${webPort}..."
$web = Start-Process -NoNewWindow -PassThru -FilePath $nextCmd `
    -ArgumentList "dev","--port",$webPort `
    -WorkingDirectory $webDir

Write-Host ""
Write-Host "=== footy-ev UI ==="
Write-Host "Frontend: http://localhost:${webPort}"
Write-Host "API docs: http://localhost:${apiPort}/docs"
Write-Host "Press Ctrl+C to stop both."
Write-Host "==================="

try {
    Wait-Process -Id $api.Id, $web.Id
} finally {
    if (!$api.HasExited) { Stop-Process -Id $api.Id -Force }
    if (!$web.HasExited) { Stop-Process -Id $web.Id -Force }
}
