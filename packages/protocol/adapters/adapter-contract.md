# Adapter Port 契约规则（FZ-2）

> 冻结于 2026-09-06，协议版本 `0.2.0`。
> 类型定义在 `packages/protocol/schema/adapter-port.json`，本文件写**类型表达不了的规则**。
> 与 `docs/施工方案.md` §7、§8 冲突时以本文件为准；本文件未覆盖的以施工方案为准。

FZ-2 解锁 W2（Agent 适配层）与 W3（编排与安全）的正式实现。

## 1. 八个方法的契约

施工方案 §7.2 给的是 8 行签名，这里补齐语义。

| 方法 | 输入 | 输出 | 失败 |
| --- | --- | --- | --- |
| `detect()` | — | `AdapterDescriptor` | `AdapterFailure` |
| `health()` | — | `AdapterHealth` | `AdapterFailure` |
| `start(spec)` | `AgentTaskSpec` | `AgentSessionHandle` | `AdapterFailure` |
| `resume(req)` | `ResumeRequest` | `AgentSessionHandle` | `AdapterFailure` |
| `streamEvents(sessionId)` | `string` | `AdapterEvent` 流，以 `AdapterStreamEnd` 收尾 | 见 §4 |
| `approve(dispatch)` | `ApprovalDispatch` | — | `AdapterFailure` |
| `cancel(req)` | `CancelRequest` | `CancelResult` | 见 §3 |
| `collectResult(sessionId)` | `string` | `AgentResult` | `AdapterFailure` |

### `detect()` 与 `health()` 的分工

**这两个不是一回事，不要合并。**

- `detect()` 回答「装没装、什么版本、能干什么」。开销大，结果可缓存，Agent 列表刷新时调用。
  产出 `AdapterDescriptor`，其中 `capabilities` 是**能力的唯一来源**——
  硬能力（`capabilities.yaml` 里 `hard: true`）只能由它声明，用户在 UI 上不能勾选覆盖（施工方案 §6.2）。
- `health()` 回答「现在还活着吗、还登录着吗」。轻量，周期调用，不重新枚举能力。

登录态失效属于 `health()` 的职责：返回 `status: not_logged_in` + `authValid: false`，
**不要**返回 `error` 然后把「请先登录」塞进错误文案里——UI 要据此给出可操作的登录引导。

## 2. Session 生命周期

`SessionStatus` 的四个值在 FZ-1 已冻结，这里定死迁移规则。

```
                    start() 成功
        (无)  ─────────────────────►  active
                                        │
              节点结束，会话可续接      │
        idle  ◄─────────────────────────┤
          │                             │
          │  resume() 成功              │  cancel() / 节点失败 / 正常收尾
          └────────────────────────►  active ──────────────►  closed
                                        │
              streamEvents 报 agent_exited
              或 resume() 报会话不存在
                                        ▼
                                     invalid
```

**规则**

1. **新任务默认新会话。** `reusePolicy` 默认 `new_session`。
   只有用户显式点「继续会话」、工作流显式声明复用，或任务传入 `resumeSessionId`
   才恢复既有会话（施工方案 §8.2）。
2. **禁止 `latest` 之类的不确定续接。** `resumeSessionId` 与
   `AgentSessionHandle.externalSessionId` 必须是明确值。
3. **同 Agent 承担实现与审核时必须两个会话**，`purpose` 分别为 `implement` 和 `review`。
   把审核塞进实现会话等于让它审自己的上下文。
4. **`invalid` 是单向的。** 一旦置为 `invalid` 不得再尝试 `resume()`，只能新建。
   外部会话已经不存在了，重试只会得到一个语义不同的新会话。
5. **`closed` 与 `invalid` 要分开。** `closed` 是正常收尾，历史仍可读；
   `invalid` 是外部会话失效。UI 上要能区分「结束了」和「断了」。
