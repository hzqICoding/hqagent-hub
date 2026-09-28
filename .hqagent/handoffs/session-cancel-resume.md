---
wp: SESSION-CANCEL-RESUME
status: done
scope_declared: [apps/hub/orchestrator/runtime.py, apps/hub/orchestrator/sessions.py, apps/hub/runtime/local_chat.py, apps/hub/tests/**, .hqagent/handoffs/session-cancel-resume.md]
scope_touched: [apps/hub/orchestrator/runtime.py, apps/hub/orchestrator/sessions.py, apps/hub/tests/test_session_cancel_resume.py, .hqagent/handoffs/session-cancel-resume.md]
build: pass
tests: pass
commit: 2efc67eea10ebc6de57f5e8166bfd3b0ef9fead7
open_questions: 0
---

# 确认取消后的原生会话续接（方案 D）

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/remote-worker`，分支 `feat/remote-worker`，本轮基线 `843c869c9e797f2d9ec6f4e6b1b3bb2ffebbde53`。实现和测试已提交，回执另提交以避免自引用。没有合并分支，没有改协议、server、desktop、依赖、迁移、TaskService 或仓储实现，没有运行 vitest。

## 改动与判定依据

`orchestrator/runtime.py` 仅替换取消末尾的一次调用：原 `sessions.close(session_id)` 改为 `sessions.finish_cancelled(session_id, current_task_id, result)`。此前 REFUSED、NOT_FOUND、ALREADY_FINISHED 三个分支原样保留；优雅取消请求、超时强杀、Task 状态事件、CancelResult 与 CancellationOutcome 的执行证据均未改。

`orchestrator/sessions.py` 新增安全收尾方法，**同时满足以下条件**才通过原 finish 路径变为 IDLE：

- CancelOutcome 是 STOPPED_GRACEFULLY 或 FORCE_KILLED；
- 当前 CancelResult 没有 orphanProcessIds；
- 通过已经注入的生产 SessionRepository.execution_state 的现有 `get` 接口，能读取当前执行 `task_spec:<taskId>`，且没有 unresolvedCancellation / recoveryRequired；
- 当前持久 Session 的 isValid 为 true，externalSessionId 存在，状态仍是 ACTIVE 或 IDLE。

isValid 的既有来源是 create_active 中的 `handle.supportsResume && externalSessionId`，因此沿用的是该 Adapter 启动句柄对这个会话的能力声明，不依赖厂商名、不猜测 CLI 行为。新方法只读结构化 enum、PID 列表和持久标志，不读取错误文字；没有新增 SQL 或改变 state 的语义。

这里传入的是 **DispatchOutcome 的当前 task_id**，不是 SessionView 上最初创建会话的 task_id。原生 Session 可跨轮次复用，若误查初始 Task，就会漏掉第二轮的未确认取消。新增测试专门覆盖了这一点。

仓储没有 execution_state 读取能力、Task 文档不存在、能力未声明、externalSessionId 丢失、已有未确认标志或残留进程时，都继续原 close 路径；不因“本次返回了停止”就覆盖已有未确认事实。已有 CLOSED/INVALID 会话不被该方法重新打开，SessionLifecycle 的状态迁移规则未放宽。

## 为什么不改 local_chat.py

原 continue 已选取最近终态轮次、检查角色与模型快照、读取原 Session，并要求它是可用 IDLE；取消后的轮次本来就在候选中。安全取消现在把该 Session 本身保留为 IDLE，因此原入口自然原生续接，无需跳过取消轮次、寻找更早上下文或自动创建新会话。

未确认取消仍关闭或保留原分支的不可续接状态，原入口继续保存并返回结构化 SESSION_NOT_RESUMABLE。角色变更、原路径失效、worktree 校验和 reviewer 隔离等既有条件仍成立，不能拿“取消已确认”绕过它们。

turnCount 在取消时不变，只由原 SessionManager.resume 成功路径递增；Hub Session ID、externalSessionId、isValid 和原执行规格不会因取消被改写。历史已经 CLOSED 的会话不做迁移或自动复活，本改动作用于此后的安全取消收尾。

## 测试

新增 `apps/hub/tests/test_session_cancel_resume.py`，共 16 项；**没有修改任何既有测试或放宽断言**。

| 场景 | 核对内容 |
| --- | --- |
| graceful / force_killed × continue / new，4 项 | 确认取消结果仍是 confirmed / adapter_confirmed、无残留；取消后 IDLE/isValid/external ID 不变、turnCount 仍为 1；continue 使用同一 Hub Session，Adapter.resume 携带原 externalSessionId，turnCount=2；new 则另建 Hub Session 并调用 start |
| 不安全或不支持续接，7 项 | orphan、持久 unresolvedCancellation、recoveryRequired、缺少持久 Task 证据、supportsResume=false（即使 external ID 存在）、无 external ID、启动后 external ID 丢失；取消收尾仍 CLOSED，continue 结构化失败且不新起/续接 Agent |
| 其它取消结果，3 项 | ALREADY_FINISHED 仍为 Session IDLE / Task RUNNING；NOT_FOUND 仍 INVALID / FAILED；REFUSED 仍 ACTIVE / FAILED |
| 同一 Session 的第二轮取消，1 项 | 第二轮有 unresolvedCancellation、初始 Task 无此标志，仍关闭 Session 并拒绝第三轮 continue，证明检查的是当前 Task |
| 修订 2 手机路径，1 项 | 真 TLS 测试内 WS、Worker、真实本机执行内核与 FakeAdapter；手机 submit/grant → cancel/grant → confirmed → continue/grant 成功，仍是同一 Hub Session/原 externalSessionId，turnCount=2 |

先在生产修改前运行确认取消/手机续接测试，得到预期失败：

```text
E   AssertionError: assert ('closed' == 'idle'
5 failed, 10 deselected, 1 warning in 2.84s
```

该输出对应最初的 15 项测试版本；随后增加了 external ID 丢失场景。最终定向输出：

```text
16 passed, 1 warning in 4.12s
```

测试使用现有 FakeAdapter，不声称已与真实 CLI Agent 再次联调。全量继续包含原 D41 三态、暂停/恢复、重试、reviewer 隔离及 continued worktree 的测试；这些生产路径没有修改。

## Hub 全量验收

cwd：`apps/hub`。TEMP/TMP/basetemp 均放在 worktree 内被 git 忽略的 `.tmp`，避免默认目录 WinError 5；串行执行，没有并行 pytest。

```powershell
$env:TEMP = 'E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP = $env:TEMP
$env:PYTHONIOENCODING = 'utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/session-cancel-resume-full 2>&1 | Tee-Object -FilePath ../../.tmp/session-cancel-resume-full.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 20%]
........................................................................ [ 40%]
........................................................................ [ 60%]
........................................................................ [ 80%]
远程送达预留清理暂未完成，将重试
....................................................................     [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_ws_close_codes_real_handshake.py::test_bad_ticket_closes_with_4401_not_a_handshake_rejection
tests/test_ws_close_codes_real_handshake.py::test_bad_origin_closes_with_4403_and_is_distinguishable_from_bad_ticket
tests/test_ws_close_codes_real_handshake.py::test_expired_cursor_closes_with_4410_and_sends_snapshot_url_first
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\websockets\exceptions.py:137: DeprecationWarning: ConnectionClosed.code is deprecated; use Protocol.close_code or ConnectionClosed.rcvd.code
    warnings.warn(  # deprecated in 13.1 - 2024-09-21

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
356 passed, 4 warnings in 177.26s (0:02:57)
```

退出码 0，原 340 项加新增 16 项。4 条为既有依赖弃用提示；通用预留清理重试日志是此前回执已记录的未归因日志，本轮没有改动或宣称解决该路径。

## 协议验证

cwd：worktree 根目录，TEMP/TMP/PYTHONIOENCODING 同上，使用已有虚拟环境：

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv/Scripts') + ';' + $env:PATH
pwsh scripts/protocol/validate.ps1 -CheckGenerated 2>&1 | Tee-Object -FilePath .tmp/session-cancel-resume-protocol.log
exit $LASTEXITCODE
```

```text
协议校验通过：321 个类型，173 个 Contract Fixture
```

退出码 0。`git diff --check` 无输出。完整输出保留在 `.tmp/session-cancel-resume-full.log`、`.tmp/session-cancel-resume-protocol.log`；没有提交临时数据。

实现提交 `2efc67eea10ebc6de57f5e8166bfd3b0ef9fead7`；回执另提交。每次提交后用 `git log -1 --format=%B` 自查，提交信息无署名或生成标记。本轮无 0xC0000142 或额度错误。
