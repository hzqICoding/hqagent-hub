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

### D39 Antigravity `agentapi` 实测不达标，判定 `incompatible`

D5 当初把 Antigravity 移出一期关键路径，理由是「唯一接入方式未经实测」。
2026-09-07 实测了，结论是**不达标**——不是暂时没接，是这个接口做不了。

**`agentapi` 的完整命令面**（`language_server.exe agentapi`）：

```text
get-conversation-metadata <conversation_id>
new-conversation [--model=<flash_lite|flash|pro>] [--title] [--profile] <prompt>
send-message [--title] <recipient_id> <content>
```

对照 Adapter Port 的八个方法：

| Port 方法 | agentapi | 结论 |
| --- | --- | --- |
| `start(spec)` | `new-conversation` | ✅ |
| `resume(req)` | `send-message` | 🟡 勉强 |
| `detect()` | 靠文件存在凑 | 🟡 |
| `health()` | 无登录态查询 | ❌ |
| `streamEvents()` | 无流式输出 | ❌ |
| `approve(dispatch)` | 无审批回传 | ❌ |
| `cancel(req)` | 无中断 | ❌ |
| `collectResult()` | 只有 metadata | ❌ |

缺的三条恰好都是硬能力：`streaming_events`、`tool_approval` 在
`capabilities.yaml` 里是 `hard: true`，`cancel` 是 D17 两段式取消的前提。

它自己的用法示例说明了设计意图不在这里：
`# Send to yourself (useful for async notifications)`——
**这是 Antigravity 会话之间互发通知的消息 API，不是给外部编排器控制 Agent 的。**

**另一条路，明确不走**：`language_server.exe` 有完整 IDE 后端接口
（`-api_server_url="http://0.0.0.0:50001"`、CSRF token、extension server、LSP、
headless）。但那是私有未文档化协议，等于逆向别人 IDE 的内部接口。
每次 Antigravity 升级都可能断，而 OTA 是本项目的 P0 能力——
用户升级 Antigravity 我们就挂，耦合方向是反的。

这印证了施工方案 §7.1 把 Sidecar 排在可靠性第 4 级的判断。

**决定（已修正，见下）**：一期不实现 Antigravity Adapter，也不创建占位。

#### 修正：上面的判定只看了 agentapi 一半

初判「不达标、不实现」时漏了施工方案 `:468` 早就写好的接入设计：

> Phase 1.1 Antigravity：Sidecar + `agentapi` 创建/续接会话，保存
> `conversation_id`；**通过共享 MCP 工具回报进度和结果**。

**设计从来没打算只用 agentapi。** 规划的是混合模式：agentapi 起会话，
MCP 回传。而 Antigravity 确实是 MCP 客户端——`~/.gemini/config/mcp_config.json`
等三份配置文件都存在（当前为空，未注册任何 server），且它自己就启动着
`chrome-devtools-mcp`（`-use_ls_chrome_devtools_mcp=true`）。

按混合方案重新对照：

| Port 方法 | 混合方案 | 结论 |
| --- | --- | --- |
| `start(spec)` | `agentapi new-conversation` | ✅ |
| `resume(req)` | `agentapi send-message` | 🟡 |
| `streamEvents()` | Antigravity 调 Hub 的 MCP `report_progress` | ✅ 推而非拉 |
| `collectResult()` | MCP `submit_result` | ✅ |
| `approve()` | MCP `request_approval`，阻塞等回应 | ✅ |
| `cancel()` | 只能协作式，无硬中断 | ❌ |
| `health()` | 无登录态查询 | ❌ |

**从三个硬缺口降到一个半。技术上可行。**

#### 但保证强度低一档，这是它留在 Phase 1.1 的真正理由

前四条靠的是**推模式**：进度和结果能不能回来，取决于 Agent 愿不愿意调那个
MCP 工具。模型忘了调，进度就静默停住，Hub 只能干等到超时。

Claude / Codex 走的是**拉模式**——Adapter 主动读子进程 stdout，Agent 想不给都不行。

定性差别：Antigravity 是「**Agent 配合**」，不是「**Adapter 保证**」。
正常路径能跑，异常路径（模型跑飞、卡死、拒绝调工具）没有兜底。
这正是 §7.1 把 Sidecar 排在第 4 级的原因——不是接不了，是保证强度低一档。

`cancel` 的硬缺口也是真的：`agentapi` 起的会话，进程归 Antigravity IDE 管，
Hub 杀不掉，D17 两段式取消里的 force 那半做不到。按 D17 该如实返回 `refused`
并报告残留——Claude 的写任务取消已有先例，不是新问题。

#### 修正后的决定

一期结论不变（**不实现**），但理由要改准确：**不是「接口做不了」，
而是「保证强度低一档 + 一期用两个 Agent 已足够证明四层解耦」（D5、D37）**。

Phase 1.1 若要接，走 agentapi + MCP 混合方案是**可行**的，
不必如初判所说「不要再往 Sidecar 这条路上投入」。届时必须在 UI 上如实标注
其能力矩阵：`cancel` 不支持、进度依赖 Agent 配合，不能和 Claude/Codex
显示成同等可靠。

**另一条明确不走的路**：直接对接 `language_server.exe` 的私有 API
（`-api_server_url="http://0.0.0.0:50001"`、CSRF token、extension server）。
那是逆向别人 IDE 的内部协议，每次 Antigravity 升级都可能断，
而 OTA 是本项目 P0 能力——用户升级 Antigravity 我们就挂，耦合方向是反的。

**当前 Agent 可用性实况**（2026-09-07 实测）：

| Agent | 状态 | 证据 |
| --- | --- | --- |
| Codex | ✅ **完整可用** | 通过 Hub 派活跑通：独立会话、隔离 worktree、真实创建 `backend/hello.txt`、结构化结果回传 |
| Claude | 🟡 部分 | 能被解析成角色、能起会话、能出事件流；写任务闭环未验，`tool_approval` / `session_resume` 实测为 false |
| Gemini CLI | ❌ 认证关闭 | `IneligibleTierError: UNSUPPORTED_CLIENT`（见 D37） |
| Antigravity | ❌ 接口不达标 | 本条 |
