$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Host 'Downloading the pinned workspace-local Python runtime (3.13.9 x64).'
    New-Item -ItemType Directory -Force -Path .runtime | Out-Null
    Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-amd64.zip' -OutFile .runtime\python.zip
    $archiveHash = (Get-FileHash -LiteralPath .runtime\python.zip -Algorithm SHA256).Hash
    if ($archiveHash -ne '91D828C2DA3A029B41699E918674A0CB379C02CF20DAB9C501306885F837402A') { throw 'Python archive checksum mismatch' }
    Expand-Archive -LiteralPath .runtime\python.zip -DestinationPath .runtime\python -Force
    Set-Content -LiteralPath .runtime\python\python313._pth -Encoding ASCII -Value "python313.zip`n.`n..\..\backend`nimport site"
    Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile .runtime\get-pip.py
    & $pythonExe .runtime\get-pip.py
    if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed' }
}
& $pythonExe -m pip install setuptools wheel
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed' }
& $pythonExe -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $pythonExe -m pip install --no-build-isolation --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'Project installation failed' }
npm.cmd ci --prefix frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed' }
npm.cmd run build --prefix frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
Write-Host 'Setup complete. Run scripts\start.ps1 or scripts\reproduce.ps1.'
