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


## R1 — 已冻结（2026-09-26，协议0.6.0）

**R1 远程协议已冻结，P1 服务端 / P2 Worker 连接 / P3 Web B 阶段可以开工。**

- 契约冻结SHA：`c443e126496c5b5115fe23efed60f9e4a2b4043f`；生成器前置：`068140a`；本分支尚未合并integration/phase1，等待主代理审核。
- 0.6.0远程契约映射到**现有执行内核**；vNext技术方案§4、§5.1是目标模型，不是本轮已迁移的状态机。
- D40：conversationId → runId(LocalRun) → executionTaskId/nodeId/sessionId。旧LocalRunView.taskId不变；不引入Attempt或retryOfRunId。
- D41：执行状态保持TaskStatus/FZ-2；confirmed/rejected/unconfirmed控制结果携带Worker结构化证据，不能解析报错文本猜测。command.completed不是任务成功的同义词。
- 新增86个远程类型、26个错误码；每个新类型均有Fixture。总计251类型、100个Contract Fixture。
- 结构：`packages/protocol/schema/remote.json`；HTTP/Worker WSS绑定：`packages/protocol/openapi/remote-hub.v2.yaml`；关系、授权、顺序及事务语义：[R1契约](../packages/protocol/remote/R1-contract.md)。
- 基线未改业务代码和旧断言：Hub199 passed；前端typecheck通过、201 passed；协议专用120 passed；validate -CheckGenerated通过。
- 完整类型/错误清单、取舍及P2业务接线项：[R1-P0回执](handoffs/R1-P0-remote-protocol.md)。这是协议门，不是远程功能已实现或已部署的声明。
- 历史预检`302ae44`的Q1/Q2已由主代理D40/D41关闭；旧needs-decision状态不再有效。

## FZ-R1.1 / 0.6.1 — 已冻结（2026-09-26）

**FZ-R1.1 / 0.6.1 已冻结。P2 与 P3-B 的本机配对界面以此为准。**

- 契约冻结 SHA：`7bfbe953df9cbdfca74cee81e9db6632db69f8d2`；基线 `872a909`，分支 `feat/remote-protocol`，未合并 integration/phase1。
- D42：27 个 Worker 帧使用整数 wireRevision=1。仅 hello 的 protocolVersion 保留为 semver 诊断信息；helloAck 回显修订，helloRejected 带 supportedWireRevisions。修订内结构冻结，升级窗口支持 N 与 N-1，包版本不决定线路兼容性。
- P1 修改握手、帧派发与回执构造的版本判断。浏览器 remote-hub.v2.yaml 未修改。
- D43：本机 v1 新增连接查询、配对、取消配对、解绑四个操作；7 个新类型；事件 remote.link.changed；LocalConversationView.authority 可选、缺省 local。沿用现有 v1 鉴权，视图与事件不暴露凭据。解绑不把已有 remote 对话降级为 local，本机只读。
- 继续遵守 D40/D41：远程契约映射现有执行内核；vNext 技术方案 §4、§5.1 为目标模型，本轮不迁移。
- 验证：258 类型 / 109 Fixture；协议 187 passed；Hub 199 passed；前端 typecheck 通过，41 文件 / 201 passed。
- [FZ-R1.1 回执](handoffs/R1-FZ11-remote-protocol.md) 记录输出来源、下游接线与待确认项。本次是协议冻结，不表示远程功能已实现或部署。

## FZ-R1.2 / 0.6.2 — 已冻结（2026-09-26）

**FZ-R1.2 / 0.6.2 已冻结；P2 与 P3-B 的本机浏览器配对入口以此为准。**