6. 项目背景通过 `.hqagent` 文档和 `AgentTaskSpec.readFirst` / `handoffDocuments` 注入，
   **不靠把所有工作塞进一个长期对话**。

## 3. 取消语义

施工方案 §7.2 的 `cancel(sessionId): Promise<void>` 太弱——它不能表达「取消失败了」。

### 两段式取消

Hub 先发 `mode: graceful` 带 `graceSeconds`，到点未停再发 `mode: force`。
**Adapter 不得自行延长宽限期**，也不得把 `force` 当成 `graceful` 处理。

理由：OTA 排空（`OTA升级架构设计.md` §8）有超时上限，`waitPids` 必须在有限时间内收敛。
一个能无限拖延取消的 Adapter 会让整个升级流程卡死。

### `refused` 必须如实上报

`CancelOutcome` 有五个值，其中 `refused` 是关键：底层 Agent 不提供中断入口时，
Adapter **必须**返回 `refused`，Hub 据此把节点标记为 `failed` 而不是 `cancelled`，
并让用户知道那个进程可能还在跑。

**不得假装取消成功。** 用户以为停了、实际还在改文件，是比取消失败更坏的结果。

`refused` 或 `force_killed` 后若有残留进程，填 `orphanProcessIds`——OTA 的 `waitPids` 需要它。

### 取消产生的事件

**成功取消只发 `task.status_changed`（`to: cancelled`），不发 `agent.failed`**（裁决 D27）。

取消是正常路径，不是故障。原规则要求成功取消也产生 `agent.failed`，但
`ErrorCode` 里根本没有取消对应的码——W3 实现时发现这条走不通。也不新增取消错误码：
新增一个只在"正常结束"时使用的错误码，本身就是矛盾的。

只有 `refused` 才是失败：`errorCode` 用 `TASK_NOT_CANCELLABLE`，
并按上文填 `orphanProcessIds`。

不新增"已发中断但 grace 到点仍在跑"这类中间 `CancelOutcome`。它和"没有中断入口"
对 Hub 的下一步动作完全相同（都是升级到 force），区别只是诊断信息，放
`CancelResult.detail`。**枚举值要为决策服务，不为叙事服务。**

## 4. 事件流的断开语义

**`transport_lost` 与 `agent_exited` 必须分开，这是 `AdapterStreamStatus` 存在的全部理由。**

| 状态 | 含义 | 会话 | Hub 行为 |
| --- | --- | --- | --- |
| `ended` | 正常收尾 | → `idle` 或 `closed` | 调 `collectResult()` |
| `transport_lost` | 连接断了，Agent 可能还活着 | 保持 `active` | 按退避重连；`resumable: true` 时可续流 |
| `agent_exited` | Agent 进程已退出 | → `invalid` | 不再重连，走失败路径 |
| `streaming` | 仅用于中途上报，不作为终止状态 | — | — |

把这两种混为一谈的后果是二选一：要么把网络抖动误判成任务失败，
要么永远等一个已经死掉的进程。

## 5. 审批语义

### Hub 是时效的唯一权威

`ApprovalRequiredPayload.expiresAt` 由 Hub 设定。
**Adapter 不得自行判定过期后放行**，也不得在没收到 `approve()` 时替用户做决定。

如果底层 Agent 自己有工具审批超时并先一步放弃了，Adapter 必须报
`AdapterFailure { kind: agent_error }` 并在 `message` 里说明是**Agent 侧超时**——
Hub 要能区分「用户没决定」和「Agent 不等了」，这两种对用户的提示完全不同。

### 能力门禁

`AgentTaskSpec.requiresApproval` 非空时，Hub **不得**把任务派给
未声明 `tool_approval` 硬能力的 Adapter。这是 Role Resolver 的硬约束，
不是运行时再检查——派出去之后才发现拦不住，危险动作已经执行了。

### ID 关联

`ApprovalDispatch` 同时带 `approvalId`（Hub 侧）与 `externalRequestId`（供应商侧）。
**关联由 Adapter 负责**：它在发起审批时就要记住这个映射。

