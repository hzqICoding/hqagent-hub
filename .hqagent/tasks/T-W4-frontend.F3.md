# T-W4 前端 F3 派活：任务、Session 和审批闭环

| 项 | 值 |
| --- | --- |
| taskId | `T-W4-frontend` |
| milestone | `F3` |
| branch | `work/w4-frontend` |
| worktree | `E:\OtherPro\HQAgent-Hub-worktrees\w4-frontend` |
| 基线 | `0fde99d`（F2 已过审，见 `.hqagent/reviews/T-W4-frontend.F2.md`） |
| 协议 | `0.2.0`，FZ-2 `bfcd91e` |

## 一、交付范围

以 `docs/前端开发与验收方案.md` §1092（F3 定义）和 §22.3（页面功能验收）为准。

1. **任务创建 / 列表 / 详情**三个页面。
2. **多 Agent 时间线**：事件流、工具调用、产物（`TaskArtifactView`）。
3. **Session 列表与继续入口**。
4. **审批中心 + 危险操作二次确认**。
5. **WebSocket Mock 的断线、重连、事件补发**。

外加两条 F2 残留（都不依赖其他包，顺手做掉）：

- **F2-R1**：`app.store` 判 `err instanceof HubApiError`，把 `code` 落成一个
  `hubGate` 状态。目前网关如实抛出了 `HubApiError`，但**全应用没有一个消费者**
  （grep 排除网关自身后零命中），`HUB_MAINTENANCE` / `FEATURE_UNAVAILABLE`
  统统退化成一句通用文案。建任务入口要读 `hubGate` 做禁用。
- **F2-R2 的前端半边**：`local-hub-gateway.ts` 的 `ws.onclose` 目前不看
  `event.code`，无条件带着同一个 `after=lastConfirmedSeq` 重连。改成读关闭码，
  见到游标过期专用码时清零游标并重新 `getBootstrap()` 取 Snapshot。
  **这是 §22.3 明列的验收项**，不是可选优化。

## 二、这些坑先说在前面

### 1. 不要做「暂停正在跑的 Agent」

`TaskActionInput.action` 冻结了 `pause | resume | cancel | retry | append_instruction`，
但 W3 交付时提出：**Adapter Port 根本没有 pause/send-message 方法**，用 `cancel()`
假装 pause 会把 Session 关掉。W0 已裁决**收窄语义**，不给 Adapter 加方法：

- `pause` 只作用于**节点之间**——当前节点跑完就停住，不打断正在执行的 Agent。
- `append_instruction` **只在节点 idle 时可用**，运行中要禁用（置灰 + tooltip 说明）。

UI 不要承诺做不到的事。按钮文案和禁用态照这个语义做。

### 2. 取消成功不发 `agent.failed`

W0 裁决：取消是正常路径不是失败。成功取消只会收到
`task.status_changed(to=cancelled)`。时间线不要把取消渲染成红色失败态。
只有 Adapter 拒绝取消（`refused`）才是失败，错误码 `TASK_NOT_CANCELLABLE`，
且会带孤儿进程 PID 信息，要如实显示（用户需要知道有个进程没杀掉）。

### 3. `NodeStatus` 比 `TaskStatus` 多两个值

`NodeStatus` 有 `resolving` 和 `skipped`，`TaskStatus` 没有。
`resolving` 是「正在解析该角色用哪个 Agent」，`skipped` 是「前序失败被跳过」。
两者都要有独立视觉，不要合并进 pending/failed。

### 4. 每个节点都有自己的 `resolveSource`

F2 在 `/teams` 右栏做的六级来源展示，**任务详情的每个节点也要有**——
`TaskNodeView.resolveSource` 是必填字段。用户在任务详情里问的是同一个问题：
「这一步为什么用了这个 Agent」。复用 F2 的展示组件，不要另做一套。
`isFallback` / `fallbackReason` 同样要展示。

### 5. 10,000 条事件不能冻结页面

§22.3 的硬指标。要虚拟滚动 + 筛选，不要一次性渲染。这条最好在 Mock 场景里
直接造一个万条事件的数据集，别等 F5 接真 Hub 才发现卡死。

