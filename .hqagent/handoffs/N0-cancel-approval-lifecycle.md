# N0 Cancel / Approval 生命周期交接

## 会话身份

| 字段 | 值 |
| --- | --- |
| canonical task | `/root/audit_orchestration` |
| 工作目录 | `E:/OtherPro/HQAgent-Hub-worktrees/cancel-approval-lifecycle` |
| 分支 | `fix/cancel-approval-lifecycle` |
| 基线 | `11f0cb5b806e7907e7ac296b2631fc46eceac163` |
| CODEX_THREAD_ID | `01a0cf38-30a9-7733-b5ff-4649ad36fecc` |
| CODEX_SESSION_ID | `01a0ceda-3bd5-7092-a443-c9e36b1eff9c` |
| 模型 / reasoning | 当前工具未提供可验证元数据，未知 |

`CODEX_SESSION_ID` 可能继承父会话；跨客户端恢复未验证。

## 状态语义

- Task 取消会在停止执行前，把该 Task 的所有 pending Approval 通过条件更新转为
  `expired`，`decision` 保持空。
- 系统失效原因记录在 `reason` 和 `details.invalidatedBy/invalidatedAt`，不冒充用户 reject，
  不发送 `approval.resolved`。
- Approval request/respond/cancel/timeout 共享 task 级异步锁；生产 ApprovalRepository 使用
  `WHERE status='pending'` 的 CAS，防止取消与批准都成功提交。
- 新审批请求若在 Task 取消后才到达，会直接保存为 expired，不产生可放行的 pending 记录。
- 审批列表会把 Task 已终态、pendingApprovalId 不匹配或 Node 不再 waiting 的旧孤立 pending
  记录收敛为 expired。

## 原生决定消费

保留“先持久化用户决定，再回送 Adapter”的抗重复语义：

1. CAS `pending -> approved/rejected`，`details.deliveryStatus=dispatching`。
2. Adapter 确认消费后写 `deliveryStatus=consumed` 并发送 `approval.resolved`。
3. AdapterFailure/异常时写 `deliveryStatus=failed` 和脱敏失败类别，Task/Node 失败。
4. `dispatching/failed` 的重复决定返回明确 INTERNAL，绝不自动重发或误报已执行。
5. 旧的 approved/rejected 历史若没有 deliveryStatus，保持既有幂等返回。

原生回送期间执行泵可能先完成 Task。回送返回后会重新核对 Task、Node 和
`pendingApprovalId`；若已终态或已切换审批，不覆盖为 running/failed。

## 可复用 helper

```python
await coordinator.invalidate_task_pending(
    task_id,
    reason="明确系统原因",
    invalidated_by="task_cancelled|restart_recovery|hub_shutdown|...",
)
```

调用方已持有 `coordinator.task_guard(task_id)` 时使用
`invalidate_task_pending_locked(...)`，避免锁重入。

## 定向验证

```text
E:\OtherPro\HQAgent-Hub-worktrees\integration\.venv\Scripts\python.exe \
  -m pytest tests\test_cancel_approval_lifecycle.py tests\test_task_service_live.py \
  security\tests\test_approvals.py -q -p no:cacheprovider \
  --basetemp E:\tmp\pytest-cancel-approval-lifecycle-final

22 passed, 2 warnings in 0.38s
```

两条 warning 是既有 FastAPI/Starlette TestClient 弃用提示。

覆盖：取消后迟到批准、cancel-first/approve-first 两种并发、回送期间 Task 先终态、孤立
pending 收敛、成功消费幂等、失败消费不重发、旧 approved 历史幂等，以及迟到/重复取消不改写
succeeded、failed、cancelled 终态。
