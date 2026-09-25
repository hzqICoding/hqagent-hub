# 执行中取消任务验收

仅临时审批测试仓库的隔离 worktree；不访问业务项目。首次默认沙箱命令返回 EPERM，exitCode=1，未创建文件，保留失败记录。第二轮先请求人工审批，未代替用户批准。

```json
{
  "conversationId": "conversation_47fd50593c7342f1a3b843440dafc8a6",
  "workspaceId": "ws_19bbce7b11a5",
  "runId": "run_134d1540ac524d87ac05969e8f85632b",
  "marker": "cancel-heartbeat.json",
  "previousRunId": "run_f05b6be0c2864256a4dde1117c88fd80",
  "taskId": "task_528535159386",
  "markerPath": "E:\\tmp\\hqagent-n0-trial\\worktrees\\task_528535159386-developer\\cancel-heartbeat.json",
  "approvalId": "approval_ab33c3f28cd542daac6f5d8b62af5d2a"
}
{
  "runStatus": "waiting_approval",
  "approvalStatus": "pending",
  "markerExists": false
}
```

批准后前台 Node 命令每秒更新 cancel-heartbeat.json，记录 pid/tick/time，最多600秒自行结束。等待用户在运行中取消后，核对任务状态、原生工具回执、PID是否退出及文件在观察窗口内是否停止变化。当前尚未通过取消验收。

## 用户取消后的实际核对

```json
{
  "taskStatus": "cancelled",
  "cancelledAtLocal": "2026-09-25 12:17:04",
  "approvedAtLocal": "2026-09-25 12:17:44",
  "markerExistsBefore": false,
  "markerExistsAfter5Seconds": false,
  "gitStatus": "",
  "runningCommandCancellationVerified": false
}
```

任务在人工批准前40秒已取消，未生成心跳文件；按本任务绝对路径筛选 Win32_Process 的 node/pwsh/powershell 进程无匹配结果。故本轮验证的是等待审批时取消，不能宣称已验证运行中命令终止。另发现已取消任务的审批仍能记录 approved，虽然本次未发生写入，需修复任务终态与审批失效联动。下一轮必须先确认心跳文件增长，再由用户取消。


## 2026-09-25 运行中原生取消实测

真实 CodexAdapter + App Server，gpt-5.6-sol/medium，独立目录 E:/tmp/hqagent-native-cancel-check。只启动不写文件、不联网的前台 Node 心跳；确认进程存在，3秒后发送 turn/interrupt。

实际命令：`E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe -B E:/tmp/hqagent-native-cancel-probe.py`

```json
{
  "observedRunningPids": [
    28128
  ],
  "cancelResult": {
    "outcome": "stopped_gracefully",
    "completedAt": "2026-09-25T05:25:01.878071Z",
    "elapsedMs": 82,
    "detail": "Codex turn 已由 turn/interrupt 停止",
    "orphanProcessIds": []
  },
  "pidsAfterCancel": [],
  "pidsAfter5Seconds": [],
  "nativeThreadId": "01a0d705-efac-73c3-87b6-db4ca46fd81a",
  "streamEnd": {
    "status": "ended",
    "endedAt": "2026-09-25T05:25:01.843393Z",
    "lastEventSeq": null,
    "resumable": false,
    "detail": "turn.status=interrupted"
  },
  "pidsAfterCleanup": []
}
```

运行进程退出，观察5秒未重启。仅覆盖原生Adapter取消链路；待审批修复合入后验证Hub HTTP及任务投影，不宣称浏览器按钮自动化通过。
