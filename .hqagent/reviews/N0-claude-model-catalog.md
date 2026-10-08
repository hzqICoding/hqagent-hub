# Claude 模型目录查询验收

2026-09-25；集成提交 `11f0cb5`。通过 CLI stream-json 的 initialize control request 获取目录，不发送 user turn，不复用业务 session。使用 safe-mode、空工具和 no-session-persistence；沿用 command_environment 的用户网络配置。超时、错误、调用方取消均清理查询进程，失败返回明确的未验证状态，不生成替代模型。

保留运行时 value（含别名和后缀）作为执行 ID，resolvedModel 仅用于显示；强度只来自 supportedEffortLevels。目录返回不等于当前代理所有模型均可调用。

实际测试输出：
```text
11 passed in 0.35s
169 passed, 4 warnings in 23.62s
```

升级前 drain：ready、activeTasksRemaining=0、backupCompleted=true。升级后真实 HTTP 接口输出：
```json
{
  "verified": true,
  "modelCount": 5,
  "models": [
    {
      "id": "default",
      "efforts": [
        "low",
        "medium",
        "high",
        "xhigh",
        "max"
      ]
    },
    {
      "id": "opus",
      "efforts": [
        "low",
        "medium",
        "high",
        "xhigh",
        "max"
      ]
    },
    {
      "id": "claude-fable-5-1[1m]",
      "efforts": [
        "low",
        "medium",
        "high",
        "xhigh",
        "max"
      ]
    },
    {
      "id": "sonnet",
      "efforts": [
        "low",
        "medium",
        "high",
        "xhigh",
        "max"
      ]
    },
    {
      "id": "haiku",
      "efforts": []
    }
  ]
}
```

前端已有模型和强度下拉消费逻辑，本次未改前端、未做浏览器视觉验收。重新连接并刷新页面后查看“场景与角色”。
