# 自定义场景与角色模板前端交付

- 分支：`feat/custom-scenes-frontend`
- worktree：`E:\OtherPro\HQAgent-Hub-worktrees\custom-scenes-frontend`
- 基线：`80f845f3d5a3d985a7c4f8a3e68025f24acd490e`
- 协议依赖：`94b75bc`（本分支 cherry-pick 为 `9aa9619`，协议版本 `0.5.0`）
- 后端集成依赖：`4e1157f`
- canonical task：`/root/project_frontend`
- 写入范围：`apps/desktop/src/**`；本文件为允许的交付 handoff

## 已完成

- 场景页区分内置与自定义场景，支持新建空白场景或复制当前场景。
- 自定义场景可编辑名称、说明，并按顺序增减、启停和上下移动 Analyst / Planner / Developer / Reviewer 阶段；同一基础角色最多一次。
- 自定义原规划者验收严格要求启用阶段为 `planner → developer → reviewer`，Reviewer 继续继承 Planner 的 Agent、Model、Reasoning Effort。
- 角色模板支持列表、创建和版本化编辑，不提供删除或权限编辑；基础角色类型更新时不可更改。
- 模板应用到场景时复制 `roleName`、`instructions`、`roleTemplateId`、`roleTemplateVersion`，后续模板更新不会修改已保存场景和 Run 快照。
- Gateway 接入 `POST /api/v2/scenes`、`GET/POST /api/v2/role-templates`、`PUT /api/v2/role-templates/{id}`；写接口携带稳定 `Idempotency-Key`。
- Mock 覆盖场景阶段约束、原规划者顺序、模板来源 ID/正整数版本、幂等重放/不匹配、版本冲突和模板副本不联动。
- 新建任务从返回的场景列表动态展示并默认当前任务场景；聊天标题和执行详情优先展示场景名称及 `roleName`，运行匹配仍使用基础 `roleId`。
- 兼容旧场景缺少 `isBuiltin`、`roleName`、`roleTemplateId`、`roleTemplateVersion` 的响应。

## 验证

```text
pnpm --filter @hqagent/desktop typecheck
结果：通过（vue-tsc --noEmit）

pnpm --filter @hqagent/desktop exec eslint <本次变更前端文件>
结果：通过，0 warning / 0 error

pnpm --filter @hqagent/desktop exec vitest run \
  src/pages/scenes \
  src/stores/scenes.store.test.ts \
  src/stores/local-auth.store.test.ts \
  src/shared/api/local-chat-gateway.test.ts \
  src/shared/api/mock-local-chat-gateway.test.ts \
  src/pages/chat/ChatPage.test.ts \
  src/pages/chat/components/ChatSidebar.test.ts \
  src/pages/chat/components/RunSnapshotDrawer.test.ts \
  src/stores/chat.store.test.ts
结果：9 files passed，61 tests passed
```

全量测试和生产构建由 Integrator 执行。本执行线未操作正式服务或真实业务数据。
