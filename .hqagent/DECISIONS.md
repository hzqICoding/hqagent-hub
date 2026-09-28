# 决策记录

> 记录"为什么这么定"，避免后来者重新讨论已经拍过板的问题。
> D1–D10 的完整论证见 `docs/分工与并行开工方案.md` §8，这里只留结论和落地位置。

## 来自分工方案 §8 的十项裁决

| # | 结论 | 落地位置 |
| --- | --- | --- |
| D1 | 更新接口用 OTA 文档的 9 条细路径；Vue 只认 Local Hub 一个门面，Update Agent 走内部 API | `openapi/local-hub.v1.yaml`、`openapi/update-agent.internal.v1.yaml` |
| D2 | 本地与云端 OpenAPI 分开生成，共享领域模型不共享路径层 | 一期只有 `local-hub.v1.yaml` |
| D3 | Hub 随机端口 + 仅回环 + 启动轮换 Token；HTTP Bearer，WS 换一次性 Ticket | `schema/runtime-descriptor.json` |
| D4 | 事件字典是事件语义唯一事实源，含事件→状态迁移表 | `events/event-dictionary.md` |
| D5 | Antigravity 移出一期关键路径，一期只做 Claude + Codex | `registry` 无特殊处理；Adapter 排期见分工方案 §5.3 |
| D6 | Local Hub 维持 Python，加四条可升级硬约束 | W1 验收项 |
| D7 | 会话按任务血缘管理，新任务默认新会话 | `schema/session.json` |
| D8 | 当前用户级 NSIS，程序装 `%LOCALAPPDATA%\Programs\`，数据与程序生命周期解耦 | W6/W7 |
| D9 | 建立独立版本化 `HQUpdateKit`，两个产品共同依赖 | `E:\OtherPro\HQUpdateKit` |
| D10 | 并行开发用独立 worktree；协议 DTO 生成、UiGateway/UI 场景手写 | 本仓库 worktree 布局 |

## W0 执行期间新增的决策

### D11 线上字段 camelCase，枚举值 snake_case

施工方案 §8 的示例用 snake_case 字段名，前端方案 §13 的包络用 camelCase，两边不一致。

**决定**：线上字段名一律 camelCase，枚举值一律 snake_case 字符串。

理由：前端是协议的主要消费方，且包络字段（`requestId`/`protocolVersion`/`occurredAt`）已经在前端文档里定成 camelCase 并被实现了；Python 侧用 pydantic `alias` 映射，内部照样写 snake_case，成本几乎为零。施工方案 §8 的示例属于设计草稿，按本决定归一。

### D12 自建生成器，不用第三方代码生成工具链

分工方案 §5.1 要求"固定工具及版本"。

**决定**：用仓库自带的 `scripts/protocol/generate.py`（零第三方依赖，仅 PyYAML 读注册表），不用 `datamodel-code-generator` + `json-schema-to-typescript` + `quicktype`。

理由：CI 门禁是 `generate + git diff --exit-code`。外部生成器版本漂移会让同一份 Schema 在不同机器产出不同文本，把门禁变成噪音。代价是只支持本仓库用到的 Schema 子集（不支持 oneOf/anyOf/allOf），需要时先改 Schema 设计或扩生成器，不允许绕过它手写类型。

### D13 architect 角色改为 read_write，但只能写 .hqagent 和 docs

施工方案 §6.5 写 architect 是 `filesystem: read_only`，但 §6.7 又要求"跨端接口先由 architect 更新 `INTERFACES.md`"，两处矛盾。

**决定**：取 `read_write`，用 `writablePaths` 限死在 `.hqagent/**` 和 `docs/**`。architect 依然碰不到任何业务代码。

（这条是协议校验器 `validate.py` 的注册表自检抓出来的，不是人肉审出来的。）

### D14 `/healthz` 是唯一免鉴权端点

Update Plan v2 的 `healthChecks` 要在没有 Token 的情况下探活新装版本。

**决定**：`GET /healthz` 免鉴权，只返回 `status / appVersion / protocolVersion / pid / startedAt`，绝不返回 Token、路径或任务内容。其余 `/api/v1/**` 与 `/internal/**` 一律鉴权。

### D15 `approval.requested` 更名为 `approval.required`

施工方案 §8.3 用 `approval.required`，早期前端 fixture 用了 `approval.requested`。统一为 `approval.required`。

### D16 `TaskNodeView.sessionKey` 改为 `sessionId`

D7 之后不存在 `workspace:role:agent` 形式的全局会话键了，节点引用的是 Hub 本地会话 ID。

## FZ-2 裁决（2026-09-06，协议 0.2.0）

### D17 `cancel()` 改为两段式，且必须能表达「取消失败」

施工方案 §7.2 的 `cancel(sessionId): Promise<void>` 表达不了取消失败。

**决定**：引入 `CancelMode`（`graceful` / `force`）与 `CancelOutcome` 五值。
Hub 先发 graceful 带 `graceSeconds`，到点未停再发 force，Adapter 不得自行延长宽限期。

理由：OTA 排空有超时上限，`waitPids` 必须在有限时间内收敛，一个能无限拖延取消的
Adapter 会让升级流程卡死。

`refused`（底层 Agent 无中断入口）必须如实上报，Hub 据此把节点标为 `failed` 而非
`cancelled`。**不得假装取消成功**——用户以为停了、实际还在改文件，比取消失败更坏。

### D18 事件流断开必须区分 `transport_lost` 与 `agent_exited`

**决定**：`AdapterStreamStatus` 四值。`transport_lost` 保持会话 `active` 并可重连；
`agent_exited` 直接把会话置 `invalid`，不再重连。

理由：混为一谈的后果是二选一——要么把网络抖动误判成任务失败，
要么永远等一个已经死掉的进程。

### D19 审批时效由 Hub 独占，Agent 侧超时是另一类失败

**决定**：`ApprovalRequiredPayload.expiresAt` 由 Hub 设定，Adapter 不得自行判定过期后放行。
底层 Agent 自己超时放弃时，报 `AdapterFailure { kind: agent_error }` 并写明是 Agent 侧超时。

理由：「用户没决定」和「Agent 不等了」对用户的提示完全不同，混成一个码就没法给对提示。

配套硬约束：`requiresApproval` 非空的任务，Hub **不得**派给未声明 `tool_approval`
硬能力的 Adapter。这是 Role Resolver 的准入检查，不是运行时检查——派出去才发现拦不住，
危险动作已经执行了。

### D20 `detect()` 与 `health()` 不合并

**决定**：`detect()` 产出 `AdapterDescriptor`（装没装、版本、能力），开销大可缓存；
`health()` 产出 `AdapterHealth`（存活、登录态），轻量周期调用，不重新枚举能力。

登录态失效走 `health()` 的 `status: not_logged_in` + `authValid: false`，
不得返回 `error` 再把「请先登录」塞进文案——UI 要据此给可操作的登录引导。

### D21 事件字典对 Adapter 只读，丢弃必须显式计数

**决定**：FZ-1 冻结的 28 条事件是全集，Adapter 不得新增类型。
每个 Adapter 必须声明 `VendorEventMapping[]`；无法映射的填 `dropped: true` 并运行时计数。
原始数据只进 `AgentProgressPayload.raw`（诊断字段，上限 2048 字符），UI 不得当主内容渲染。

理由：静默吞事件会让「为什么进度卡住」无从查起。

### D22 路径越界要前后两道，不能只做后置

**决定**：能在写入前拦截的 Adapter 必须拦截并返回 `kind: path_violation`；
不能拦截的由 Hub 在 `collectResult()` 后按 `changedFiles` 校验。两道都要有。

理由：只做后置校验时，发现越界文件已经被改了。

### D23 新增 `ORIGIN_NOT_ALLOWED`（403）

FZ-1 的 `error-codes.yaml` 里没有任何一个码是给「Host / Origin 不在白名单」用的，
W1 只能复用 `UNAUTHORIZED`（401），导致排障时分不清是凭据问题还是来源问题；
且 HTTP 返 401、WebSocket 返 403，同一条件两种传输不一致。
（这是 W1×W5 冒烟查出来的，见 `.hqagent/reviews/INT-smoke-W1xW5.md` R4。）

**决定**：新增 `ORIGIN_NOT_ALLOWED`，HTTP 403，WS 侧以关闭码 4403 表达。
`UNAUTHORIZED` 收窄为「没带对 token」。W1 需相应调整。

### D24 协议版本升到 0.2.0，且只能有一个事实源

FZ-2 新增 18 个类型（118 → 136），属相容扩展，按 semver 升次版本号。

**决定**：`packages/protocol/VERSION` 是唯一事实源，生成物导出 `PROTOCOL_VERSION`。
W1 现在在 `apps/hub/core/constants.py` 里硬编码了 `PROTOCOL_VERSION = "0.1.0"`，
**必须改成从生成包导入**，否则协议升版时会静默失配。

---

## FZ-2.1（2026-09-06）

W2 和 W3 交付时各提了 7 条协议变更请求。**两边互不通信、分别实现、独立提交**，
其中第一条逐字相同——这是把冻结契约重新打开的充分理由。去重后 13 条，逐条裁决如下。

裁决人 W0。依据：W2 `.hqagent/handoffs/T-W2-adapters.md` §「FZ-2.1 候选」、
W3 `.hqagent/handoffs/T-W3-orchestrator.md` §「FZ-2.1 协议变更请求」。

### D25 `AgentTaskSpec` 增加必填 `sessionId`（W2#1 = W3#1，双方独立提出）

`AgentSessionHandle.sessionId` 的描述是「Hub 生成后传给 Adapter」，但 `start()` 的唯一
入参 `AgentTaskSpec` 没有这个字段，八个方法也没有别的传入通道。

两个包被迫做了同一件事：W2 只能由 Adapter 自己生成 `session_<uuid>`，
W3 只能接受 `start()` 返回的本地 ID。**结果是会话身份的所有权从 Hub 漏到了 Adapter。**

这不是美观问题。D7 要求「同一 Agent 承担实现与审核时必须是两个不同会话」——
这个约束只有 Hub 能保证，Adapter 不知道自己这次是在实现还是在审核。
所有权一漏，D7 就失去了强制手段。

**决定**：`AgentTaskSpec` 增加 **required** `sessionId`。不是可选——可选会让两种
所有权模型并存，等于没裁决。Adapter 收到什么就用什么，不得自行生成。

### D26 `TaskActionInput` 的 `pause` / `append_instruction` 收窄语义，不给 Adapter Port 加方法（W3#2）

冻结的 `TaskActionInput` 有 `pause` 和 `append_instruction`，但 Adapter Port 没有
对应方法。用 `cancel()` 假装 pause 会把 Session 关掉，是欺骗。

**决定**：不加 `pause()` / `sendInstruction()`。多数 CLI Agent 没有真正的暂停语义，
加了会逼每个适配器假装实现——这正是 D17 要避免的那类谎报。改为收窄动作语义：

- `pause`：只作用于**节点之间**。当前节点跑完就停住，不打断正在执行的 Agent。
- `append_instruction`：只在节点 idle 时可用，运行中必须拒绝（`TASK_ACTION_INVALID`）。

前端据此做按钮禁用态，不承诺做不到的事。

### D27 成功取消不发 `agent.failed`（W3#3，关联 W2#7）

原事件规则要求成功取消也产生 `agent.failed`，其 `errorCode` 映射
`AdapterFailureKind.cancelled`；但 `ErrorCode` 里没有取消对应码。

**决定**：**取消是正常路径，不是失败。** 成功取消只发
`task.status_changed(to=cancelled)`，不发 `agent.failed`，也不新增取消错误码。
修订事件字典里那条规则。`refused` 仍用 `TASK_NOT_CANCELLABLE`，并按 FZ-2 保留
`orphanProcessIds`。

W2#7 问「要不要区分『无中断入口』和『已发中断但 grace 到点仍在跑』」：
**不新增 outcome**。两者对 Hub 的下一步动作完全相同（升级到 force），
区别只是诊断信息，放 `CancelResult.detail` 即可。枚举值要为决策服务，不为叙事服务。

### D28 `SessionView.externalSessionId` 改为可选（W3#4）

`AgentSessionHandle.externalSessionId` 在不支持恢复时允许缺省，而 `SessionView` 里
是必填字符串。W3 只能填空字符串并令 `isValid=false`。

**决定**：View 字段改可选。空字符串能跑，但让前端无法区分「这个 Agent 不支持恢复」
和「支持恢复但凭据丢了」——Session 页的「继续」按钮该不该出现，取决于这个区别。

### D29 `resume()` 返回 `AgentSessionHandle`，`continue_lineage` 建子会话（W3#5）

`continue_lineage` 有 `parentSessionId` 语义，但 `resume()` 返回 void，
没法创建并关联一个新的 Hub 本地 Session。

**决定**：定为**新建子 Session 并记 `parentSessionId`**，`resume()` 返回
`AgentSessionHandle`。若复用原 Session 记录，lineage（世系）这个词就没有意义了。

### D30 `RoleId` 边界类型回退 `str`，另导出内置角色常量（W3#6）

Schema 明确允许用户自定义角色，但生成器把 `RoleId` 生成成了八值闭枚举，
自定义角色进不了 `TaskNodeView` / `ResolvedTeamView`。

**决定**：这是**生成器的缺陷**，不是 schema 的。边界类型回退 `str`，
另导出内置角色常量供代码引用。Role Resolver 对未知角色按「无内置能力要求」处理。

### D31 删掉 `AdapterDescriptor` 里引用不存在字段的描述（W2#2）

`installed=false` 的描述写「status 必须是 incompatible 或 unknown」，
但 `AdapterDescriptor` 根本没有 `status` 字段。

**决定**：删掉这句描述。发现状态由 `AdapterManager` 组合 health 后生成
`AgentView.status`——这是对的分层（Descriptor 描述「装了什么」，
AgentView 描述「现在能不能用」），不该往 Descriptor 里塞运行时状态。

### D32 冻结 `AdapterEvent` 最小形状（W2#3）

`streamEvents()` 只冻结了终止对象 `AdapterStreamEnd`，没冻结单条事件。
直接产出 `HubEvent` 不对——全局 `seq` / `eventId` 归 W1 分配。

**决定**：冻结 `AdapterEvent`（无 `seq` / `eventId`，由 Hub 补齐）。
不冻结的话，W2 定义一套、W3 消费时再猜一套，接缝正好落在两个包中间。

### D33 `ApprovalRequiredPayload` 增加可选 `externalRequestId`（W2#4）

`ApprovalDispatch.externalRequestId` 要求 Adapter 关联供应商请求，
但 `ApprovalRequiredPayload` 没有这个字段，关联信息在事件里丢失。

**决定**：加可选 `externalRequestId`。W2 当前在内部 `AdapterEvent` 上额外携带，
属于绕路；关联 ID 应当随事件走完全程，否则排障时对不上供应商日志。

### D34 统一「无法映射」的措辞：显式噪声可 drop，未知事件必须降级（W2#5）

D21 / adapter-contract 说无法映射可 `dropped: true`；
`event-dictionary.md` §1.2 又说未知原生事件必须降级为 `agent.progress`、不得丢弃。
两句话打架。

**决定**：按 W2 的实现口径统一，它是对的——

- **已知噪声**（心跳、rate-limit、重放 user 等，Adapter 明确认得出来的）：
  显式 `dropped: true` 并计数。
- **真正未知的事件**：降级为 `agent.progress`，带截断 `raw`，并计数。**不得丢弃。**

区别在于「认得出来所以决定不要」和「不认识」。前者是设计，后者是盲区，
盲区必须留痕。两处文档都改。

### D35 `AgentProgressPayload.raw` 的 2048 上限约束的是序列化总长度（W2#6）

D21 写「raw 上限 2048 字符」，但生成的 Python 类型是 `dict[str, Any]`，
「字符」指什么不明确。W2 当前实现为 `{"vendor": "<截断到 2048 的 JSON 文本>"}`。

**决定**：上限约束的是 **`raw` 序列化后的总长度**，不是某个字符串字段。
保持 `dict` 类型（结构化更有用），在文档里写清是序列化总长。

### D36 `event-dictionary.md` 版本号跟进（W3#7）

页头和示例仍写协议 `0.1.0`。**决定**：随本次一并改到 `0.2.1`。纯文档，无争议。

### 版本与影响面

`AgentTaskSpec.sessionId` 是**必填新增**，对已有 Adapter 实现是破坏性的
（W2 要改 `start()`）。但 W2/W3 都还没并入 integration，此刻改的成本最低——
这正是「先看 W2 交出什么再一次性出 FZ-2.1」要等的时机。

协议版本升 **0.2.1**。虽然含一处破坏性变更，但一期尚未发布任何外部消费者，
按补丁号推进并在此记录，不单独走大版本。

### D37 Gemini CLI 备选路径作废，Phase 1.1 变为单路

**事实**（2026-09-07 实测）：`gemini` CLI `0.58.0` 登录失败，Google 已停止该客户端
对个人版 Code Assist 的支持：

```text
IneligibleTierError: This client is no longer supported for Gemini Code Assist
for individuals. To continue using Gemini, please migrate to the Antigravity
suite of products.
  reasonCode: 'UNSUPPORTED_CLIENT'
  tierId: 'free-tier'
```

CLI 本身的能力是够的——`--output-format stream-json`、`--resume`、`--session-id`、
`--approval-mode`、`--acp` 一应俱全，按施工方案 §7.1 属 1–2 级接入，
比 Claude 那条路还齐。**卡的纯粹是认证。**

**影响**：D5 有两句话，第一句「Antigravity 未经实测，移出一期关键路径」不变；
第二句「Gemini CLI headless JSONL 作为备用方案」（施工方案 §3.2、
分工方案 §106）**作废**。Phase 1.1 从「两条路选一条」变成单路：
想接 Google 的模型只剩 Antigravity 的 sidecar，而它恰恰是 §7.1 里可靠性第 4 级。

**决定**：一期范围不动——四层解耦用 Claude + Codex 互换角色即可证明，
这是 D5 的核心依据，不受本变化影响。

三选一已由用户拍板（2026-09-07）：**选 3——一期就用两个 Agent，
Phase 1.1 的三 Agent 目标后移**。另两个选项存档备查：

1. ~~实测 Antigravity `agentapi`（`language_server.exe agentapi`，本机已存在）~~ 后移
2. ~~换一个接入方式在 1–2 级的第三方 Agent（Phase 3 清单里的 GLM / K3 等）~~ 后移
3. **一期就用两个 Agent，Phase 1.1 目标后移** ← 采纳

无论选哪个，**对外宣传「三 Agent 联动」的前置条件不变**（D5 硬约束）。

**建议顺序**：先把 tasks / sessions / approvals 三个 Port 接完，让真实任务链路
跑起来，再拿第三个 Agent 做「换 Agent 不改工作流代码」的验证——
那时候有闭环可测，比现在盲接强。

### D38 非 Git 工作区只能派只读任务，界面提供一键 `git init`

**背景**：集成时第一个真实任务被 Claude Adapter 的 preflight 拒绝——
`claude_adapter.py:287` 要求写任务必须提供存在的 `worktreePath`。
这不是缺陷，是施工方案 §3.1 第 8 条「每个写任务使用独立 Git worktree、分支和
固定 baseCommit」在起作用。

但协议里 `Vcs` 枚举是 `["git", "none"]`，非 Git 目录是**合法工作区**，
只是拿不到隔离保护。于是需要明确：用户添加一个非 Git 目录时会怎样。

**决定**（用户拍板，2026-09-07）：

- **A**：非 Git 工作区**只能派只读任务**。写任务在 Hub 侧就拒绝，
  错误码 `PATH_NOT_ALLOWED`，理由写清「该目录不是 Git 仓库，无法隔离写任务」。
  不允许「就地直接写」——那等于把 §3.1 第 8 条开一个口子，
  同时丢掉越界校验（`git diff --name-only`）和回滚能力。
- **C**：工作区页面提供**一键 `git init`**。前端 F2 已经有 `.hqagent` 记忆目录的
  一键初始化，这是同一个交互模式，用户不会卡在「知道不行但不知道怎么办」。

**为什么不选「非 Git 就地写」**：worktree 隔离兜的是三件事——多个 Agent 并行改
同一项目不互相踩、跑完能用 `git diff --name-only` 做 `allowed_paths` 越界校验、
干砸了能 `git worktree remove` 干净退出。没有版本控制，「改了什么」这个概念都不存在，
`allowed_paths` 会退化成一句空话。安全约束不能为了方便悄悄放宽。

**影响**：需要补工作区的增删与 `git init` 路由（当前 openapi 只有
`GET /api/v1/workspaces`），属相容扩展，见 FZ-2.2。


### D40 R1远程契约沿用现有执行身份，不引入Attempt（主代理裁决，2026-09-26）

**背景**：vNext技术方案§4中的长期Task/独立Attempt是目标模型；当前每个LocalRun创建执行Task，非终态重试重置Node，终态重试创建子Task。远程定位是通信工具，本轮不迁移执行内核。

**决定**：

- 身份链为conversationId → runId（LocalRun，一轮用户要求）→ executionTaskId/nodeId/sessionId；远程控制和结果使用runId作为用户可见句柄。
- 远程对内核Task的引用叫executionTaskId；现有LocalRunView.taskId不改名、不改变其语义。
- 远程DTO不得包含attemptId，连可选空字段也不提供，不得用Node或Session ID伪造它。
- 终态retry由Worker依现有_create_child逻辑产生子执行Task；command.completed.resultRef报告新引用，parentExecutionTaskId仅映射既有Task.parentTaskId。不发明retryOfRunId。
- 长期Task/Attempt另立后续内核迁移工作包及兼容映射。

**影响**：P1只保存执行引用/投影，P2负责与当前LocalRun/Task对接，P3以runId导航。0.6.0不改变旧DTO或本机执行逻辑。

### D41 R1控制结果与执行状态分离（主代理裁决，2026-09-26）

**背景**：草案cancel_requested/recovery_required不是当前TaskStatus；FZ-2的Adapter refused返回failed，无句柄等场景在内部task spec保存recoveryRequired并将Task置paused。

**决定**：

- 执行状态继续使用现有TaskStatus和FZ-2，不新增recovery_required/cancel_requested等执行状态。
- 远程控制结果独立为confirmed/rejected/unconfirmed，携带executionMayStillBeRunning、orphanProcessIds、结构化evidence、reason与observedAt。
- confirmed必须有实际生效证据；cancel需确认停止或本来已结束，pause需节点边界真正paused。收到请求/写入意图不等于生效。
- Adapter refused报告rejected；无句柄、recoveryRequired、回执不明报告unconfirmed，不靠解析错误文本或failed/paused标签猜测。
- P2从CancelResult/CancelOutcome、orphanProcessIds及TaskService.state的task_spec:<executionTaskId>中取得结构化标记。公开这些信息属于P2后续业务实现，本轮仅定义契约。
- 浏览器分开展示传输状态、控制结果、执行状态。unconfirmed不能发送伪造command.completed；command.completed也不能一概显示成开发成功。

**影响**：保留FZ-2；远程通信层提供显式映射，不替代执行内核。具体字段与命令终态矩阵见packages/protocol/remote/R1-contract.md。


### D42 远程线路修订与协议包版本分离（主代理裁决，2026-09-26）

**背景**：原27个Worker↔Server帧把protocolVersion固定为0.6.0，会使异步部署的服务端/Worker因无关包升级互拒。

**决定**：所有这些帧使用整数wireRevision，本轮const 1。仅hello另带semver格式的protocolVersion用于诊断，不能参与版本协商。helloAck回显接受的修订；helloRejected带supportedWireRevisions，尤其REMOTE_PROTOCOL_UNSUPPORTED时不得省略。修订内帧结构冻结，严格校验下加可选字段也要开新修订；升级窗口服务端同时支持N与N-1。包版本升级与线路修订无关。浏览器remote-hub.v2 HTTP API不改。

**影响**：P1调整Worker握手/帧派发/回执构造与版本测试；P2按线路修订序列化，而不是包版本相等判断。0.6.1中的初始线路为1。

### D43 本机远程连接管理与对话authority（主代理裁决，2026-09-26）

**背景**：只有远程协议不足以让本机用户发起配对、看短码与连接状态、取消或解绑；P2不能自建第二套路由事实源。

**决定**：增量冻结GET /api/v1/remote/link、POST/DELETE /api/v1/remote/pairing、POST /api/v1/remote/unlink及RemoteLinkView。沿用v1现有鉴权，状态unpaired/pairing/paired/revoked/frozen，任何视图/事件均不得含设备secret、Authorization或Hub Token。serverOrigin只接受HTTPS，开发调试可允许127.0.0.1/localhost HTTP。本机WS增加remote.link.changed，payload为同一RemoteLinkView。

解绑删除本机凭据并断开，尽力通知服务端撤销，完成状态unpaired；不能冒称服务端必已撤销，不扩远程HTTP或给设备Bearer授予owner权限。既有remote对话不回退local，本机只读。LocalConversationView追加可选authority=local/remote，缺省视为local以兼容旧对象。后续如何接续解绑对话另行设计。

**影响**：P2实现连接状态/凭据生命周期和authority写拦截，P3-B本机配对界面消费此契约。具体状态字段、并发与通知边界见R1-contract.md§12。

### D44 本机浏览器会话下的远程连接等价路由（主代理裁决，2026-09-26）

**背景**：D43只有本机v1 Bearer操作，实际工作台通过连接码取得本机Cookie后使用v2 API。不能把Hub Token交给浏览器来打通配对，FZ-R1.1回执接线事项2需协议明确入口。

**决定**：在已有本机Cookie契约 `packages/protocol/openapi/local-chat.v2.yaml` 增加GET /api/v2/remote/link、POST/DELETE /api/v2/remote/pairing、POST /api/v2/remote/unlink。请求和响应完全复用RemoteLinkView/RemoteLinkPairingInput与既有错误码。使用localSession Cookie，写请求沿用Origin、Idempotency-Key规则，全部响应Cache-Control:no-store。允许轮询GET link，remote.link.changed不变。

本机Local Hub的v2与云端Hub Server的remote-hub.v2不是同一服务，Cookie不能互换；本机v1 Bearer路由保留给桌面壳和诊断。包版本0.6.2、wireRevision仍为1，不新增类型、不修改云端接口或执行内核。

**影响**：P2复用本机v2认证依赖和D43同一连接管理器实现等价路由，覆盖错误与中间件拒绝的no-store响应；P3-B使用本机Cookie入口并可轮询。关闭FZ-R1.1接线事项2的协议缺口，应用实现与联调由对应工作包负责。解绑的云端授权通知仍是原有best-effort边界，本次不扩权。

### D45 会话快照带出待处理审批（主代理裁决，2026-09-26）

**背景**：手机晚于审批发起打开对话，或游标过期后重建，无法只靠之后的增量事件发现已有pending审批，尤其无法拒绝高风险动作。

**决定**：RemoteConversationSnapshot增加可选approvals数组，元素复用RemoteApprovalView，只包含该对话当前pending且未过期的审批，最多100条；有更多符合条件记录时沿用hasMore。旧服务端缺省字段时前端按空数组处理，不新增列审批路由。快照是浏览器对账入口，重建以approvals初始化，再用增量审批事件更新；消费、失效或到期的审批不再出现在快照。禁止远程approve的高风险pending审批仍应可见并可按既有规则reject。

**影响**：包版本0.6.3，仅浏览器HTTP DTO增量，wireRevision仍为1。P1负责同事务、owner/对话归属和期限过滤后填充；P3-B负责快照恢复及增量维护。通用审批视图/Worker事件不变，执行状态与审批权限不扩展。本轮只改协议，服务端填充另行实现。

### D46 扫码配对仅改前端（主代理已裁决，2026-09-27）

**决定**：电脑配对页显示 `https://<服务器域名>/remote/pair#code=<8位短码>` 二维码，同时保留短码备用。手机仍需登录、预览和确认，读取短码后清除URL片段。短码不放入查询参数；前端依赖和锁文件由对应前端工作包/Integrator处理。

**影响**：复用已有配对协议和后端，不新增接口、DTO或认证。本工作包只登记，不实现二维码或改前端。依据为手机远程接入方案v0.3 §11.1。

### D47 电脑唯一写入、完整副本与两端继续（v0.4主代理裁决，2026-09-27）

**决定**：9bb608d / bf15428那一版镜像+接力草稿作废。电脑是唯一写入方，服务端保存完整副本，手机和电脑都继续原对话；不需要handover。同步默认开启，关闭/电脑删除/设备撤销须删除对应副本。全文不截断，超帧分段拼齐再发布；历史分批并有完成标记。visibility=both/pc_only/mobile_only只作显示过滤，不控制上传。电脑可includeHidden找回mobile_only。

busy只由电脑queued/running/waiting_approval轮次推导，recoveryRequired只提示不占忙碌锁；重连及每次变化发送完整忙碌集合，服务端整体覆盖，不持锁，手机不持锁。取消不受busy限制。高风险审批规则不变。

**实现取舍**：修订2独立命名DTO/union；为30秒未送达失败后不执行的承诺增加provisional收件与持久显式grant门闩，ACK不充当授权。手机创建对话也以电脑执行的控制命令完成。具体原子性、分段和双向升级栅栏见packages/protocol/remote/R1.5-contract.md。

### D48 撤销本机只读与离线排队（主代理裁决，2026-09-27）

**决定**：撤销D43的remote对话本机只读，本机写入口不再因authority=remote返回CONVERSATION_AUTHORITY_MISMATCH；authority保留为兼容来源字段。撤销新浏览器操作的服务端离线排队，离线立即REMOTE_DEVICE_OFFLINE，输入保留。在线传输缺省/最多30秒deliverBy，未获得grant到期失败，迟到命令不执行、不接单。旧已受理的修订1命令继续如实对账，不能伪造失败或取消。

**影响**：P2改同一本机互斥/事务边界与执行门闩；P1改准入/期限竞争和只读投影；前端去掉authority只读假设。新提交要求修订2，旧连接仍可兼容对账，不能对rev1承诺新门闩保证。

### D49 修订1错误值域单独冻结（Q1采用建议B，主代理裁决，2026-09-27）

**决定**：批准必要的Schema/生成类型引用调整例外，保持修订1旧报文接受/拒绝行为不变。RemoteWire1ErrorCode固定为0.6.3注册表；RemoteWire1Error及RemoteWire1ApprovalView封装固定字段，rev1帧仅替换错误/审批payload引用。公共ErrorCode仍跟随registry追加，仅HTTP和rev2可用新码。原rev1 Fixture不改。

**影响**：Q1已关闭，不再needs-decision。冻结测试需检查引用闭包和值域，不仅对比顶层frame文本；不得把公共ErrorCode锁死或偷偷放宽rev1。

### D50 设备删除、远程暂停与标准开放接口（用户裁决，2026-09-27）

**决定**：删除取代撤销的UI位置，作废凭据、删除全部副本并从列表移除；旧revocations保留deprecated。已revoked设备也可删除；删除ID不复用，再次配对生成新ID。首次DELETE返回删除回执，之后含重复DELETE统一NOT_FOUND，保留无正文最小墓碑保证副作用幂等和拒绝旧凭据。

remoteAccess=enabled/suspended是持久管理状态，与online/status独立。暂停不关连接/同步/历史；受限业务写拒绝REMOTE_DEVICE_SUSPENDED，run.cancel与审批reject豁免。暂停切换使当时全部未grant窗口失败，已grant如实处理；恢复不重放失败命令。不改Worker线路，仍为1/2，P2无需业务改动。

设备标准GET/PATCH/DELETE开放账号PAT：devices:read/manage/delete精确scope不互相包含。PAT仅Cookie管理，hqr_pat_前缀，默认90天最长365天；首次签发明文一次，同意图重放仅metadata，服务端只存不可逆HMAC。Cookie与Bearer同现拒绝，PAT不能用于其它资源或签发更多PAT。

**规范与兼容**：协议包0.8.0，完整Hub Server OpenAPI、api-guide、错误总表、自包含公开规范及requestId贯通要求一并冻结。HTTP新增detail独立于Worker错误；rev2错误引用固定到0.7值域，保持所有原报文行为，HTTP新码不入线路。旧请求和deprecated入口保留N/N−1窗口；当前业务适配交P1/P3。

**实施**：P1提供公开GET /api/v2/openapi.json，与仓库bundle一致；响应X-Request-Id与信封同值，日志只记固定operation/状态/错误码/耗时等，不记凭据/正文。P3增加管理、暂停恢复、删除与一次性令牌页。可选离线托管文档UI，不依赖外网CDN。
