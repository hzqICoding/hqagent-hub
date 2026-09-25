# 本地可靠性收尾验收（2026-09-25）

## 改动与分工

- 主代理：真实原生与Worker HTTP取消验证、代码审查、整合部署。
- `/root/audit_orchestration`：取消/审批共享锁与pending CAS、迟到请求失效、决定消费状态与幂等；源63fd942，集成3b73645。
- `/root/planner_acceptance_ui`：恢复全分页、活动Session失效、存量paused收敛、无副作用重放；源1a373ab，集成9d50b07。
- 两个已有子会话复用，独立worktree；无业务项目改动。协议未变更。

## 自动化结果

```text
整合定向：13 passed, 1 warning in 0.98s
后端完整：182 passed, 4 warnings in 23.78s
```

覆盖审批cancel-first/approve-first、原生消费期间执行泵先终态、迟到取消不覆盖终态、审批失败消费不重复发送；恢复覆盖208任务跨页、SQLite关闭重开、FastAPI lifespan重新装配及回执窗口。

## 正式试用服务重启检查

升级前排空：ready、activeTasksRemaining=0、backupCompleted=true。升级后比较旧记录摘要；以下记录逐项保留：

```json
{
  "local_conversations": {
    "countBefore": 8,
    "preserved": true
  },
  "local_messages": {
    "countBefore": 46,
    "preserved": true
  },
  "local_scenes": {
    "countBefore": 3,
    "preserved": true
  },
  "idleSessions": {
    "countBefore": 11,
    "preserved": true
  }
}
```

## 真实Worker运行中取消

命令：`.venv/Scripts/python.exe -B E:/tmp/hqagent-worker-cancel-probe.py`。先由Win32_Process确认前台心跳Node已启动，再通过 `/api/v2/runs/{id}/commands` 取消，观察5秒。

```json
{
  "conversationId": "conversation_795409ad62154ce3bdd9881b572259be",
  "runId": "run_406f16a992964557a7ab1302acb0242c",
  "marker": "HQ_CANCEL_WORKER_ab1505c832",
  "observedRunningPids": [
    34556
  ],
  "taskId": "task_9337190880d3",
  "cancelStatus": "cancelled",
  "pidsAfterCancel": [],
  "pidsAfter5Seconds": [],
  "finalStatus": "cancelled",
  "nodeStatuses": [
    "cancelled"
  ],
  "commandEvents": [
    {
      "toolName": "commandExecution",
      "argumentsExcerpt": "\"C:\\\\Program Files\\\\PowerShell\\\\7\\\\pwsh.exe\" -Command \"node -e \\\"console.log('HQ_CANCEL_WORKER_ab1505c832');let n=0;const t=setInterval(()=>{console.log(++n);if(n>=120)clearInterval(t)},1000)\\\"\"",
      "failed": false
    }
  ],
  "pendingApprovals": []
}
```

本轮为纯控制台心跳，无文件写入，不需要人为放行。浏览器按钮未做视觉自动化，但使用同一任务控制HTTP接口。

## 真实取消后迟到审批

从先前测试创建新原生审批，确认waiting_approval后取消；随后对同一请求提交approve。

```json
{
  "runId": "run_e54f9dacb49a407c81c3ce1e064c8a1c",
  "taskId": "task_6770d22310c0",
  "approvalId": "approval_4a4504b243304894836095db6216c319",
  "fixtureNote": "Retry reused previously approved test worktree; compare existing marker hash and mtime instead of absence",
  "cancelStatus": "cancelled",
  "approvalStatus": "expired",
  "decision": null,
  "invalidatedBy": "task_cancelled",
  "lateApprovalHttpStatus": 410,
  "lateApprovalError": "APPROVAL_EXPIRED",
  "markerUnchangedAfter5Seconds": true,
  "finalStatus": "cancelled",
  "pendingApprovalId": null,
  "successfulCommandCompletions": 0
}
```

测试最初以“文件不存在”为前提；Retry复用了之前已批准测试的工作树，所以该前提不成立，随即取消并保留现场，没有删除旧文件。后续改为比较文件SHA-256与mtime、核对本轮无成功命令完成事件。迟到审批真实返回410且不执行。

## 验收结论与边界

取消后审批失效、运行中任务取消、重启状态收敛与历史保留均通过本轮范围的验证。恢复不等于原生命令断点续跑：不可确认执行结果的任务暂停待核对，用户显式resume是重新执行未完成节点。未进行操作系统断电或强杀正在写文件的破坏性试验；不保证断电时业务操作可回滚。恢复时不自动重复执行未知副作用。
