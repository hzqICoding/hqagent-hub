---
wp: desktop-stdin-fix
status: done
scope_declared: [apps/hub/**, .hqagent/**]
scope_touched: [apps/hub/runtime/parent_process.py, apps/hub/runtime/main.py, apps/hub/runtime/workspaces.py, apps/hub/runtime/descriptor.py, apps/hub/runtime/tasks.py, apps/hub/runtime/review_evidence.py, apps/hub/runtime/directory_picker.py, apps/hub/adapters/process.py, apps/hub/security/worktrees.py, apps/hub/tests/test_desktop_process.py, apps/hub/tests/test_desktop_stdin_isolation.py, apps/hub/tests/test_workspace_probe_timeout.py, apps/hub/tests/test_subprocess_input_policy.py, .hqagent/codex-sessions.md, .hqagent/reviews/desktop-stdin-fix/**, .hqagent/handoffs/desktop-stdin-fix.md]
build: pass
tests: pass
commit: 41aede80b82c3988f01cb40c82e752ed5257ef19
open_questions: 0
---

# 桌面控制 stdin 隔离与工作区查询修复

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/hub-0101`，分支 `feat/hub-0101`；开工按要求执行 `git merge integration/phase1`，输出 `Already up to date.`，基线 `8211b85`。交付仅源码、测试与证据，没有合并回 integration、部署、替换或重启已安装桌面程序。主代理需要将本修复重新打入 core/安装包后发布，旧安装包不会因源码提交而自动修复。

## 根因核实

在全新临时目录创建真实 Git 工作区，持久登记到 Hub DB，然后以 `HQAGENT_PARENT_CONTROL=stdio-v1`、stdin=PIPE 启动源码 Hub。原实现下 health 成功，但 `/api/v1/workspaces` 在 4 秒后超时：

```text
FAILED tests/test_desktop_process.py::test_real_source_process_desktop_lifetime[shutdown]
TimeoutError: timed out
1 failed, 1 warning in 6.45s
```

此前进程生命周期测试没有登记工作区，因此没有覆盖“控制读取线程阻塞期间再启动 Git”这一条件。没有使用或修改用户的 `E:/tmp/hqagent-n0-trial`。

仅增加 parent stdin 接管、尚未加入其余入口 DEVNULL 防御时，同组桌面进程测试已经变为 `11 passed, 1 warning in 8.45s`，确认根因不依赖 PyInstaller。

另作最小阻塞栈实验：故意保留旧行为 `watch_parent(sys.stdin, ...)`，启动一个默认继承 stdin 的无操作 Python 子进程。父写端持续持有时子进程不能完成，关闭父写端后立即退出 0。栈显示控制线程在 readline，主线程在 subprocess.communicate 等待子进程完成。因此已确认控制管道与默认继承标准输入的关联；本次栈证据没有把 Windows 内部具体卡点定位为某一次 DuplicateHandle，不将该推断写成已观测事实。完整证据见 [inheritance-stack.txt](../reviews/desktop-stdin-fix/inheritance-stack.txt)。

## 修复

### 控制管道由专属读取线程接管

- `take_parent_stdin()` 在应用装配、探测子进程和控制线程开始之前执行。
- 复制输入管道为私有 fd，显式设置不可继承。Windows 同时禁止原始 Win32 STD_INPUT_HANDLE 继承，兼容它与 CRT fd 0 不同的宿主。
- CRT fd 0 重定向到 NUL，并调用 SetStdHandle 更新 Win32 STD_INPUT_HANDLE。POSIX 同样重定向到 /dev/null，私有控制 fd 保持 close-on-exec。只有 NUL fd 0 可以被继承，确保 POSIX 默认输入子进程得到 EOF，而非无效 fd。
- 控制读取线程只读自己的私有流，正常 shutdown/EOF 后自行关闭；主线程不关闭或等待仍阻塞在 readline 的 TextIO。应用因其它原因结束且父管道仍开着时，daemon reader 也不会阻塞进程退出。
- 启动失败时仅关闭尚未交给 reader 的流；未设置 stdio-v1 的 CLI 模式行为不变。
- 保持原有关闭门禁、任务恢复标记、数据库/descriptor/锁清理顺序与 15 秒桌面退出约定。

### 所有 Hub 子进程入口显式输入策略

生产代码搜索与 AST 审计结果：`Production subprocess entry points verified: 10; no implicit stdin`。完整清单：[subprocess-audit.txt](../reviews/desktop-stdin-fix/subprocess-audit.txt)。

| 入口 | stdin | 时间边界 |
| --- | --- | --- |
| ProcessRunner.run / Agent CLI 探测 | DEVNULL | 保留调用方 timeout；超时和取消均清理自有进程树 |
| ProcessRunner.start / Agent 交互与 RPC | 专属 PIPE | 保留会话生命周期与取消控制，不借用父控制输入 |
| Windows taskkill helper | DEVNULL | 等待及 kill 后清理均有界 |
| Workspace Git 查询 | DEVNULL | 单命令 2 秒；整次列表/单项读取共用 3 秒查询预算，清理最多额外 1 秒 |
| Task HEAD 查询 | 经 ProcessRunner/DEVNULL | 5 秒，失败转换为现有业务错误 |
| Worktree Git | DEVNULL | 30 秒 |
| Review evidence Git | DEVNULL | 15 秒 |
| whoami / icacls | DEVNULL | 各 5 秒 |
| 目录选择器 | 原有 DEVNULL | 补齐 kill 后等待上限 3 秒 |
| 打包 smoke-core 启动 | 原有专属 PIPE | 用于父控制协议，保留 |

当前分支没有独立 PI 适配器的子进程实现；未修改另一个 remote-worker 工作区或其 PI 开发。交互 ProcessRunner.start 的 PIPE 及接口签名保持不变。Hub 的 Update Agent 接入是现有代理接口，没有发现直接启动更新代理的入口；shutil 使用仅为查找/复制/清理文件，不另起进程。

### 工作区超时降级

- Git 超时返回内部 124，区分正常的非 Git 目录与超时/不可用，不能将超时误标“不是仓库”或“干净”。
- 不新增协议枚举：保留已登记 vcs，省略未知 branch/isClean，关闭 canRunWriteTasks/canInitGit 并提供状态未确认原因；探测结果不落库，下次正常读取即恢复。
- 列表共用查询截止时间，不按工作区数量成倍累计超时；仍返回完整记录及正确 workspaceCount。专项覆盖 30 个慢工作区与 bootstrap。
- 超时或请求取消时有界终止自有 Git 进程树，避免 fsmonitor 等子进程使输出管道继续悬挂。POSIX 探测进程使用独立 session。

## Windows 实测

真实源码进程、stdin=PIPE、控制读取线程持续阻塞、真实 Git 仓库；无真实模型调用。API 单次上限断言 4 秒，shutdown/EOF 上限 15 秒。输出如下：

```text
{"mode": "stdio-v1", "control": "shutdown", "endpoint": "/api/v1/workspaces", "elapsedMs": 125.0}
{"mode": "stdio-v1", "control": "shutdown", "endpoint": "/api/v1/bootstrap", "elapsedMs": 105.5}
{"control": "shutdown", "exitCode": 0, "exitMs": 362.2}
{"mode": "stdio-v1", "control": "eof", "endpoint": "/api/v1/workspaces", "elapsedMs": 133.4}
{"mode": "stdio-v1", "control": "eof", "endpoint": "/api/v1/bootstrap", "elapsedMs": 139.8}
{"control": "eof", "exitCode": 0, "exitMs": 465.9}
19 passed, 1 warning in 10.06s
```

完整输出：[windows-evidence.txt](../reviews/desktop-stdin-fix/windows-evidence.txt)。新增隔离测试故意让子进程省略 stdin 且 close_fds=False：它只能读到 EOF，父控制 reader 仍存活等待；覆盖不同 Win32 标准句柄与 CRT fd、shutdown、EOF，以及父写端未关闭时服务自行退出。POSIX 分支保留可运行测试，本次主机为 Windows，不声称已在 POSIX 实机执行。

## 串行全量与提交

所有测试仅使用指定 Python、`-B` 和 PYTHONDONTWRITEBYTECODE=1；主测试 TEMP/TMP/basetemp 均在本工作区 `.hqagent/r3-tmp`。子代理专项使用其独立工作区及 E:/tmp。没有修改 vnext-integration 工作区或 venv。没有真实模型调用；没有实际服务端 429/403、0xC0000142 或额度错误；测试内预期的鉴权拒绝反例正常通过。

定向合并回归：

```text
37 passed, 1 warning in 12.07s
```

见 [targeted-final.txt](../reviews/desktop-stdin-fix/targeted-final.txt)。早期 30 工作区夹具误用了相同唯一目录，修正测试夹具后通过；原始输出保留在 targeted.txt，没有放宽断言。

Hub 全量，cwd 为本工作区 apps/hub：

```text
E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp=../../.hqagent/r3-tmp/pytest-desktop-stdin-hub-full --tb=short
745 passed, 9 skipped, 4 warnings in 304.00s (0:05:03)
```

Hub 结束后运行 server 全量，cwd 为本工作区 apps/server：

```text
E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp=../../.hqagent/r3-tmp/pytest-desktop-stdin-server-full --tb=short
343 passed, 1 warning in 88.59s (0:01:28)
```

完整日志：[Hub](../reviews/desktop-stdin-fix/hub-tests.txt)、[server](../reviews/desktop-stdin-fix/server-tests.txt)。9 项跳过均为既有 POSIX 条件；未新增 Windows 跳过或 xfail。输出仅规范换行和行尾空白。

语法检查：`Python syntax verified: 13 changed files`；`git diff --check` 通过。本轮未重打安装器，build=pass 指源码语法/装配与真实源码进程验证。

| 提交 | 主题 |
| --- | --- |
| 49b1580 | 子进程显式 stdin 与辅助命令时间边界 |
| 7cb6256 | 控制管道私有接管、fd 0/Win32 标准输入重定向、生命周期回归 |
| 41aede8 | Git 探测超时和工作区/引导接口降级 |

主代理负责 parent/main/workspaces 与合并、全量；一个子代理在独立 desktop-input-policy 工作区审计并修复其它入口。身份与复用信息见 [.hqagent/codex-sessions.md](../codex-sessions.md)。对子分支提交只 cherry-pick 到 feat/hub-0101，没有合并 integration。每次提交后均用 `git log -1 --format=%B` 自查，无禁止署名。

供 PI 适配器线合并核对：本轮改了公共 `adapters/process.py`（run 的 DEVNULL、取消清理和 taskkill 防御），没有改交互 start 的签名或消息协议，也没有改任何 runtime/remote、native/history、协议或 server 文件。
