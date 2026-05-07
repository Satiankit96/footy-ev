param(
    [Parameter(Position=0)][string]$Target = "help",
    [string]$League,
    [string]$Season,
    [string]$FromSeason,
    [string]$ToSeason,
    [switch]$Refresh,
    [int]$TrainMinSeasons = 3,
    [int]$StepDays = 7,
    [string]$ModelVersion = "dc_v1",
    [double]$XiDecay = 0.0019,
    [string]$XgSkellamRunId = "",
    [string]$FeatureSubset = "",
    [string]$RunId,
    [string]$DevigMethod = "shin",
    [switch]$NoCalibrate
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
    "backtest-epl" {
        $lg = if ($League) { $League } else { "EPL" }
        $cliArgs = @(
            "run","python","-m","footy_ev.backtest.cli","backtest-walkforward",
            "--league",$lg,
            "--train-min-seasons",$TrainMinSeasons,
            "--step-days",$StepDays,
            "--model-version",$ModelVersion,
            "--xi-decay",$XiDecay,
            "--xg-skellam-run-id",$XgSkellamRunId,
            "--feature-subset",$FeatureSubset
        )
        & uv @cliArgs
    }
    "diagnose-features" {
        if (-not $RunId) {
            Write-Error "Usage: .\make.ps1 diagnose-features -RunId <xgb-run-uuid>"
            exit 1
        }
        & uv run python -m footy_ev.eval.cli diagnose-features --run-id $RunId
    }
    "diagnose-shap" {
        if (-not $RunId) {
            Write-Error "Usage: .\make.ps1 diagnose-shap -RunId <xgb-run-uuid>"
            exit 1
        }
        & uv run python -m footy_ev.eval.cli diagnose-shap --run-id $RunId
    }
    "evaluate-run" {
        if (-not $RunId) {
            Write-Error "Usage: .\make.ps1 evaluate-run -RunId <uuid> [-DevigMethod shin|power]"
            exit 1
        }
        $cliArgs = @(
            "run","python","-m","footy_ev.eval.cli","evaluate-run",
            "--run-id",$RunId,
            "--devig-method",$DevigMethod
        )
        if ($NoCalibrate) { $cliArgs += "--no-calibrate" }
        & uv @cliArgs
    }
    "dashboard" {
        & uv run streamlit run dashboard/app.py
    }
    default            { Write-Host "Targets: install, check-stack, test, test-integration, test-all, lint, format, typecheck, precommit, ingest-season, ingest-league, ingest, backtest-epl, evaluate-run, diagnose-features, diagnose-shap, dashboard" }
}