## 6. 事件映射规则

### 事件字典已冻结，Adapter 不得新增类型

`packages/protocol/events/event-dictionary.md` 的 28 条事件是全集。
供应商有再多花样的原始事件，也只能映射到这 28 条之内。

### 三条硬规则

1. **必须声明映射表。** 每个 Adapter 提供 `VendorEventMapping[]`，
   说明每种供应商事件映射到哪个统一事件。
2. **分两种情况，都必须计数**（裁决 D34）。
   - **已知噪声**（心跳、rate-limit、重放 user 消息——Adapter 明确认得出来、
     确定不需要的）：填 `dropped: true` 并计数。
   - **真正未知的事件**：降级为 `agent.progress`，原文放 `payload.raw`，并计数。
     **不得丢弃。**

   区别在于「认得出来所以决定不要」和「不认识」。前者是设计，后者是盲区，
   盲区必须留痕——静默吞掉会让「为什么进度卡住」这类问题无从查起。
3. **原始数据不泄漏到 UI。** `AgentProgressPayload.raw` 是**诊断字段**，
   仅进诊断包与日志，UI 不得把它当主内容渲染。
   2048 上限约束的是 **`raw` 序列化后的总长度**，不是某个字符串字段（裁决 D35）。
   未知字段一律不进 `payload` 的具名字段。

### 最小映射集

每个 Adapter 至少要能产出这几条，否则任务在 UI 上就是个黑盒：

```
agent.started      ← 会话建立，必须带 externalSessionId
agent.progress     ← 有任何可读进展就发，不要攒到最后
agent.tool_call    ← 声明了 shell / file_write 能力的必须发
approval.required  ← 声明了 tool_approval 能力的必须发
agent.completed    ← 带 AgentResult
agent.failed       ← 带 AdapterFailure，kind 必须准确
```

## 7. 路径越界

`AgentTaskSpec.allowedPaths` 是 glob 白名单。

- **能在写入前拦截的 Adapter 就拦截**，返回 `AdapterFailure { kind: path_violation }`。
- 不能拦截的，Hub 在 `collectResult()` 后按 `AgentResult.changedFiles` 校验，
  越界则发 `task.path_violation` 事件并把节点标记失败。

两条路径都要有，不能只做后置校验——那时文件已经被改了。

## 8. 失败必须分类，不许靠解析文案

`AdapterFailureKind` 九个值决定 Hub 的后续动作：

| kind | Hub 的反应 |
| --- | --- |
| `not_installed` / `version_incompatible` | 标记 Agent `incompatible`，从可选列表移除 |
| `not_logged_in` | 提示登录引导，不重试 |
| `capability_missing` | 交 Role Resolver 提示能力缺口，必填 `missingCapabilities` |
| `transport_error` | 可重试，按退避 |
| `agent_error` | 不自动重试，交用户决定 |
| `timeout` | 触发两段式取消 |
| `cancelled` | 正常路径，不算故障 |
| `path_violation` | 节点失败，必填 `violationPaths` |

**接入失败或缺少硬能力时返回失败，不得伪装成功。**
这条在 `docs/Agent适配接入规范.md` §3 已经写死，这里重申一次是因为它是最容易被违反的一条：
Adapter 返回「成功」然后在事件里说「其实我没做」，会让编排层完全无法判断任务状态。

## 9. W2 仍需实测补齐的部分

FZ-2 冻结的是**接口形状**，不是各家 Agent 的具体行为。
`docs/Agent适配接入规范.md` §2 的调研矩阵仍需 W2 用实测填满：

| 项目 | Claude | Codex |
| --- | --- | --- |
| 首选接入方式 | 待实测 | 待实测 |
| 版本与探测命令 | 待补 | 待补 |
| 外部会话 ID 获取/恢复 | 待补 | 待补 |
| 流式事件格式 | 待补 | 待补 |
| 审批与取消语义 | 待补 | 待补 |
| 结构化结果能力 | 待补 | 待补 |
| 已知限制与降级状态 | 待补 | 待补 |