- 冻结 SHA：`1e00d2c20ca346e4ab37cc690d59a1e2b2fac64f`。已先用 merge `96b7adfd886b75db91efe7d4423282be810889fa` 合入 integration/phase1@`b84fe9137bcc35e0bb97f9f149d75476ca358c8d`；本次改动仅在 feat/remote-protocol，尚未合回集成分支。
- D44：四个本机 Cookie 等价操作位于现有 `packages/protocol/openapi/local-chat.v2.yaml`：GET /api/v2/remote/link、POST/DELETE /api/v2/remote/pairing、POST /api/v2/remote/unlink。复用 D43 DTO/错误码、本机 localSession 鉴权、Origin 和 Idempotency-Key；成功和错误响应都 no-store。允许轮询 GET link。
- 本机 Local Hub 的 v2 与云端 Hub Server 的 remote-hub.v2 是不同服务，Cookie 不可互换。本机 v1 Bearer 保留给桌面壳/诊断；remote.link.changed 不变。FZ-R1.1 接线事项2的协议缺口已由 D44 关闭。
- wireRevision 仍为 1；没有新增类型、错误码或 Fixture，没有修改云端 HTTP、v1 路由或现有执行内核。D40/D41 仍有效，vNext 技术方案 §4、§5.1 为目标模型。
- 本轮实测：validate -CheckGenerated 通过（258 类型 / 109 Fixture）；协议 198 passed；Hub 270 passed / 4 个已有 warning。前端验证依任务要求交主代理，本轮未启动 Vitest。
- [FZ-R1.2 回执](handoffs/R1-FZ12-remote-protocol.md) 含完整命令、输出与下游要求；新 Cookie 路由的业务实现和真实联调由 P2/P3 承担，本次只冻结契约。

## FZ-R1.3 / 0.6.3 — 已冻结（2026-09-26）

**FZ-R1.3 / 0.6.3 已冻结；P1 快照填充与 P3-B 审批对账以此为准。**

- 冻结 SHA：`500bf1f215fd6d96eb80f9e8677401e57229aa19`。已通过 merge `d442bdc311c4cbd59ee398a730858da880e03b19` 合入 integration/phase1@`dd12a2e0dba162078339d7d7c81306926da3af5e`；本次提交仍在 feat/remote-protocol，未合回集成分支。
- D45：RemoteConversationSnapshot 增加可选 approvals: RemoteApprovalView[]，只含该对话当前 pending 且未过期的审批，最多 100 条，超出以 hasMore 表达。字段缺省按空数组处理，快照初始化后用增量审批事件更新；消费、失效或过期项不再入快照。
- 不新增列审批路由、类型或错误码；保留 RemoteApprovalView 的通用状态语义。高风险不可远程 approve 的 pending 项仍可见并可依现有规则 reject。wireRevision 仍为 1，所有 Worker 帧不变。
- 实测：validate -CheckGenerated 通过（258 类型 / 110 Fixture）；协议 212 passed；Hub 285 passed / 4 warnings；server 85 passed / 1 warning。未启动 Vitest，前端验证交主代理。
- [FZ-R1.3 回执](handoffs/R1-FZ13-remote-protocol.md) 附真实输出、测试调整说明及下游验收项。P1 尚未填充该字段；本次服务端回归通过证明可选字段兼容，不代表审批补全业务已实现。

## 已作废：R1.5 v0.3 镜像+接力草稿（9bb608d / bf15428）

> 以下是历史记录，不是当前状态。v0.4取代该方案；Q1已按D49建议B解决，当前冻结见下一节。

- 已合入 integration/phase1@`ab889b3a04ebf50ee4246dc8e3f27a10751b096c`，merge `d495c051f836ddf4ca25a992d1cceef4fbe0a097`；本分支尚未合回集成。
- **没有0.7.0冻结SHA，P1/P2/P3不可据此记录按新协议开工。** VERSION仍为0.6.3，线路仍只有修订1，Schema、注册表与生成物均未改动。
- Q1：新增接力/镜像专用错误码会经公共ErrorCode扩大rev1 DTO可接受值域，和“rev1 DTO一字不改且不放宽严格性”冲突。需主代理选择注册表值域例外，或授权独立rev1冻结错误类型及保持线路行为的引用调整。
- 只读证据提交：`9bb608dcca8be3cb89110934dd6f9f83ce8f27ea`，不是协议冻结提交。D46已登记；D47登记产品方向及协议待裁决状态。
- [R15-P0回执](handoffs/R15-P0-remote-protocol.md) 含复现、选项和接续事项。未运行发布门禁全套，未启动Vitest；等待Q1裁决后继续，不用0.6.3结果冒充0.7.0验证。


## R1.5 / 0.7.0 — 已冻结（v0.4，2026-09-27）

**R1.5 协议 0.7.0 已冻结，P1 / P2 / 前端可开工。**

