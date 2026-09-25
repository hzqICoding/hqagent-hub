# N0 原规划会话验收前端回执

## 范围

- 分支：`feat/planner-acceptance-ui`
- 基线：`18a46cbdbad7ed605d67a420036154db22535ad7`
- 可写范围：`apps/desktop/src/**`、`.hqagent/handoffs/N0-planner-acceptance-ui.md`

## 已完成

- `develop` 场景增加验收方式选择，支持 `original_planner` 与已有 `independent`；旧场景省略 `reviewMode` 时按 `independent` 展示。
- 原规划者验收启用时，Planner、Developer、Reviewer（验收阶段）必须启用；Reviewer 的 Agent、Model、Reasoning Effort 从 Planner 继承且不可独立填写，职责提示仍可编辑。
- 明确选择原规划者验收会立即开启三阶段并锁定 Planner/Reviewer 开关；缺少阶段或 Planner Agent 时页面明确提示且禁止保存。Mock 同样以 `VALIDATION_FAILED / 422` 拒绝无效组合。
- 保存时提交 `reviewMode`，并将 Planner 身份参数复制到 Reviewer 配置，配合后端统一校验与继承。
- 页面提示配置仅冻结到新 Run，模式变更后使用「新一轮上下文」，历史轮次和 Continue 不受影响。
- Run 快照展示冻结的验收方式；`phase=acceptance` 且 `roleId=planner` 的节点显示为“原规划者验收”。
- 验收节点展示 Hub Session、原生 Session、证据 ID、来源节点与明确 verdict；`changes_requested`、`insufficient_evidence` 与无 verdict 的执行错误分别显示，不推断或伪造通过结论。
- Mock 场景保存与新 Run 快照支持 `reviewMode`；原规划者验收节点复用 Planner 的本地及原生 Session。Mock 只提供待验收节点，不伪造真实成功。
- Mock 历史 Run 的 `sceneSnapshot` 改为深拷贝，后续场景保存不会改写历史快照。

## 定向验收

```powershell
pnpm install --offline --frozen-lockfile
pnpm --filter @hqagent/desktop typecheck
pnpm --filter @hqagent/desktop lint
pnpm --filter @hqagent/desktop test -- src/pages/scenes/ScenesPage.test.ts src/stores/scenes.store.test.ts src/shared/api/mock-local-chat-gateway.test.ts src/pages/chat/ChatPage.test.ts src/pages/chat/components/RunSnapshotDrawer.test.ts
```

覆盖重点：

- 缺省 `reviewMode` 兼容独立 Reviewer。
- 原规划者模式保存时身份继承。
- 原规划者模式不会保存 Reviewer 关闭或 Planner Agent 缺失的配置。
- 场景修改不影响历史 Run 快照。
- 新 Run 的规划与验收节点复用 Planner Session。
- 审核不通过与验收执行错误分开显示，且无有效 verdict 时不显示“验收通过”。

## 集成说明

- 未修改 Hub、协议生成物、根配置或 Composition Root。
- 后端返回的 `reviewVerdict` 是 UI 展示审核结论的唯一依据；节点失败或 `error` 本身不会被推断为 `changes_requested`。
- 无需重启或联调本地 Hub；主线合并后可用真实 `original_planner` Run 验证原生 Session ID 与证据 ID。
