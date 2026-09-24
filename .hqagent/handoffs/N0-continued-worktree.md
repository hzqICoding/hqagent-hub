# N0 Continue Worktree 交接

## 修复

`TaskService._prepare_execution_path()` 在角色存在明确 `resumeSessions[roleId]` 时：

1. 读取持久 Session 与 `session_spec:{sessionId}`。
2. 要求 Session 为 `idle/isValid`、有明确 external ID，且 workspace、role、Hub Session ID
   与当前任务一致。
3. 要求原 `readOnly` 与当前角色权限一致，并复用原 `allowedPaths`。
4. 写角色复用原 worktree/branch/baseCommit，不创建空的新 worktree；原路径必须存在并位于
   WorktreeManager 受控根目录。
5. 当前 Task 的 `worktrees[nodeId]` 记录实际复用 checkout，后置校验因此读取真实累计改动。
6. 只读角色只恢复自己的原执行路径，不继承其他角色的 worktree，也不写入 worktree 校验元数据。

只读测试 fixture 允许“原路径不存在但规范化后与当前授权 workspace 根完全相同”，最终仍由
Adapter preflight 判定；写角色没有此兼容分支。

## 定向验证

```text
E:\OtherPro\HQAgent-Hub-worktrees\integration\.venv\Scripts\python.exe \
  -m pytest tests\test_continued_worktree.py tests\test_task_service_live.py \
  -q -p no:cacheprovider --basetemp E:\tmp\pytest-continued-worktree-2

13 passed, 2 warnings in 0.23s
```

两条 warning 是既有 FastAPI/Starlette TestClient 弃用提示。

回归覆盖：

- 写 Continue 不调用 `WorktreeManager.create()`。
- Node dispatch 输入、当前 Task worktree 元数据及后置 `WorktreeSpec` 都指向原实际路径。
- 当前 Task 使用原 branch/baseCommit/allowedPaths，累计改动从原 base 计算。
- Session/spec 的 workspace 或 role 任一不一致均返回 `SESSION_NOT_RESUMABLE`。
- planner 只读 Continue 保持自己的原路径，不静默切到 developer checkout。

## 累计改动说明

Continue 复用包含未提交改动的旧 worktree，因此 `git diff <原baseCommit>` 会同时包含先前轮次与
本轮新增改动。这是本次修复选择的明确语义；UI/报告应描述为“当前 checkout 自原基线的累计改动”，
不能冒充仅本轮增量。若产品需要严格每轮增量，应改用新 Session + 新 worktree + handoff。
