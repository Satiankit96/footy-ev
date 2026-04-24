param([string]$Target = "help")

$ErrorActionPreference = "Stop"

Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    $uvExe = $uvCmd.Source
} elseif (Test-Path "$env:USERPROFILE\.local\bin\uv.exe") {
    $uvExe = "$env:USERPROFILE\.local\bin\uv.exe"
} else {
    Write-Error "uv not found on PATH and not at $env:USERPROFILE\.local\bin\uv.exe. Install from https://docs.astral.sh/uv/"
    exit 1
}

function Assert-Success {
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Target) {
    "install" {
        & $uvExe sync --all-groups; Assert-Success
        & $uvExe run playwright install chromium; Assert-Success
        & $uvExe run pre-commit install; Assert-Success
        Write-Output ""
        Write-Output "Install complete. Next: '.\make.ps1 check-stack' to verify everything is wired."
    }
    "check-stack" {
        Write-Output "Checking Python..."
        & $uvExe run python --version; Assert-Success
        Write-Output "Checking Ollama (optional)..."
        if (Get-Command ollama -ErrorAction SilentlyContinue) {
            ollama --version
        } else {
            Write-Output "  Ollama not installed (OK if using Gemini fallback)"
        }
        Write-Output "Checking .env..."
        if (Test-Path ".env") { Write-Output "  .env exists" } else { Write-Output "  .env missing - copy from .env.example" }
        Write-Output "Smoke test..."
        & $uvExe run pytest tests/unit -m "not slow" -q; Assert-Success
    }
    "test" {
        & $uvExe run pytest tests/unit -m "not slow" -v; Assert-Success
    }
    "test-integration" {
        & $uvExe run pytest tests/integration -v; Assert-Success
    }
    "test-all" {
        & $uvExe run pytest -v; Assert-Success
    }
    "lint" {
        & $uvExe run ruff check src tests; Assert-Success
    }
    "format" {
        & $uvExe run ruff format src tests; Assert-Success
        & $uvExe run ruff check --fix src tests; Assert-Success
    }
    "typecheck" {
        & $uvExe run mypy src; Assert-Success
    }
    "precommit" {
        & $uvExe run pre-commit run --all-files; Assert-Success
    }
    default {
        Write-Output "Usage: .\make.ps1 <target>"
        Write-Output ""
        Write-Output "Available targets:"
        Write-Output "  install           uv sync + playwright chromium + pre-commit install"
        Write-Output "  check-stack       Python/Ollama/.env check + unit smoke tests"
        Write-Output "  test              Run unit tests (excludes slow)"
        Write-Output "  test-integration  Run integration tests"
        Write-Output "  test-all          Run all tests"
        Write-Output "  lint              ruff check src tests"
        Write-Output "  format            ruff format + ruff check --fix"
        Write-Output "  typecheck         mypy src"
        Write-Output "  precommit         pre-commit run --all-files"
    }
}
