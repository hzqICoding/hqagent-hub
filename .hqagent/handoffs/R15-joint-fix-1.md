---
wp: R15-JF1
status: done
scope_declared: [apps/hub/**, apps/server/**, .hqagent/handoffs/R15-joint-fix-1.md]
scope_touched: [apps/hub/runtime/remote/worker.py, apps/hub/tests/test_r15_joint_server.py, apps/server/server/replica.py, apps/server/server/service_sync.py, apps/server/server/worker.py, apps/server/tests/test_joint_metadata_busy.py, apps/server/tests/test_r15_guards.py, .hqagent/handoffs/R15-joint-fix-1.md]
build: pass
tests: pass
commit: 680713d59089c9d33d035b9390726206b724e749
open_questions: 0
---

# R1.5 联调修复 1

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/remote-worker`，分支 `feat/remote-worker`。基线是主代理合入的 `4e580545007ca712eb4a68b7b17a81420e8e5356`，本轮未再合并分支。头部 commit 指实现与测试末次提交，回执单独提交。没有改 packages/protocol、前端、迁移、执行内核、依赖或根文件，没有运行 vitest，没有推送或合并回 integration。

## 结论与真实来源

这是 **P1 元数据冲突判断过严 + P2 错误帧被改报为 epoch 错误** 的组合缺陷；busy 展示还有独立的过期投影问题。不是握手或 ACK 的 epoch/connectionId 真正不一致。

### 只读现场诊断

只读取 `.tmp/joint-evidence`；先把冻结数据库及其 WAL/SHM 复制到忽略目录 `.tmp/jf1-inspection`，对副本以 SQLite `mode=ro` / `query_only=ON` 查询。没有打开服务端 key、加载现场凭据或修改现场数据库，也没有把现场数据库、凭据、对话正文、完整 ID 写进测试或提交。

查询得到：

- Hub 的 `ack=431 / high=433 / wireRevision=2` 与提供的证据一致。
- `sync-work.phase` 已是 **synced**，`batch=5 / waitAck=433`。
- seq **424** 是 `sync.backfill.progress(batchIndex=2, batchEventCount=0, complete=true)`；426 和 433 是同一补传后的增量批次标记 `complete=false`。因此，不能从“最后一帧 complete=false”推断此前历史从未补齐。没有改动补传时序来掩盖这个问题。
- seq **425** 的 upsert 已被服务端接受；未确认的 **432** 对应同一个本机对话，二者 **metadataVersion 都为 1，只有 updatedAt 改变**。服务端对话投影仍持有 425 的时间值。

### 精确故障链

1. 本机消息进入 `LocalChatRepository.enqueue`，更新对话 `updatedAt`，不增加元数据 `version`。这是现有冻结语义：`packages/protocol/schema/local-chat.json` 的 LocalConversationView.version 明确说明 **message/run updates do not increment this revision**。
2. Worker 按 R1.5 §2/§3 上传本机事实：`sync.conversation.upserted.payload.metadataVersion=1`，`payload.updatedAt` 随本机活动前进。Worker 没有擅自改 CAS 版本，这一步正确。
3. **P1 错误点**：基线 `Replica.conversation()` 在同版本时要求 `previous['_metadataHash'] == digest(payload)`，把活动时间也纳入不可变元数据比较，抛出 **REMOTE_SYNC_CONFLICT**。该事件事务回滚，连续 ACK 停在 431；设备记录没有因此设置 `_frozen`。
4. P1 的 `WorkerTransport.run()` Fault 分支通过当前线路发送生成 DTO 合法的 **worker.hello_rejected**，其中 `error.code=REMOTE_SYNC_CONFLICT`、`retryable=false`、`supportedWireRevisions=[1,2]`，随后关闭当前连接。
5. **P2 错误点**：基线 `worker.py::connection.receive()` 没处理连接建立后的该错误包，落入第三处异常分支：**“连接中出现非命令握手帧” → HubError(REMOTE_EPOCH_STALE)**。不是 hello_ack/common 比对，也不是 ACK/heartbeat 的 connectionId 比对。外层 run 将这个被错误替换的码视为终止故障，冻结本机 link。
6. ACK/发送循环已停止，后续助手消息和运行结束快照不能继续上传；P1 失去连接后 busyFresh=false，但旧视图仍直接输出缓存 `_busy=true`，形成手机上的假忙碌展示。

真实双方测试捕获了上述 `worker.hello_rejected`；另用真正的同版本标题冲突断言：服务端 `_frozen` 仍为 false、服务端 `_epoch` 等于 Hub identity.epoch、收到的 ACK connectionId 都等于 hello_ack 的 connectionId，而旧 Worker 却报 EPOCH_STALE。R1 契约 §4 要求结构化错误保留 registry code，不能用关闭文本或无依据的 epoch 推断替代。这里无需增加协议类型或兼容字段。

## 先复现，再修复

新增 `apps/hub/tests/test_r15_joint_server.py`，先在未修改生产代码时跑出 **3 个与现象对应的失败**，日志为 `.tmp/jf1-reproduced.log`：

```text
E   assert 'frozen' == 'paired'
E   AssertionError: assert 'REMOTE_EPOCH_STALE' == 'REMOTE_SYNC_CONFLICT'
3 failed, 1 warning in 6.81s
```

两个正常对话场景的失败诊断还捕获了收到的 REMOTE_SYNC_CONFLICT 错误包及同 metadataVersion 的不同活动时间。上面是原失败输出中的摘录，不是把超时、fixture 错误或连接失败算作业务复现。

测试构成：

- 所有数据由测试生成：schema 3 的合成 R1 已配对服务端账本、schema 6 的 Hub 两条旧对话/历史消息、临时账号、随机设备凭据；不读取 `.tmp/joint-evidence`。
- 真正调用 P1 `create_app`，自动迁移 server 3→4；真正构造 Worker / Hub 服务，迁移 Hub 6→7并自动协商修订 2。
- 同一进程运行真实 uvicorn TLS HTTP/WSS，使用仓库已有测试证书、随机 loopback 端口、真实浏览器 Cookie 登录、真正生成 DTO 编解码和连续 ACK。没有用 FakeRemoteServer 替代 P1。
- 在“历史已 complete”与“首批历史 ACK 被控制暂停、尚未 complete”两种时序创建本机对话并执行一轮；后者证明新对话增量未越过历史完成标记。之后继续电脑会话，校验两条完整助手回复、busy=false/fresh=true、连接保持 paired。
- 又通过真正 P1 的手机 HTTP → received → grant → Worker 入口继续电脑会话，检查本机 Adapter 的 resume 路径和第三条回复。
- **模型边界**：执行使用真实 LocalChat / TaskService / SessionManager，但 Adapter 是现有测试替身，合成回复为“记住了”。本轮没有调用外部模型或真实 CLI Agent，不把测试说成已经重跑用户那条真实 Agent 脚本。

修复后该模块实际结果：

```text
3 passed, 1 warning in 7.84s
```

## 修复内容

### P1：活动时间与元数据 CAS 分离

`apps/server/server/replica.py`：

- 同一 metadataVersion 仍逐字段严格检查 workspaceId、sceneId/sceneVersion、title、createdAt、archived、visibility、authority；仅将 `updatedAt` 作为可独立前进的活动时间。
- 时间前进则更新投影、lastActivityAt 与浏览器事件；重复或更早时间不使投影回退；真正元数据字段变化仍要求更高版本，否则仍报 REMOTE_SYNC_CONFLICT。
- 更高 metadataVersion 更新也保留更晚的 lastActivityAt，避免元数据投影覆盖已有活动时间。
- 不修改本机版本语义，不靠“发消息就加版本”绕过冲突，不关闭事件身份/hash 校验，不重写未确认的 Worker 事件。

### P2：保留服务端错误，不伪造 EPOCH_STALE

`apps/hub/runtime/remote/worker.py`：

- 建立连接后收到当前 codec 已验证的 worker.hello_rejected，使用其注册 error.code；不再落入“非命令握手帧”的 epoch 错误分支。
- 对非 retryable 拒绝保持安全冻结（撤销仍走原 revoked 路径），避免同一坏事件的重连风暴。
- 仅使用错误码和 retryable，不回显对端任意错误文本，不削弱真正的 hello/common 或 ACK/heartbeat connectionId 栅栏。
- 真正的同版本标题冲突现如实显示 **REMOTE_SYNC_CONFLICT**；正常活动时间更新不再触发拒绝。

### P1：busy 只展示当前完整且有效的快照

`apps/server/server/service_sync.py`、`replica.py`、`worker.py`：

- 对话视图的 busy 改为 `fresh && storedBusy`，busyFresh=false 时必为 busy=false。列表、详情、snapshot 共用这个 Mapper；device 的 busySnapshotFresh 也排除冻结状态。
- 完整 busy 快照的浏览器事件在原事务中采用该完整快照的有效性生成，连接内存标志仍在 commit 后更新，避免改成 gate 后反而把新鲜快照错误显示为空闲。
- 冻结与当前连接断开时，持久失效标志并发 conversation.updated（busy=false / busyFresh=false），让已经消费过旧游标的事件客户端也收到清理通知。旧连接的 finally 不会清空替代连接的新快照。
- 历史 browser event 重放时重新投影当前 busy/fresh/observedAt，防止旧游标把离线前的 busy=true 重新带回手机。Worker 原始事件及其 seq/hash 不变。
- 内部仍保留历史 busy 集合供核对，不把离线误认为执行已经停止；不改 Run 的真实状态，不影响“离线发送直接失败”或取消权限。

## 测试范围与唯一旧断言调整

- Hub 新增真实双方集成 **3 项**；原 337 项保留，全量 **340 项**。
- server 新增 **12 项**（`test_joint_metadata_busy.py`）：活动时间前进/不回退/真实 CAS 编辑；同版本篡改 title、visibility、archived、workspaceId、sceneId、authority 仍拒绝；断线、45 秒超时、冻结、分片未齐时的列表/详情/快照/事件重放；已消费旧 cursor 的客户端收到断线失效事件。
- server 既有 `test_r15_guards.py::test_restart_invalidates_freshness_without_retaining_lock` 仅一行按本任务第 4 条调整：原 `busy=True, busyFresh=False` 改为 `busy=False, busyFresh=False`。原来显式允许的“保留旧 busy 展示”被此次展示要求收紧；没有放宽其它旧断言。
- server 定向验证（新增模块 + 原 guards 模块）：`21 passed, 1 warning in 7.76s`。

## 全量验证的真实命令与输出

全部串行执行，没有 pytest 并行 worker、没有 vitest、没有安装依赖。TEMP / TMP / basetemp 都在本 worktree 内被 git 忽略的 `.tmp`，避免默认临时目录 WinError 5。

### Hub

cwd：`apps/hub`。

```powershell
$env:TEMP = 'E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP = $env:TEMP
$env:PYTHONIOENCODING = 'utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/jf1-hub-full 2>&1 | Tee-Object -FilePath ../../.tmp/jf1-hub-full.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 63%]
........................................................................ [ 84%]
远程送达预留清理暂未完成，将重试
....................................................                     [100%]
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
340 passed, 4 warnings in 184.75s (0:03:04)
```

退出码 0。原 R15-P2「返修 1」已记录的通用清理重试日志本轮又出现一次；本轮没有改动清理逻辑、没有取得该日志的内部异常栈，也不把它无依据地归因为本次 EPOCH_STALE。此处完整保留输出，不宣称它已被解决。4 条 warning 是既有依赖弃用提示。

### server

cwd：`apps/server`，TEMP/TMP/PYTHONIOENCODING 同上。

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/jf1-server-full 2>&1 | Tee-Object -FilePath ../../.tmp/jf1-server-full.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 44%]
........................................................................ [ 88%]
..................                                                       [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
162 passed, 1 warning in 63.85s (0:01:03)
```

退出码 0。

### 协议

cwd：worktree 根目录，TEMP/TMP/PYTHONIOENCODING 同上。

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv/Scripts') + ';' + $env:PATH
pwsh scripts/protocol/validate.ps1 -CheckGenerated 2>&1 | Tee-Object -FilePath .tmp/jf1-protocol.log
exit $LASTEXITCODE
```

```text
协议校验通过：321 个类型，173 个 Contract Fixture
```

退出码 0。`git diff --check` 无输出。本轮无 0xC0000142 或额度错误。

## 交付与复测边界

- `1c2bac29750ba16c3fb5db09eb37ec5f16cf3e70`：P1 活动时间、CAS 严格校验、busy 视图/事件失效及服务端测试。
- `680713d59089c9d33d035b9390726206b724e749`：P2 保留真实错误与真实 P1/Worker TLS 集成测试。
- 回执单独提交；每次提交后执行 `git log -1 --format=%B` 自查，无署名或生成标记。
- 没有修改现场 frozen 状态、凭据或账本，也没有引入自动解冻。真实 Agent 复测应由主代理在其联调环境核对后进行；重启本身不等于获准解冻，不能因服务端 `_frozen=False` 就跳过本机冻结/连续性核对。
- 本轮已解决并直接复现的是本机消息活动引发的错误冲突、错误码掩盖和旧 busy 展示；未运行前端测试或真实 CLI Agent，未修改前端。
