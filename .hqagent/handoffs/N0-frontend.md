# N0 本地角色对话版前端交付报告 (N0-frontend)

| 项 | 值 |
| --- | --- |
| taskId | `N0-frontend` |
| milestone | `N0 本地角色对话版前端` |
| branch | `work/vnext-frontend` |
| worktree | `E:\OtherPro\HQAgent-Hub-worktrees\vnext-frontend` |
| 共同基线 | `3dc0704` (`feat(protocol): 定义本地场景与对话增量契约`) |
| 协议版本 | `0.3.0` |
| 日期 | `2026-09-24` |

---

## 1. 交付范围与功能清单

依据 `docs/vnext/前端独立开工说明.md` 与 `packages/protocol/openapi/local-chat.v2.yaml`，已完成前端全量独立开发与闭环验证：

### 1.1 本地连接页 (`/connect` - `ConnectPage.vue`)
- **HttpOnly Cookie 本地鉴权**：用户输入 Worker 控制台输出的一次性连接码（6~128位），向 `POST /api/v2/auth/local-session` 发起安全建连；浏览器完全不将 Token 写入 localStorage，不读 hub.json，不使用 VITE_HUB_TOKEN。
- **状态异常明确提示**：后端未就绪、连接码失效或过期有独立错误提示和刷新入口。
- **模式切换与显式标识**：提供"演示模式 (Mock)"与"真实 Worker"显式切换，界面有高保真演示模式标识条，杜绝静默使用 Mock 伪装连接。

### 1.2 对话工作台 (`/chat` - `ChatPage.vue`)
- **三栏式工作台架构**：
  - **左栏 (`ChatSidebar.vue`)**：对话列表、关键字与场景搜索、新建对话弹窗（包含标题输入、已登记项目选择、初始场景选择，只提交业务配置不立即执行模型）。
  - **中栏 (`ChatMessageItem.vue` & `ChatComposer.vue`)**：
    - 消息流：用户输入、系统过程信息与助手最终回复独立分块展示；明确标注当前角色，不输出模型内部隐藏思考过程。
    - 安全 Markdown 渲染：复用 `HqMarkdown`，无注入风险。
    - 运行中排队：当前轮次执行中支持继续输入，后续指令进入排队状态，防止重复请求与重复点击。
    - 上下文模式：提供「新一轮上下文 (new)」与「继续已有Agent会话 (continue)」切换；首条默认 new，后续默认 continue；若底层会话不支持恢复如实提示 `SESSION_NOT_RESUMABLE` 拒绝原因并引导切换为 new。
  - **右栏 (`RunSnapshotDrawer.vue`)**：
    - 本轮场景快照 (`sceneSnapshot`)：展示当前轮次固化的角色分配、模型规格与思考强度。
    - 步骤与状态：展示节点流转、状态徽标（含 resolving, running, waiting_approval 等）与 6 级 `resolveSource` 徽标。
    - 真实变更文件与越界违规：如实展示工作区内改动的真实文件列表与违规越界路径高危红色提示。
    - 产物清单：展示生成的报表、文件与 diff 产物。
    - 任务控制：节点间暂停 (`pause`)、继续 (`resume`)、重试 (`retry`)，取消任务需二次确认弹窗 (`cancel`)。
    - 高危审批：若有等待审批的危险动作，抽屉顶部提请放行或拒绝。

### 1.3 场景与角色配置 (`/scenes` - `ScenesPage.vue`)
- **三套预置场景**：代码分析 (`analyze`，只读)、需求规划 (`plan`，只读)、开发修复 (`develop`，读写)。
- **角色分配与模型规格配置**：
  - 支持配置执行 Agent、职责约束提示词 (`instructions`，上限 12000 字符带字数统计)、模型规格 (`modelId`)、思考强度 (`reasoningEffort`) 以及可选角色启用状态。
  - 只读角色锁定，禁用前端提权。
  - 动态模型目录：从后端拉取模型列表；若空目录且未验证，显示未验证原因并提供手填模型规格输入，由后端实时验证。
  - 乐观并发与版本冲突 (HTTP 409)：保存提交 `expectedVersion`，冲突时红框提示并提供一键刷新覆盖。
  - 提示说明：明确告知修改配置仅对后续新建 Run 生效，历史消息始终保留其自身的场景快照。

### 1.4 双网关同构解耦 (`src/shared/api/`)
- `LocalChatGateway` 接口定义 20+ 个强类型 OpenAPI 操作。
- `RealLocalChatGateway`：基于 `fetch` (with `credentials: 'include'`) 实现与后端通讯，所有写操作附带 `Idempotency-Key` 请求头。
- `MockLocalChatGateway`：严格组合 `@hqagent/fixtures` 原子契约构建（代码分析场景、多角色执行中、等待审批、失败重试、409 冲突模拟、会话不可恢复模拟、410 游标过期模拟）。

---

## 2. 改动文件范围

