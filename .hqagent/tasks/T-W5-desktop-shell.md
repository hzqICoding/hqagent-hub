# T-W5 桌面壳与本机接入

| 项 | 值 |
| --- | --- |
| taskId | `T-W5-desktop-shell` |
| owner | Codex |
| baseCommit | `a3e1047874e8e900e36f4377bc07cea550b524af`（FZ-1） |
| branch | `work/w5-shell` |
| worktreePath | `E:\OtherPro\HQAgent-Hub-worktrees\w5-shell` |
| handoff | `.hqagent/handoffs/T-W5-desktop-shell.md` |

## allowedPaths

```
apps/desktop/src-tauri/**
```

不要动 `apps/desktop/src/`（W4 前端在做），不要动 `apps/hub/`（W1 在做），不要动 `packages/protocol/`（W0 的），不要动仓库根共享配置。

## 开工前必读

1. `AGENTS.md` —— 全局边界，与本文件冲突时以 AGENTS.md 为准
2. `.hqagent/PROJECT_CONTEXT.md`、`.hqagent/ARCHITECTURE.md`、`.hqagent/INTERFACES.md`
3. `docs/分工与并行开工方案.md` §5.6 —— 你的完整交付物和 7 条验收；§8 D3 —— 鉴权裁决
4. `packages/protocol/schema/runtime-descriptor.json` —— **本包的核心契约**，hub.json / update-agent.json / WS Ticket 全在这
5. `docs/OTA升级架构设计.md` §4.2（进程边界）、§14（本地目录）

## 范围

单实例、系统托盘、开机自启、原生标题栏、窗口状态持久化；子进程生命周期；Hub 发现与本机鉴权；Windows Credential Manager 安全存储；维护模式 Gate；WebView 安全策略。

## 本包最重要的部分：本机鉴权

Local Hub 能改文件、跑 shell、推 git。裸开一个本地端口等于给本机任意程序开后门。按 `runtime-descriptor.json` 的 `x-contract` 实现，**不要简化**：

1. Hub 启动后原子写入 `%LOCALAPPDATA%\HQAgent-Hub\runtime\hub.json`，含 `schemaVersion / instanceId / port / token / pid / baseUrl / appVersion / protocolVersion / startedAt`，文件 ACL 移除继承、只保留当前用户。
2. Tauri 读取后通过 `invoke('get_hub_endpoint')` 只把 `baseUrl` 与 `token` 交给前端。**Vue 拿不到 Update Agent 的 endpoint。**
3. HTTP 用 `Authorization: Bearer <token>`。WebSocket 不能用 Bearer（WebView 原生 WebSocket 设不了 Header），必须先用 Bearer 调 `POST /api/v1/auth/ws-ticket` 换 30 秒一次性 Ticket，再以查询参数握手。
4. 用 `instanceId` 识别陈旧 Descriptor：进程被强杀时文件会残留，只看 pid 会连到已不存在或被复用的进程上。
5. Tauri CSP 只允许打包资源和明确的 loopback 连接，禁止远程页面导航。

安全目标是阻止其他 Windows 用户、普通网页和误调用；**不宣称**能抵御已获得当前用户权限的恶意进程——不要在实现或文档里过度承诺。

## 与 W1 的边界

Hub 侧的 Token 校验、CORS/Origin 校验、ws-ticket 端点由 **W1** 实现。你负责壳这一侧：读 Descriptor、守护进程、把 endpoint 交给前端、CSP。

如果联调时发现 Hub 侧还没做好，**不要自己去改 `apps/hub/`**，写 handoff 提出来。W1 与你并行开工，短期内 Hub 可能还跑不起来，这是预期内的——你可以先用一个符合 `runtime-descriptor.json` 的假 hub.json 和一个最小 HTTP stub 自测。

## 子进程生命周期

拉起并守护 `hqagent-core.exe` 与 `hqagent-update-agent.exe`；崩溃自动重启（带退避）；桌面窗口关闭**不杀** Hub；应用退出时按序停止。进程边界严格按 OTA 文档 §4.2。

一期这两个 exe 还不存在，用可配置路径 + 明确的"未找到可执行文件"状态处理，不要硬编码也不要静默失败。

## 验收（逐条自测并交回实测记录）

- [ ] 双击第二次不产生第二个实例，而是激活已有窗口
- [ ] 杀掉子进程后 10 秒内自动重启（可用一个 stub 可执行文件验证）
- [ ] 关闭主窗口后子进程仍在运行，托盘可恢复窗口
- [ ] 用 curl 不带 token 打 Hub 端口返回 401（可用 stub 验证）
- [ ] `hub.json` 的 ACL 检查通过：**必须给出实测证据**，例如 `icacls` 输出显示只有当前用户
- [ ] Bearer 能换一次性 WS Ticket，同一 Ticket 第二次握手失败
- [ ] 陈旧 Descriptor（instanceId 不匹配或进程已退出）被正确忽略
- [ ] 从非允许 Origin 发起的 HTTP/WS 请求被拒绝

```powershell
cd E:\OtherPro\HQAgent-Hub-worktrees\w5-shell\apps\desktop\src-tauri
cargo check
cargo test
```

## 交付

- 在 `work/w5-shell` 上提交。commit message 只描述改动本身，**不要任何 AI 署名、不要 Co-Authored-By、不要 Generated with 字样**。提交后用 `git log -1 --format=%B` 自查。
- 写 `.hqagent/handoffs/T-W5-desktop-shell.md`：做了什么、没做什么、验收逐条结果（贴真实命令输出）、需要 W1 配合的点。
- ACL 和 Ticket 重放这两项必须有实测证据，不接受"应该没问题"。
