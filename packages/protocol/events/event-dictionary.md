# HQAgent-Hub 事件字典

> 本文件是事件语义的**唯一事实源**（裁决 D4）。Schema 定义结构，本文件定义"什么时候发、发了之后状态怎么变"。
> 协议版本 `0.1.0`。改动走 `.hqagent/handoffs/` 变更流程，不得由消费方自行扩展。

## 1. 包络

所有事件共用一个包络 `HubEvent`（见 `schema/envelope.json`）。不存在第二种事件类型。

```jsonc
{
  "eventId": "evt_0003",              // 全局唯一，相同 eventId 不得重复应用
  "seq": 40,                          // Hub 内单调递增，由 events 表自增列提供
  "occurredAt": "2026-09-05T18:04:30Z",
  "aggregateType": "task",            // 路由与订阅过滤用
  "aggregateId": "task_20260905_001",
  "type": "agent.started",            // 见下表
  "payload": { },                     // 结构由 type 决定，见下表
  "protocolVersion": "0.1.0",
  // 以下为业务标识冗余，前端时间线直接用，不必挖 payload
  "taskId": "task_20260905_001",
  "nodeId": "node_02",
  "roleId": "general_implementer",
  "agentInstanceId": "agent_codex_default",
  "adapterId": "codex"
}
```

### 1.1 seq 与补发

- `seq` 由 Local Hub 单一分配，全局单调递增，**不因进程重启而回退**。
- 客户端断线重连时携带最后确认的 `seq`，Hub 返回 `(after, now]` 区间的事件。
- Update Agent 自己不分配 `seq`。它的事件由 Local Hub 消费后重新包装、分配 `seq` 再入总线。
- 保留策略：默认 7 天或 20 万条，超出归档。客户端拿到 `hasMore=true` 时应继续拉，直到追平。
- 相同 `eventId` 必须幂等：重复投递不得产生第二次状态迁移。

### 1.2 未知事件

适配器产生的、映射表里没有的原生事件，**必须降级为 `agent.progress`** 并把原文放进 `payload.raw`，不得静默丢弃。前端遇到未知 `type` 时按 `agent.progress` 渲染。

## 2. 业务事件

| # | type | aggregateType | payload | 触发方 | 说明 |
|---|------|---------------|---------|--------|------|
| 1 | `task.created` | task | `TaskCreatedPayload` | Orchestrator | 任务落库后立即发 |
| 2 | `task.claimed` | task | `TaskCreatedPayload` | Cloud（**Phase 2 预留**） | 一期不产生。云端把离线队列任务下发给本机 Runner 时使用 |
| 3 | `node.resolved` | task | `NodeResolvedPayload` | Role Resolver | **必须带 `resolveSource`**，前端要展示"为什么用了这个 Agent" |
| 4 | `agent.started` | task | `AgentStartedPayload` | Adapter | 带 `sessionId`/`purpose`/`reusePolicy`，用于验证会话隔离 |
| 5 | `agent.progress` | task | `AgentProgressPayload` | Adapter | 高频事件，前端用虚拟列表；也是未知事件的降级目标 |
| 6 | `agent.tool_call` | task | `AgentToolCallPayload` | Adapter | 工具调用可见性 |
| 7 | `agent.question` | task | `AgentQuestionPayload` | Adapter | Agent 需要人回答，任务进入 `waiting_approval` 之外的等待 |
| 8 | `approval.required` | approval | `ApprovalRequiredPayload` | Permission Engine | 注意是 `required` 不是 `requested` |
| 9 | `approval.resolved` | approval | `ApprovalResolvedPayload` | 用户 | 批准或拒绝 |
| 10 | `agent.completed` | task | `AgentCompletedPayload` | Adapter | 单个节点成功，带完整 `AgentResult` |
| 11 | `agent.failed` | task | `AgentFailedPayload` | Adapter | 单个节点失败，带 `errorCode` |
| 12 | `task.path_violation` | task | `PathViolationPayload` | Worktree Manager | 越界修改。发这条事件即判定任务失败，且**保留 worktree 现场** |
| 13 | `task.status_changed` | task | `TaskStatusChangedPayload` | Orchestrator | 所有状态迁移都要发，见 §4 |
| 14 | `task.completed` | task | `TaskStatusChangedPayload` | Orchestrator | 终态，等价于 `status_changed(to=succeeded)` 的语义化别名 |
| 15 | `task.failed` | task | `TaskStatusChangedPayload` | Orchestrator | 终态 |
| 16 | `agent.discovery.completed` | agent | `AgentDiscoveryCompletedPayload` | Agent Registry | 探测完成，前端刷新 Agents 页 |
| 17 | `system.maintenance` | system | `SystemMaintenancePayload` | Hub | 进入/退出维护模式，前端据此显示全局 Gate |

