param(
    [string]$Model = "glm-5.1",
    [int]$Workers = 3,
    [string]$BaseUrl = "",
    [string]$ApiKeyEnv = "",
    [switch]$Resume,
    [switch]$NoSkipReport,
    [switch]$AllowRecordErrors
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python not found: $Python"
}

$EnvPath = Join-Path $Root ".env"
if (-not (Test-Path $EnvPath)) {
    throw ".env not found at project root. Add the API key env var used by config.yaml/llm_profiles first."
}

$EnvText = Get-Content $EnvPath -Raw
if ($ApiKeyEnv -and $EnvText -notmatch "(?m)^$([regex]::Escape($ApiKeyEnv))=") {
    throw "$ApiKeyEnv is not defined in .env"
}

$SafeModel = $Model.ToLowerInvariant().Replace("-", "_").Replace(".", "_")
$FinalDir = "outputs/results/molpatent-240/final"
$LogDir = "outputs/runtime/logs"
New-Item -ItemType Directory -Force -Path $FinalDir, $LogDir | Out-Null

$TestOutput = Join-Path $FinalDir "test.llm_only.$SafeModel.skip_report.json"
$FullOutput = Join-Path $FinalDir "molpatent-240.llm_only.$SafeModel.infringement.json"
$TestLog = Join-Path $LogDir "test_llm_only_$SafeModel.out.log"
$FullLog = Join-Path $LogDir "llm_only_$SafeModel.out.log"

$CommonArgs = @(
    "scripts/run_llm_infringement_dataset.py",
    "--llm-model", $Model,
    "--workers", "$Workers"
)

if ($BaseUrl) {
    $CommonArgs += @("--llm-base-url", $BaseUrl)
}
if ($ApiKeyEnv) {
    $CommonArgs += @("--llm-api-key-env", $ApiKeyEnv)
}
if (-not $NoSkipReport) {
    $CommonArgs += "--skip-report"
}
if (-not $AllowRecordErrors) {
    $CommonArgs += @("--fail-on-record-errors", "--fail-on-llm-errors")
}

Write-Host "[1/3] Syntax check..."
& $Python -m py_compile scripts/run_llm_infringement_dataset.py pipelines/llm_infringement.py tools/llm_client.py
if ($LASTEXITCODE -ne 0) {
    throw "Syntax check failed"
}

Write-Host "[2/3] Smoke test: model=$Model workers=1 output=$TestOutput"
$TestArgs = @(
    "scripts/run_llm_infringement_dataset.py",
    "--output", $TestOutput,
    "--llm-model", $Model,
    "--limit", "1",
    "--workers", "1",
    "--no-resume"
)
if ($BaseUrl) {
    $TestArgs += @("--llm-base-url", $BaseUrl)
}
if ($ApiKeyEnv) {
    $TestArgs += @("--llm-api-key-env", $ApiKeyEnv)
}
if (-not $NoSkipReport) {
    $TestArgs += "--skip-report"
}
if (-not $AllowRecordErrors) {
    $TestArgs += @("--fail-on-record-errors", "--fail-on-llm-errors")
}

& $Python @TestArgs 2>&1 | Tee-Object -FilePath $TestLog
if ($LASTEXITCODE -ne 0) {
    throw "Smoke test failed. See $TestLog"
}

Write-Host "[3/3] Full run: model=$Model workers=$Workers output=$FullOutput"
$FullArgs = $CommonArgs + @("--output", $FullOutput)
if (-not $Resume) {
    $FullArgs += "--no-resume"
}

& $Python @FullArgs 2>&1 | Tee-Object -FilePath $FullLog
if ($LASTEXITCODE -ne 0) {
    throw "Full run failed. See $FullLog"
}

Write-Host "Done."
Write-Host "Test output: $TestOutput"
Write-Host "Full output: $FullOutput"
Write-Host "Full log: $FullLog"
