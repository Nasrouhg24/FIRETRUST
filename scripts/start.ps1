param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts\setup.ps1 first.' }
if (-not (Test-Path -LiteralPath frontend\dist\index.html)) { throw 'Build frontend first: npm.cmd run build --prefix frontend' }
Write-Host "FIRETRUST: http://127.0.0.1:$Port  API: http://127.0.0.1:$Port/docs"
& $pythonExe -m uvicorn firetrust.api:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