所有改动严格限制在 `apps/desktop/src/**`、`apps/desktop/vite.config.ts` 以及本 handoff 文件：

```text
apps/desktop/src/app/layouts/components/AppSidebar.vue
apps/desktop/src/app/router/index.ts
apps/desktop/src/pages/auth/ConnectPage.vue
apps/desktop/src/pages/auth/ConnectPage.test.ts
apps/desktop/src/pages/chat/ChatPage.vue
apps/desktop/src/pages/chat/ChatPage.test.ts
apps/desktop/src/pages/chat/components/ChatSidebar.vue
apps/desktop/src/pages/chat/components/ChatMessageItem.vue
apps/desktop/src/pages/chat/components/ChatComposer.vue
apps/desktop/src/pages/chat/components/RunSnapshotDrawer.vue
apps/desktop/src/pages/scenes/ScenesPage.vue
apps/desktop/src/pages/scenes/ScenesPage.test.ts
apps/desktop/src/shared/api/local-chat-gateway.interface.ts
apps/desktop/src/shared/api/local-chat-gateway.ts
apps/desktop/src/shared/api/local-chat-gateway.test.ts
apps/desktop/src/shared/api/mock-local-chat-gateway.ts
apps/desktop/src/shared/api/mock-local-chat-gateway.test.ts
apps/desktop/src/shared/api/local-chat-provider.ts
apps/desktop/src/shared/api/index.ts
apps/desktop/src/stores/local-auth.store.ts
apps/desktop/src/stores/local-auth.store.test.ts
apps/desktop/src/stores/chat.store.ts
apps/desktop/src/stores/chat.store.test.ts
apps/desktop/src/stores/scenes.store.ts
apps/desktop/src/stores/scenes.store.test.ts
apps/desktop/src/stores/index.ts
apps/desktop/vite.config.ts
.hqagent/handoffs/N0-frontend.md
```

未修改任何外部目录：`packages/protocol/**`、`apps/hub/**`、`src-tauri/**`、根 package.json/lockfile 均保持原样。

---

## 3. 启动方式

### 开发启动
```powershell
cd E:\OtherPro\HQAgent-Hub-worktrees\vnext-frontend
pnpm --filter @hqagent/desktop dev
```
- 访问：`http://localhost:5173/chat`
- 如未启动后端 Worker，可在 `/connect` 点击「进入 Mock 演示环境」体验完整交互与场景切换。
- 若连接真实 Worker，启动 Worker 后在 `/connect` 输入控制台输出的 6 位以上连接码即可。

---

## 4. 验收命令与执行输出

在 `E:\OtherPro\HQAgent-Hub-worktrees\vnext-frontend` 真实执行并全部退出 0：

### 4.1 代码规范检查 (`pnpm --filter @hqagent/desktop lint`)
```powershell
$ eslint src
# 退出代码: 0 (0 errors, 0 warnings)
```

### 4.2 严格类型检查 (`pnpm --filter @hqagent/desktop typecheck`)
```powershell
$ vue-tsc --noEmit
# 退出代码: 0
```

### 4.3 单元测试套件 (`pnpm --filter @hqagent/desktop test`)
```powershell
$ vitest run

 ✓ src/shared/api/local-chat-gateway.test.ts (4 tests) 8ms
 ✓ src/shared/theme/theme.engine.test.ts (5 tests) 9ms
 ✓ src/shared/api/local-hub-gateway.test.ts (8 tests) 138ms
 ✓ src/shared/api/mock-local-chat-gateway.test.ts (8 tests) 8ms
 ✓ src/shared/api/mock-gateway.test.ts (10 tests) 50ms
 ✓ src/stores/chat.store.test.ts (5 tests) 26ms
 ✓ src/stores/approval.store.test.ts (4 tests) 234ms
 ✓ src/stores/app.store.test.ts (8 tests) 309ms
 ✓ src/stores/task.store.test.ts (7 tests) 579ms
 ✓ src/stores/team.store.test.ts (5 tests) 1130ms
 ✓ src/stores/workspace.store.test.ts (3 tests) 251ms
 ✓ src/pages/approvals/ApprovalsPage.test.ts (3 tests) 121ms
 ✓ src/pages/tasks/TasksPage.test.ts (3 tests) 121ms
 ✓ src/pages/templates/TemplatesPage.test.ts (3 tests) 171ms
 ✓ src/pages/tasks/TaskDetailPage.test.ts (5 tests) 286ms
 ✓ src/pages/auth/ConnectPage.test.ts (2 tests) 93ms
 ✓ src/stores/agent.store.test.ts (3 tests) 411ms
 ✓ src/pages/agents/AgentsPage.test.ts (3 tests) 169ms
 ✓ src/pages/sessions/SessionsPage.test.ts (3 tests) 169ms
 ✓ src/app/layouts/AppLayout.test.ts (3 tests) 231ms
 ✓ src/pages/workspaces/WorkspacesPage.test.ts (3 tests) 158ms
 ✓ src/pages/chat/ChatPage.test.ts (3 tests) 275ms
 ✓ src/pages/onboarding/OnboardingPage.test.ts (2 tests) 238ms
 ✓ src/stores/scenes.store.test.ts (3 tests) 6ms
 ✓ src/pages/scenes/ScenesPage.test.ts (3 tests) 218ms
 ✓ src/stores/local-auth.store.test.ts (2 tests) 5ms
 ✓ src/shared/ui/HqButton.test.ts (4 tests) 37ms
 ✓ src/pages/teams/TeamsPage.test.ts (3 tests) 91ms
 ✓ src/pages/overview/OverviewPage.test.ts (2 tests) 62ms
 ✓ src/stores/session.store.test.ts (2 tests) 285ms

 Test Files  30 passed (30)
      Tests  122 passed (122)
   Start at  18:47:24
   Duration  4.84s (transform 3.16s, setup 0ms, collect 17.85s, tests 5.89s, environment 24.24s, prepare 3.99s)
# 退出代码: 0
```

