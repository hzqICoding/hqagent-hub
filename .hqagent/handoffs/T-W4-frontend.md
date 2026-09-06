# T-W4 桌面前端 F2 交付报告

| 项 | 值 |
| --- | --- |
| taskId | `T-W4-frontend` |
| milestone | `F2: 工作区、团队配置与任务模板 (Workspaces, Teams, Templates)` |
| branch | `work/w4-frontend` |
| worktree | `E:\OtherPro\HQAgent-Hub-worktrees\w4-frontend` |
| date | `2026-09-06` |

---

## 1. F1 必修项闭环 (R1–R4, R6, R7 详报)

按照 `.hqagent/reviews/T-W4-frontend.F1.md` 审核结论，已全量修复并在 `src/shared/api/local-hub-gateway.test.ts` 补齐单元测试：

1. **R1 消除硬编码回退 Token 与固定端口** (`local-hub-gateway.ts`):
   - 彻底移除 `tok_dev_fallback_hub_token` 字面量与硬编码 `49210` 端口。
   - `getHubEndpointFromTauri()` 在 Tauri 环境调用 `invoke('get_hub_endpoint')` 失败时直接 `throw`，确保 W5 桌面壳的四重描述符校验拒绝能被前端如实捕获；浏览器 Dev 模式下仅读取 `import.meta.env.VITE_HUB_BASE_URL` 与 `VITE_HUB_TOKEN`，未配置时显式抛错。
2. **R4 协议错误码解析与 `HubApiError` 封装** (`local-hub-gateway.ts`, `shared/api/index.ts`):
   - 实现 `export class HubApiError extends Error`，携带 `code: ErrorCode`、`status: number`、`detail?: Record<string, unknown>`、`retryable: boolean`、`requestId?: string`。
   - `fetchApi` 无论 HTTP 状态码是否为 2xx，优先解析 JSON 信封 `ApiEnvelope<T>`，若发现 `envelope.error` 则提取业务错误码抛出 `HubApiError`（适配 `ORIGIN_NOT_ALLOWED`、`HUB_MAINTENANCE`、`EVENT_CURSOR_EXPIRED` 等 30 个协议错误码）。
3. **R2 WebSocket 竞态单飞 (Single-flight)** (`local-hub-gateway.ts`):
   - 引入 `connectPromise: Promise<void> | null`。同一 tick 内多次调用 `subscribeEvents` 时共享同一个在建连接 Promise，杜绝重复换票与孤儿 WebSocket 泄漏。
4. **R3 换票失败退避重连** (`local-hub-gateway.ts`):
   - 换票 `acquireWsTicket()` 失败在 catch 块捕获，统一引导至 `scheduleReconnect()`，避免 Hub 启动较慢时出现永久性断连。
5. **R6 游标过期恢复路径** (`local-hub-gateway.ts`):
   - 捕获 `EVENT_CURSOR_EXPIRED` 错误码时，重置 `this.lastConfirmedSeq = 0`，确保下次重连能够重新获取全量 Snapshot。
6. **R7 指数退避重连** (`local-hub-gateway.ts`):
   - 替换原固定 3 秒重试，改为指数退避 `Math.min(1000 * Math.pow(1.5, attempts), 15000)`，并在退订或成功建立连接时清理定时器与计数。
7. **R5 补齐 ESLint 配置与 `lint` Script** (`apps/desktop/package.json`, `eslint.config.js`):
   - 配置 ESLint Flat Config，增加 `"lint": "eslint src"`。全代码库 51 处未用变量告警全部清零，达到 0 errors, 0 warnings。

---

## 2. F2 核心功能交付清单

### 2.1 领域 Store 层扩展 (`apps/desktop/src/stores/`)
- `workspace.store.ts`:
  - 管理本地工作区列表 (`WorkspaceView[]`)、当前激活工作区 (`currentWorkspace`)、最近打开工作区排序 (`recentWorkspaces`)。
  - 工作区操作：`fetchWorkspaces()`、`switchWorkspace()`、`addWorkspace()`、`removeWorkspace()`。
  - 共享记忆状态管理：`initMemoryDir(id)` 支持一键初始化 `.hqagent/` 目录。
  - 项目级 Team Profile 覆盖：`setWorkspaceProfile(workspaceId, profileId)`。
