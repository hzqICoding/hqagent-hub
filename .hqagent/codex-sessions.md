# Codex 会话登记

派给 codex 的每条线都记在这里，方便后续 `codex exec resume <id>` 复用上下文，
而不是重开一个冷会话把任务书再喂一遍。

恢复命令：

```
codex exec resume <session-id> -C <worktree> - < followup.md
```

复用会话时**不需要**重贴任务书，直接说增量要求即可；但署名禁令要重申一次，
codex 有自己的默认署名行为。

## 一期在跑的会话

| 包 | 会话 ID | 模型 / 档位 | worktree | 派出时间 |
| --- | --- | --- | --- | --- |
| W2 Agent 适配层 | `01a076e4-fb8a-7000-a95a-a068be2fecd8` | `gpt-5.6-sol` / `xhigh` | `w2-adapters` | 2026-09-06 21:25 |
| W3 编排与安全 | `01a076e5-1b87-7470-9d9c-f8388815514d` | `gpt-5.6-sol` / `xhigh` | `w3-orchestrator` | 2026-09-06 21:25 |
| W6 HQUpdateKit | `01a076e5-32e0-7ee1-aadc-65f19d1ca419` | `gpt-6-astra` / `high` | `w6-updatekit` | 2026-09-06 21:25 |

会话文件在 `%USERPROFILE%\.codex\sessions\`，文件名形如
`rollout-<时间戳>-<session-id>.jsonl`。

## 档位怎么选的

| 包 | 难度 | 是否阻塞别人 | 选择 | 理由 |
| --- | --- | --- | --- | --- |
| W2 | 高 | 是，W3 依赖它的 Port 语义 | sol / xhigh | 要先实测调研两家 Agent 的真实行为再实现 8 个方法，D17–D22 每条都有坑，档位低了容易漏边界 |
| W3 | 高 | 否 | sol / xhigh | Role Resolver 六级优先级 + 审批准入 + 路径双层校验，错一级就是信任问题 |
| W6 | 中 | 否 | astra / high | 主要是移植 HQDroidDeck 已验证的 Go 代码，路径清晰；换 NSIS 是唯一新工作。顺带分散模型风险 |

## 已结束的会话

| 包 | 结局 |
| --- | --- |
| W1 Local Hub | 429 限流中断在自测前，代码由 W0 抢救落库并验收 |
| W5 桌面壳 | 429 限流中断在自测前，代码由 W0 抢救、修编译、补测试 |
