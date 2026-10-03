---
wp: hub-sync-conflict
status: done
scope_declared: [apps/hub/**, .hqagent/handoffs/hub-sync-conflict.md]
scope_touched: [apps/hub/runtime/native/service.py, apps/hub/runtime/remote/recovery.py, apps/hub/runtime/remote/sync.py, apps/hub/runtime/remote/worker.py, apps/hub/runtime/cli.py, apps/hub/api/app.py, apps/hub/README.md, apps/hub/tests/test_sync_conflict_recovery.py, .hqagent/handoffs/hub-sync-conflict.md]
build: pass
tests: pass
commit: 9a6e6aefb33a36912030469a21aabce339586876
open_questions: 0
---

# Hub 原生元数据同步冲突：根因、修复与恢复

## 根因与只读证据

开工 `git merge integration/phase1` 输出 `Already up to date.`，基线 `c014e62`（含返修 5 与本机会话持久化）。没有修改 apps/server、packages/protocol、apps/desktop，也没有修改用户数据。

诊断仅以 SQLite `mode=ro` + `PRAGMA query_only=ON` 访问 `E:/tmp/hqagent-n0-trial/data/hub.db`。SQL 只投影事件类型、seq、状态、版本、源摘要、活动证据及变更字段名，没有读取或输出会话正文、标题、文件正文、凭据。没有把用户数据库复制进仓库或测试。

本次读取时：

- link 仍为 frozen/offline，lastErrorCode=`REMOTE_SYNC_CONFLICT`，lastConnectedAt=`2026-10-03T02:06:58.130249Z`。
- 本机 identity 为 wireRevision=4，ack=13933，high=13935；sync-work.phase=synced，syncGeneration=1。与任务中的服务端 `_lastReportedAck=13827` 快照不同，不能把13828直接当作最终坏帧。
- 原生索引已经有57条 readable。事件序列中一批原生索引从 indexVersion=1 增至2；13887至13933主要为 indexVersion=2 的 `native.index.upserted`，本机已收到连续 ACK。
- 未确认 Outbox 为 `13934 sync.conversation.upserted` 与 `13935 sync.backfill.progress`。

**实际冲突资源是已导入的原生对话，不是未导入索引的 indexVersion 回退。** 该对话 nativeSessionId=`native_e87b2b593d584fba90d7b9be1b1eb91d`。对同一资源，SQL 比较结果：

| seq | metadataVersion | nativeSourceRevision | nativeActivity.activity |
| --- | --- | --- | --- |
| 13343 | 1 | 744b23ba0d2ca9ac91df043ce1c6d630a9f62edae07457d3d203bccc34a673dc | closed_confirmed |
| 13934 | 1 | 320eda02db15fa30b109d1ff1145449136fe53d393fd73b5557239befd0a97ae | unknown |

两帧 payload 变更键只有 `nativeActivity`、`nativeSourceRevision`。此前 seq 12174、12754、13343 均为旧摘要、metadataVersion=1。新活动观测时间为 `2026-10-03T02:07:03.715511Z`。

`NativeService._scan` 重新计算已导入会话的源版本/活动状态时，只改了这两个字段，**没有递增 LocalConversationView.version**。`SyncService.metadata` 按协议把 version 原样映射为 metadataVersion。P1 `server/replica.py::conversation` 对同 metadataVersion 比较除 conversationId/updatedAt 外的全部元数据，因此正确拒绝该变化。更新读取策略会改变 readerId/sourceRevision 并让旧关闭确认失效，是这次问题的触发条件；源文件变化、活动证据变化也可能触发同一漏洞。

真实 TLS 服务端夹具首先复现失败：收到 `worker.hello_rejected`，`error.code=REMOTE_SYNC_CONFLICT`、`retryable=false`、wireRevision=4，Worker 按现有规则冻结。没有修改服务端校验；不需要派服务端修改。

契约依据：R3 §4 的原生对话字段必须按 R1.5 电脑权威元数据同步；R1.5 同版本不同元数据是冲突。R3 §5 要求索引版本变化单调、真正冲突不能覆盖；R1.5 reset 关闭 generation，恢复上传必须用更大的 generation。

## 修复

### 元数据 CAS

`runtime/native/service.py`：仍忽略只有 observedAt 变化的观测，避免每5秒无意义地更新CAS。真实事实变化时在同一事务重读当前对话；如并发路径已保存相同事实则不重复写，否则保存新活动/源版本并递增 version、更新 updatedAt 及行 updated_at。这样不会覆盖同时发生的重命名、可见性修改，并由现有数据库触发器排入同步变化。

未导入索引原有 indexVersion 推进逻辑保持不变，测试明确验证旧策略 unsupported → 新策略 readable 的 indexVersion 增长。

### 显式恢复，不能仅把 link 改回 paired

新增 `runtime/remote/recovery.py`，恢复意图存于现有 remote_state 的 `sync-recovery` 键，无新协议字段或数据库迁移。提供 operator Bearer 保护的内部 `POST /internal/remote/resync`；CLI `remote resync --confirm-reset` 复用本机 descriptor 与 loopback 认证。Cookie 或云端凭据不能操作该内部接口。

状态顺序：

1. 只接受本机 frozen + REMOTE_SYNC_CONFLICT、修订至少3、同步开启、存储连续性完整且无 reconciliationRequired。STORE_CHANGED、ACK_CONFLICT、EPOCH_STALE、凭据问题等拒绝。持久化 requested，并仅允许重新握手；此时尚未 reset。
2. 服务器明确 hello_ack.commandDelivery=ready 后，事务创建 reset generation `G+1`，调用现有 reset/retire。保留原 seq/eventId/hash，使用协议 ContentRedaction 覆盖旧未确认内容槽，不将坏帧原地改写成新帧；命令、grant、控制证据等不作为可删除内容槽。
3. 等 reset 的连续 ACK 后，事务切到更大的 `G+2`，捕获完整快照并补传。**不能在 reset 的同一 generation 里补传**，否则服务器会按关闭栅栏忽略。
4. 全部补传完成标记连续确认后，内部恢复记录为 complete。重复请求不重复分配 generation。意图及阶段均持久，Worker 重启可继续；同步设置被主动切换时取消恢复意图，服从用户最新设置。
5. 重握手若仍有服务端冻结，记录 blocked、保留冻结码，不发 reset；握手前的 store/ACK 校验同样不绕过。

接线仅涉及 api/app.py 的内部路由、worker.py 的握手点、sync.py 的 reset ACK→下一代补传接续、runtime/cli.py 的命令。没有放松正常帧、ACK、世代或服务端冲突校验。

## 对用户这台电脑的恢复步骤（由主代理执行）

**本轮没有修改真实用户数据，也没有连接线上服务或代用户执行恢复。** 主代理先部署本包代码，按原方式重启 Hub，仍使用数据目录 `E:/tmp/hqagent-n0-trial` 和原配对信息，不能重新生成设备凭据。

在已部署代码的 `apps/hub` 目录，使用该 Hub 的虚拟环境（下面相对路径适用于仓库布局）：

```powershell
../../.venv/Scripts/python.exe -m runtime.cli --data-dir E:/tmp/hqagent-n0-trial remote status
../../.venv/Scripts/python.exe -m runtime.cli --data-dir E:/tmp/hqagent-n0-trial remote resync --confirm-reset
../../.venv/Scripts/python.exe -m runtime.cli --data-dir E:/tmp/hqagent-n0-trial remote status
```

第二条返回 `{"requested": true}` **不是补传完成**。等待 link 恢复 paired/online，lastErrorCode 清除，并等待手机历史补齐。主代理如需更细核对，可只读查看 remote_state 的 sync-recovery.phase=complete、sync-work.phase=synced、sync-settings.syncGeneration（若原本G=1，本流程成功后为3）。设备 workerId、workerStoreId 和凭据保持原值，不重新配对。若握手返回真正冻结码，应停止使用此命令，按该码对账，不直接改库。

影响：

- reset 删除这台电脑的云端对话副本、全文、原生索引及相关云端附件；补传期间手机列表/历史会暂时清空或不完整。其他电脑不受影响。
- 本机对话、消息、原生源文件、Session、执行结果与凭据不删。稳定对话映射保留，完整补传后恢复；未导入原生会话仍只上传索引，不上传正文。
- reset 使用原有规则释放未获 grant 的送达预留；不把历史执行命令重新执行，不伪造已完成结果。附件按现有上传机制重建，本机已丢失文件的云端内容不能凭空恢复。
- 这是一次显式副本重建，不对所有 frozen 状态自动解冻；不产生重连/重建风暴。

## 测试

新增 `tests/test_sync_conflict_recovery.py`，全部使用合成文件与真实本地 P1 TLS 服务端：

1. 旧 structures-v2/较窄版本策略同步3条 unsupported 索引及一个已导入原生对话，再改新策略：索引版本增长、变为 readable；已导入对话源变化时 metadataVersion 增长，连接不冻结；仅观测时间变化不增加CAS。
2. 显式制造旧生产者的同版本原生元数据变化：服务端仍拒绝且投影不变，设备本身未被冻结。operator 恢复、Worker 生命周期重启后完成两阶段 generation 切换；凭据/store不变、消息全文恢复、对话稳定ID保留、不启动任何 Agent。
3. 本机 STORE_CHANGED/ACK_CONFLICT/EPOCH_STALE/认证冻结拒绝恢复；即使本机暂报同步冲突，真实服务器握手仍冻结时也不 reset。
4. 同 indexVersion 不同索引内容仍被服务端拒绝，不放宽校验。
5. CLI 必须显式 --confirm-reset，调用内部端点。
6. 用户关闭同步取消待恢复意图，不重开同步。

修复前复现命令（cwd `apps/hub`，已设置 worktree 内 TEMP/TMP）：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/sync-conflict-red tests/test_sync_conflict_recovery.py --tb=short
```

当时测试文件只有第一条复现用例，真实失败输出：

```text
F                                                                        [100%]
================================== FAILURES ===================================
_______ test_reader_policy_upgrade_syncs_indexes_and_imported_metadata ________
tests\test_sync_conflict_recovery.py:56: in test_reader_policy_upgrade_syncs_indexes_and_imported_metadata
    asyncio.run(scenario())
E:\SoftWare\Python313\Lib\asyncio\runners.py:195: in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
E:\SoftWare\Python313\Lib\asyncio\runners.py:118: in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E:\SoftWare\Python313\Lib\asyncio\base_events.py:725: in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
tests\test_sync_conflict_recovery.py:41: in scenario
    assert pair.system.repo.get('link')['view']['state'] == 'paired', [
E   AssertionError: [{'error': {'code': 'REMOTE_SYNC_CONFLICT', 'message': 'REMOTE_SYNC_CONFLICT', 'retryable': False}, 'supportedWireRevisions': [1, 2, 3, 4], 'type': 'worker.hello_rejected', 'wireRevision': 4}]
E   assert 'frozen' == 'paired'
E
E     - paired
E     + frozen
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/test_sync_conflict_recovery.py::test_reader_policy_upgrade_syncs_indexes_and_imported_metadata
1 failed, 1 warning in 2.85s
```

修复后定向命令：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/sync-conflict-final-focus tests/test_sync_conflict_recovery.py tests/test_r3_api_sync.py tests/test_runtime_cli.py --tb=short
```

实际输出：`17 passed, 1 warning in 20.05s`。

Hub 全量命令（cwd `apps/hub`）：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/sync-conflict-hub --tb=short
```

真实输出：

```text
........................................................................ [ 10%]
........................................................................ [ 21%]
...............................................................s........ [ 31%]
........ssssssss........................................................ [ 42%]
........................................................................ [ 53%]
........................................................................ [ 63%]
........................................................................ [ 74%]
........................................................................ [ 85%]
........................................................................ [ 95%]
远程送达预留清理暂未完成，将重试
远程送达预留清理暂未完成，将重试
............................                                             [100%]
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
=========================== short test summary info ===========================
SKIPPED [1] tests\test_posix_credentials.py:166: POSIX mode bits
SKIPPED [1] tests\test_posix_path_guard.py:50: POSIX absolute redirect path
SKIPPED [1] tests\test_posix_path_guard.py:68: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:76: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:84: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:101: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:108: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:115: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:122: POSIX executable symlink and directory-fd semantics
667 passed, 9 skipped, 4 warnings in 271.97s (0:04:31)
```

Server 全量命令（cwd `apps/server`，在 Hub 全量结束后串行执行）：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/sync-conflict-server --tb=short
```

真实输出：

```text
........................................................................ [ 23%]
........................................................................ [ 47%]
........................................................................ [ 71%]
........................................................................ [ 94%]
................                                                         [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
304 passed, 1 warning in 77.07s (0:01:17)
```

`git diff --check` 通过。Hub 9 项 skipped 均为既有 POSIX 专属测试；warning 为依赖弃用提示，没有新增失败。未发生 429、额度错误或 0xC0000142。


TEMP/TMP/--basetemp 均指向 worktree 内 git 忽略的 `.tmp`；Hub/server 串行，不运行 vitest、不调用模型、不联网。Windows 本机验证；未声称真实线上恢复已完成。


## 提交

- `9a6e6aefb33a36912030469a21aabce339586876`：原生元数据CAS修复、受控恢复路径及真实服务端回归测试。
- README 与本回执另作文档提交。每次提交后均执行 `git log -1 --format=%B` 自查；不含署名或生成标记。未合并回 integration。
