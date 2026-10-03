[CmdletBinding()]
param(
    [string]$UpdateAgentPath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'Windows is required for the NSIS installer.' }
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$desktopRoot = Join-Path $repoRoot 'apps/desktop'
$coreScript = Join-Path $repoRoot 'apps/hub/packaging/windows/build-core.ps1'
if (-not (Test-Path -LiteralPath $coreScript -PathType Leaf)) {
    throw 'R17-P1 is not integrated: apps/hub/packaging/windows/build-core.ps1 is missing.'
}
if ($env:TAURI_CONFIG) { throw 'Clear TAURI_CONFIG before packaging; validation resource overrides must not enter an installer.' }
$env:CARGO_BUILD_JOBS = '1'
$env:CARGO_NET_OFFLINE = 'true'
$env:CARGO_TARGET_DIR = Join-Path $desktopRoot 'src-tauri/target'
$env:TEMP = Join-Path $repoRoot '.tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null

Push-Location $repoRoot
try {
    # P1 owns this script and its pinned PyInstaller environment. No dependency installation here.
    & pwsh -NoProfile -File $coreScript
    if ($LASTEXITCODE -ne 0) { throw "Hub core packaging failed ($LASTEXITCODE)." }
    $coreDir = Join-Path $repoRoot 'dist/hqagent-core'
    if (-not (Test-Path -LiteralPath (Join-Path $coreDir 'hqagent-core.exe') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $coreDir '_internal') -PathType Container)) {
        throw 'P1 must produce the full PyInstaller onedir bundle (exe + _internal).'
    }
    Set-Location $desktopRoot
    & pnpm build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed ($LASTEXITCODE)." }
    # The frontend has just been built. Avoid building it a second time inside Tauri.
    $overlay = @{ build = @{ beforeBuildCommand = $null } }
    if ($UpdateAgentPath) {
        $agent = (Resolve-Path -LiteralPath $UpdateAgentPath).Path
        if (-not (Test-Path -LiteralPath $agent -PathType Leaf)) { throw 'UpdateAgentPath must be an executable file.' }
        $overlay.bundle = @{ resources = @{ $agent = 'hqagent-update-agent.exe' } }
    } else {
        Write-Output 'Update Agent omitted: get_shell_status will report missing; Hub startup remains available.'
    }
    $overlayPath = Join-Path $repoRoot '.tmp/tauri-windows-build.json'
    $overlay | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $overlayPath -Encoding utf8
    & pnpm exec tauri build --bundles nsis --config $overlayPath
    if ($LASTEXITCODE -ne 0) { throw "Tauri/NSIS build failed ($LASTEXITCODE)." }
    $bundleDir = Join-Path $env:CARGO_TARGET_DIR 'release/bundle/nsis'
    $installers = @(Get-ChildItem -LiteralPath $bundleDir -Filter '*.exe' -File)
    if ($installers.Count -eq 0) { throw "No installer found in $bundleDir" }
    Write-Output "Hub onedir: $coreDir"
    Write-Output "Desktop executable: $(Join-Path $env:CARGO_TARGET_DIR 'release/hqagent-desktop.exe')"
    foreach ($installer in $installers) {
        Write-Output "Installer: $($installer.FullName)"
        Write-Output "SHA256: $((Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash)"
    }
} finally { Pop-Location }
