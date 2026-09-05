# 接口冻结记录

> 冻结点固定契约，就绪门确认实现可联调，二者不能混用。
> 变更流程见 `docs/分工与并行开工方案.md` §7：任何包发现协议有问题，写 `.hqagent/handoffs/` 变更请求，不得自行在本端加兼容字段。

## FZ-1 — 已冻结

| 项 | 值 |
| --- | --- |
| 协议版本 | `0.1.0` |
| 冻结日期 | 2026-09-05 |
| Git SHA | `f56c891b336dd42aa112bc019bfcdc56e1ebc38d` |
| 解锁 | W1 Local Hub 内核、W4 桌面前端、W5 桌面壳、W6 更新模块抽取，四条线可并行开工 |

### 冻结内容

| 类别 | 位置 |
| --- | --- |
| 领域模型 Schema（15 份，114 个类型） | `packages/protocol/schema/` |
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

## FZ-2 — 未冻结

Adapter Port 方法签名、Session 生命周期细则、能力探测规则、取消/审批/事件映射。
产出物为 `docs/Agent适配接入规范.md`，由 W2 调研后补齐，冻结后 W2/W3 才进入正式实现。

## RD-1 / RD-2 — 未达成

实现就绪门，不是契约。RD-1 要求 Local Hub 的鉴权、bootstrap/events、WS Ticket、Update Proxy、drain/backup 端口可运行；RD-2 要求 Claude/Codex Adapter 与角色/任务/审批闭环可运行。

## 变更历史

| 日期 | 协议版本 | 变更 | SHA |
| --- | --- | --- | --- |
| 2026-09-05 | 0.1.0 | FZ-1 初次冻结 | `f56c891` |
