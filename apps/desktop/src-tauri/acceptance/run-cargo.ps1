param(
    [ValidateSet("fetch", "check", "test", "fmt")]
    [string]$Command = "check",
    [string]$CargoHome = "E:\tmp\hqagent-w5-cargo",
    [string]$RustupHome = "E:\tmp\hqagent-w5-rustup",
    [string]$Cache = "E:\tmp\hqagent-w5-registry-cache"
)

$ErrorActionPreference = "Stop"
$ready = Join-Path (Split-Path -Parent ([IO.Path]::GetFullPath($Cache))) "hqagent-w5-registry-ready.txt"
Remove-Item -LiteralPath $ready -Force -ErrorAction SilentlyContinue
$proxy = Start-Process -FilePath "E:\SoftWare\Python313\python.exe" -WindowStyle Hidden -PassThru -ArgumentList @(
    (Join-Path $PSScriptRoot "cargo_registry_proxy.py"),
    "--cache", $Cache,
    "--ready-file", $ready
)

try {
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $ready)) {
        if ([DateTime]::UtcNow -gt $deadline) { throw "Cargo registry bridge did not start" }
        Start-Sleep -Milliseconds 100
    }
    $port = (Get-Content -Raw -LiteralPath $ready).Trim()
    $env:CARGO_HOME = $CargoHome
    $env:RUSTUP_HOME = $RustupHome
    $env:PATH = "$CargoHome\bin;$env:PATH"
    $env:CARGO_REGISTRIES_CRATES_IO_INDEX = "sparse+http://127.0.0.1:$port/index/"
    $env:CARGO_HTTP_PROXY = ""

    & cargo $Command
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    if ($proxy -and -not $proxy.HasExited) {
        Stop-Process -Id $proxy.Id -Force
        $proxy.WaitForExit()
    }
}
