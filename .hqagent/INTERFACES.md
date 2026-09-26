# 接口冻结记录

> 冻结点固定契约，就绪门确认实现可联调，二者不能混用。
> 变更流程见 `docs/分工与并行开工方案.md` §7：任何包发现协议有问题，写 `.hqagent/handoffs/` 变更请求，不得自行在本端加兼容字段。

## FZ-1 — 已冻结

| 项 | 值 |
| --- | --- |
| 协议版本 | `0.1.0` |
| 冻结日期 | 2026-09-05 |
| Git SHA | `a3e1047874e8e900e36f4377bc07cea550b524af` |
| 解锁 | W1 Local Hub 内核、W4 桌面前端、W5 桌面壳、W6 更新模块抽取，四条线可并行开工 |

### 冻结内容

| 类别 | 位置 |
| --- | --- |
| 领域模型 Schema（15 份，118 个类型） | `packages/protocol/schema/` |
| 角色 / 能力 / 错误码注册表 | `packages/protocol/registry/` |
| Local Hub 公共 API（Vue 唯一网络契约） | `packages/protocol/openapi/local-hub.v1.yaml` |
| Update Agent 内部 API | `packages/protocol/openapi/update-agent.internal.v1.yaml` |
| 事件字典与状态迁移表 | `packages/protocol/events/event-dictionary.md` |
| 原子 Contract Fixture（7 个） | `packages/protocol/fixtures/contracts/` |
| 运行时描述符与鉴权（hub.json / update-agent.json / WS Ticket） | `packages/protocol/schema/runtime-descriptor.json` |
| 三端生成 DTO | `packages/protocol/generated/{ts,python,go}` |

### 冻结时的实测结论

不是"应该能用"，是当场跑过：

| 端 | 命令 | 结果 |
| --- | --- | --- |
| TypeScript | `tsc --noEmit`（strict，TS 5.9.3） | 0 |
| Python | pydantic v2 对 7 个 Fixture `model_validate` + 按别名 round-trip | 7/7 |
| Go | `go build ./...` + `go vet ./...`（Go 1.26.4） | 0 / 0 |
| 幂等 | `generate.py` 重跑后 `git diff` 仅剩生成器自身，`generated/**` 零差异 | 通过 |
| 结构 | `validate.py --check-generated` | 通过 |

### 边界要点（最容易做错的四条）

1. **Token 不进响应体。** 前端拿 Hub Token 的唯一途径是 Tauri `invoke('get_hub_endpoint')` 读 `hub.json`。`BootstrapView` 里没有、也永远不会有 token 字段。
2. **WebSocket 不用 Bearer。** WebView 原生 WebSocket 设不了 Header，必须先用 Bearer 调 `POST /api/v1/auth/ws-ticket` 换 30 秒一次性 Ticket，再以查询参数握手。用过即废、过期即废、重放必败。
3. **`/healthz` 是唯一免鉴权端点。** 因为 Update Plan v2 的健康检查要在没有 Token 的情况下探活。它只返回 `status/appVersion/protocolVersion/pid/startedAt`。
4. **Vue 只认 Local Hub 一个 Base URL。** Update Agent 的 9 条更新能力由 Hub 代理，前端不管理第二个端口、第二个 Token、第二条事件序列。

### W4 迁移清单

前端此前手写的 `packages/protocol/generated/ts/index.ts` 已被生成物取代。改动如下，其余保持不变：

| 原写法 | 现在 | 原因 |
| --- | --- | --- |
| 自己声明协议类型 | 从 `@hqagent/protocol` 导入 | 生成物是唯一事实源 |
| `BootstrapView.hubEndpoint.token` | **删除**，改用 Tauri invoke | 循环依赖 + token 会进日志 |
| `BootstrapView.agentsCount / onlineAgentsCount` | `agents.total / agents.ready / agents.issues` | 首屏要能引导用户处理有问题的 Agent |
| `reduceMotion: boolean \| 'system'` | `'system' \| 'on' \| 'off'` | 联合类型在 Python/Go 侧无法干净生成 |
| `UpdatePhase`（9 值） | 18 值，补齐 OTA §6 状态机 | 缺 `verifying`/`waiting_user`/`health_checking`/`rolling_back` 等，W6 实现会对不上 |
| `UpdateActionInput` 含 `pause/resume/retry` | `check/download/cancel/install/defer/acknowledge` | 与 OTA 的 9 条细路径一一对应 |
| 事件 `approval.requested` | `approval.required` | 与施工方案 §8.3 统一 |
| `TaskNodeView.status: TaskStatus` | `NodeStatus` | 节点有 `resolving`/`skipped`，任务没有 |
| `fixtures/*.json` | `fixtures/contracts/*.json` | 原子 Fixture 与 UI 组合场景分层 |
| UI 场景数据 | 放 `apps/desktop/src/**/scenarios/`，引用原子 Fixture | 协议目录不放 UI 状态 |

