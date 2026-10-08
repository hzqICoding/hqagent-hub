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

## 拒绝测试结果：通过

用户于11:19:26点击拒绝后确认“已拒绝”。实际核对：

```text
approval.status = rejected
approval.decision = reject
run.status = failed（拒绝阻断，预期）
marker_exists = False
git status --porcelain = 空
```

只有同一命令的开始/拒绝两条工具事件；拒绝回执failed=true、exitCode为空，没有替代写入命令。任务报告“人工审批拒绝已成功阻止写入操作”。

## 批准测试准备与关联修复

准备下一条申请时发现Codex Adapter按externalRequestId在多个Session中回退匹配；各原生连接都可能使用编号0，旧请求会错误匹配新任务。还存在找不到请求却返回成功的问题。

修复为仅匹配完整Hub approvalId，再校验该请求的externalRequestId；未知、错配、已结束请求均明确失败，不发送到其他会话。回归覆盖两个连接同编号、旧请求已处理、新请求未处理、未知Hub ID及原生编号不一致。提交`a45627c`，集成`d62b762`。

```text
pytest tests/test_approval_correlation.py tests/test_approval_shell_paths.py adapters/tests security/tests -q -p no:cacheprovider
40 passed, 1 warning in 0.19s
pytest -q -p no:cacheprovider
156 passed, 4 warnings in 22.13s
```

先前准备的正向Run `run_6030ebaf9a8a4e8c9f3ec065823de35a` 已通过任务取消命令撤回，未代替用户做批准/拒绝，标记文件不存在。新的正向申请：

- 对话：`conversation_eef215d1e9874c9db007c6c313d033d9`，标题“人工审批测试：批准后只执行一次”。
- Run：`run_a6286c7bafd348839f26bd0cdca8a8cc`，Task：`task_2e7c06a05211`。
- Approval：`approval_0498d232d7fd4575a8c971e82c2c107c`。
- 状态：waiting_approval / pending，`approval-approved.txt`尚不存在。
- 预期内容：`APPROVAL_EXECUTED_ONCE`，以`flag=wx`独占创建，不允许覆盖。

等待用户点击最新申请的“批准放行”，然后核对真实执行和重复决定的幂等性。此时尚不宣称批准测试通过。


## 连接码在线续发与批准测试重建（2026-09-25）

为部署在线续码功能，先取消未执行的 `run_a6286c7bafd348839f26bd0cdca8a8cc`，未代替用户批准或拒绝。升级后重建同一测试。

实现集成提交 `a6c268c`。后端全量测试实际输出：`158 passed, 4 warnings in 22.88s`。

- Run：`run_fbf793c577f84e629620458935c58b49`；Task：`task_a6b8150746e8`。
- Approval：`approval_6d8fe1e132874766bde73e441d34acd4`。
执行 `python -B -m runtime.pair --data-dir E:/tmp/hqagent-n0-trial` 后核对输出：

```json
{
  "pidUnchanged": true,
  "approvalUnchanged": true,
  "runStatus": "waiting_approval",
  "approvalStatus": "pending",
  "markerExists": false
}
```

续码未重启 Worker、未丢失待审批请求。仍等待用户批准，正向执行及幂等验收尚未完成。


## 批准与重复决定测试：通过

用户点击批准并回复“已批准”后，核对真实工具回执和磁盘文件。对同一已批准请求以相同幂等键重复提交、再以新幂等键重复提交批准，均未新增执行。实际输出：

```json
{
  "approvalStatus": "approved",
  "runStatus": "succeeded",
  "markerContent": "APPROVAL_EXECUTED_ONCE",
  "successfulCommandCompletions": 1,
  "commandEvents": 2,
  "repeatDecisionStatuses": [
    "approved",
    "approved",
    "approved"
  ],
  "fileAndExecutionUnchangedAfterRepeats": true,
  "gitStatus": "?? approval-approved.txt"
}
```

两条 commandExecution 事件分别为开始与退出码 0 的完成记录，并非两次执行。重复提交前后文件 SHA-256、mtime_ns 与命令事件数量一致。变更仅为临时工作树中的 approval-approved.txt；业务项目未改动。拒绝阻断、批准执行、重复决定不重复执行三项验收通过。
