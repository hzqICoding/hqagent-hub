# Local Hub 重启恢复回执

## 执行身份与范围

- canonical task：`/root/planner_acceptance_ui`
- `CODEX_THREAD_ID`：`01a0d5cf-e410-7ef3-9d12-994f55e91b83`
- `CODEX_SESSION_ID`：`01a0ceda-3bd5-7092-a443-c9e36b1eff9c`
- 分支：`fix/restart-recovery`
- 基线：`11f0cb5b806e7907e7ac296b2631fc46eceac163`
- worktree：`E:/OtherPro/HQAgent-Hub-worktrees/restart-recovery`

## 已修复

- 启动恢复从固定第一页 200 条改为遍历全部持久化 Task 页面。
- 非阻塞的 `queued`、`running`、`waiting_approval` Task 在重启后统一转为 `paused + recoveryRequired`，不会自动重放结果未知的原生命令。
- `blockedByParent` 的 queued 子任务确认尚未具备派发条件，保持 queued，等待父任务显式释放。
- 中断节点的 `running / waiting_approval / resolving` 状态转为 failed，并保留“执行结果无法确认”的恢复原因。
- 恢复按 `taskId` 查找全部 Session，覆盖“Adapter 已创建原生 Session，但 Node 尚未写入 sessionId/running”的崩溃窗口；仅将 `active` Session 转为 `invalid`，已确认的 `idle / closed` 历史 Session 原样保留。
- `waiting_approval` Task 收敛后调用审批线 `invalidate_task_pending(..., invalidated_by="restart_recovery")`，避免旧 pending 审批仍可点击却无法安全投递。当前分支通过兼容探测调用，合并审批线后使用其真实实现。
- Task 转为 paused 时同步清空 `pendingApprovalId`，不再指向已失效审批。
- 兼容旧版本已写入 `paused + recoveryRequired`、但仍残留活跃节点、active Session 或 pending 审批的记录；收敛一次后再次启动不会重复更新时间或追加 paused 事件。正常用户主动 paused 的 Task 不受影响。
- `shutdown()` 不再只处理当前内存 `_outcomes`，而是在取消 pump 后收敛全部持久化非终态 Task，覆盖“进程内句柄已丢失但数据库仍非终态”的情况。

## 明确边界

- 恢复不会声称原生进程已经停止；状态统一表达为结果未知、需要人工核对。
- 用户后续执行 Task `resume` 时，现有 TaskService 会重置 failed Node 并重新执行。这是显式重新执行，不是原生继续被中断的命令。
- LocalRun 的 `task_id` 为空但状态已为 running 时，测试模拟通过持久化幂等回执重新取得已有 Task，一次绑定后投影为 paused；不会创建第二个 Task。
- 本测试使用真实 SQLite 关闭/重开和 FastAPI lifespan 重新装配，不等同于 OS 断电、强杀正式进程或真实供应商模型进程测试。
- 未访问业务项目、未连接或重启正式试用服务、未调用付费模型。

## 验证

测试使用 `vnext-integration` worktree 的隔离 Python 环境，数据由 pytest 写入临时目录：

```powershell
E:\OtherPro\HQAgent-Hub-worktrees\vnext-integration\.venv\Scripts\python.exe `
  -m pytest tests/test_restart_recovery.py tests/test_task_service_live.py `
  tests/test_local_chat.py tests/test_approval_correlation.py -q
```

结果：

```text
.....................                                                    [100%]
22 passed, 1 warning in 1.98s
```

唯一 warning 是依赖环境中的 Starlette/httpx deprecation，不是本次代码失败。

```powershell
E:\OtherPro\HQAgent-Hub-worktrees\vnext-integration\.venv\Scripts\python.exe `
  -m compileall -q runtime tests/test_restart_recovery.py
```

结果：退出码 0，无输出。

## 集成提示

- 与审批线合并时保留 `ApprovalCoordinator.invalidate_task_pending` 调用；恢复流程没有持有 TaskService task lock 或审批 task lock，不存在共享锁反入。
- 主代理合并后应重新执行全量测试，并使用隔离数据目录完成正式 Hub 进程重启 smoke，核对 Task、LocalRun、Session 和 Approval 投影。
