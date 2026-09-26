---
wp: R1-P2
status: done
scope_declared: [apps/hub/runtime/remote/**, apps/hub/storage/remote*.py, apps/hub/storage/migrations.py, apps/hub/runtime/local_chat.py, apps/hub/runtime/tasks.py, apps/hub/storage/local_chat.py, apps/hub/api/local_chat.py, apps/hub/api/app.py, apps/hub/runtime/composition.py, apps/hub/tests/**, .hqagent/handoffs/R1-P2-remote-worker.md]
scope_touched: [apps/hub/runtime/remote/__init__.py, apps/hub/runtime/remote/api.py, apps/hub/runtime/remote/commands.py, apps/hub/runtime/remote/link.py, apps/hub/runtime/remote/projection.py, apps/hub/runtime/remote/security.py, apps/hub/runtime/remote/wire.py, apps/hub/runtime/remote/worker.py, apps/hub/storage/remote.py, apps/hub/storage/migrations.py, apps/hub/storage/local_chat.py, apps/hub/runtime/local_chat.py, apps/hub/runtime/tasks.py, apps/hub/runtime/composition.py, apps/hub/api/app.py, apps/hub/tests/test_custom_scenes.py, apps/hub/tests/remote_support.py, apps/hub/tests/test_remote_worker.py, apps/hub/tests/test_remote_controls.py, apps/hub/tests/test_remote_faults.py, apps/hub/tests/test_remote_guards.py, apps/hub/tests/test_remote_admission.py, apps/hub/tests/test_remote_dispatch.py, apps/hub/tests/fixtures/remote/test-cert.pem, apps/hub/tests/fixtures/remote/test-key.pem, .hqagent/handoffs/R1-P2-remote-worker.md]
build: pass
tests: pass
commit: 4df001826073e83b1459316213bab5798add9eed
open_questions: 0
---

# R1-P2 Worker 交付回执

工作目录 `E:/OtherPro/HQAgent-Hub-worktrees/remote-worker`，分支 `feat/remote-worker`，协议基线 `8268c5c8be7ed5411f82a9fa6c126facb05e2978`。头部 commit 是最终实现与测试提交；本回执单独提交以避免自引用。未合并、推送或部署。**未与真实服务端联调**。

远程层负责设备连接、持久接单和事实投影，所有执行仍进入原 LocalChatService、TaskService、WorkflowRuntime 与 Adapter。没有云端模型调用、模型凭据上传、执行内核迁移、Attempt 或长期 Task。

## 第 0 步与审核修复

先按主题提交主代理已验证的现状，没有回滚：`199382e`、`577647b`。这两笔提交正文均注明“验证结果见主代理复跑”；来源是本轮用户提供的 Hub 257 passed、前端 typecheck/201 passed、协议 258 类型/109 Fixture 通过。

### G1：逐条坏命令持久拒绝

`runtime/remote/commands.py` 将接单抽为 `_admit()`。逐条命令错误导致原接单事务完整回滚，然后 `_record_rejection()` **另开事务**保存 rejected Inbox、拒绝事件/Outbox 和排序占位，返回 `command.rejected`，不向 consume 抛出业务错误。

- 处理 `_bind_conversation` 的目标/authority 错误、`_slot` 冲突、撤回目标不匹配和非法日历时间等。
- 拒绝按当前 worker/store、规范化请求 hash 缓存；相同输入重投返回同一 eventId、seq、epoch、时间和错误码，普通重启和 Outbox 裁剪后仍保持。
- 若 commandId 已接单，冲突副本有独立拒绝缓存，不能覆盖原 Inbox/接单回执。
- 被拒 submit 仍消费其 conversationSeq；已有合法槽不可覆盖。同一 ID 的冲突副本若使用另一个空序号，则在 remote_state 保存独立拒绝槽，保留原真实槽的同时避免新缺口。
- 尚未合法绑定的目标只保存拒绝槽/游标，不把 local 或其它世代对话改成 remote；后续合法绑定继承已消费的拒绝序号。
- store/epoch/link 状态、凭据反射、线路修订、事件确认或持久性等连接/世代故障仍断开或冻结。

对应 `tests/test_remote_admission.py`：6 类坏命令后正常命令在同一 WSS 执行；拒绝回执重放；失败事务 ROLLBACK 后独立 BEGIN/COMMIT；ack/重启后原回执；冲突 ID 不覆盖原接单；冲突副本新序号占位；已缓冲的后续消息被拒绝槽释放。原 store 不匹配冻结用例保留。

### G2：接单与执行分离

`receive()` 不再 await `_execute()`；全局锁仅覆盖接单、持久提交和后台任务登记，回执立即返回。控制执行在后台，只通过 `_finish` / `_completed` / `_failed` 的持久事件报告结果。

- `_execute_serialized()` 按 runId 加锁，同 run 按接单顺序执行；不同 run 和新消息接单不相互等待。
- 每个 store/worker/commandId 至多一个正在执行的后台任务。重复接单/recover 不会再启动一个；结束后清理任务计数和 run 锁。
- 连接结束会收尾后台控制任务，不取消 LocalChat 执行轮次。已进入 executing 但缺结果的控制由 recover 报 unconfirmed；未执行的 admitted 按持久顺序恢复。
- recover 不持全局锁等待执行。此前控制投递未确认时，后续 resume/retry 不能借串行队列绕过本机核对。
- WS 队列仍限 200 条，满时 `await queue.put()` 背压，不因 QueueFull 断线。

对应 `tests/test_remote_dispatch.py`：真实等待数秒的 cancel 期间另一对话立即 accepted、另一 run 的 cancel 完成、同 run 后续控制等待；重复投递/recover 不重复启动；重连后未知控制不重发且不自动 resume；205 条积压命令排空后正常命令执行，连接保持一次。

### G3：暂缓

未实施 seal 提交后唤醒 publish 的优化。仍每 0.2 秒扫描、每 5 秒检查 catalog、每 15 秒重传未确认帧。此项留作后续性能工作，本轮不扩大事件唤醒范围。

## 真实验证与来源

### 本轮最终 Hub 全量

cwd：`apps/hub`；串行，无 pytest 并行 worker。

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/pytest-r1p2-complete --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r1p2-complete-hub-tests.log; exit $LASTEXITCODE
```

```text
........................................................................ [ 26%]
........................................................................ [ 53%]
........................................................................ [ 80%]
......................................................                   [100%]
270 passed, 4 warnings in 83.30s (0:01:23)
```

原 199 项全部保留，本包新增 71 项，其中本轮审核修复新增 13 项。4 个 warning 是既有 Starlette/httpx 和 websockets 弃用提示。TEMP、TMP、--basetemp 均在 worktree 内被 git 忽略的 `.tmp`，避开默认 pytest 临时目录的 WinError 5。

完整输出：[r1p2-complete-hub-tests.log](../../.tmp/r1p2-complete-hub-tests.log)。日志为本机忽略文件，未越权提交其它路径。

### 本轮最终协议校验

cwd：worktree 根。

```powershell
$env:PATH=(Join-Path (Get-Location) '.venv/Scripts') + ';' + $env:PATH
$env:TEMP=(Resolve-Path .tmp).Path
$env:TMP=$env:TEMP
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated 2>&1 | Tee-Object -FilePath .tmp/r1p2-complete-protocol-validation.log; exit $LASTEXITCODE
```

```text
协议校验通过：258 个类型，109 个 Contract Fixture
```

退出码 0。输出：[r1p2-complete-protocol-validation.log](../../.tmp/r1p2-complete-protocol-validation.log)。没有修改协议源、生成物或增加兼容字段，没有安装依赖。

### 前端来自主代理复跑

本轮按要求**未启动 Vitest，也未启动新的前端检查进程**。使用主代理复跑并由用户提供的结果：

```text
typecheck 通过
201 passed
```

本轮仅调整 Hub 与测试。apps/desktop、packages/protocol 相对协议基线无 diff。不把主代理的结果冒充本轮亲自执行，不虚构前端日志路径或耗时。

### 定向验证与历史失败

- G1：`16 passed, 1 warning in 11.10s`。
- G2 首次组合为 11 passed / 1 failed：假服务端主动关闭 WSS 后仍发送 ack，Starlette 抛 WebSocketDisconnected。夹具显式处理此传输关闭异常，未隐藏 DTO 校验或执行断言。
- G2 修正夹具后：`12 passed, 1 warning in 16.22s`。
- 最后拒绝槽补充的 G1/G2：`13 passed, 1 warning in 18.34s`。
- 补充前全量 269 passed；最终源码全量为上面的 270 passed。

前两轮曾因 0xC0000142 按要求停工；本轮未遇到。没有并行测试、网络安装或真实模型调用。

## Q1、原回归与范围

Q1 已按裁决落实：test_custom_scenes.py 仅把 `upgraded.initialize()` 改为 `upgraded.initialize(target_version=5)`，`assert upgraded.schema_version == 5` 和全部数据保留断言不变。新增测试覆盖 v5 → 最新迁移、旧数据保留、remote 表可用、缺省 authority=local。

原 6 项最小 TaskService 实例回归已修复：缺少 state 或持久 spec 时返回 `evidenceAvailable=False`；观察代码不阻断原取消语义，远程 Mapper 判 unconfirmed，没有 pytest 专用分支。原取消生命周期测试未改。

本轮只按新语义调整本包自新增测试：逐条目标错误断言相同错误码的 rejected 回执而非异常，后台撤回等待实际持久结果后保留原断言。相对协议基线，原测试文件的修改仍只有获准的一行。

`git diff --check` 通过。相对 `8268c5c`，packages/protocol、apps/desktop、apps/server、docs、scripts/protocol 无 diff。迁移 1–5 原文前缀比较输出：

```text
Migrations 1-5 unchanged
```

## 模块与表结构

仅追加 migration 6，旧迁移未改。

| 表 | 用途 |
| --- | --- |
| remote_state | store/epoch/ack/分配高水位/覆盖游标、见证版本、link 世代/重试意图、策略/catalog 修订、拒绝缓存及补充拒绝槽/游标 |
| remote_inbox | worker+command 去重、规范化 hash、原命令、接单回执、Run 引用与执行前观测 |
| remote_slots | submit/skip/撤回/拒绝的对话有序槽，原槽不可覆盖 |
| remote_conversations | 固定 worker/store/Workspace/Scene 目标与已消费序号 |
| remote_outbox | store+seq、eventId、原始 frame/hash，确认后裁剪 |
| remote_operations | 配对/取消/解绑的幂等键与操作世代 |
| remote_projections | Run、消息、审批投影 hash |

authority 保存在既有 LocalConversation.payload_json；旧记录缺省 local，远程新建明确 remote，解绑不降级。

## 契约规则落点

| 规则 | 文件/入口 |
| --- | --- |
| 四个 v1 remote 操作、统一生成 DTO Mapper | runtime/remote/api.py、link.py、storage/remote.py 的 view/set_view |
| Bearer/Host/Origin、提交后 remote.link.changed | api/app.py 原中间件；storage/remote.py 复用 EventStore.after_commit |
| origin/host/port 校验、规范化、开发例外 | runtime/remote/security.py，例外仅 Worker 配置可开启 |
| 256-bit secret、DPAPI/文件权限、解绑删除 | security.py 的 CredentialVault，link.py 的操作事务与世代 |
| 服务端撤销未确认，不借 owner 权限 | link.py 的 unlink，返回 REMOTE_AUTH_REQUIRED |
| WSS/hello/心跳/退避/修订 | worker.py、wire.py；生成 PROTOCOL_VERSION 与 Literal[1] |
| Inbox/slot/LocalRun/accepted/Outbox 同事务 | commands.py、storage/remote.py、storage/local_chat.py 的事务入队 |
| 去重、顺序、撤回、逐条持久拒绝 | commands.py 的 _admit/_withdraw/_drain/_record_rejection |
| 专用内部消费、authority 防绕过 | runtime/local_chat.py、storage/local_chat.py、api/app.py，包含 Task/Session/父 Task/Profile |
| D41 结构化控制证据 | runtime/tasks.py 的 control_observation、commands.py 的 control_result |
| seq/ack/原 epoch/hash 重传/omitted | storage/remote.py、projection.py、worker.py |
| pending 审批与当前策略、未知消费不重放 | commands.py 的锁内 current_guard，runtime/tasks.py 的 ApprovalService |
| 有界登记目录与场景索引 | projection.py，仅 Workspace/Scene 摘要 |

## 既有内核的最小改动

- storage/local_chat.py 复用原 enqueue SQL/约束，增加调用方事务参数与 authority/引用链检查，没有新增执行身份。
- runtime/local_chat.py 增加本机写检查、内部控制入口、提交后唤醒、恢复派发检查，仍由原 supervisor/_execute 每轮创建 Task。
- runtime/tasks.py 观察式保存真实 CancellationOutcome/CancelResult、orphan PID、节点边界暂停与恢复证据；无 state 不影响原动作。增加审批锁内回调及派发前更新见证的可选提交观察器，没有修改 _create_child/_reset_node 语义。
- api/app.py、runtime/composition.py 装配生命周期与既有 ports，并检查 Task/Session/父 Task/内部 Profile 归属。api/local_chat.py 未改。
- 新远程类型不进入旧 Adapter 固定事件映射；Adapter、orchestrator、security 内核目录未改。

## 设计取舍、限制与未做事项

1. 默认凭据在 `%LOCALAPPDATA%\HQAgent-Hub\remote\`，沿用 HubPaths 数据目录覆盖。Windows DPAPI 已实测；非 Windows 至少目录 0700、文件 0600，未做跨平台实机验收。测试证书/密钥是专用 TLS fixture，不是设备 secret。
2. 生产使用 HTTPS/WSS；仅 Worker 的 `HQAGENT_REMOTE_DEVELOPMENT=1` 允许 loopback HTTP，请求不能开启，重连/轮询也重新校验。HTTP/WSS 不自动重定向，设备凭据仅用于 Authorization，不借浏览器 Cookie 或 Hub Token。
3. store.witness 独立于 hub.db 备份，在接单和新 Task 提交前更新。恢复旧库/无法证明连续性时换 store、清 ack、冻结并暂停恢复的远程队列；测试覆盖断网执行后的旧库恢复不重放。正常恢复应停止 Hub；整个文件系统连同见证一起回滚时仍需要服务端观测和运营核对，不宣称单机可独立证明未执行。
4. Adapter refused、recovery、orphan、消费不明优先于状态标签。仅有终态标签而没有停止证据时保持 unconfirmed；ALREADY_FINISHED 从真实取消回执确认，不解析 reason/error 文本。
5. 远程 retry 对终态 Run 复用 _create_child，resultRef 返回新 Run/Task 和 parentExecutionTaskId；非终态节点重置返回策略拒绝，保留本机 _reset_node。有未核实副作用时不允许远程 resume/retry 清掉旧证据。
6. git_push/deploy/delete/db_migrate、generic shell、本机策略禁止项不能远程 approve；reject 可以。审批在原锁内重读真实请求/当前策略，未知消费不重批。高风险本机审批仍走原本机能力，不新增 R5/签名入口。
7. 不直接上传原生日志、环境变量、认证内容或私有思考，只投影白名单事实及脱敏消息。私有事件（包括短码）用 omitted，远程关键状态/审批不被 omitted 掩盖。未完成的执行引用绑定先等待。
8. 超长答案完整留本机，远程发布明确 system 上限提示，真实终态仍发布，不静默截断或伪造失败。超界 catalog 报错，不上传部分索引。
9. G3 的发布唤醒优化留作后续，当前仍有 0.2 秒扫描。
10. 未做附件、R3 原生会话、飞书、小程序签名、电脑端 UI、长期 Task/Attempt；未与真实服务端联调。

## P1 与电脑端前端接线

- 使用冻结的 pairing-requests 与 /ws/v2/worker。wireRevision=1 与包版本独立，hello.protocolVersion 取生成常量。
- accepted 是持久接单，不是执行完成。逐条 rejected 可在原连接处理、原回执重放；被拒 submit 仍有顺序占位。同 run 控制串行，不同 run 和新消息可独立接单。
- unknown 控制保持 unconfirmed，重连不会重发可能已消费的原生决定。
- 四个本机 remote API 在 v1，复用桌面 Bearer/Host/Origin；远程浏览器 Cookie 不授予 v1 权限，JSON/事件不提供 Hub Token 或设备 secret。
- GET 与 remote.link.changed 共用 RemoteLinkView。pairCode 只在 pairing；lastConnectedAt=null 表示尚未成功握手；frozen+online 仍不能投递执行命令。
- unlink 后 unpaired.lastErrorCode=REMOTE_AUTH_REQUIRED 表示“本机已解绑、服务端撤销未确认”，不承诺取消运行中的任务。旧 remote 对话仍只读；local 不自动转换、同步或重放历史。

## 本轮提交

```text
199382e 完善远程连接与本机执行证据隔离
577647b 增加远程 Worker 故障与契约集成测试
4c4c35a 持久化逐条命令拒绝并推进拒绝序号槽
dcab012 分离远程命令接单与按轮次串行执行
4df0018 为命令冲突副本保留独立拒绝序号占位
```

每次提交后均运行 `git log -1 --format=%B` 自查，没有署名、Co-Authored-By 或生成工具标记。本回执另作交付记录提交。
