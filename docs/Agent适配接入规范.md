# HQAgent-Hub Agent 适配接入规范

> 状态：W2 Phase 1 实测基线。Adapter 的唯一代码级契约仍以
> `packages/protocol/` 和 `.hqagent/INTERFACES.md` 为准。
> 实测日期：2026-09-06；平台：Windows 11 Professional
> `10.0.26200`、PowerShell 7。

## 1. 目的

本文件用于记录 Claude、Codex、Antigravity/Gemini 及后续 Agent 的真实接入方式、会话生命周期、事件映射、审批/取消能力和兼容版本，避免实现方依据猜测开发 Adapter。

## 2. Phase 1 实测调研矩阵

Antigravity / Gemini 属于 Phase 1.1，本轮不调研、不实现，也不保留一个看似已开始的
占位 Adapter。下表只覆盖 Phase 1 的 Claude 与 Codex。

| 项目 | Claude | Codex |
| --- | --- | --- |
| 首选接入方式 | `cli_stream`。本机未安装独立 Python Agent SDK；已安装的 Claude Code CLI 能以 `--print --output-format stream-json --verbose` 输出 JSONL，并在 `system.init` 立即给出会话 ID。Phase 1 直接管理本机 CLI 子进程，避免引入未冻结的新依赖。证据：§2.1 E1。 | `sdk`（Codex App Server JSON-RPC over stdio）。`codex app-server --listen stdio://` 实测可 `initialize`、`account/read`、`thread/start`、`thread/resume`、`turn/start`、`turn/interrupt`；比 `codex exec --json` 更完整地暴露线程、审批和取消。证据：§2.2 E1-E5。 |
| 版本与探测命令 | `claude --version` → `2.1.263 (Claude Code)`；`Get-Command claude` → `C:\Users\ua-hzq\AppData\Roaming\npm\claude.ps1`；`claude auth status --json` → `loggedIn: true`、`authMethod: claude.ai`。`detect()` 用版本命令，`health()` 只解析登录布尔值，不保存账号字段。证据：§2.1 E1-E2。 | `codex --version` → `codex-cli 0.153.4`；`Get-Command codex` → `C:\Users\ua-hzq\AppData\Roaming\npm\codex.ps1`；`codex login status` → `Not logged in`；App Server `account/read` → `account: null, requiresOpenaiAuth: true`。证据：§2.2 E1-E2。 |
| 外部会话 ID 获取/恢复 | `system.init.session_id` 和最终 `result.session_id` 均为同一 UUID，例如 `e3704fb0-a9ba-4055-8786-7a69ebae24b1`。恢复只允许 `claude --resume <明确 UUID>`。当前执行沙箱不允许 CLI 写 `C:\Users\ua-hzq\.claude\projects`，新会话虽成功但随后 `--resume` 返回 `No conversation found with session ID`；`--bg` 同样因创建 `.claude\jobs` 得到 `EPERM`。因此本轮 `session_resume` 硬能力声明为 `supported=false`，但 `resume()` 保留精确 ID 调用并如实返回失败，不使用 `--continue`/`latest`。证据：§2.1 E3。 | `thread/start` 响应的 `result.thread.id` 是明确外部 ID，例如 `01a076eb-bb5b-7b30-968a-7979ed65dbce`；同一 ID 传给 `thread/resume`，响应仍为该 `thread.id`，并返回既有 interrupted turn。禁止使用 `codex resume --last`。证据：§2.2 E3。 |
| 流式事件格式 | 实测 JSONL 类型包括：`system/init`、`rate_limit_event`、`assistant`（`content[].type=text/tool_use`）、`user`（`tool_result`）、`system/task_started`、`tool_progress`、`system/task_notification`、`system/permission_denied`、`result`。映射：init→`agent.started`；assistant text / tool progress→`agent.progress`；tool_use / tool_result→`agent.tool_call`；result success→`agent.completed`；result error→`agent.failed`。重放 user、thinking token、rate-limit 等诊断事件显式声明为 dropped 并计数。证据：§2.1 E4-E5。 | 实测通知包括：`thread/started`、`thread/status/changed`、`turn/started`、`item/started`、`item/completed`、`error`、`turn/completed`；生成协议还声明 agent-message delta、command output delta、file-change 和 approval request。映射：thread started→`agent.started`；turn/item/delta→`agent.progress` 或 `agent.tool_call`；approval request→`approval.required`；turn completed→`agent.completed`/`agent.failed`。证据：§2.2 E3-E6。 |
| 审批与取消语义 | `--permission-prompts host` 在本轮 `--print` 实测未产生可回传的宿主审批请求；危险 `Remove-Item` 只输出 `system.permission_denied`，`permission_denials` 记录拒绝。因此 `tool_approval` 声明 `supported=false`，带 `requiresApproval` 的任务必须在 `start()` 前返回 `capability_missing`。前台 stream 也没有实测成功的会话级 graceful 中断入口；`graceful` 返回 `refused`，Hub 到点后再发 `force`，后者终止该子进程并报告仍存活 PID。不得把权限拒绝或进程终止伪装成成功。证据：§2.1 E5-E6。 | App Server 生成协议实测含 `item/commandExecution/requestApproval`、`item/fileChange/requestApproval`；响应 decision 为 `accept` / `acceptForSession` / `decline` / `cancel`。Adapter 关联 JSON-RPC request ID 与 Hub approval ID；Agent 自己先超时则返回 `agent_error`，不替 Hub 判断过期。取消实测：进行中 turn `01a076eb-e968-72f1-ad3f-f7164b6e2f4b` 收到 `turn/interrupt` 后响应 `{}`，随后 `turn/completed.status=interrupted`。`graceful` 只等待 Hub 给定 `graceSeconds`；`force` 才杀隔离的 App Server 子进程。证据：§2.2 E4-E5。 |
| 结构化结果能力 | 实测 `--json-schema` 成功：输入要求 `{probe:string, ok:boolean}`，退出码 0，`result` 与 `structured_output` 均为 `{"probe":"CLAUDE_STRUCTURED","ok":true}`。Adapter 对正式任务传 `AgentResult` JSON Schema，并用生成 DTO 校验；校验失败返回 `agent_error`。证据：§2.1 E4。 | `turn/start.params.outputSchema` 实测被 0.153.4 App Server 接受并返回 in-progress turn；本机因 Codex 未登录/TLS 证书问题无法得到模型最终结构化内容。能力形状由本机二进制生成的 schema 明确存在，但运行任务前必须先通过 `health()`；未登录时返回 `not_logged_in`，绝不伪装完成。证据：§2.2 E2、E6。 |
| 已知限制与降级状态 | 当前可验证能力：streaming、structured output、coding/file tools；会话恢复与宿主工具审批未通过当前沙箱实测，均声明 false。CLI 不能对所有 shell 写入做静态路径判定；Adapter 会在可见 `tool_use` 写入前检查明确路径，无法证明安全的 shell 写命令拒绝，其他情况由 Hub 在 `collectResult()` 后复核 `changedFiles`。Graceful 取消无可靠入口时返回 `refused`。 | 当前安装正常但未登录，`health()` 必须是 `status=not_logged_in, authValid=false`；`start()` 返回 `AdapterFailure(kind=not_logged_in)`。App Server 为 experimental，最低实测版本锁为 `0.153.4`。stdio 断开且进程仍在为 `transport_lost`；进程退出为 `agent_exited`。每个 Hub Session 使用隔离 App Server 进程，避免 force cancel 误杀别的任务。 |

