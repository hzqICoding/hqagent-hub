[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Worktree .venv is required; build does not install dependencies.' }
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = ''
$env:PYINSTALLER_CONFIG_DIR = Join-Path $repoRoot '.tmp/pyinstaller-config'
$env:TEMP = Join-Path $repoRoot '.tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
& $python -c "import PyInstaller; assert PyInstaller.__version__ == '6.22.3', 'PyInstaller 6.22.3 required'"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -B -m PyInstaller --noconfirm --clean --distpath (Join-Path $repoRoot 'dist') --workpath (Join-Path $repoRoot '.tmp/pyinstaller-core') (Join-Path $PSScriptRoot 'hqagent-core.spec')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$bundle = Join-Path $repoRoot 'dist/hqagent-core'
$files = Get-ChildItem -LiteralPath $bundle -Recurse -File
$bytes = ($files | Measure-Object -Property Length -Sum).Sum
Write-Output "Bundle: $bundle"
Write-Output "Files: $($files.Count); Bytes: $bytes; MiB: $([Math]::Round($bytes / 1MB, 2))"
