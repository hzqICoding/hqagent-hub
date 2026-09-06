# T-W3-orchestrator 交接

## 状态

- 分支：`work/w3-orchestrator`
- 基线：协议 `0.2.0`，FZ-2 SHA `bfcd91e`
- W3 独占路径实现完成；未修改 `apps/hub/core|api|storage|runtime`、`apps/hub/adapters` 或 `packages/protocol`。
- RD-2 仍需 Integrator 合入 W1、W2 并完成 Composition Root 接线后判定。

## 已实现

1. Role Resolver 六级优先级，逐级保留冻结 `ResolveSource`；能力自动匹配不会把配置 fallback 错标为 `capability_match`。
2. fallback 输出 `isFallback=true`、`fallbackReason`；硬能力缺失输出 `missingCapabilities`。
3. `requiresApproval` 非空时，在 `Adapter.start()` 前要求 `tool_approval`，不把任务派给无法拦截工具调用的 Adapter。
4. provider-neutral DAG：节点只认角色，支持依赖推进、失败跳过、重试和结果聚合。
5. Session 生命周期：`active <-> idle -> closed`、`invalid` 单向不可逆；默认新会话、禁止 `latest`、同 Agent 实现/复核强制隔离 Session。
6. 审批闭环：Hub 独占 `expiresAt`，决定先持久化再通知 Adapter；Agent 侧审批超时按 `agent_error` 单独呈现。
7. 安全：角色权限只能收紧；七类危险动作需显式审批；只有 integrator 可 `git_merge`，且同一时刻只有一个 integrator 租约。
8. 路径/Worktree：角色 `writablePaths` 与任务 `allowedPaths` 取交集；结果按 `changedFiles` 后置复核；越界失败并不清理 worktree。
9. 两段式取消：graceful 到点后 force；`refused` 标记任务失败并保留孤儿 PID 信息，不伪装为 cancelled。
10. 任务恢复：按持久化事件流重建 task/node/approval/fallback/session 状态，eventId 幂等、seq 倒退拒绝。

## 测试证据

当前 W3 worktree：

```text
> .venv/Scripts/python.exe -m pytest apps/hub/orchestrator/tests apps/hub/security/tests -q --basetemp E:\tmp\pytest-w3-final
........................................                                 [100%]
40 passed in 0.28s
```

将 `work/w1-hub` 归档到临时目录并叠加本 W3 目录后的 W1 回归：

```text
> .venv/Scripts/python.exe -m pytest apps/hub/tests -q
.............                                                            [100%]
13 passed, 2 warnings in 0.40s
```

两条 warning 均来自 W1 现有 FastAPI/Starlette TestClient 弃用提示。

## Integrator 必做接线

1. 合入 W1 后，在 `apps/hub/pyproject.toml` 的 Hatch wheel packages 中加入 `orchestrator`、`security`；这是共享/W1 路径，W3 未越界修改。
2. 让默认 Hub Composition Root 注入：
   - W1 事务事件总线 -> `RuntimeEventSink`
   - W1 Session/Approval 持久化 -> `SessionRepositoryPort` / `ApprovalRepositoryPort`
   - W2 AdapterManager -> `AdapterDirectoryPort`
3. W1 的 `testpaths=["tests"]` 不会发现 W3 独占目录内的测试。Integrator 应在共享配置中加入 `orchestrator/tests`、`security/tests`，或在 CI 显式执行两条 pytest 命令；不要把 W3 测试移动到 W1 独占的 `apps/hub/tests/**`。
4. W1 当前 `core.ports` 是 API Handler Port，没有面向 W3 的事务化 Task/Session/Approval Repository Port。集成时需由 W1 在其路径提供薄适配器，复用现有 `Database`/`EventStore`；不要在 W3 再建 SQLite 或第二套事件表。
5. W2 的实现需结构化满足 `orchestrator.ports.AgentAdapterPort` 的八个方法，并由 Agent Instance ID 获取绑定 Adapter；W3 不识别厂商名。

## FZ-2.1 协议变更请求

W3 未修改 `packages/protocol`。以下冻结形状存在实现歧义，请由 W0 裁决：

1. `AgentSessionHandle.sessionId` 描述为“Hub 生成后传给 Adapter”，但 `AgentTaskSpec` 没有 `sessionId` 字段，八个方法也没有其他传入通道。当前 W3 只能接受 `start()` 返回的本地 ID。建议给 `AgentTaskSpec` 增加可选 `sessionId`，或新增 `StartRequest { sessionId, spec }`。
2. `TaskActionInput` 冻结了 `pause` 和运行中 `append_instruction`，但 Adapter Port 没有 pause/send-message 方法；`resume()` 只适用于明确的 idle Session。用 `cancel()` 假装 pause 会把 Session 关闭，不能安全实现。建议补 `pause()` / `sendInstruction()`，或收窄这两个动作的语义。
3. 取消规则要求成功取消产生 `agent.failed`，其 `errorCode` 应映射 `AdapterFailureKind.cancelled`，但 `ErrorCode` 没有取消对应码。当前 W3 对成功取消只发 `task.status_changed(to=cancelled)`；`refused` 使用 `TASK_NOT_CANCELLABLE`。建议新增明确错误码或修订事件规则。
4. `AgentSessionHandle.externalSessionId` 在不支持恢复时允许缺省，而 `SessionView.externalSessionId` 是必填字符串。当前 W3 用空字符串并令 `isValid=false`。建议把 View 字段改为可选，或冻结空字符串语义。
5. `continue_lineage` 有 `parentSessionId` 语义，但 `resume()` 返回 `void`，无法创建并关联一个新的 Hub 本地 Session。请明确“复用原 Session 记录”还是“新建子 Session”；若后者需返回 Session handle。
6. Schema 描述允许用户自定义角色，但生成的 Python `RoleId` 是八值 `StrEnum`，自定义角色无法进入 `TaskNodeView`/`ResolvedTeamView`。建议边界类型保留 `str`，另导出内置角色常量。
7. `events/event-dictionary.md` 页头和示例仍写协议 `0.1.0`，与当前 `packages/protocol/VERSION=0.2.0` 不一致。

## 环境说明

按任务命令使用清华镜像安装时，沙箱代理 `127.0.0.1:7898` 无法完成 Hatchling 构建依赖下载。为继续验证，当前 `.venv` 复制了同机 W1 `.venv` 中 Python 3.13.7、Pydantic 2.13.5、pytest 8.4.2 等已安装依赖，并排除了 W1 的 editable `.pth`；`protocol.__file__` 指向当前 W3 `.venv/Lib/site-packages/protocol/__init__.py`。源码或项目配置没有为此降级。

## Git 提交阻断

当前执行环境只允许读取主仓库 Git 元数据，而本 worktree 的 Index 位于主仓库：

```text
> git add -- apps/hub/orchestrator apps/hub/security .hqagent/handoffs/T-W3-orchestrator.md
fatal: Unable to create 'E:/OtherPro/HQAgent-Hub/.git/worktrees/w3-orchestrator/index.lock': Permission denied
```

因此本次无法在 `work/w3-orchestrator` 创建提交，工作区文件均已保留。权限恢复后执行：

```powershell
git add -- apps/hub/orchestrator apps/hub/security .hqagent/handoffs/T-W3-orchestrator.md
git diff --cached --check
git commit -m "feat(hub): 实现工作流编排与安全控制"
git log -1 --format=%B
```
