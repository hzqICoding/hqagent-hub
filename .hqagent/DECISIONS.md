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
