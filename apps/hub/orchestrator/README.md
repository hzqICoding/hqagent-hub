# W3 Orchestrator & Security

本包实现 HQAgent-Hub 的 provider-neutral 工作流编排、安全与恢复核心。

## 核心约束

- 工作流节点只保存 `role_id`，不保存厂商或具体 Adapter 名称。
- Role Resolver 固定按 `task_override -> workspace_profile -> global_profile -> capability_match -> fallback -> manual` 解析。
- 每个成功解析都生成 `NodeResolvedPayload`；fallback 必须同时写 `isFallback=true` 和可读的 `fallbackReason`。
- 角色要求的硬能力和带审批任务要求的 `tool_approval` 在 `Adapter.start()` 前检查。
- Adapter 收到的 `allowedPaths` 是角色 `writablePaths` 与任务 `allowedPaths` 的保守交集；结果收集后再次用两层原始白名单校验。
- Session 只允许 `active <-> idle -> closed`，`invalid` 单向不可逆；恢复必须提供明确 Session ID。
- 审批过期只由 Hub 时钟裁定；`agent_error` 中的 Agent 侧超时保留为另一类失败。

## 模块

- `catalog.py`：从已安装 `protocol/registry/*.yaml` 读取 8 个角色、14 项能力和 7 类危险动作，不维护第二份注册表。
- `role_resolver.py` / `team_resolver.py`：角色和团队解析。
- `workflow.py` / `runtime.py`：DAG 推进、角色分派、结果聚合、取消和 Adapter 失败分类。
- `sessions.py` / `recovery.py`：Session 状态机和事件流重建。
- `security/paths.py` / `permissions.py`：路径交集、角色权限、危险动作和 integrator 单租约。
- `security/approvals.py` / `worktrees.py`：审批闭环与独立 worktree 校验。

## 注入边界

`RuntimeEventSink`、`SessionRepositoryPort`、`ApprovalRepositoryPort` 由 W1 的存储与事务事件总线实现；`AdapterDirectoryPort` 由 W2 实现。W3 不创建第二套数据库，也不直接调用任何 Agent CLI/SDK。

Hub Composition Root 与 `apps/hub/pyproject.toml` 属于共享/W1 路径，集成动作见 `.hqagent/handoffs/T-W3-orchestrator.md`。

## 测试

```powershell
$env:PYTHONPATH = (Resolve-Path 'apps/hub').Path
.venv/Scripts/python.exe -m pytest apps/hub/orchestrator/tests apps/hub/security/tests -q --basetemp E:\tmp\pytest-w3
```