### 4.4 生产打包编译 (`pnpm --filter @hqagent/desktop build`)
```powershell
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1710 modules transformed.
dist/index.html                                                                   2.50 kB │ gzip:  1.02 kB
dist/assets/index-Djn4IftJ.css                                                   48.94 kB │ gzip:  9.05 kB
dist/assets/echarts-l0sNRNKZ.js                                                   0.00 kB │ gzip:  0.02 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-DvuscHYE.js          1.17 kB │ gzip:  0.62 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-CtkFEANJ.js          1.55 kB │ gzip:  0.75 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-BTadDkMb.js            1.69 kB │ gzip:  0.82 kB
dist/assets/PlaceholderPage-DwWF9sVE.js                                           1.74 kB │ gzip:  1.10 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-Dyofv_Zs.js              2.16 kB │ gzip:  1.06 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-B6LWDtqz.js               2.32 kB │ gzip:  1.04 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-CFsQHVqv.js          2.44 kB │ gzip:  1.19 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-CqBmmyi8.js    2.61 kB │ gzip:  1.42 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-Cc4pHqsb.js              2.85 kB │ gzip:  1.33 kB
dist/assets/team.store-DLqzpzNk.js                                                3.73 kB │ gzip:  1.88 kB
dist/assets/ConnectPage-BUYHspTa.js                                               5.09 kB │ gzip:  2.46 kB
dist/assets/task.store-Cb5mdnuT.js                                                6.99 kB │ gzip:  2.61 kB
dist/assets/WorkspacesPage-DbQbUne_.js                                            8.80 kB │ gzip:  3.50 kB
dist/assets/TemplatesPage-BEJchLsc.js                                             9.61 kB │ gzip:  4.26 kB
dist/assets/SessionsPage-kaf-eOit.js                                             10.55 kB │ gzip:  4.50 kB
dist/assets/ScenesPage-nvj4WtMu.js                                               11.42 kB │ gzip:  4.87 kB
dist/assets/AgentsPage-DnYujqun.js                                               11.61 kB │ gzip:  4.05 kB
dist/assets/TasksPage-DoN1zNqb.js                                                11.73 kB │ gzip:  4.67 kB
dist/assets/OverviewPage-BcYjwiDL.js                                             12.10 kB │ gzip:  3.95 kB
dist/assets/ApprovalsPage-DYOaa8u8.js                                            12.26 kB │ gzip:  4.95 kB
dist/assets/OnboardingPage-CiU9ecZQ.js                                           12.93 kB │ gzip:  4.91 kB
dist/assets/TeamsPage-mDiz_bAI.js                                                15.96 kB │ gzip:  5.93 kB
dist/assets/TaskDetailPage-CojodLdt.js                                           23.40 kB │ gzip:  7.98 kB
dist/assets/ChatPage-DSFYkorO.js                                                 35.73 kB │ gzip: 11.46 kB
dist/assets/vendor-CB21-3Re.js                                                  138.72 kB │ gzip: 48.18 kB
dist/assets/index-BLJBWbdm.js                                                   158.79 kB │ gzip: 50.56 kB
✓ built in 5.05s
# 退出代码: 0
```

---

## 5. 真实后端联调状态说明

- **当前状态**：前端独立开工验收完成（前端单测与 Mock 验收 100% 通过）。
- **联调就绪度**：
  - `RealLocalChatGateway` 严格按照 `local-chat.v2.yaml` 规格编写，配置了 `credentials: 'include'` 与 `Idempotency-Key`。
  - Vite 已预设 `/api` 与 `/ws` 代理到本地 Worker 服务端口。
  - 后端 Worker 就绪后，仅需输入本地连接码即可直接联调，前端无需任何代码修改。

---

## 6. 尚未完成项与后续演进

- 本期交付范围内的功能已全部完成并闭环，无未完成遗留项。
- 二期规划项（未在此次 N0 范围）：原生物理设备远程配对、手机协同入口、CLI 全文导入，按后续规划阶段执行。
