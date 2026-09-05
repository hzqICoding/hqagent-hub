# 校验协议包。
#
# 用法：
#   pwsh scripts/protocol/validate.ps1                  结构 + 注册表 + Fixture
#   pwsh scripts/protocol/validate.ps1 -CheckGenerated  额外检查生成物是否漂移（CI 用）

param(
    [switch]$CheckGenerated
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Push-Location $repoRoot
try {
    $args = @('-X', 'utf8', (Join-Path $PSScriptRoot 'validate.py'))
    if ($CheckGenerated) { $args += '--check-generated' }
    python @args
    if ($LASTEXITCODE -ne 0) { throw "协议校验失败，退出码 $LASTEXITCODE" }
}
finally {
    Pop-Location
}
