# Launches FastAPI + Next.js dev servers concurrently.
$ErrorActionPreference = "Stop"

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

Write-Host "Starting FastAPI on ${apiHost}:${apiPort}..."
$api = Start-Process -NoNewWindow -PassThru -FilePath "uv" `
    -ArgumentList "run","uvicorn","footy_ev_api.main:app","--reload","--host",$apiHost,"--port",$apiPort `
    -WorkingDirectory "$PSScriptRoot/../api"

Write-Host "Starting Next.js on localhost:${webPort}..."
$web = Start-Process -NoNewWindow -PassThru -FilePath "pnpm" `
    -ArgumentList "dev","--port",$webPort `
    -WorkingDirectory "$PSScriptRoot/../web"

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
