# 聊天连续会话 UI 回执

## 执行身份与范围

- canonical task：`/root/planner_acceptance_ui`
- `CODEX_THREAD_ID`：`01a0d5cf-e410-7ef3-9d12-994f55e91b83`
- `CODEX_SESSION_ID`：`01a0ceda-3bd5-7092-a443-c9e36b1eff9c`
- 分支：`feat/chat-session-ui`
- 基线：`9890dff11b6477c2fe5cc23ce1d956f89c4d49a6`
- worktree：`E:/OtherPro/HQAgent-Hub-worktrees/chat-session-ui`
- 修改范围：`apps/desktop/src/pages/chat/**`、本回执

## 完成内容

- 输入框移除 New/Continue 永久模式选择，不直接读取或写入 `sessionMode`，仅显示“当前任务连续对话”。
- 发送按钮在消息列表或 Run 切换加载期间禁用，避免切换瞬间按错误的内部模式发送。
- 聊天页右上角、执行详情按钮左侧增加“新建任务”主入口；侧边栏保留次入口。
- 两个新建入口复用 `ChatSidebar.openCreateModal()` 和同一套创建表单，没有复制创建逻辑。
- 新建任务弹窗优先选择当前 conversation 的 workspace，仍允许选择其他工作区和场景。
- 当前任务页头更多菜单提供“重置 Agent 上下文”，弹窗明确说明：保留聊天历史、下一条使用新 Agent 会话、不会自动携带全部历史。
- 重置只调用 Store 的 `requestContextReset()`；输入区使用 `pendingContextReset` 显示一次性提示，并通过 `cancelContextReset()` 撤销。
- 会话恢复错误保留明确的“重置 Agent 上下文”入口，仍进入同一个确认流程，不静默切换。
- UI 使用 Store 的 `canResetContext` 控制菜单、恢复错误按钮与确认按钮；运行、发送、加载或存在排队消息时均不可重置。
- 保留运行中停止、指令排队、移除排队项以及发送/恢复错误提示。

## Store 集成依赖

主代理 Store 线提供以下接口，本分支仅消费，不修改 `stores/chat.store.ts`：

- `pendingContextReset: boolean`
- `canResetContext: boolean`
- `requestContextReset(): boolean`
- `cancelContextReset(): void`
- `effectiveSessionMode: 'new' | 'continue'`（UI 不直接显示）

本 worktree 为集成验证临时 cherry-pick Store 提交 `3841a5e`（本地 SHA `cc7161a`）；UI 代码直接消费真实响应式字段。主代理可继续分别集成 Store 与本 UI 提交。

## 验证

```powershell
pnpm --filter @hqagent/desktop typecheck
pnpm --filter @hqagent/desktop lint
pnpm --filter @hqagent/desktop test -- `
  src/pages/chat/ChatPage.test.ts `
  src/pages/chat/components/ChatComposer.test.ts `
  src/pages/chat/components/ChatSidebar.test.ts `
  src/pages/chat/components/ChatMessageItem.test.ts `
  src/pages/chat/components/ProcessActivityGroup.test.ts `
  src/pages/chat/components/RunSnapshotDrawer.test.ts `
  src/stores/chat.context.test.ts `
  src/stores/chat.store.test.ts `
  src/stores/chat.reliability.test.ts
```

结果：

```text
typecheck: passed
lint: passed
Test Files  9 passed (9)
Tests       38 passed (38)
```

未运行全量 build，按分工交由主代理合并 Store 后统一执行。