### 2.1 Claude 可复现证据

**E1：安装、版本与入口**

```powershell
Get-Command claude
claude --version
claude --help
```

输出摘要：入口为 npm 的 `claude.ps1`；版本 `2.1.263 (Claude Code)`；帮助中明确有
`--output-format stream-json`、`--json-schema`、`--session-id`、`--resume`、
`--permission-prompts host|none`、`stop|kill`。

**E2：登录态**

```powershell
claude auth status --json
```

输出摘要：`loggedIn=true`、`authMethod=claude.ai`、`apiProvider=firstParty`。Adapter
只消费这些非敏感状态字段；邮箱、组织与凭据不进入事件、日志或 DTO。

**E3：会话 ID 与受限宿主下的恢复失败**

```powershell
claude --safe-mode --print --output-format stream-json --verbose `
  --tools "" --permission-mode dontAsk --session-id `
  e3704fb0-a9ba-4055-8786-7a69ebae24b1 `
  "Reply with exactly CLAUDE_W2_FIRST"

claude --safe-mode --print --output-format stream-json --verbose `
  --tools "" --permission-mode dontAsk --resume `
  e3704fb0-a9ba-4055-8786-7a69ebae24b1 `
  "Reply with exactly CLAUDE_W2_RESUMED"

claude --safe-mode --bg "Reply later"
```

