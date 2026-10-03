# HQAgent-Hub 接入 PI 编码 Agent 方案

## 变更记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-10-04 | v0.2 | 用户确认 §6：排在 R1.7 之后、R2 之前；默认模型按建议（规划 / 审核 `deepseek/deepseek-v4-pro`，执行 `deepseek/deepseek-v4-flash`，看图 `deepseek/deepseek-v4-flash-vision-exp`）。协议 P0 先行开工。 |
| 2026-10-04 | v0.1 | 用户确定先接入 PI（DSH 暂不考虑）。本机安装 PI CLI 1.0.1 并完成 RPC 实测，给出接入设计与分工。 |

## 1. 背景

用户希望 Hub 除 Claude Code、Codex 外也能调度 PI（官网 https://pi.dev/ ，npm 包 `@earendil-works/pi-coding-agent`，命令 `pi`）。PI 是一个轻量的编码 Agent 框架，可接入 15+ 家模型提供商，支持扩展、技能、无界面调用。用户已有 PI 桌面版（PI-Desktop 0.15.10），本次另装 CLI；并提供了一个 DeepSeek 兼容渠道（1aicode）。

## 2. 本机实测结论（2026-10-04，PI CLI 1.0.1）

| 能力 | 结果 | 说明 |
| --- | --- | --- |
| 自定义模型渠道 | 通过 | `~/.pi/agent/models.json` 配置 OpenAI 兼容渠道；密钥放在仅当前用户可读的文件，`apiKey` 用 `!node -e ...` 读取（Windows 下 `!type` 不可用）。渠道提供 DeepSeek V4 Pro / Flash / 4.1 Flash / Flash Vision Exp |
| 单次调用 `pi -p` | 通过 | 回复正确 |
| RPC 模式 `pi --mode rpc` | 通过 | stdin/stdout JSON；命令带 `id`，响应回带同一 `id` |
| 会话身份 | 通过 | `get_state` 返回 `sessionId`、`sessionFile`；`--session-dir` 可指定会话目录 |
| 精确续接 | 通过 | 新进程 `switch_session {sessionPath}` 后 `sessionId` 不变，记得上一轮暗号 |
| 中断 | 通过 | `abort` 后有完整 `agent_end`、`agent_settled` |
| 事件流 | 通过 | `agent_start → turn_start → message_start/update/end → turn_end → agent_end → agent_settled`，工具调用有 `tool_execution_start/end`（含 `toolName`、参数、`isError`） |
| 图片输入 | 通过 | `prompt` 的 `images: [{type:"image", data:<base64>, mimeType}]`；用 `deepseek-v4-flash-vision-exp` 正确识别左红右蓝 |
| 工具拦截 | 机制可用，策略需加强 | 扩展 `pi.on('tool_call')` 返回 `{block:true, reason}` 可在执行前拦截。但示范扩展只做字符串匹配，模型被拦后改用 `bash` 列目录、读取扩展源码，再换不含关键字的写法读到了目标文件（见 §4.3） |

## 3. 总体设计

PI 作为第三种 Runtime（`agentType = "pi"`），与 Claude Code、Codex 并列，复用现有任务、会话、审批、附件、原生会话、远程同步体系。

```
Hub PiAdapter ──spawn──> pi --mode rpc --session-dir <Hub管理目录> --provider <p> --model <m>
                          --extension <Hub安装目录>/pi/hub-guard.js
     ▲  stdin: prompt / switch_session / abort / get_state
     │  stdout: 事件流 → 映射为 Hub 任务事件
     └─ hub-guard 扩展：每次 tool_call 交给 Hub 判定（越界检查 + 危险操作审批），返回放行或拦截
```

## 4. 详细设计

### 4.1 协议（W0）

- `agentType` 增加 `pi`；catalog、原生会话、图片能力等所有按 Agent 类型区分的地方同步扩展。
- 图片传输标识，例如 `pi-rpc-images-v1`；能力仍按「Agent 实例 + CLI 版本 + 模型」验证（沿用 0.10.1 验证作业）。
- 模型选择器：PI 需要 `provider` + `modelId` 两段，约定为 `provider/modelId` 形式的单字段，或在 Agent 实例配置里拆分（由 W0 冻结）。
- 是否需要升 wireRevision 由 W0 判断（新增枚举值若被旧端严格校验拒绝则需要）。