保留未动：`UiGateway` 方法签名、View 模型命名与 `id` 字段风格、`PageResult<T>`、`resolveSource` 六值、`TaskSource`、`RiskLevel`、`ContrastMode`、`FontScale`、四套 palette 名（`hq-blue`/`ai-violet`/`tech-cyan`/`ops-emerald`）、`UserSettingsView` 五分组、`drainProgress.step` 五步。

`UiGateway` 与 ViewModel 属于前端应用层，手写，不由 Schema 生成（裁决 D10）。

## FZ-2 — 已冻结（2026-09-06，协议 0.2.0，SHA `bfcd91e`）

解锁 W2（Agent 适配层）与 W3（编排与安全）的正式实现。

### 冻结内容

| 产出 | 说明 |
| --- | --- |
| `packages/protocol/schema/adapter-port.json` | 18 个类型。把施工方案 §7.2 的 8 行签名补成精确契约 |
| `packages/protocol/adapters/adapter-contract.md` | JSON Schema 表达不了的规则，见下 |
| `ORIGIN_NOT_ALLOWED`（403） | 新增错误码，`UNAUTHORIZED` 收窄为「没带对 token」 |
| 裁决 D17–D24 | 见 `.hqagent/DECISIONS.md` |

类型总数 118 → 136。`generate + validate` 通过，7 个 Contract Fixture 全绿。

### 契约规则（表达不了在 Schema 里的部分）

1. **Session 生命周期**：`active ⇄ idle → closed`，`invalid` 单向不可逆。
   新任务默认新会话；`invalid` 后只能新建不能 resume。
2. **两段式取消**：Hub 先 `graceful` 带 `graceSeconds`，到点再 `force`。
   Adapter 不得自行延长。`refused` 必须如实上报，Hub 据此标 `failed` 而非 `cancelled`。
3. **事件流断开二分**：`transport_lost` 保持 `active` 可重连；`agent_exited` 置 `invalid` 不重连。
4. **审批时效归 Hub**；Agent 侧超时报 `kind: agent_error` 并写明来源。
   `requiresApproval` 非空的任务不得派给无 `tool_approval` 能力的 Adapter。
5. **事件字典对 Adapter 只读**（28 条为全集），丢弃填 `dropped: true` 并计数。
6. **路径越界前后两道**：能拦截的写入前拦截，不能的由 Hub 按 `changedFiles` 后置校验。

### 下游必须跟进的改动

| 包 | 改动 | 原因 |
| --- | --- | --- |
| W1 | `apps/hub/core/constants.py` 的 `PROTOCOL_VERSION` 改为从生成包导入 | 现在硬编码 `"0.1.0"`，协议升版会静默失配（D24） |
| W1 | Origin/Host 拒绝改用 `ORIGIN_NOT_ALLOWED`（403），WS 侧关闭码 4403 | 现在 HTTP 返 401、WS 返 403，同条件两种传输不一致（D23） |
| W4 | 无需改动 | `adapter-port.json` 是 Hub 内部端口，Vue 不可见 |
| W5 | 无需改动 | 同上 |

### 仍未冻结的部分

FZ-2 冻结的是**接口形状**，不是各家 Agent 的具体行为。
`docs/Agent适配接入规范.md` §2 的调研矩阵（Claude / Codex 的接入方式、探测命令、
外部会话 ID、流式格式、审批取消语义、结构化结果、已知限制）仍需 W2 实测填满。
实测后若发现形状不匹配，写 handoff 提出，由 W0 决定是否需要 FZ-2.1。

## RD-1 / RD-2 — 未达成

实现就绪门，不是契约。RD-1 要求 Local Hub 的鉴权、bootstrap/events、WS Ticket、Update Proxy、drain/backup 端口可运行；RD-2 要求 Claude/Codex Adapter 与角色/任务/审批闭环可运行。

## 变更历史

| 日期 | 协议版本 | 变更 | SHA |
| --- | --- | --- | --- |
| 2026-09-05 | 0.1.0 | FZ-1 初次冻结 | `f56c891` |
| 2026-09-05 | 0.1.0 | FZ-1 重新裁切：补齐 W1/W5 规格要求的 EVENT_CURSOR_EXPIRED、FEATURE_UNAVAILABLE、`instanceId`、`FeatureAvailability`、`waitPids`/`backupCompleted`、Session `status`。**在任何工作包开工之前完成**，因此不构成破坏性变更 | `a3e1047` |


## R1-P0 远程协议预检：未冻结（2026-09-26）

- 状态：needs-decision；协议仍为0.5.0；冻结SHA：无。
- 设计基线855d871，代码基线6f38217；阻断证据提交`302ae4403c911d27e883aaa615738eba93542d27`（不是冻结SHA）。
- 草案长期Task/独立Attempt与当前LocalRun→Task实现不同；取消recovery_required与FZ-2、现有TaskStatus及实际取消实现不同，需明确映射。
- 按本轮“文档与代码不符即指出并停下”要求记录证据，未修改业务代码或生成未经裁决的0.6.0类型。
- 证据、两项待决问题及基线真实输出：[R1-P0回执](handoffs/R1-P0-remote-protocol.md)。
- **本记录不解锁P1服务端、P2 Worker连接、P3 Web B阶段的远程协议实施门。**