输出摘要：首条 `system.init.session_id` 与 `result.session_id` 都是给定 UUID，首轮成功；
第二条退出码 1，错误为 `No conversation found with session ID`。后台模式在当前宿主返回
`EPERM: operation not permitted, mkdir 'C:\Users\ua-hzq\.claude\jobs\…'`。这是当前
执行沙箱的会话目录写权限限制，不能包装成 Agent 功能成功。

**E4：流与结构化结果**

```powershell
claude --safe-mode --print --output-format json --tools "" `
  --permission-mode dontAsk `
  --json-schema '{"type":"object","properties":{"probe":{"type":"string"},"ok":{"type":"boolean"}},"required":["probe","ok"],"additionalProperties":false}' `
  "Return probe=CLAUDE_STRUCTURED and ok=true"
```

输出摘要：退出码 0，`subtype=success`，`result` 和 `structured_output` 都是
`{"probe":"CLAUDE_STRUCTURED","ok":true}`。stream-json 的成功样本按顺序出现
`system.init`、`assistant`、`result`。

**E5：工具事件与权限拒绝**

```powershell
claude --safe-mode --print --input-format stream-json `
  --output-format stream-json --verbose --replay-user-messages `
  --tools PowerShell --permission-mode manual --permission-prompts host `
  "删除 E:\tmp 下指定的临时探针文件"
```

输出摘要：先输出 `assistant.content[].type=tool_use`，读命令产生 `user.tool_result`；
删除命令没有产生可由宿主答复的 approval request，而是产生
`system.subtype=permission_denied`，最终 `permission_denials` 非空。探针文件未由 Agent
删除，调研结束后不再用于实现。

**E6：取消入口**

```powershell
claude stop --help
claude agents --help
```

输出摘要：2.1.263 只对 `--bg` 管理的后台 Session 提供 `stop <id>`；`stop` 会保留会话，
之后可 `attach`。但 E3 中本宿主无法创建后台 Session，故 Phase 1 前台 JSONL Adapter
不能据此宣称已验证 graceful cancel。

### 2.2 Codex 可复现证据

**E1：安装、版本与 App Server 能力入口**

```powershell
Get-Command codex
codex --version
codex app-server --help
codex app-server generate-json-schema --experimental --out E:\tmp\codex-schema
```

输出摘要：入口为 npm 的 `codex.ps1`；版本 `codex-cli 0.153.4`；App Server 支持
`stdio://` / Unix socket / WebSocket；生成的本机协议包包含 thread、turn、item、approval
请求与结构化输出类型。

**E2：登录态**

```powershell
codex login status
codex doctor
```

App Server 输入：

```json
{"id":2,"method":"account/read","params":{"refreshToken":false}}
```

输出摘要：CLI 为 `Not logged in`；`account/read` 为
`{"account":null,"requiresOpenaiAuth":true}`；doctor 还报告当前代理链 TLS
`UnknownIssuer`。因此运行时必须返回 `not_logged_in`，网络错误不冒充代码错误。

**E3：明确 thread ID 与恢复**