- 冻结SHA：`4e597fb5e88a315a271d39528d43e7846d53aa40`；基线integration/phase1@`8d2058f43f7bd94028b4d3fd1fd2bac65e6b1992`，开工merge为`2c839b1e402d52e585ab9afd8d4edb5b74145c34`。提交仍在feat/remote-protocol，未合回integration。
- D46扫码只改前端；D47电脑唯一写入、完整副本、两端继续、完整忙碌集合、显示可见性；D48撤销本机remote只读与新提交的离线排队；D49独立冻结修订1错误值域。旧镜像+接力和Q1待裁决状态全部作废。
- 线路支持1/2；rev2独立DTO/union，39个具体帧；原27个rev1帧仅做批准的错误引用替换，110份旧Fixture不变。63个新类型都有Fixture，共321类型/173Fixture。
- 全文分段拼齐才发布；关闭/删除通过无正文覆盖记录及栅栏避免复活并维持连续ACK。30秒送达要求使用provisional→持久grant→正式接单门闩，ACK不作许可。服务端不持有对话锁，忙碌以电脑最新完整集合覆盖。
- 协议304 passed；Hub285 passed/4 warnings；Server110 passed/1 failed/1 warning，唯一失败是P1尚未适配新HTTP绑定，详见回执。前端测试依分工由主代理运行，未启动Vitest。
- [当前契约](../packages/protocol/remote/R1.5-contract.md)、[覆盖后的回执](handoffs/R15-P0-remote-protocol.md)、[复核与失败证据](reviews/R15-P0-v04-review.md)。冻结的是协议，尚未实现新同步/门闩/分页/忙碌业务，不能把既有测试通过当作新功能已部署。


## 设备管理与Hub Server开放接口 / 0.8.0 — 已冻结（2026-09-28）

冻结SHA：`739756f423dff891963925f75ae24534497e0d6c`，基线`ea63a7293db4097d2a0be5084f29bbbd2dc5c8d2`。D50已登记；P1服务端/P3前端可按此适配，P2 Worker无需业务改动。仍在feat/remote-protocol，未合回integration。

- 标准设备GET/PATCH/DELETE、暂停/恢复、服务端别名与version CAS；旧revocations deprecated。删除后从列表移除且统一NOT_FOUND，最小墓碑不对外；暂停保持连接同步，取消运行/拒绝审批豁免。
- 账号PAT仅Cookie管理，明文首次201返回一次，同键重放200仅metadata；六个设备操作开放精确devices:read/manage/delete，不包含其它资源。Cookie与Bearer歧义拒绝。
- 完整规范覆盖27个已有＋6个新增HTTP操作，72个错误码，公开OpenAPI bundle与源码可校验一致；requestId/header/日志贯通纳入P1实现要求。Worker修订仍[1,2]，两个旧错误值域不受HTTP新码扩展。
- 本轮完整验证：335类型/189Fixture，API规范检查通过，43专项测试通过；173份旧Fixture不变。未运行应用/前端测试，未宣称新功能已部署。
- [接口指南](../packages/protocol/remote/api-guide.md)、[协议增量](../packages/protocol/remote/R1.5-contract.md)、[交接回执](handoffs/R15-P0-devices.md)。


## R3 / 0.9.0 — 原生会话与授权项目登记已冻结（2026-09-29）

冻结SHA：`77e505348c518fed72a463820bbd0fb50eb0f94d`。R3协议0.9.0已冻结，P1服务端 / P2 Worker与Hub / P3前端可按契约开工，等待主代理审核；未合回integration。D51已登记。

独立线路3，支持[1,2,3]；旧线路及189份Fixture不变。91个新类型、48个具体帧；索引可靠同步，历史/目录查询临时不落盘；完整导入、精确续接、关闭确认与单写进程、电脑本机授权根和受限逐层登记。

本轮复跑validate通过（426类型/288Fixture）、API通过（33现有+6新增HTTP，81错误码）、专项191 passed。额外旧集301 passed/3 failed，三项在2b3377c基线均复现，不是本次回归；具体证据及P1/P2/P3实施要求见[回执](handoffs/R3-P0-protocol.md)。冻结的是协议，不代表R3业务已实现。


### R3返修1验收更新（2026-09-29）

三个历史测试前提已修正，未改协议冻结SHA、未删除/skip/xfail测试。全量packages/protocol/tests与scripts/protocol/tests：**495 passed in 28.98s**；validate（426类型/288Fixture）和api-contract均通过。原301/3记录仅为历史证据，不再是当前失败状态，详见R3-P0回执“返修1”。


