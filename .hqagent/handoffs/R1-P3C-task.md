# R1-P3C 任务：电脑端「连接手机」面板与远程对话只读展示

背景：手机远程接入的服务端（P1）、电脑端 Worker 连接（P2）已完成，本机真实联调通过：配对、手机发消息、电脑执行回传、离线排队、远程取消都已跑通。现在缺的是**电脑上的界面**：用户要在本机工作台里发起配对、看到短码、看连接状态、解除绑定；远程对话在电脑上要显示为只读。

## 产品定位（必须遵守）

远程能力只是通信工具。界面上**不出现任何模型 API Key、模型账号**之类的输入或展示。

## 工作区

- 新 worktree：`E:\OtherPro\HQAgent-Hub-worktrees\remote-pc-pairing`，分支 `feat/remote-pc-pairing`，基于 `integration/phase1`（含协议 0.6.1 与 P1/P2 后端），已 `pnpm install`。
- 基线：`apps/desktop` 下 `pnpm typecheck` 通过，`pnpm test` 201 passed。
- 只在这个目录工作。它**不包含** P3-A / P3-B 的改动，不要去别的 worktree 拷代码。

## 先读

1. `AGENTS.md`（路径所有权、提交规范、安全红线）
2. `packages/protocol/schema/remote-link.json`：RemoteLinkView 五种状态（unpaired / pairing / paired / revoked / frozen）与 RemoteLinkPairingInput
3. `packages/protocol/remote/R1-contract.md` §11 之后关于 D43 的说明，以及 `.hqagent/DECISIONS.md` 的 D43
4. 现有本机工作台的网关：
   - `apps/desktop/src/shared/api/local-chat-gateway.ts`
   - `apps/desktop/src/shared/api/local-chat-gateway.interface.ts`
   - `apps/desktop/src/shared/api/mock-local-chat-gateway.ts`

   它们走本机 `/api/v2/*` 的 Cookie 会话，`credentials: 'include'`。

## 接口（D44，主代理已裁决，后端正在同步实现）

本机工作台用 Cookie 会话调用下面四个接口，请求与响应类型都是已冻结的 `@hqagent/protocol` 类型：

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/v2/remote/link` | — | `RemoteLinkView` |
| POST | `/api/v2/remote/pairing` | `RemoteLinkPairingInput`（serverOrigin、deviceName），带 Idempotency-Key | `RemoteLinkView`（state=pairing，含短码与过期时间） |
| DELETE | `/api/v2/remote/pairing` | 带 Idempotency-Key | `RemoteLinkView` |
| POST | `/api/v2/remote/unlink` | 带 Idempotency-Key | `RemoteLinkView` |

- 注意：这是 **Local Hub 本机**的 `/api/v2`，和云端服务器的 `/api/v2` 同名前缀但不是一个服务。**不要**调用本机 `/api/v1/remote/*`：那组要 Bearer Hub Token，前端不能拿。
- 后端合入之前，请先用 Mock 网关开发。主代理合入 D44 后会通知你，再对真实本机 Hub 自测。
- 状态更新用轮询：pairing 状态下每 2 秒 GET 一次；其余状态可以更慢，或者只在进入页面、切回页面时刷新。

## 要做的

1. **网关**：在本机工作台的网关接口里加这四个方法，真实实现和 Mock 实现都要有。Mock 要能模拟完整流程：unpaired → pairing（短码 5 分钟倒计时）→ paired online → 断线 offline → 解绑回到 unpaired；还要能模拟 revoked 和 frozen。
2. **「连接手机」页面或面板**：放在侧边栏或设置入口里，位置你来定，移动端和桌面端都要可用。
   - **unpaired**：填服务器地址（只接受 https，提示格式）和设备名（默认值可取「我的电脑」），点「开始配对」。
   - **pairing**：大号显示 8 位短码与剩余时间，提示「在手机上登录后输入此短码」；可以取消配对；过期后提示重新发起。
   - **paired**：显示服务器、设备名、在线 / 连接中 / 离线、上次连接时间、最近错误（错误码转成中文提示）；提供「解除绑定」，需要二次确认。确认框里写明两点：
     - 解绑后，已有的远程对话在电脑上仍是只读，不会变回本地对话；
     - 服务端的撤销可能要在手机端再撤销一次设备才生效。
   - **revoked / frozen**：如实说明状态和用户下一步该做什么。frozen 表示存储世代需要核对，**不要**提供「一键解除冻结」这类按钮。
   - 服务器地址非法、服务器不可达、配对已在进行中等错误码，都要有中文提示并放进 i18n。
   - 短码只在 pairing 状态显示。界面、日志、本地存储（localStorage / sessionStorage / IndexedDB / Pinia 持久化）里都不能出现设备 secret、Authorization 或 Hub Token；短码也不要写进任何持久存储。
3. **远程对话只读**：`LocalConversationView.authority === 'remote'` 的对话，在电脑工作台里：
   - 对话列表加「远程」标识；
   - 聊天页禁用输入框和运行控制按钮（发送、追加、暂停、恢复、取消、重试、改标题、归档等写操作），显示提示「这是手机远程对话，请在手机上继续」；
   - 历史消息和运行状态照常可看；
   - authority 字段缺失时视为 local，现有本地对话的行为一点不能变。

   后端对这类写请求本来就会返回 409 `CONVERSATION_AUTHORITY_MISMATCH`，前端禁用只是体验，但收到这个错误码时也要有正确提示。

## 明确不做

- 手机端页面：P3-B，Gemini 另一条线在做，不要碰
- 云端服务器的任何接口
- 附件、飞书、原生会话、小程序签名审批

## 范围

只改 `apps/desktop/**` 和你的回执 `.hqagent/handoffs/R1-P3C-remote-pc-pairing.md`。不改 `packages/protocol/**`、`apps/hub/**`、`apps/server/**`、根共享文件。缺字段或接口不符就写进回执，不要自造类型。

## 验收（贴真实命令输出）

- `pnpm typecheck` 通过；`pnpm test` 全绿，原有 201 个一个不少，不放宽任何已有断言。
- 新增测试至少覆盖：
  - 五种状态的展示；
  - 发起配对与取消；
  - 短码倒计时与过期；
  - 解绑二次确认；
  - 错误码中文提示；
  - remote 对话输入禁用；
  - local 对话不受影响；
  - 各类前端存储里没有短码、secret 或 token。
- 截图：连接手机页各状态，以及远程对话的只读聊天页，宽屏和 375×812 各一组，放进回执。
- 本轮先用 Mock，回执写明「未对真实本机 Hub 自测」。主代理合入 D44 后会通知你补测。

## 提交与回执

- 提交到 `feat/remote-pc-pairing`，不合并其它分支。
- commit message 只描述改动本身，**不得出现任何 AI 署名**（不写 Co-Authored-By，不写「Generated with」「由 XX 生成」之类字样）。提交后用 `git log -1 --format=%B` 自查。
- 回执写清：
  - 改了哪些文件；
  - 入口放在哪里；
  - 轮询策略；
  - 只读是怎么判定和实现的；
  - 没做到的点；
  - 截图。
- 审核方会读真实 diff 和命令输出，不看自述总结。做不到就直接说做不到。
