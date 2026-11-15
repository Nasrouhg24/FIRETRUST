$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts\setup.ps1 first.' }
$steps = @(
    @('fetch-country','Portugal','--start-year','2000','--end-year','2025'),
    @('fetch-country','Uruguay','--start-year','2022','--end-year','2025'),
    @('build-warehouse'),
    @('run-pilot'),
    @('audit-pairs'),
    @('verify-evidence')
)
foreach ($stepArgs in $steps) {
    & $pythonExe -m firetrust.cli @stepArgs
    if ($LASTEXITCODE -ne 0) { throw "Pipeline step failed: $($stepArgs[0])" }
}
& $pythonExe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
npm.cmd run build --prefix frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
npm.cmd run test:e2e --prefix frontend
if ($LASTEXITCODE -ne 0) { throw 'Browser tests failed (Microsoft Edge must be installed)' }
& $pythonExe scripts\benchmark_api.py
if ($LASTEXITCODE -ne 0) { throw 'Performance benchmark failed' }