## R3本机接口补冻 / 0.9.1（2026-09-29）

冻结SHA：`271c9046e3bb9d7be62e563c2962a2a7dd3e030e`。D51补充已登记；P2 Q1关闭，P2/P3可按本机v1/v2列表、详情、读取、同步201导入接口实施。新增LocalNativeSessionPage；本机使用独立于配对/线路，3不可用时延迟同步。线路仍3，既有帧不变。全量498 passed；validate 427类型/289Fixture、api-contract均通过。详见[R3-P0回执补冻节](handoffs/R3-P0-protocol.md)。未合回integration。


## R3错误语义补冻 / 0.9.2（2026-09-30）

冻结SHA：`ec10a24b4730874080234c26242ce79edc311750`。云端原生列表/详情/读取同步关闭统一409 REMOTE_SYNC_DISABLED（这台电脑已关闭同步），认证/归属在前，设备删除404优先，暂停不影响读取；同步开启无会话返回空页/未知ID404。线路与本机接口不变。P1实现三个门禁，P3确认已有错误展示。全量501 passed；validate 427类型/289Fixture与api-contract（39现有接口、81错误码）均通过。详见回执“补冻0.9.2”，未合回integration。


## R1.6 对话附件 / 0.10.0 — 已冻结（2026-09-30）

冻结SHA：`fa1b327ddb10742d7a90a09de78a624f7a8f1ee5`。wireRevision 4，支持[1,2,3,4]；方案中的3已由R3占用。D52记录Q1：暂停禁手机上传/发送，Worker已有用户消息的附件同步继续，下载两端不受影响。P1/P2/P3可按契约开工，未合回integration，待审核。

80新类型、48个修订4帧、84份合成Fixture；原1/2/3闭包和289份Fixture不变。清单走WSS、字节走鉴权HTTPS；有界准备/取消/恢复、能力三层验证、逻辑配额与CAS引用、真删除、电脑/手机双向及本机接口一并定义。

验证：507类型/373Fixture；api-contract 39现有+8新增HTTP、92错误码；全量608 passed。此为协议验收，不是CLI图片或业务真删除已完成。见[R1.6契约](../packages/protocol/remote/R1.6-contract.md)、[回执与下游实施要点](handoffs/R16-P0-protocol.md)。


## 0.10.1 本机维护接口补冻（2026-10-02）

冻结SHA：`7f9c8d23dd69a93af5b0f617544465e5dff79345`。D52补充；v1/v2各增加验证矩阵、显式费用确认异步作业、进度、取消，以及CAS删除对话。模型默认选择器省略modelId；实例/型号绑定不跨用，安全诊断不含输出/提示/路径，清理未确认不假取消。删除本机数据及附件，CLI原生日志不动，远端确认状态另列。手机删除为后续needs-decision F1，本轮无云端操作。

线路4不变、无新错误码；16新类型/20合成Fixture；523类型/393Fixture校验通过，协议全量643 passed，api-contract47现有操作通过。P2/P3按[回执0.10.1节](handoffs/R16-P0-protocol.md)实施，未合回integration。


## PI-P0 / 0.11.0 冻结（D53，2026-10-04）

- 冻结SHA：`36c472eb72a4e7c101db26ec62c355b1007b672a`（feat/remote-protocol，未合并integration）。
- PI Runtime协议0.11.0已冻结，Hub适配器/hub-guard、前端、服务端可开工；原生读取实现属于第二期，类型本次一并冻结。
- wireRevision新增5、支持1–5；修订1–4及其递归类型/Fixture不变，4→5须完成双向升级栅栏。
- 当前HTTP/本机DTO使用RuntimeNativeAgentType含pi；旧客户端缺省0.10.1投影，显式X-HQ-Client-Features:pi-v1启用，游标/WS票据绑定能力集。
- provider/modelId按首斜线拆分，pi-rpc-images-v1沿本机五probe；无新HTTP路由、模型凭据或云端模型调用。
- 606类型 / 485 Fixture；validate -CheckGenerated及api-contract通过，全量协议测试768 passed。
- 契约：packages/protocol/remote/PI-contract.md；回执：.hqagent/handoffs/PI-P0-protocol.md；真实输出：.hqagent/reviews/pi-p0/。
