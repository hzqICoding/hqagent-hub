# 项目分组任务工作台前端交付

- 分支：`feat/project-chat-frontend`
- worktree：`E:\OtherPro\HQAgent-Hub-worktrees\project-chat-frontend`
- 基线：`d4379b056f57685303d84e7b2691e55af2d7efb6`
- 协议依赖：`362d3ba`（本分支对应 cherry-pick 提交 `e5a1b5e`）
- canonical task：`/root/project_frontend`
- 写入范围：`apps/desktop/src/**`；本文件为允许的交付 handoff

## 已完成

- Sidebar 按 Workspace 分组任务，支持项目折叠、空项目定向新建、任务/项目搜索和归档视图切换。
- 任务菜单支持重命名、归档、恢复；运行、排队、待审批、暂停状态禁止归档。
- 归档任务保留历史只读，发送、重试、继续执行入口均要求先恢复。
- 接入 `PATCH /api/v2/conversations/{id}`、`UpdateLocalConversationInput`、必填 `Idempotency-Key`、metadata version conflict 刷新与高版本防倒退。
- MockGateway 覆盖版本校验、幂等重放/冲突、未完成任务归档拒绝、归档拒发和恢复。
- 草稿按 `conversationId` 保存在内存；切换不触发模型；异步发送失败只回填原任务且受 draft revision 保护。
- 发送中切换任务后，发送/恢复错误和排队消息均按原 `conversationId` 隔离。

## 验证

```text
pnpm --filter @hqagent/desktop typecheck
结果：通过（vue-tsc --noEmit）

pnpm --filter @hqagent/desktop exec vitest run \
  src/shared/api/local-chat-gateway.test.ts \
  src/shared/api/mock-local-chat-gateway.test.ts \
  src/stores/chat.store.test.ts \
  src/stores/chat.context.test.ts \
  src/stores/chat.reliability.test.ts \
  src/stores/chat.polling.test.ts \
  src/pages/chat/components/ChatSidebar.test.ts \
  src/pages/chat/components/ChatComposer.test.ts \
  src/pages/chat/ChatPage.test.ts \
  src/pages/chat/components/RunSnapshotDrawer.test.ts
结果：10 files passed，65 tests passed

pnpm --filter @hqagent/desktop exec eslint <本次变更的 15 个前端文件>
结果：通过，exit 0
```

全量测试、生产构建和部署由 Integrator 按任务分工执行。当前环境没有可用浏览器 surface，本执行线未声明视觉截图验收通过。