- `team.store.ts`:
  - 团队配置方案管理 (`TeamProfileView[]`)、当前激活方案、全局/工作区作用域分组。
  - 方案操作：`fetchProfiles()`、`saveProfile()`、`duplicateProfile()`、`deleteProfile()`、`setDefaultProfile()`。
  - 导入导出：`exportProfile()` 序列化 JSON、`importProfile()` 结构校验与导入。
  - 实时路由解析：`resolveProfile()` 调用 `gateway.resolveTeamProfile()`，解析首选/备用链并检视能力缺口。

### 2.2 业务页面交付（全部覆盖 loading / empty / error / offline 四态）
- `WorkspacesPage.vue` (`/workspaces`):
  - 顶部统计 Bento 卡片：受管工作区总数、Git 支持率、.hqagent 共享记忆就绪率。
  - 工作区卡片流：展示绝对路径（带一键复制）、Git 分支名、`isClean` 干净状态徽标、`.hqagent` 记忆目录就绪状态。
  - 快速操作：切换为当前工作区、未就绪时「一键初始化记忆」、从列表移除工作区。
  - 「添加目录」模态弹窗 (`HqDialog` + `HqInput`)。
- `TeamsPage.vue` (`/teams`):
  - **三栏式 Studio 架构**（施工方案 §11.4 标准）：
    - **左栏（团队方案列表）**：展示全局/工作区配置、当前激活态、默认配置徽标、新建与导入按钮。
    - **中栏（角色分配与备用链 Studio）**：
      - 六大系统角色 (`orchestrator`, `architect`, `frontend_implementer`, `general_implementer`, `reviewer`, `tester`)。
      - 首选 Agent (Primary) 下拉选择器（来自探测就绪列表）。
      - 备用链 (Fallback Chain) 动态标签列表，支持添加/移除备用实例。
      - 方案快捷操作：设为默认、克隆副本、导出 JSON、删除。
    - **右栏（实时路由解析与缺口预览）**：
      - 严格落实四层解耦，**`resolveSource` 六级来源完整呈现且视觉特征高度区分**：
        1. `task_override`: 单次任务指定 (Indigo)
        2. `workspace_profile`: 项目配置绑定 (Cyan)
        3. `global_profile`: 全局团队配置 (Purple)
        4. `capability_match`: 动态能力匹配 (Teal)
        5. `fallback`: **备用链故障降级** (Amber 警告高亮 + 醒目环形徽标 + 显示 `fallbackReason` 降级原因说明)
        6. `manual`: **等待人工决策** (Rose 警示动画高亮 + 提请人工干预)
      - 能力缺口清单 (`gaps`)：展示缺口角色、缺少硬能力与具体原因。
- `TemplatesPage.vue` (`/templates`):
  - 开箱模板库（标准全栈协作团队、代码审查与质量把关、极速原型与敏捷构建、架构重构与平滑升级）。
  - 分类过滤（全部/开发协作/代码审查/极速原型）与文本模糊搜索。
  - 每套模板展示所需角色清单、所需硬能力、以及本机当前兼容 Agent 数量。
  - 「应用此模板」预览弹窗：预估角色映射并一键生成新团队配置并跳转到配置页。

### 2.3 路由接入 (`apps/desktop/src/app/router/index.ts`)
- 将 `/workspaces`、`/teams`、`/templates` 正式从 `PlaceholderPage` 切换为上述业务页面组件。

---

## 3. 验收命令与实测执行结果

### 3.1 代码规范检查 (`pnpm --filter @hqagent/desktop lint`)
```powershell
$ eslint src
# 退出代码: 0（0 errors, 0 warnings）
```

### 3.2 严格类型检查 (`pnpm --filter @hqagent/desktop typecheck`)
```powershell
$ vue-tsc --noEmit
# 退出代码: 0
```

