param(
    [Parameter(Position=0)][string]$Target = "help",
    [string]$League,
    [string]$Season,
    [string]$FromSeason,
    [string]$ToSeason,
    [switch]$Refresh
)
switch ($Target) {
    "install"          { uv sync --all-groups; uv run playwright install chromium; uv run pre-commit install }
    "check-stack"      { uv run python --version; uv run pytest tests/unit -m "not slow" -q }
    "test"             { uv run pytest tests/unit -m "not slow" -v }
    "test-integration" { uv run pytest tests/integration -v }
    "test-all"         { uv run pytest -v }
    "lint"             { uv run ruff check src tests }
    "format"           { uv run ruff format src tests; uv run ruff check --fix src tests }
    "typecheck"        { uv run mypy src }
    "precommit"        { uv run pre-commit run --all-files }
    "ingest-season" {
        if (-not $League -or -not $Season) {
            Write-Error "Usage: .\make.ps1 ingest-season -League EPL -Season 2024-2025 [-Refresh]"
            exit 1
        }
        $cliArgs = @("run","python","-m","footy_ev.ingestion.cli","ingest-season","--league",$League,"--season",$Season)
        if ($Refresh) { $cliArgs += "--refresh" }
        & uv @cliArgs
    }
    "ingest-league" {
        if (-not $League) {
            Write-Error "Usage: .\make.ps1 ingest-league -League EPL [-FromSeason 2000-2001] [-ToSeason 2024-2025] [-Refresh]"
            exit 1
        }
        $cliArgs = @("run","python","-m","footy_ev.ingestion.cli","ingest-league","--league",$League)
        if ($FromSeason) { $cliArgs += @("--from-season",$FromSeason) }
        if ($ToSeason)   { $cliArgs += @("--to-season",$ToSeason) }
        if ($Refresh)    { $cliArgs += "--refresh" }
        & uv @cliArgs
    }
    "ingest"           { uv run python -m footy_ev.ingestion.cli all }
    default            { Write-Host "Targets: install, check-stack, test, test-integration, test-all, lint, format, typecheck, precommit, ingest-season, ingest-league, ingest" }
}
