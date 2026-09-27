---
wp: R15-P2
status: done
scope_declared: [apps/hub/runtime/remote/**, apps/hub/storage/remote*.py, apps/hub/storage/migrations.py, apps/hub/runtime/local_chat.py, apps/hub/runtime/tasks.py, apps/hub/storage/local_chat.py, apps/hub/api/local_chat.py, apps/hub/api/app.py, apps/hub/runtime/composition.py, apps/hub/tests/**, .hqagent/handoffs/R15-P2-remote-worker.md]
scope_touched: [apps/hub/api/app.py, apps/hub/api/local_chat.py, apps/hub/runtime/local_chat.py, apps/hub/runtime/remote/api.py, apps/hub/runtime/remote/busy.py, apps/hub/runtime/remote/commands.py, apps/hub/runtime/remote/deadline.py, apps/hub/runtime/remote/delivery.py, apps/hub/runtime/remote/link.py, apps/hub/runtime/remote/security.py, apps/hub/runtime/remote/sync.py, apps/hub/runtime/remote/window.py, apps/hub/runtime/remote/wire.py, apps/hub/runtime/remote/worker.py, apps/hub/runtime/tasks.py, apps/hub/storage/local_chat.py, apps/hub/storage/migrations.py, apps/hub/storage/remote.py, apps/hub/tests/remote_support.py, apps/hub/tests/test_r15_delivery_guards.py, apps/hub/tests/test_r15_local_api.py, apps/hub/tests/test_r15_recovery.py, apps/hub/tests/test_r15_sync.py, apps/hub/tests/test_r15_worker.py, apps/hub/tests/test_remote_guards.py, apps/hub/tests/test_remote_worker.py, .hqagent/handoffs/R15-P2-remote-worker.md]
build: pass
tests: pass
commit: 0771e0b36b0dab32c2b2659729c1ec600c78986d
open_questions: 0
---

# R1.5-P2 Worker 交付回执

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/remote-worker`，分支 `feat/remote-worker`。基线为主代理已合入的 `6752576d9cf2c16c25f78fc89b3fd8eb26d116c3`（协议 0.7.0）；从磁盘未提交状态续作，没有回滚或另行合并。头部 commit 指实现及测试末次提交，回执另提交以避免自引用。

电脑仍是唯一执行与写入方：远程层接入原 LocalChatService → TaskService → WorkflowRuntime → Adapter / SessionManager；没有模型上云、模型凭据上传、Attempt、长期 Task 或执行内核迁移。未修改 packages/protocol、apps/server、apps/desktop、docs 或根共享文件，未增加依赖，未安装依赖，未推送或合并回 integration。

## 主代理裁决与未实施项

- **同步状态视图**：遵照本轮裁决，不暴露“补传中 / 已同步 / 异常”的新字段。0.7.0 的设置响应严格为 `mirrorEnabled/version/syncGeneration`。内部工作状态持久化在 remote_state，不另造 DTO；公开状态字段留待协议后续冻结。
- **单个对话删除**：0.7.0 未冻结本机删除路由，当前 Hub 也没有现有对话删除入口。本包没有新增删除路由或宣称已实现端到端单对话删除。实现了 sync reset、设备撤销及解绑时的远程副本清理。迁移仅为可能的本机删除保留稳定 ID tombstone / journal；单对话删除事件的产品入口与联调留后续。
- **前端验证**：按任务要求由主代理负责；本轮没有启动 typecheck、vitest 或其它前端测试，不把早期 R1 的前端结果当成本轮验证。
- **联调**：本轮使用测试内真实 TLS HTTP/WSS 假服务端、真实 SQLite 与本机执行内核、FakeAdapter；**未与真实修订 2 服务端联调**。此前 R1 真实服务端/浏览器/Agent 联调通过不替代本轮验收。
- publish 保留 0.2 秒轮询。首次历史快照在一个 SQLite 事务中逐资源物化到磁盘暂存表，未把全部历史放进内存；事务耗时仍随历史规模增长。本轮未做大型生产数据库容量/时延压测，通知唤醒与大库捕获优化留后续，不声称已消除这一成本。

这些是已裁决后续项及验证边界，没有新增待裁决契约问题。

## 模块与表结构

| 文件 | 职责 |
| --- | --- |
| runtime/remote/wire.py | 独立 CODECS[1]/CODECS[2]，按真实线路校验生成 DTO；除握手拒绝协商外禁止混用修订，不改重传版本、epoch 或 hash |
| runtime/remote/worker.py | 修订协商、持久升级栅栏、连接恢复顺序、心跳校时、两套消费入口与发送窗口接线 |
| runtime/remote/deadline.py | serverTime + 握手 RTT + 单调时钟的保守期限；墙钟跳变、长暂停、重启失去界限时拒绝新许可 |
| runtime/remote/delivery.py | 修订 2 双向 ID 映射、顺序槽、provisional/grant、元数据 CAS、拒绝与 skip tombstone、回执去重；复用原按 run 串行后台控制执行 |
| runtime/remote/busy.py | 结构化忙碌观察、恢复核对、空/非空完整集合及每片至多 100 ID 的快照 |
| runtime/remote/sync.py | 设置、generation、快照高水位/暂存、全文分段、增量 journal、执行结果、reset/redaction、撤销/解绑清理 |
| runtime/remote/window.py | 每连接至多 16 未确认帧/1MiB，预留删除控制容量，重传前复查当前 generation 与正文是否仍存在 |
| runtime/remote/api.py、api/app.py、api/local_chat.py | v1 Bearer / v2 Cookie 共用设置服务、no-store、Origin/幂等键；v1/v2 对话 GET/PATCH 与 includeHidden |
| runtime/remote/link.py、security.py | 解绑清理回调仍在原事务；沿用 DPAPI 凭据保护与安全文本过滤，同时不再误删仅谈论“token”的普通正文 |
| storage/remote.py | 复用原 Inbox/Outbox/seq/ACK/witness，支持修订 2 与无正文退休记录；存储回退隔离覆盖修订 2 的执行预留 |

**只追加 migration 7**，migrations 1–6 原样保留。新增九张表：

| 表 | 持久事实 |
| --- | --- |
| remote2_routes | `(worker_id,store_id,public_id)` 到 local_id；反向唯一，防止同一公开 ID 或本机 ID 换绑 |
| remote2_delivery | 规范化摘要、原命令、期限、waiting/provisional/accepted/最终状态、received/result/grant；独立 execution_json 只保留执行所需引用 |
| remote2_order | 每 worker/store/public conversation 的远程序号槽与 consumed 标记 |
| remote2_gates | LocalRun 的 provisional/granted/rejected/recovery 门闩 |
| remote_sync_changes | conversation/message/run/approval 的事务内变更 journal 和单调高水位 |
| remote_sync_items | 历史或增量暂存、完整文本、分段位置、UTF-8 字节偏移、整条 hash/字节数 |
| remote_sync_versions | 每 store/generation/资源的 revision 与摘要 |
| remote_sync_deletions | 本机稳定对话 ID 的删除 tombstone；当前没有对外删除入口 |
| remote_sync_redactions | 删除事件引用及原 seq/eventId/hash 的独立删除证明 |

源表触发器与原写入同事务产生 journal；运行触发器只在 status/task_id/error 实际变化时记录。已有 remote_state 保存设置、补传位置、切换水位、skip tombstone；已有 hub_state 仅新增 `local-run-failure:<runId>` 的结构化错误码记录，不增加公共字段。

## 契约落点与关键语义

### §1 / D49：修订隔离与升级

wire.py 使用生成的两个 union；protocolVersion 使用生成常量，修订 1 仍使用生成 Literal。worker.can_upgrade 检查旧 Inbox 最终状态、原执行状态/待投影消息及旧 Outbox。收到服务端 ready 的修订 2 hello_ack 并核实 ACK 后，先持久化 `identity.wireRevision=2` 和 `upgradeFence`，再分配修订 2 事件。

只支持修订 1 的服务端：先尝试 2，按 supportedWireRevisions 回到 1，维持 R1 命令与原回执行为；本机 link 的 lastErrorCode 为 `REMOTE_REVISION_REQUIRED`，设置修改如实返回“服务端不支持同步”。支持 2 但升级栅栏暂未解除时，先以 1 对账并每 30 秒在本机排空后重试升级。已持久切换到 2 后不降级改写记录。重传保留原事件 epoch 与摘要。

### §2 / D48：电脑写入、Session 与元数据

authority 保留来源值，原 assert_local_authority 调用点改为只检查对话存在。本机对 remote 对话的消息、控制、Task / Session 引用入口不再仅因来源拒绝。

远程 submit 校验公开路由 ID、localConversationId、workspace/scene/version，在本机已有对话中使用原 enqueue；sessionMode=continue 仍经过原精确角色/模型/Session 匹配。无法续接时，直接保存并回报结构化 `SESSION_NOT_RESUMABLE`；不从错误文字推断，也不自动新建上下文。恢复项不能被跳过后偷偷续接更早 Session。

conversation.create/update 在 grant 事务内创建/修改本机元数据，update 使用原 expectedVersion 和至少一个修改项规则；同步 upsert 回报实际值，completed 使用 `metadata_committed`，不虚构 Run/resultRef。三种 visibility 均完整上传；本机列表只默认隐藏 mobile_only，includeHidden=true 可找回。Supervisor 使用 include_hidden=True，显示隐藏不影响调度。

### §5：忙碌快照与防卡死

busy.py 从 local_runs 的 queued/running/waiting_approval（以及待核对的 paused 记录）读取候选；有 task_id 时由 TaskService.activity_observation 结合真实 Task 状态、`task_spec:<id>` 的 recoveryRequired / unresolvedCancellation、当前执行句柄和派发期观察判断。缺证据或遗留 running 无句柄进入恢复提醒；不读报错文本，不把旧 running 标签直接当锁。

无 Task 的真正 queued 预留计入忙碌；未证实的 running 无活跃 LocalChat job 进入恢复。连接建立后先 delivery.recover / busy.reconcile，再发送当前连接完整集合；空集合显式发一片，超过 100 ID 使用同一 snapshotId 分片。集合变化重发完整集合，服务端不得累积 IDs。

本机 enqueue 与远程 provisional 入队都在同一本机 SQLite 写事务检查 busy 并排序，先到者取得 queued 槽，后到者 BUSY。取消不依赖 busy。无 grant 过期、本机取消、解绑、撤销和重启未确认都会释放预留。恢复提醒不占忙碌，不阻挡后续显式新上下文。用户本机明确恢复原 Task 后，监督器重新跟踪原 LocalRun 的终态与回复；不会因残留 recovery 门闩丢失结果。

### §6：grant 状态机

```text
首次命令
  ├─ 期限/目标/策略不合法 → rejected + consumed 拒绝槽
  ├─ 前序槽未齐 → waiting（不产生可执行轮次）
  └─ 期限与顺序合法 → provisional + queued LocalRun + closed gate
                         ├─ ACK → 仅确认日志，无执行权
                         ├─ 到期/本机取消/重启未证实 → rejected + 释放预留
                         └─ 显式 matching grant → 同事务 accepted + opened gate
                                                     └─ 原内核 / 后台控制 → 真实结果
```

命令、摘要、Inbox、顺序槽、原生 LocalRun 入队、接单回执和 Outbox 共用事务。grant 核对 commandId、store、路由、commandDigest、receivedEventId、deliverBy、grantedAt，重新读取元数据版本、实际 pending 审批/到期时间与策略。任何首次过期命令或迟到新 grant 均不入执行内核。

已执行命令/许可重放返回原结果，不重新检查期限并伪造“未执行过期”。同 ID 不同内容单独记录拒绝，不覆盖原事实。skip 持久占槽及 tombstone，迟到 submit 不会复活。逐条错误持久 rejected 并消费槽，连接继续处理后续合法命令。正式接单提交后释放接单锁，控制执行复用按 run 的后台串行锁；慢 cancel 不挡其它对话接单，接收队列沿用 await put 背压。

### §3 / §4：完整同步与删除覆盖

sync.capture 在事务中捕获 journal 高水位、backfillId/generation 和磁盘暂存内容；sync.pump 每批至多 100 内容事件/1MiB，同时受更严格的未确认帧预算约束。每批有 progress，只有此前批次连续 ACK、暂存耗尽后才发 complete=true；收到 complete 的连续 ACK 才将内部工作阶段置为 synced。高水位后的变更从 journal 增量上传。

消息先按沿用的隐私规则去除凭据/私有推理，再对完整待同步文本计算 SHA256 和 UTF-8 字节数；不做 32K 截断。每段至多 16000 码点/64000 字节，并校验整个序列化帧。以 BLOB 字节偏移读取分段，保留 NUL、CRLF、非 BMP Unicode 和 JSON 转义字符；同一消息更新以完整更高 revision 发送。元数据、运行状态和审批使用生成 DTO；原模型/执行日志保持私有，由事务 journal 产生受限投影。

关闭设置：配置 CAS、version/generation 递增、释放未获准预留、reset 与删除证明同事务。待重传内容被转成无正文记录，原 eventId/seq/digest 不变；ContentRedaction 只覆盖允许的内容类型，不吞接单、grant、控制结果或 busy。已 ACK 但还留在本机 transport event log 的正文副本也清除，原本机消息不删除。远程 Inbox 原正文、暂存副本清理，保留无正文去重与控制引用。发送前再次复核开关、generation 及正文仍存在，关闭后不发送旧正文；重新开启使用更高 generation 重新补传。

证明按最多 100 slot 分批，连续 ACK 后前进；已覆盖证明不阻挡后续证明，直到删除 seq 连续确认后才清理证明。设备撤销/解绑清理本机可重放内容并释放预留，不冒用设备 Bearer 撤销云端、不借浏览器 Cookie、不宣称云端删除已获确认。

### §9 历史审批及安全约束

复用原协调器锁内 current_guard，在真正投递时重读 pending 请求与当前本机策略。git_push/deploy/delete/db_migrate/shell 远程 approve 拒绝，reject 可消费；grant 前尚不投递审批，grant 时也核对真实到期时间。控制结果继续由 CancelResult / CancellationOutcome、结构化恢复/暂停与 orphanProcessIds 推导。没有通过 failed/paused 标签或错误字符串伪造确认。

沿用 TLS Authorization 与 DPAPI（Windows）；非 Windows 的既有目录 0700 / 文件 0600 保护未改。catalog 仍只上报登记的 Workspace/Scene 有界索引，不上报任意目录或模型配置。

## 对现有内核的最小改动

- **runtime/tasks.py**：仅增加 activity_observation 与派发中的观察集合，避免 Adapter 启动 await 期间被误判为“无句柄遗留”。不改变取消、恢复、重试或 Task/Node/Session 语义；缺 state 的最小实例仍证据不可得。
- **runtime/local_chat.py**：透传列表过滤、Supervisor 遍历隐藏对话、拒绝跳过待核对上下文、保存直接捕获的 HubError.code。原 create_task、Session 匹配、TaskService 调用仍是执行入口。
- **storage/local_chat.py**：来源门禁移除；visibility CAS/列表与 busy 观察；原 enqueue 事务检查忙碌；next_run 识别不可调度预留和恢复提醒；状态提交后生成完整 busy；结构化失败码读取。原本机 user/assistant 消息和 LocalRun 表不重建。
- **storage/migrations.py**：仅追加 7；事务 journal 避免修改大量内核事件生产点，兼容已有数据，既有 v5 专项测试保持原授权版本定位。
- **api/app.py / api/local_chat.py**：复用既有鉴权和服务，只补 frozen v1 GET/PATCH 与两版本设置/可见性参数。
- **runtime/composition.py**：本轮无需修改，沿已有 app / Worker 组合接线。

## 测试、旧断言变更与实际输出

新增五个测试文件共 **39 项**，原 285 项数量保留，最终合计 324 项：

| 测试文件 | 主要覆盖 |
| --- | --- |
| test_r15_worker.py | 手机复用电脑原 Session；手机创建后电脑可写；ACK 不授予许可；重复命令/许可不重复执行；首次过期、坏摘要/receipt、无 grant 到期、迟到 grant、本机取消释放预留；双向 BUSY 先到者优先；慢 cancel 期间其它对话及时接单 |
| test_r15_recovery.py | 保留运行中持久状态模拟崩溃后重建 System；provisional 与 granted 分支；恢复快照排除待核对项；本机明确恢复后原轮次完成；重连空集合覆盖旧集合；rev1-only 真实回退；旧事件原 bytes/epoch 保留、升级栅栏、禁止降级；服务端栅栏解除后无需重启；乱序/skip/迟到重放 |
| test_r15_sync.py | 暂停 ACK 时未确认窗口有界；多批历史/完成标记；超 32K 的 Unicode/NUL/CRLF 全文分段与 hash；增量 revision；reset 原 hash 删除证明、关闭无旧正文、重开新 generation；预留释放；设备撤销清理；响应/事件/日志凭据隔离 |
| test_r15_local_api.py | 真实 local-session Cookie、v1 Bearer 隔离、401/Origin/幂等键/CAS/no-store、仅三个设置字段、三档可见性和 includeHidden、pc_only 仍完整同步、解绑后本机发送正常 |
| test_r15_delivery_guards.py | 时钟跳变/睡眠/重启、元数据接单前竞争、坏目标拒绝回执重放且后续命令执行、高风险 approve / reject、received 后策略变化、真实审批过期、Session 不可恢复错误码、101 ID 快照分片 |

假服务端按协商修订对每个实际收发帧使用生成 union 校验，并检查连续覆盖、重传原字节、完整分段字节数/hash、删除证明和完整 busy 替换；新本机响应使用生成视图/Envelope 校验。未连外网，没有 pytest 并行 worker。

### D48 推翻的旧断言（逐项）

仅以下两个既有测试按授权更新，其它既有业务断言未放宽或删除：

1. `test_remote_worker.py::test_remote_authority_is_persistent_and_all_execution_writes_reject` 改名为 `test_remote_authority_is_persistent_but_local_execution_writes_are_allowed`。
   - 原 pause/resume/retry/cancel/append_instruction 均断言 409 / CONVERSATION_AUTHORITY_MISMATCH；现断言 202，并等待 resume/retry/append 的真实终态。
   - 原直接 Task retry 断言 AUTHORITY_MISMATCH；现断言 200，等待新 Task succeeded。
   - 原 Session resume 断言 AUTHORITY_MISMATCH；现断言 200，核对 Adapter 使用原 Session ID。
   - 原解绑后往 remote 对话发消息断言 AUTHORITY_MISMATCH；现断言 202。
   - authority 解绑后仍为 remote、本机创建为 local、原 local 发送 202 的断言保留。依据 D48 / 契约 §2。
2. `test_remote_guards.py::test_remote_scene_profile_and_parent_cannot_bypass_authority` 改名为 `test_remote_scene_profile_and_parent_remain_usable_from_local_computer`。
   - 原 parentTaskId / local-profile 引用创建均断言 409 / AUTHORITY_MISMATCH，且 Adapter 总启动数仍为 1；现使用有效已登记 profile + workflowRoles、两个独立幂等键，分别断言 200 与 succeeded，启动数为 3。
   - 请求补齐真实执行所需配置，因为这些请求现在到达内核，不能继续使用原“执行前已拦截”的简化 fixture。依据 D48 / 契约 §2。

没有修改旧离线/排队断言使其在修订 2 偷偷执行：旧 R1 测试明确仍连接修订 1，验证已受理历史命令按 D48 保留真实执行/对账。新浏览器离线立即失败属于 P1；Worker 的修订 2 不具备无 grant 放行路径。

### `reject_revisions=[2]` 改为 `[3]` 的单独说明

`test_unsupported_wire_revision_freezes_without_reconnect_storm` 原意是：只有修订 1 的 Worker 遇到没有共同修订号的服务端后冻结、停止重连风暴。原参数 `[2]` 在 R1 中表示不支持；现 Worker 已支持 `[1,2]`，所以把无共同修订集合改为 `[3]`，原冻结状态、错误码、连接次数与无错误断言均保留。

这不替代 rev1-only 兼容测试。新增 `test_rev1_only_server_falls_back_reports_no_sync_and_executes_original_protocol` 真正验证服务端仅支持 1：请求修订依次 `[2,1]`，仍能执行旧命令，全部上行帧为 1，没有 sync.*，link 显示 `REMOTE_REVISION_REQUIRED`，设置写入返回该错误。另有完整升级/禁止降级/服务端延后升级测试。依据 D47/D49 与契约 §1，不是通过改参数绕开回退要求。

### 最终 Hub 全量输出

cwd：`E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/apps/hub`。Windows 沙箱默认 TEMP 会 WinError 5，本轮显式将 TEMP、TMP、basetemp 全部放入 worktree 内 git 忽略的 `.tmp`：

```powershell
$env:TEMP = 'E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP = $env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r15-acceptance 2>&1 | Tee-Object -FilePath ../../.tmp/r15-hub-acceptance.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 22%]
........................................................................ [ 44%]
........................................................................ [ 66%]
........................................................................ [ 88%]
....................................                                     [100%]
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
324 passed, 4 warnings in 144.41s (0:02:24)
```

退出码 0。4 条均为既有依赖的弃用提示，没有放宽断言来消除它们。中途检查发现的恢复后结果跟踪问题，先新增测试复现失败，再修门闩并重跑此最终全量；不以修复前的全量结果代替。

### 协议生成物验证输出

cwd：worktree 根目录，TEMP/TMP 同上；将已有 `.venv/Scripts` 加到该进程 PATH，不安装依赖：

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv/Scripts') + ';' + $env:PATH
pwsh scripts/protocol/validate.ps1 -CheckGenerated 2>&1 | Tee-Object -FilePath .tmp/r15-protocol-validation.log
exit $LASTEXITCODE
```

```text
协议校验通过：321 个类型，173 个 Contract Fixture
```

退出码 0。`git diff --check` 与 `git diff --cached --check` 无输出。实际完整日志保留在忽略目录 `.tmp/r15-hub-acceptance.log`、`.tmp/r15-protocol-validation.log`，上文为命令真实输出。

## 给 P1 与前端的接线事项

1. Worker 初始会尝试修订 2；P1 有旧未决命令时应坚持升级栅栏，不能仅因本次 Outbox 为空就 ready。双方均保留旧 hash/epoch；新 Worker 不会降级改写修订 2 记录。
2. 下行 public conversationId 与 localConversationId 不可互换；submit 只绑定已存在本机对话，手机新建先发 conversation.create，等待 metadata_committed 与 upsert。sessionMode=continue 使用原本机 Session。
3. `command.received` 只代表不可调度预留。P1 只有显式、持久 delivery_granted 才授予执行；连续 events_ack 不授予执行。超时/重启拒绝仍消费日志 seq；本机取消可使后续 grant 拒绝。
4. busy 必须按当前 connection/epoch 的最新完整 snapshot 整体替换，空集合必须清空旧状态；恢复提醒不是锁。控制不受 busy 门禁，新 submit 遵守电脑最终 BUSY 判定。
5. P1 先拼齐并校验分段全文再展示；reset 可先持久删除，再用原 hash 的 ContentRedaction 补齐连续确认。不能把证明当普通 omitted 或重写原事件。
6. 电脑端设置用共享 v1 Bearer / v2 Cookie GET/PUT，CAS expectedVersion 与 Idempotency-Key；成功只表示本机配置持久化，不意味着离线服务端已删除。不要读取不存在的公开 syncStatus 字段。
7. 电脑端去掉 authority 只读假设；默认过滤 mobile_only，用 includeHidden 找回并 PATCH visibility。三档都上传全文，pc_only 的远端显示过滤由 P1 负责。

## 提交

- `606852a`：delivery grants、忙碌/恢复观察、顺序门闩与持久存储。
- `f3f11b6`：完整同步、发送窗口、reset/清理、修订协商与本机 API。
- `0771e0b`：39 项新测试、D48 授权断言调整与假服务端兼容。
- 本回执单独提交。

每次提交后均执行 `git log -1 --format=%B` 自查；提交信息仅描述改动，无署名或生成标记。本轮无 0xC0000142 或额度错误。
