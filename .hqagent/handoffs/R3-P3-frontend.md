# R3-P3 前端：原生会话 + 授权根目录添加项目（协议 0.9.1，D51）

协议、服务端和电脑端 Hub 都已经合入 integration，并同步到本分支。实际行为以 `apps/server` 和 `apps/hub` 为准，接口以 `packages/protocol/remote/api-guide.md`、`local-chat.v2.yaml` 为准。

## 必读

1. `.hqagent/handoffs/R3-P0-protocol.md`：「下游实施要点 · P3 前端」和「补冻 0.9.1」。
2. `packages/protocol/remote/R3-contract.md`：§3 活跃与确认、§4 导入、§7–8 根目录与浏览、本机原生会话接口一节。
3. `docs/vnext/手机远程接入方案.md` §8、§8.3a、§13。
4. `.hqagent/handoffs/R3-P1-server.md`、`R3-P2-hub.md`。

## 要做（范围 `apps/desktop/**`，类型只从 `@hqagent/protocol` 导入）

### A. 手机端：原生会话

1. 对话列表中，每台电脑下面单独一组「原生会话」，按项目分组，每条标明 Agent 类型（Claude Code / Codex），并显示活跃状态：
   - `unknown` 显示「可能仍在终端中运行」；
   - `likely_active` 显示「终端正在使用」；
   - `closed_confirmed` 显示「已确认关闭」。
2. 点开后只读查看历史：`GET /native-sessions/{id}/messages`，用 before 分页。
   - 这是电脑在线时的实时读取：电脑离线时提示「电脑离线，无法读取原生会话内容」；
   - 遇到 `REMOTE_QUERY_TIMEOUT`（可重试）、`REMOTE_QUERY_TOO_LARGE`、`NATIVE_SESSION_UNSUPPORTED`，显示对应原因和 requestId。
3. 「接着对话」：
   - 弹出确认框，文案要清楚：「请先在电脑终端里退出这个会话。同时写入会损坏会话记录。确认已退出后再继续。」加一个勾选框「我已在终端退出该会话」；
   - 勾选后才能提交 `POST /native-sessions/{id}/imports`，并且 `terminalClosedConfirmed=true`；
   - 202 后显示「正在电脑上导入…」占位（沿用新建任务的占位模式），同步回来后打开导入的对话；
   - 处理 `NATIVE_SESSION_ACTIVE`（「电脑检测到该会话仍在运行」）、`NATIVE_SESSION_CHANGED`（「终端中有新内容，请重新确认」）、`NATIVE_SESSION_WRITER_CONFLICT`、暂停时的 `REMOTE_DEVICE_SUSPENDED`。
4. 导入后的对话（kind=native）没有场景角色：
   - 对话页标题栏显示 Agent 类型；
   - 发送时固定使用 continue；
   - 其余沿用普通对话：忙碌锁、取消、可见性、状态标记。
5. 同步没开或电脑不支持修订 3 时，这一组显示对应原因，不要显示空列表。

### B. 手机端：在授权根目录内添加项目

1. 「新建任务」弹窗的项目下拉框旁边加一个「添加项目」入口。电脑没有授权根目录时，入口置灰并提示「电脑未开放远程添加项目」。
2. 添加项目页面：
   - 先选根目录，显示名称，不显示路径；
   - 然后逐层浏览：`POST /devices/{workerId}/directory-listings`，用 directoryToken 和 cursor 分页；
   - 每行显示文件夹名和「Git 仓库」标记；
   - 支持返回上一层，靠前端自己维护的面包屑栈，不能拼路径；
   - 处理 `REMOTE_ROOT_NOT_AUTHORIZED`、`REMOTE_PATH_OUTSIDE_ROOT`、`REMOTE_DIRECTORY_CHANGED`（提示后回到根目录）、超时、电脑离线、暂停。
3. 选中一个文件夹后点「添加为项目」：`POST /devices/{workerId}/workspaces`，返回 202 后显示占位，目录同步回来后项目出现在下拉框里并自动选中。非 Git 仓库的文件夹要提示「非 Git 仓库只能运行只读任务」。

### C. 电脑端（桌面工作台）

1. **授权根目录设置**：放在「连接手机」页新增的一节，调用本机 `GET` / `PUT /api/v2/remote/authorized-roots`，带 CAS：
   - 列出已授权的根目录，可以添加（复用本机「选择目录」对话框）和移除；
   - 最多 32 个；
   - 说明文案：「手机只能在这些目录内浏览和添加项目，默认不开放」。
2. **原生会话**：在「本地对话」侧栏新增「原生会话」一组，使用本机 `/api/v2/native-sessions`：
   - 可以只读查看；
   - 可以本地导入，确认勾选与手机端一致，201 后直接打开对话；
   - 导入后显示 Agent 类型。
3. **导入对话的同步状态**：已导入、但尚未上传的 native 对话（服务端不支持修订 3，或栅栏未完成），按契约显示「已在本机导入，待连接支持修订 3 的服务后同步」。离线、未配对、同步关闭时各自显示真实原因，不要显示「同步成功」。

### D. 通用

- 新增错误码的中文提示与 api-guide 的错误码总表一致，失败时附 requestId（沿用 R1.5+ 的做法）。
- 原生会话内容、目录名、令牌都不能写进持久存储或日志。

## 测试

- A：
  - 分组和活跃状态标签；
  - 离线时读取提示；
  - 不勾选时无法提交；
  - 导入的 202 占位和打开；
  - ACTIVE / CHANGED / WRITER_CONFLICT / SUSPENDED 的提示；
  - native 对话发送固定为 continue。
- B：
  - 没有根目录时入口置灰；
  - 逐层浏览与返回上一层，靠面包屑栈；
  - DIRECTORY_CHANGED 后回到根目录；
  - 登记后项目出现并被选中；
  - 非 Git 仓库的提示。
- C：
  - 根目录增删与 CAS 冲突；
  - 本地原生会话的查看与导入；
  - 待同步状态的文案。

跑 lint、typecheck、`vitest run --minWorkers=1 --maxWorkers=2`、build，贴真实输出。375×812 截图：原生会话列表、导入确认框、目录浏览；外加电脑端 1280×800 截图：授权根目录设置。截图用 Mock 数据，**不要用真实会话内容**。

回执写到 `.hqagent/handoffs/R3-P3-frontend-receipt.md`，提交到 `feat/r15-web`。commit message 不得出现任何 Claude / Anthropic / Codex / Gemini 署名，不写 Co-Authored-By，不写「Generated with」字样；每次提交后用 `git log -1 --format=%B` 自查。
