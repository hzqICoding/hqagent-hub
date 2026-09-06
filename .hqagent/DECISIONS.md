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
