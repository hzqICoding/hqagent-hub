# T-W4 桌面前端

| 项 | 值 |
| --- | --- |
| taskId | `T-W4-frontend` |
| owner | Antigravity（备选 Gemini） |
| baseCommit | `f64f60e3fa530b21e4922eb97d63eb6255a9f1bf` |
| branch | `work/w4-frontend` |
| worktreePath | `E:\OtherPro\HQAgent-Hub-worktrees\w4-frontend` |
| handoff | `.hqagent/handoffs/T-W4-frontend.md` |

## 重要：换工作目录

此前 F0 是在仓库主目录 `E:\OtherPro\HQAgent-Hub` 里做的。现在仓库已初始化 Git 并建立了分支模型，**必须改到自己的 worktree 里工作**：

```powershell
cd E:\OtherPro\HQAgent-Hub-worktrees\w4-frontend
pnpm install          # 这个 worktree 还没装依赖，node_modules 不跟随 worktree
```

F0 的产出（主题引擎、四套 Palette、Design Token、17 个基础组件、Mock Gateway 骨架）已经在 `f64f60e` 里，worktree 检出后就在，不用重做。

多个 Agent 禁止共用同一工作目录，即使写不同路径也不行——会争用 Git Index、lockfile 和构建产物。

## allowedPaths

```
apps/desktop/**        排除 apps/desktop/src-tauri/**
```

包含 `apps/desktop/package.json`、Vite/Vitest/Playwright 配置、`src/` 和前端测试。

不要动 `apps/desktop/src-tauri/`（W5 桌面壳在做）、`packages/protocol/`（W0 的）、`apps/hub/`（W1 的）、仓库根的共享 Lockfile 与 workspace 配置（Integrator 统一改）。

## 开工前必读

1. `AGENTS.md`
2. `.hqagent/INTERFACES.md` —— **重点看「W4 迁移清单」**，你手写的协议类型已被生成物取代
3. `docs/前端开发与验收方案.md` —— 主文档，页面/主题/组件/Mock 规范/验收矩阵
4. `docs/分工与并行开工方案.md` §5.5
5. `packages/protocol/generated/ts/index.ts` —— 你要 import 的东西
6. `packages/protocol/events/event-dictionary.md` —— 事件语义与状态迁移

## 第一件事：协议迁移

`packages/protocol/generated/ts/index.ts` 现在是**生成物**（118 个类型，由 JSON Schema 生成），你之前手写的那份已被替换。迁移清单见 `.hqagent/INTERFACES.md`，共 10 处：

| 原写法 | 改成 |
| --- | --- |
| 自己声明协议类型 | `import type { ... } from '@hqagent/protocol'` |
| `BootstrapView.hubEndpoint.token` | **删除**。token 只能从 Tauri `invoke('get_hub_endpoint')` 拿 |
| `BootstrapView.agentsCount / onlineAgentsCount` | `agents.total / agents.ready / agents.issues` |
| `reduceMotion: boolean \| 'system'` | `'system' \| 'on' \| 'off'` |
| `UpdatePhase`（9 值） | 18 值，补齐了 OTA 状态机 |
| `UpdateActionInput` 的 `pause/resume/retry` | `check/download/cancel/install/defer/acknowledge` |
| 事件 `approval.requested` | `approval.required` |
| `TaskNodeView.status: TaskStatus` | `NodeStatus`（多了 `resolving`/`skipped`） |
| `fixtures/*.json` | `fixtures/contracts/*.json` |
| UI 场景数据 | 放 `apps/desktop/src/mocks/scenarios/`，引用协议 Fixture 组合 |

**保留未动**，不用改：`UiGateway` 方法签名、View 模型命名和 `id` 字段风格、`PageResult<T>`、`resolveSource` 六值、`TaskSource`、`RiskLevel`、`ContrastMode`、`FontScale`、四套 palette 名（`hq-blue`/`ai-violet`/`tech-cyan`/`ops-emerald`）、`UserSettingsView` 五分组、`drainProgress.step` 五步。

新增可用：`BootstrapView.features`（FeatureAvailability）——分阶段交付期未就绪的包会在这里报 `available:false` 并给原因，你据此禁用入口并显示说明，**不要把空列表当成"功能可用但没数据"渲染**。

## 四条硬约束

1. 协议层类型只 import 不声明。`UiGateway`、ViewModel、Application Service 由你手写，但不得重定义同名 DTO。
2. 原子协议数据来自 `packages/protocol/fixtures/contracts/`；UI 组合场景放 `apps/desktop/src/mocks/scenarios/`，引用协议 Fixture 构建，不复制另一套协议字段。
3. Local Hub 地址和令牌不由你决定。`LocalHubGateway` 通过 `invoke('get_hub_endpoint')` 拿 `{ baseUrl, token }`，页面层完全不感知。
4. **原生 WebSocket 不能设 Authorization 头**。必须先用 Bearer 调 `POST /api/v1/auth/ws-ticket` 拿 30 秒一次性 Ticket，再用 Ticket 建连；每次重连都要重新取 Ticket，不能缓存复用。

## 节奏

F0 已完成 → F1 → F2 → F3 → F4 → F5。F0–F4 全程用 Mock，不依赖任何其他包；F5 才需要真实 Local Hub（W1 就绪后另行通知）。

页面不得直接调 HTTP/WebSocket/Tauri invoke，不得把 Claude/Codex/Gemini 与固定职责绑定，不得硬编码颜色。每页必须覆盖 loading / empty / error / offline 四态。

## 验收

```powershell
cd E:\OtherPro\HQAgent-Hub-worktrees\w4-frontend
pnpm typecheck
pnpm lint
pnpm test
```

最终以 `docs/前端开发与验收方案.md` 第 22、23 节为准。每阶段交付附运行命令、截图、测试结果和未完成项。

## 交付

- 在 `work/w4-frontend` 上提交。commit message 只描述改动本身，**不要任何 AI 署名、不要 Co-Authored-By、不要 Generated with 字样**。提交后用 `git log -1 --format=%B` 自查。
- 写 `.hqagent/handoffs/T-W4-frontend.md`。
- 发现协议要改，**不要动 `packages/protocol/`**，写进 handoff 提出来。
