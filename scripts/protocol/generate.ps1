# 重新生成协议边界 DTO。
#
# 用法：
#   pwsh scripts/protocol/generate.ps1
#
# 生成范围：packages/protocol/generated/{ts,python,go}
# 事实源：  packages/protocol/{VERSION,registry,schema}
#
# 生成物必须提交进版本库。CI 执行 validate.ps1 -CheckGenerated 时会重新生成
# 并逐字节比对，不一致即失败——这条门禁是为了防止有人手改 generated/**。

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Push-Location $repoRoot
try {
    python -X utf8 (Join-Path $PSScriptRoot 'generate.py')
    if ($LASTEXITCODE -ne 0) { throw "协议生成失败，退出码 $LASTEXITCODE" }
}
finally {
    Pop-Location
}
