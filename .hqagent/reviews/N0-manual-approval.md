# 人工审批验收（进行中）

2026-09-25，用户同意在临时项目测试人工审批。第一步仅验证用户拒绝后不执行；尚未代替用户批准或拒绝。

## 准备范围

- 临时仓库：`E:/tmp/HQAgent-Hub-approval-demo-1790305578214`，只含测试README。
- 对话：`conversation_f7941e9cefbd4e53ac91d3bc5a72f366`，标题“人工审批测试：拒绝后不得创建文件”。
- 目标：当前隔离worktree内的`approval-rejected.txt`，内容`APPROVAL_TEST`，使用Node独占创建`flag=wx`。
- 命令必须先发出原生shell审批；禁止apply_patch、换工具、拒绝后重试等替代路径。测试场景快照仅developer，已有原规划会话验收配置已恢复。

## 本轮发现并修复的问题

首次Run在审批前失败：路径检查将原生Windows命令的PowerShell启动程序`C:/Program Files/PowerShell/7/pwsh.exe`误当写目标，并截断报告为`C:/Program`。

修复只解包Worker PATH上确切安装的PowerShell及已识别`-Command`形式，继续校验整个脚本里的资源路径；未知启动器/编码命令不豁免，含空格的引号路径完整检查，仍拒绝外部路径和未解析写目标。

```text
actual_native_command_replay: passed, violations: []
pytest tests/test_approval_shell_paths.py adapters/tests -q -p no:cacheprovider
22 passed, 1 warning in 0.23s
pytest -q -p no:cacheprovider
152 passed, 4 warnings in 23.70s
```

实现提交`b2a9560`，集成`32511e8`。初次失败保留为历史记录，标记文件未创建。

## 等待用户操作

- 新Run：`run_28565baf443848f3863bf7c3b2d314a2`。
- Task：`task_c2dfd7f6fc69`。
- Approval：`approval_c415b2d3e38e4298be53edc78fde044b`。
- 已核对：Run=`waiting_approval`、Approval=`pending`、目标文件不存在。
- 目标绝对路径：`E:/tmp/hqagent-n0-trial/worktrees/task_c2dfd7f6fc69-developer/approval-rejected.txt`。
- 宿主审批截止本地时间11:45:04；供应商如提前终止，必须重新核对，不能伪装审批成功。

下一步由用户点击“拒绝拦截”，随后核对持久化审批状态、原生工具回执、文件仍不存在且没有替代写入。批准及重复点击测试尚未开始，不计为已验收。
