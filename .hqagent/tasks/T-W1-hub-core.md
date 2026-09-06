# T-W1 Local Hub 内核

| 项 | 值 |
| --- | --- |
| taskId | `T-W1-hub-core` |
| owner | Codex |
| baseCommit | `a3e1047874e8e900e36f4377bc07cea550b524af`（FZ-1） |
| branch | `work/w1-hub` |
| worktreePath | `E:\OtherPro\HQAgent-Hub-worktrees\w1-hub` |
| handoff | `.hqagent/handoffs/T-W1-hub-core.md` |

## allowedPaths

```
apps/hub/core/**
apps/hub/api/**
apps/hub/storage/**
apps/hub/runtime/**
apps/hub/tests/**
apps/hub/pyproject.toml
apps/hub/README.md
```

不要动 `apps/hub/adapters/`、`apps/hub/orchestrator/`、`apps/hub/security/`（W2/W3 的），不要动 `packages/protocol/`（W0 的），不要动 `apps/desktop/`（W4/W5 的），不要动仓库根的共享配置。

## 开工前必读

1. `AGENTS.md` —— 全局边界，与本文件冲突时以 AGENTS.md 为准
2. `.hqagent/PROJECT_CONTEXT.md`、`.hqagent/ARCHITECTURE.md`、`.hqagent/INTERFACES.md`
3. `docs/分工与并行开工方案.md` §5.2 —— 你的完整交付物和 9 条验收
4. `docs/施工方案.md` §5.3、§8
5. `docs/OTA升级架构设计.md` §14（目录布局）、§13.2
6. `packages/protocol/openapi/local-hub.v1.yaml` —— 接口以此为准，已冻结
7. `packages/protocol/events/event-dictionary.md` —— 事件语义与状态迁移
8. `packages/protocol/schema/runtime-descriptor.json` —— hub.json 与鉴权契约

## 范围

进程骨架与单实例、SQLite（WAL / 向前迁移 / 一致性 Backup）、事务事件总线、Local Hub 公共 API 门面、HTTP Bearer + WS Ticket、严格 Origin/CORS、Update Agent 私有代理、bootstrap、维护模式与排空接口。

**不做**：角色解析、Agent 适配、工作流编排——那是 W2/W3。这些能力通过预先冻结的 Port 注入，你实现 Port 定义和空实现即可，但空实现必须在 `BootstrapView.features` 里如实报 `available:false` 并给原因，**不许用空列表伪装成"功能可用但没数据"**。

## 硬约束

1. 数据模型全部 `from protocol.generated.python import ...`，不得手写重复定义。内部领域模型可以手写，但必须经 Mapper 与 DTO 隔离。
2. Vue 只连 Hub。`/api/v1/updates/**` 由 Hub 通过 `update-agent.internal.v1.yaml` 代理 Update Agent，不给前端第二个 Base URL。Update Agent 未运行时返回 `FEATURE_UNAVAILABLE` 并说明原因。
3. `/internal/drain/*` 必须在本包实现，含 checkpoint、WAL checkpoint、SQLite Backup 和完整 `waitPids`。这是 W6 的硬依赖，不能留给 W6 自己补。
4. `seq` 必须与业务状态**同一事务**写入 `events` 表，提交成功后再推送。游标过期返回 `EVENT_CURSOR_EXPIRED` 并给 Snapshot 入口，不许静默丢事件。
5. 运行期不写安装目录，全部写 `%LOCALAPPDATA%\HQAgent-Hub\`；进程要能在 15 秒内被外部干净停止。
6. Token / WS Ticket 不进响应体、不进事件、不进访问日志。
7. 依赖装不上时用镜像：`-i https://pypi.tuna.tsinghua.edu.cn/simple`。

## 验收（逐条自测并交回实测记录）

```powershell
cd E:\OtherPro\HQAgent-Hub-worktrees\w1-hub
pytest apps/hub/tests -q            # 全绿，含对 packages/protocol/fixtures/contracts 的契约测试
```

- [ ] 起停 20 次无残留锁、无端口泄漏
- [ ] 断开 WS 后携带旧 seq 重连，完整补回缺失事件且无重复
- [ ] 过期 seq 返回 `EVENT_CURSOR_EXPIRED`，可经 bootstrap/Snapshot 恢复完整状态
- [ ] 相同 `Idempotency-Key` 重放 3 次只产生一条记录、一份事件
- [ ] 数据库能从 v1 向前迁移到 v2；恢复 v1 用升级前一致性备份，数据不丢
- [ ] 不带 Token 的 HTTP 返回 401；Bearer 能换一次性 WS Ticket；Ticket 重放失败
- [ ] 非允许 Origin 的 HTTP/WS 请求被拒
- [ ] Update Agent 未运行时更新接口返回明确 unavailable；运行后由同一 Base URL 正常代理
- [ ] 排空后 `POST /api/v1/tasks` 返回 `HUB_MAINTENANCE`
- [ ] `GET /healthz` 免鉴权可访问，且只返回 status/appVersion/protocolVersion/pid/startedAt

## 交付

- 在 `work/w1-hub` 上提交。commit message 只描述改动本身，**不要任何 AI 署名、不要 Co-Authored-By、不要 Generated with 字样**。提交后用 `git log -1 --format=%B` 自查。
- 写 `.hqagent/handoffs/T-W1-hub-core.md`：做了什么、没做什么、验收逐条结果（贴真实命令输出）、发现的协议问题（如有）。
- 发现协议需要改动，**不要自己改 `packages/protocol/`**，写进 handoff 提出来。