## 3. 升级事件

对应 `docs/OTA升级架构设计.md` §13.2 的 11 个事件。全部由 Update Agent 产生、Local Hub 转发。

| # | type | aggregateType | payload | 说明 |
|---|------|---------------|---------|------|
| 18 | `update.state.changed` | update | `UpdateStateChangedPayload` | 状态机迁移，带 `previousPhase` |
| 19 | `update.download.progress` | update | `UpdateDownloadProgressPayload` | 高频，前端节流渲染 |
| 20 | `update.verification.completed` | update | `UpdateVerificationCompletedPayload` | 大小 / SHA-256 / Ed25519 三项分别给结果 |
| 21 | `update.tasks.draining` | update | `SystemMaintenancePayload` | 排空进度，带 `drainProgress` |
| 22 | `update.install.ready` | update | `UpdateStateChangedPayload` | 排空完成，可以启动 Updater |
| 23 | `update.health_check.started` | update | `UpdateHealthCheckPayload` | 新版本启动后自检开始 |
| 24 | `update.health_check.failed` | update | `UpdateHealthCheckPayload` | 自检失败，接下来必然是回滚 |
| 25 | `update.rollback.started` | update | `UpdateRollbackPayload` | 开始恢复程序和升级前数据库备份 |
| 26 | `update.rollback.completed` | update | `UpdateRollbackPayload` | 带 `succeeded` 与 `restoredDatabaseBackup` |
| 27 | `update.completed` | update | `UpdateCompletedPayload` | 带完整回执，等待用户 acknowledge |
| 28 | `update.failed` | update | `UpdateStateChangedPayload` | 带 `errorCode` |

## 4. 事件 → 任务状态迁移

`TaskStatus` 只能由下表驱动。**事件类型不是状态值**：`task.claimed`、`node.resolved` 这类事件不对应任何 `TaskStatus`。

| 当前状态 | 事件 | 新状态 |
|---------|------|--------|
| （无） | `task.created` | `queued` |
| `queued` | `agent.started` | `running` |
| `running` | `approval.required` | `waiting_approval` |
| `waiting_approval` | `approval.resolved(approve)` | `running` |
| `waiting_approval` | `approval.resolved(reject)` | `failed` |
| `waiting_approval` | 审批超时 | `failed`（`APPROVAL_EXPIRED`） |
| `running` | 用户暂停 | `paused` |
| `paused` | 用户继续 | `running` |
| `running` / `paused` / `waiting_approval` | 用户取消 | `cancelled` |
| `running` | `task.path_violation` | `failed`（`PATH_NOT_ALLOWED`，保留现场） |
| `running` | `agent.failed`（最后一个节点） | `failed` |
| `running` | `agent.completed`（全部节点完成） | `succeeded` |

未在表中出现的迁移一律非法，Hub 必须拒绝并记录 `TASK_ACTION_INVALID`。

`unknown` 是前向兼容值：客户端遇到本版本不认识的状态时落到 `unknown`，正常显示而不是崩溃，**服务端不得主动产生它**。

## 5. 节点状态

`NodeStatus` 比 `TaskStatus` 多两个值，不能复用：

| 状态 | 含义 |
|------|------|
| `pending` | 节点已创建，尚未开始解析角色 |
| `resolving` | Role Resolver 正在解析（`TaskStatus` 里没有对应值） |
| `running` | Agent 执行中 |
| `waiting_approval` | 等待审批 |
| `succeeded` / `failed` / `cancelled` | 终态 |
| `skipped` | 因前序失败或策略跳过（`TaskStatus` 里没有对应值） |

## 6. 会话隔离的可观测性

裁决 D7 要求"新任务默认新会话，同一 Agent 承担实现与审核时必须是两个独立会话"。这条约束靠事件可验证：

- 同一 `taskId` 下，`roleId=general_implementer` 与 `roleId=reviewer` 的两条 `agent.started`，其 `payload.sessionId` 必须不同。
- 若两者 `agentInstanceId` 相同而 `sessionId` 相同，即为违规，INT-2 集成验收判定失败。
- `payload.reusePolicy` 为 `resume_explicit` 时，必须能在事件流中找到用户的显式恢复动作。

## 7. 变更记录

| 日期 | 协议版本 | 变更 |
|------|---------|------|
| 2026-09-05 | 0.1.0 | 初版。合并施工方案 §8.3 的业务事件与 OTA §13.2 的升级事件；`approval.requested` 更名为 `approval.required`；新增 `node.resolved`、`task.path_violation`、`task.status_changed`、`agent.tool_call`、`agent.discovery.completed`、`system.maintenance`；补齐事件到状态的迁移表 |