```json
{"id":1,"method":"initialize","params":{"clientInfo":{"name":"hqagent-w2-probe","version":"0.1.0"},"capabilities":{}}}
{"id":3,"method":"thread/start","params":{"cwd":"E:\\tmp","approvalPolicy":"never","sandbox":"read-only","ephemeral":false,"experimentalRawEvents":false}}
{"id":6,"method":"thread/resume","params":{"threadId":"01a076eb-bb5b-7b30-968a-7979ed65dbce","cwd":"E:\\tmp","approvalPolicy":"never","sandbox":"read-only"}}
```

输出摘要：`thread/start` 返回
`result.thread.id=01a076eb-bb5b-7b30-968a-7979ed65dbce` 并发
`thread/started`；`thread/resume` 返回同一 ID，并带回之前 `status=interrupted` 的 turn。

**E4：事件流**

```json
{"id":4,"method":"turn/start","params":{"threadId":"01a076eb-bb5b-7b30-968a-7979ed65dbce","input":[{"type":"text","text":"Reply exactly CODEX_W2_PROBE"}]}}
```

输出摘要：依次看到 `turn/started`、userMessage 的 `item/started` 与
`item/completed`、可重试 `error`；thread 保持 active，未把供应商网络重试误判为进程退出。

**E5：取消**

```json
{"id":5,"method":"turn/interrupt","params":{"threadId":"01a076eb-bb5b-7b30-968a-7979ed65dbce","turnId":"01a076eb-e968-72f1-ad3f-f7164b6e2f4b"}}
```

输出摘要：响应 `{"id":5,"result":{}}`；随后
`thread/status/changed.status.type=idle`，且
`turn/completed.turn.status=interrupted`、`durationMs=11049`。

**E6：审批与结构化结果形状来自已安装二进制**

```powershell
codex app-server generate-json-schema --experimental --out E:\tmp\codex-schema
```

实际生成物摘要：

- `CommandExecutionRequestApprovalParams` 必含 `itemId/startedAtMs/threadId/turnId`，可带
  `command/cwd/reason/approvalId/availableDecisions`；响应必含 `decision`。
- command decision 含 `accept`、`acceptForSession`、`decline`、`cancel`；file-change
  decision 同样含这四项。
- `TurnStartParams` 必含 `input/threadId`，并有 `outputSchema`。

实际请求：

```json
{"id":7,"method":"turn/start","params":{"threadId":"01a076eb-bb5b-7b30-968a-7979ed65dbce","input":[{"type":"text","text":"Return probe CODEX_STRUCTURED"}],"outputSchema":{"type":"object","properties":{"probe":{"type":"string"}},"required":["probe"],"additionalProperties":false}}}
```

输出摘要：App Server 接受 `outputSchema` 并返回 in-progress turn；因 E2 的登录/TLS
状态没有模型完成结果，随后用 `turn/interrupt` 收为 `interrupted`，未伪造结构化成功。

## 3. 固定边界

- Phase 1 必须完成 Claude 与 Codex；Antigravity/Gemini Adapter 属于 Phase 1.1，不阻塞一期，
  本轮不创建占位模块。
- Adapter 必须实现 `docs/施工方案.md` §7.2 的统一接口，并声明 §7.3 的能力。
- 新任务默认创建新的本地和外部 Session；只有明确继续或传入 `resumeSessionId` 才能恢复指定会话。
- 供应商原始事件必须映射到统一事件字典，未知字段不能直接泄漏到 UI。
- 接入失败或缺少硬能力时返回 `incompatible`/能力缺口，不得伪装成功。
- 正式实现前必须记录实测命令、输入、输出摘要、版本和可复现证据。

## 4. 冻结出口

FZ-2 已在协议 `0.2.0`、Git SHA `bfcd91e` 冻结。本文件只记录供应商实测结论与
Phase 1 能力降级，不改变冻结契约。发现形状不匹配时只写 handoff，由 W0 决定是否进入
FZ-2.1。