实测结论回填后，若发现本契约有形状不匹配的地方，**不要自己改 `packages/protocol/`**，
写进 handoff 提出来，由 W0 决定是否需要 FZ-2.1。

## 10. FZ-2.1 补充（2026-09-06）

### `sessionId` 由 Hub 生成并传入（裁决 D25）

`AgentTaskSpec` 现在有**必填** `sessionId`。Adapter 收到什么就用什么，
**不得自行生成**。

这条是 W2 和 W3 独立提出来的同一个问题：原来 `AgentSessionHandle.sessionId` 说是
「Hub 生成后传给 Adapter」，但 `start()` 的唯一入参里没有这个字段，也没有别的通道。
两个包只好各自绕路——W2 让 Adapter 生成 `session_<uuid>`，W3 接受 `start()` 的返回值。
**结果是会话身份的所有权从 Hub 漏到了 Adapter。**

为什么不能漏：D7 要求同一 Agent 承担实现与复核时必须是两个不同会话，
而 Adapter 不知道自己这次是在实现还是在复核。只有 Hub 知道，所以只有 Hub 能保证。

### `pause` 与 `append_instruction` 的语义收窄（裁决 D26）

`TaskActionInput` 冻结了这两个动作，但 **Adapter Port 不为它们新增方法**。
多数 CLI Agent 没有真正的暂停语义，加了会逼每个适配器假装实现——
那正是 §3 要避免的那类谎报。改为收窄动作本身：

- `pause`：只作用于**节点之间**。当前节点跑完就停住，**不打断正在执行的 Agent**。
- `append_instruction`：只在节点 idle 时可用。运行中必须拒绝，返回 `TASK_ACTION_INVALID`。

前端据此做按钮禁用态。用 `cancel()` 假装 pause 是明确禁止的——那会关掉会话。

### `resume()` 返回 handle，`continue_lineage` 建子会话（裁决 D29）

`resume()` 现在返回 `AgentSessionHandle`。`continue_lineage` 的语义定为
**新建子 Session 并记 `parentSessionId`**，不是复用原 Session 记录——
否则 lineage（世系）这个词没有意义。

### `AdapterEvent` 已冻结（裁决 D32）

`streamEvents()` 逐条产出 `AdapterEvent`。它**故意不带 `eventId` 和 `seq`**：
全局单调 `seq` 与幂等 `eventId` 由 Hub 分配，Adapter 直接产出 `HubEvent`
会把这个所有权弄乱。Hub 收到后补齐两个字段再落库广播。

审批类事件必须填 `externalRequestId`，用于和 `ApprovalDispatch` 关联——
`ApprovalRequiredPayload` 也同步加了这个可选字段（裁决 D33），
关联 ID 要随事件走完全程，否则排障时和供应商日志对不上。

### `AdapterDescriptor` 不表达运行时状态（裁决 D31）

`installed` 的描述里原来写「status 必须是 incompatible 或 unknown」，
但这个 DTO 根本没有 `status` 字段。已删掉那句。

分层是：`AdapterDescriptor` 描述**装了什么**，`AdapterHealth` 描述**现在能不能用**，
两者由 `AdapterManager` 组合出 `AgentView.status`。不要把运行时状态塞回 Descriptor。

### `RoleId` 是开放类型（裁决 D30）

Schema 一直允许用户自定义角色，但生成器把 `RoleId` 生成成了八值闭枚举，
自定义角色进不了 `TaskNodeView` / `ResolvedTeamView`。这是**生成器的缺陷**。

现在边界类型是 `string`；内置八个角色另出常量：
TS 是 `BUILTIN_ROLE_IDS`，Python 是 `BuiltinRoleId`。
Role Resolver 对未知角色按「无内置能力要求」处理。
