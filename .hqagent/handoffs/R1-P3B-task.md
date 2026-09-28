# R1-P3B 任务：手机 H5 远程网关与远程页面

你上一轮完成的 P3-A（移动端布局，`9b189bf`）已审核通过。这一轮做 P3-B：让同一套 Vue 前端在手机浏览器里通过**云端 Hub Server** 和用户自己电脑上的 Agent 会话通信。

## 产品定位（必须遵守）

远程能力只是通信工具。服务端只做账号、设备配对、消息与状态中转，不调用模型、不保存模型凭据。前端里**不要出现任何模型 API Key、模型账号之类的输入或展示**。

## 工作区

- 新 worktree：`E:\OtherPro\HQAgent-Hub-worktrees\remote-web-gateway`，分支 `feat/remote-web-gateway`。它已经包含你的 P3-A 提交，以及冻结的远程协议 0.6.0，并且已执行 `pnpm install`。
- 基线：在 `apps/desktop` 下 `pnpm typecheck` 通过，`pnpm test` 为 207 passed。
- 只在这个目录工作，不要去改 `remote-web`、`remote-protocol` 或其它 worktree。

## 先读

1. `AGENTS.md`：路径所有权与提交规范
2. `packages/protocol/remote/R1-contract.md`：重点读 §2 认证与浏览器会话、§3 配对、§6 撤回、§7 控制结果、§8 浏览器游标、§9 审批分级
3. `packages/protocol/openapi/remote-hub.v2.yaml`：浏览器使用的全部 `/api/v2/*` 路径
4. `.hqagent/handoffs/R1-P0-remote-protocol.md` 里的「P3 Web B 阶段」一节
5. 现有网关写法：`apps/desktop/src/shared/api/index.ts`、`local-hub-gateway.ts`、`local-chat-gateway.ts`、`mock-local-chat-gateway.ts`

## 范围

- 只改 `apps/desktop/**`，外加你的回执 `.hqagent/handoffs/R1-P3B-remote-web-gateway.md`。
- **不改** `packages/protocol/**`（包括生成物）、`apps/hub/**`、`apps/server/**`、根目录共享文件。发现协议缺字段，写进回执，不要在前端自造同名类型。
- 所有远程类型都从 `@hqagent/protocol` 导入（`Remote*` 开头的那些），不要手写一份。

## 要做的

1. **RemoteGateway**：新建独立的远程网关，只调 `/api/v2/*`。
   - 认证靠服务端下发的 HttpOnly Cookie，写请求带 CSRF 头，具体方式看契约 §2。
   - 不复用、也不读取本机 Hub Token。
   - 前端任何存储（localStorage、sessionStorage、IndexedDB、Pinia 持久化）都不能写入会话凭据、Cookie 值或设备凭据。
   - 另做一个基于 `packages/protocol/fixtures/contracts/remote.*.json` 的 Mock 版本，供测试和无服务端时开发。
2. **运行模式**：启动时确定一次，之后不再混用。
   - 本机桌面模式：保持现有行为，一行都不要改坏。
   - 远程 H5 模式：只走 RemoteGateway。
   - 判定规则你来定，比如沿用 `VITE_GATEWAY_MODE` 增加 `remote`，在回执里写清楚。
3. **登录页**（远程模式）：用户名 + 口令。
   - 登录失败统一提示，不区分「用户不存在」和「口令错误」。
   - 被限速时按 `Retry-After` 显示需要等待的时间。
   - 登出能清掉前端内存里的状态。
4. **配对确认页**（手机端）：输入电脑上显示的短码，先预览设备信息，确认后再绑定。要处理过期、冲突、无效三种错误码。
   - 电脑端「发起配对、显示短码」的面板**这一轮不做**，它依赖本机接口 0.6.1，还在冻结中。
5. **设备列表**：在线 / 离线状态，撤销设备（二次确认）。
6. **远程对话**：会话列表、消息、发送、运行列表、run 控制（暂停 / 恢复 / 取消 / 重试）。尽量复用 P3-A 已适配移动端的聊天组件，数据来源换成 RemoteGateway。
7. **事件同步**：用 `/api/v2/events` 加不透明的 `serverCursor` 增量拉取。
   - 游标只原样保存和回传，不解析，也不要拿 Worker 的 seq 当游标。
   - 收到 `REMOTE_CURSOR_EXPIRED` 或 `REMOTE_CURSOR_INVALID` 时，改用 `/snapshot` 取快照重建。
8. **三层状态分开展示**（契约强制，最容易做错）：
   - **传输状态**：电脑在线 / 电脑离线、指令已排队 / 已投递。电脑离线时必须显示「电脑离线，指令已排队」，**绝不能显示成执行中**。
   - **控制结果**：已确认生效（confirmed）、被拒绝（rejected，执行可能仍在进行）、未能确认（unconfirmed，需要回电脑核对）。
   - **执行状态**：Worker 报上来的 TaskStatus，原样展示。
   - 注意：`accepted` 和 `command.completed` 都**不代表任务成功**。
9. **撤回排队中的指令**：只允许撤回尚未投递的指令。要处理 `REMOTE_WITHDRAWAL_TOO_LATE` 和 `REMOTE_WITHDRAWAL_UNCONFIRMED`。
10. **审批分级**：
    - 高风险动作（git_push、deploy、delete、db_migrate，以及服务端标记为高风险的动作）不显示批准按钮，只显示「请回到电脑上处理」，可以拒绝。
    - 服务端返回 `REMOTE_APPROVAL_FORBIDDEN` 时要正确提示。
    - 前端隐藏按钮只是体验，后端另有校验，不要把它当安全措施来写注释或文案。
11. **错误码提示**：`REMOTE_*` 与 `CONVERSATION_AUTHORITY_MISMATCH` 都要有中文提示文案，放进 i18n。

## 明确不做

- 电脑端配对面板（等 0.6.1）
- 附件上传
- 飞书
- 原生会话
- 小程序签名审批：不要留入口或占位按钮

## 验收（贴真实命令输出）

- `apps/desktop` 下 `pnpm typecheck` 通过，`pnpm test` 全绿，原有 207 个一个不少，不放宽任何已有断言。
- 新增测试至少覆盖：
  - 登录成功、失败、限速
  - 配对三种错误
  - 离线排队显示为「已排队」而不是「执行中」
  - 三种控制结果的展示
  - 游标过期后回退到快照
  - 高风险审批没有批准按钮
  - 撤回太晚的提示
  - 本机模式行为不变
  - 前端各类存储里没有凭据
- 用浏览器 DevTools 设备模式（375×812）截图几张关键页（登录、配对确认、对话含离线排队状态、审批），放进回执。这一轮服务端还在开发，用 Mock RemoteGateway 跑即可，并在回执写明「未连接真实服务端验证」。

## 提交与回执

- 提交到 `feat/remote-web-gateway`，不合并其它分支。
- commit message 只描述改动本身，**不得出现任何 AI 署名**：不写 Co-Authored-By，不写「Generated with」「由 XX 生成」之类字样。提交后用 `git log -1 --format=%B` 自查。
- 回执写到 `.hqagent/handoffs/R1-P3B-remote-web-gateway.md`，写清楚以下几项：
  - 改了哪些文件
  - 运行模式怎么判定
  - 三层状态分别在哪个组件里展示
  - 没做到的点
  - 截图
  - 需要服务端 / 协议配合的问题
- 审核方会读真实 diff 和命令输出，不看自述总结。做不到就直接说做不到。