### 3.3 单元测试全家桶 (`pnpm --filter @hqagent/desktop test`)
```powershell
$ vitest run

 ✓ src/shared/theme/theme.engine.test.ts (5 tests)
 ✓ src/shared/api/local-hub-gateway.test.ts (6 tests)
 ✓ src/shared/api/mock-gateway.test.ts (6 tests)
 ✓ src/shared/ui/HqButton.test.ts (4 tests)
 ✓ src/stores/workspace.store.test.ts (3 tests)
 ✓ src/stores/app.store.test.ts (5 tests)
 ✓ src/stores/agent.store.test.ts (3 tests)
 ✓ src/pages/overview/OverviewPage.test.ts (2 tests)
 ✓ src/pages/workspaces/WorkspacesPage.test.ts (3 tests)
 ✓ src/pages/agents/AgentsPage.test.ts (3 tests)
 ✓ src/pages/teams/TeamsPage.test.ts (3 tests)
 ✓ src/pages/templates/TemplatesPage.test.ts (3 tests)
 ✓ src/pages/onboarding/OnboardingPage.test.ts (2 tests)
 ✓ src/app/layouts/AppLayout.test.ts (3 tests)
 ✓ src/stores/team.store.test.ts (5 tests)

 Test Files  15 passed (15)
      Tests  56 passed (56)
# 退出代码: 0
```

### 3.4 生产打包构建 (`pnpm --filter @hqagent/desktop build`)
```powershell
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1676 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                                                             2.50 kB │ gzip:  1.02 kB
dist/assets/index-DboPdze2.css                                             45.17 kB │ gzip:  8.46 kB
dist/assets/echarts-l0sNRNKZ.js                                             0.00 kB │ gzip:  0.02 kB
dist/assets/PlaceholderPage-DLyJ5i4L.js                                     1.74 kB │ gzip:  1.09 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-D-jzXRhs.js        2.16 kB │ gzip:  1.05 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-CVQccAqC.js         2.32 kB │ gzip:  1.04 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-D4G_SYzi.js    2.44 kB │ gzip:  1.19 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-DGK7Wdy7.js    2.60 kB │ gzip:  1.16 kB
dist/assets/team.store-BZrZ1LC8.js                                          3.73 kB │ gzip:  1.88 kB
dist/assets/WorkspacesPage-y2DCnOXT.js                                      8.72 kB │ gzip:  3.48 kB
dist/assets/TemplatesPage-Bg2HUWG0.js                                       9.53 kB │ gzip:  4.24 kB
dist/assets/AgentsPage-CeYXWOig.js                                         11.53 kB │ gzip:  4.03 kB
dist/assets/OverviewPage-CA5GVN1g.js                                       12.11 kB │ gzip:  3.96 kB
dist/assets/OnboardingPage-wE91Z3k4.js                                     12.85 kB │ gzip:  4.89 kB
dist/assets/TeamsPage-lCUIQ1G3.js                                          15.88 kB │ gzip:  5.91 kB
dist/assets/vendor-h-qv6l4d.js                                            130.37 kB │ gzip: 46.75 kB
dist/assets/index-Ce9bvaOR.js                                             133.90 kB │ gzip: 42.39 kB
✓ built in 5.18s
# 退出代码: 0
```

---

## 4. 交付约束遵循情况自查

- [x] **工作目录隔离**：在 `E:\OtherPro\HQAgent-Hub-worktrees\w4-frontend` 独占 worktree 开发。
- [x] **路径所有权**：代码修改严格限定在 `apps/desktop/**`（排除 `src-tauri/**`）及本 handoff 文件。仓库根共享文件未作任何改动。
- [x] **无硬编码 Token/端口**：`LocalHubGateway` 移除所有默认 fallback 字面量，`invoke` 错误直接抛出；浏览器测试仅依赖显式 `VITE_HUB_*` 环境变量。
- [x] **协议错误码完整支持**：抛出 `HubApiError` 附带 `code`、`detail`、`retryable` 与 `requestId`。
- [x] **四态覆盖**：`/workspaces`、`/teams`、`/templates` 全部完整接入 `LoadingState`、`HqEmptyState`、`HqErrorState`、`OfflineState`。
- [x] **`resolveSource` 六级清晰可见**：尤其 `fallback`（故障降级+琥珀告警+原因说明）与 `manual`（人工介入+红调强调），与正常来源肉眼可辨。
- [x] **无 AI 署名**：commit 信息仅包含改动内容，严禁任何 AI 署名与 Co-Authored-By 字样。
- [x] **待 Integrator 合并事项**：`apps/desktop/package.json` 新增了 ESLint 依赖项，合并进主干时由 Integrator 同步根 `pnpm-lock.yaml`。