### 4.2 Hub 适配器（W1/W2）

- 进程：Windows 下 `pi` 是 npm 的 `.cmd` 包装，按现有 npm shim 解析规则找到真实的 node 入口启动，不经 shell。
- 会话：由 Hub 指定 `--session-dir`（Hub 数据目录下），启动后 `get_state` 记录 `sessionId` 与 `sessionFile`；续接一律 `switch_session` 指定会话文件，不用「最近一次」。
- 事件映射：`agent_start/agent_end/agent_settled` 对应回合开始与结束；`message_update` 的文本增量对应进度；`tool_execution_*` 对应工具活动；结果仍要求最终输出符合 AgentResult。
- 取消：`abort`，以 `agent_settled` 为停止证据；进程不响应时按现有进程组策略终止。
- 模型：`--provider`、`--model` 由角色配置决定；`get_available_models` 用于 Agent 发现时列出可选模型。
- 凭据：Hub **不保存、不读取** PI 的模型密钥，完全使用 PI 自己的配置（`~/.pi/agent/`）。

### 4.3 安全：hub-guard 扩展（关键）

实测表明只做字符串匹配的扩展会被绕过。设计要求：

1. **判定交给 Hub**：扩展不内置规则，把每个 `tool_call`（工具名、参数）通过 RPC 扩展 UI 通道（`extension_ui_request` / `extension_ui_response`）或本机回环接口交给 Hub，由现有 PathGuard（含 shell 解析、通配符 / 变量 / 管道保守拒绝、附件精确只读放行）与危险操作审批判定，再返回放行或拦截。Hub 无响应或超时一律拦截。
2. **只读场景收紧工具集**：扩展启动时用 `setActiveTools` 只保留只读工具（read、grep、find、ls 等），去掉 bash、edit、write。
3. **扩展放在 Hub 安装目录**，不放进 Agent 工作区；PI 的用户级、项目级扩展（`~/.pi/agent/extensions/`、`.pi/extensions/`）可能引入未受控工具，需核实 PI 是否有禁用扩展自动发现的选项；若没有，Hub 启动 PI 时检测并在 catalog 中如实标注风险，或拒绝在存在未知扩展时以写权限运行。
4. 审批通过手机的流程与 Claude、Codex 一致。

### 4.4 原生会话读取

- PI 会话为单文件、树形结构（分支），默认位于 `~/.pi/agent/sessions/`（以实际为准）。按 R3 的做法：结构普查 → 版本化读取器 → 只列出工作目录在已登记 workspace 内、由终端直接开的会话 → 导入后续接用 `switch_session`。
- 树形会话需要定义「当前分支」的线性化规则（默认取叶子分支）。
- 可作为第二期，不阻塞第一期调度功能。

### 4.5 图片

- 能力判定沿用 0.10.1 验证作业：对 PI 实例 + 模型跑五项探测；只有模型声明 `input` 含 `image`（例如 `deepseek-v4-flash-vision-exp`）才可能通过。

## 5. 分期

| 期 | 内容 | 出口 |
| --- | --- | --- |
| 第一期 | 协议加 `pi`；PiAdapter（启动、续接、取消、事件映射、模型选择）；hub-guard 扩展接入 PathGuard 与审批；Agent 发现与模型列表；图片验证 | 手机派任务给 PI（DeepSeek）完成一轮只读分析与一轮受审批的修改；越界读写与危险命令被拦；续接与取消正常；图片验证通过的模型可收图 |
| 第二期 | PI 原生会话读取、导入与续接 | R3 同等验收 |

## 6. 待用户确认

1. 排期：建议在 R1.7（Windows 桌面版，进行中）之后、R2（飞书通知）之前开始第一期。
2. 默认模型：PI 角色默认用哪个模型（建议规划 / 审核用 `deepseek/deepseek-v4-pro`，执行用 `deepseek/deepseek-v4-flash`，看图用 `deepseek-v4-flash-vision-exp`）。
3. 密钥：渠道密钥已在对话中出现，测试完成后建议在渠道后台更换；本机只存放在 `~/.pi/agent/1aicode.key`（仅当前用户可读），不进仓库、日志与 Hub 数据。

## 7. 参考

- https://pi.dev/
- https://github.com/earendil-works/pi/blob/HEAD/packages/coding-agent/docs/rpc.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md