### 6. 双订阅并发场景要在 Mock 里造出来

F1 审核的 R2 是这样一个 bug：`AppLayout` 和页面在同一 tick 各订阅一次，
守卫同步读、赋值异步做，于是开了两条 WebSocket，每个事件投递两次，
第一条还变成关不掉的孤儿。F2 已经用 `connectPromise` 单飞修掉了，
**但 `subscribeEvents` 至今只有单测在调，真实链路一次没上电过。**

F3 是这条线第一次通电，而任务页 + AppLayout 同时订阅正是当初的触发场景。
请在 Mock 里显式造这个并发订阅用例并断言「只建一条连接、事件不重复」。

## 三、四条硬约束（沿用，未变）

1. 协议层类型**只 import 不声明**。`UiGateway`、ViewModel、Application Service
   你手写，但不得重定义同名 DTO。F3 要用的：`TaskSummaryView`、`TaskDetailView`、
   `TaskNodeView`、`TaskArtifactView`、`TaskQuery`、`CreateTaskInput`、
   `TaskActionInput`、`SessionView`、`SessionQuery`、`ResumeSessionInput`、
   `ApprovalView`、`ApprovalQuery`、`ApprovalResponseInput`、`HubEvent`、`EventPage`、
   `TaskCreatedPayload`、`TaskStatusChangedPayload`、`NodeResolvedPayload`、
   `ApprovalRequiredPayload`、`ApprovalResolvedPayload`。
2. 原子协议数据来自 `packages/protocol/fixtures/contracts/`；UI 组合场景放
   `apps/desktop/src/mocks/scenarios/`，引用协议 Fixture 构建，不复制第二套字段。
3. Local Hub 地址和令牌不由你决定。页面层完全不感知。
4. 原生 WebSocket 不能设 Authorization 头。必须先用 Bearer 换 30 秒一次性 Ticket，
   每次重连重新换票，不能缓存复用。

另：页面不得直接调 HTTP/WebSocket/Tauri invoke，不得把任何厂商与固定职责绑定，
不得硬编码颜色。每页覆盖 loading / empty / error / offline 四态。

## 四、验收

```powershell
cd E:\OtherPro\HQAgent-Hub-worktrees\w4-frontend
pnpm --filter @hqagent/desktop lint
pnpm --filter @hqagent/desktop typecheck
pnpm --filter @hqagent/desktop test
pnpm --filter @hqagent/desktop build
```

四条都要退出 0。对应 §22.3 这几条要能演示：

- 创建任务并看到 `queued → running → waiting_approval → succeeded` 全流程
- 暂停、继续、取消、重试、追加指令（按第二节收窄后的语义）
- 审批能批准、拒绝、超时，并同步到任务页
- Session 能搜索、查看、继续
- 断线后有明确状态，重连后**不重复事件**
- 收到 `EVENT_CURSOR_EXPIRED` 后重新 bootstrap，界面不继续显示过期增量

## 五、边界声明

- **只改 `apps/desktop/**`（不含 `src-tauri/**`）** 和 `.hqagent/handoffs/T-W4-frontend.md`。
- **不要动 `packages/protocol/`。** 发现协议要改，写进 handoff 提出来，由 W0 裁决。
  （W3 就是这么做的，提了 7 条，全部受理了。）
- 发现需要改本文档范围外的东西，**先停下来说明原因，得到同意再动**，不闷头跨界改。
- 仓库根共享文件（`pnpm-lock.yaml` 等）如需变更，写进 handoff 交 Integrator 同步。

## 六、提交要求

- 在 `work/w4-frontend` 上提交。
- **commit message 只描述改动本身。不要任何 AI 署名，不要 `Co-Authored-By`，
  不要 `Generated with` 字样。** 提交后用 `git log -1 --format=%B` 自查。
- 写 `.hqagent/handoffs/T-W4-frontend.md`（覆盖为 F3 版本）。
- 附**真实**运行命令输出、测试结果和未完成项。F1/F2 两轮的自述都经得起复跑，
  这个标准请保持——审核方会独立重跑全部四条命令。
