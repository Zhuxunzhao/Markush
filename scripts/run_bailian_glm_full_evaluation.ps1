param(
    [string]$Model = "glm-5.1",
    [int]$Workers = 1,
    [int]$RequestTimeout = 240,
    [switch]$Resume,
    [switch]$SkipSmoke
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
    throw ".env not found at project root"
}

$EnvText = Get-Content $EnvPath -Raw
if ($EnvText -notmatch "(?m)^OPENAI_API_KEY=") {
    throw "OPENAI_API_KEY is not defined in .env"
}
if ($EnvText -notmatch "(?m)^OPENAI_API_BASE=https://dashscope\.aliyuncs\.com/compatible-mode/v1\s*$") {
    Write-Warning "OPENAI_API_BASE in .env is not the expected Bailian compatible endpoint."
}

$SafeModel = $Model.ToLowerInvariant().Replace("-", "_").Replace(".", "_")
$FinalDir = "outputs/results/molpatent-240/final"
$LogDir = "outputs/runtime/logs"
New-Item -ItemType Directory -Force -Path $FinalDir, $LogDir | Out-Null

$TestOutput = Join-Path $FinalDir "test.llm_only.$SafeModel.bailian.skip_report.json"
$FullOutput = Join-Path $FinalDir "molpatent-240.$SafeModel.claim_text_first_image.bailian.infringement.json"
$AnalysisOutput = [System.IO.Path]::ChangeExtension($FullOutput, ".analysis.md")
$TestLog = Join-Path $LogDir "test_llm_only_$SafeModel.bailian.out.log"
$FullLog = Join-Path $LogDir "llm_only_$SafeModel.bailian.out.log"
$AnalysisLog = Join-Path $LogDir "analysis_llm_only_$SafeModel.bailian.out.log"

$CommonArgs = @(
    "scripts/run_glm_first_image_infringement_dataset.py",
    "--model", $Model,
    "--base-url", "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "--api-key-env", "OPENAI_API_KEY",
    "--text-source", "claim",
    "--request-timeout", "$RequestTimeout",
    "--workers", "$Workers"
)

Write-Host "[1/4] Syntax check..."
& $Python -m py_compile `
    scripts/run_glm_first_image_infringement_dataset.py `
    scripts/analyze_glm_first_image_experiment.py
if ($LASTEXITCODE -ne 0) {
    throw "Syntax check failed"
}

if (-not $SkipSmoke) {
    Write-Host "[2/4] Smoke test: model=$Model output=$TestOutput"
    $TestArgs = @(
        "scripts/run_glm_first_image_infringement_dataset.py",
        "--output", $TestOutput,
        "--model", $Model,
        "--base-url", "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "--api-key-env", "OPENAI_API_KEY",
        "--text-source", "claim",
        "--request-timeout", "$RequestTimeout",
        "--limit", "1",
        "--workers", "1",
        "--force"
    )

    & $Python @TestArgs 2>&1 | Tee-Object -FilePath $TestLog
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke test failed. See $TestLog"
    }
} else {
    Write-Host "[2/4] Smoke test skipped."
}

Write-Host "[3/4] Full run: model=$Model workers=$Workers output=$FullOutput"
$FullArgs = $CommonArgs + @("--output", $FullOutput)
if (-not $Resume) {
    $FullArgs += "--force"
}

& $Python @FullArgs 2>&1 | Tee-Object -FilePath $FullLog
$FullExitCode = $LASTEXITCODE

if (-not (Test-Path $FullOutput)) {
    throw "Full output was not created. See $FullLog"
}

Write-Host "[4/4] Analysis report: $AnalysisOutput"
& $Python scripts/analyze_glm_first_image_experiment.py `
    --input $FullOutput `
    --output $AnalysisOutput 2>&1 | Tee-Object -FilePath $AnalysisLog
if ($LASTEXITCODE -ne 0) {
    throw "Analysis failed. See $AnalysisLog"
}

Write-Host "Done."
Write-Host "Full output: $FullOutput"
Write-Host "Analysis: $AnalysisOutput"
Write-Host "Full log: $FullLog"
