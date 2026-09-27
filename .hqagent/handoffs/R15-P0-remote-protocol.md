---
wp: R15-P0
status: done
scope_declared: [packages/protocol/**, scripts/protocol/**, .hqagent/**]
scope_touched: [".hqagent/DECISIONS.md", ".hqagent/INTERFACES.md", ".hqagent/codex-sessions.md", ".hqagent/handoffs/R15-P0-remote-protocol.md", ".hqagent/reviews/R15-P0-compatibility-review.md", ".hqagent/reviews/R15-P0-error-code-probe.log", ".hqagent/reviews/R15-P0-error-code-probe.py", ".hqagent/reviews/R15-P0-generate.log", ".hqagent/reviews/R15-P0-hub-tests.initial.log", ".hqagent/reviews/R15-P0-hub-tests.log", ".hqagent/reviews/R15-P0-offline-package.log", ".hqagent/reviews/R15-P0-protocol-tests.initial.log", ".hqagent/reviews/R15-P0-protocol-tests.log", ".hqagent/reviews/R15-P0-protocol-validation.log", ".hqagent/reviews/R15-P0-server-tests.log", ".hqagent/reviews/R15-P0-v04-review.md", "packages/protocol/VERSION", "packages/protocol/fixtures/contracts/manifest.json", "packages/protocol/fixtures/contracts/r15.RemoteBrowserConversationDeleted.json", "packages/protocol/fixtures/contracts/r15.RemoteBrowserStoreReset.json", "packages/protocol/fixtures/contracts/r15.RemoteBrowserV2WorkerEvent.json", "packages/protocol/fixtures/contracts/r15.RemoteSyncConversation.json", "packages/protocol/fixtures/contracts/r15.RemoteSyncConversationInput.json", "packages/protocol/fixtures/contracts/r15.RemoteSyncConversationUpdate.json", "packages/protocol/fixtures/contracts/r15.RemoteSyncMessagePage.json", "packages/protocol/fixtures/contracts/r15.RemoteSyncMessageSegment.json", "packages/protocol/fixtures/contracts/r15.RemoteSyncRedactedSlot.json", "packages/protocol/fixtures/contracts/r15.RemoteSyncRunState.json", "packages/protocol/fixtures/contracts/r15.RemoteSyncSettingsInput.json", "packages/protocol/fixtures/contracts/r15.RemoteSyncSettingsView.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ApprovalDecisionCommand.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ApprovalEvent.json", "packages/protocol/fixtures/contracts/r15.RemoteV2BackfillProgress.json", "packages/protocol/fixtures/contracts/r15.RemoteV2BusySnapshot.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CancelCommand.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CatalogEvent.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CommandAccepted.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CommandCompleted.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CommandEnvelope.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CommandFailed.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CommandReceipt.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CommandReceived.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CommandRejected.json", "packages/protocol/fixtures/contracts/r15.RemoteV2CommandWithdrawalCommand.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ContentRedaction.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ControlConfirmed.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ControlObserved.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ControlResult.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ConversationCreateCommand.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ConversationDeleted.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ConversationGap.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ConversationSkip.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ConversationUpdateCommand.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ConversationUpserted.json", "packages/protocol/fixtures/contracts/r15.RemoteV2DeliveryGrant.json", "packages/protocol/fixtures/contracts/r15.RemoteV2EventAck.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ExecutionEvent.json", "packages/protocol/fixtures/contracts/r15.RemoteV2MessageEvent.json", "packages/protocol/fixtures/contracts/r15.RemoteV2MessageSegment.json", "packages/protocol/fixtures/contracts/r15.RemoteV2OmittedEvents.json", "packages/protocol/fixtures/contracts/r15.RemoteV2PauseCommand.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ProgressEvent.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ResumeCommand.json", "packages/protocol/fixtures/contracts/r15.RemoteV2RetryCommand.json", "packages/protocol/fixtures/contracts/r15.RemoteV2RunStateEvent.json", "packages/protocol/fixtures/contracts/r15.RemoteV2RunSubmitCommand.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ServerHeartbeat.json", "packages/protocol/fixtures/contracts/r15.RemoteV2ServerOutboundFrame.json", "packages/protocol/fixtures/contracts/r15.RemoteV2SkipRecorded.json", "packages/protocol/fixtures/contracts/r15.RemoteV2SyncReset.json", "packages/protocol/fixtures/contracts/r15.RemoteV2SyncedRunState.json", "packages/protocol/fixtures/contracts/r15.RemoteV2VisibleWorkerEvent.json", "packages/protocol/fixtures/contracts/r15.RemoteV2WorkerEvent.json", "packages/protocol/fixtures/contracts/r15.RemoteV2WorkerHeartbeat.json", "packages/protocol/fixtures/contracts/r15.RemoteV2WorkerHello.json", "packages/protocol/fixtures/contracts/r15.RemoteV2WorkerHelloAck.json", "packages/protocol/fixtures/contracts/r15.RemoteV2WorkerHelloRejected.json", "packages/protocol/fixtures/contracts/r15.RemoteV2WorkerOutboundFrame.json", "packages/protocol/fixtures/contracts/r15.RemoteWire1ApprovalView.json", "packages/protocol/fixtures/contracts/r15.RemoteWire1Error.json", "packages/protocol/fixtures/contracts/r15.RemoteWire1ErrorCode.json", "packages/protocol/generated/go/protocol.go", "packages/protocol/generated/python/models.py", "packages/protocol/generated/ts/index.ts", "packages/protocol/openapi/local-chat.v2.yaml", "packages/protocol/openapi/local-hub.v1.yaml", "packages/protocol/openapi/remote-hub.v2.yaml", "packages/protocol/registry/error-codes.yaml", "packages/protocol/remote/R1-contract.md", "packages/protocol/remote/R1.5-contract.md", "packages/protocol/schema/local-chat.json", "packages/protocol/schema/remote-sync.json", "packages/protocol/schema/remote.json", "scripts/protocol/generate.py", "scripts/protocol/tests/test_remote_link_browser_contract.py", "scripts/protocol/tests/test_remote_link_contract.py", "scripts/protocol/tests/test_remote_snapshot_contract.py", "scripts/protocol/tests/test_remote_sync_contract.py"]
build: pass
tests: fail (1 failed)
commit: 4e597fb5e88a315a271d39528d43e7846d53aa40
open_questions: 0
---

**9bb608d / bf15428 那一版镜像 + 接力草稿已作废。** 本回执覆盖重写为手机远程接入方案 v0.4，Q1 已按建议 B / D49 解决。

# R15-P0 / 0.7.0 协议冻结回执

状态 done 表示协议定义、生成、验证和交付完成，不表示业务已适配。tests 如实记录服务端 1 项新旧 HTTP 绑定差异，按任务要求交 P1，不改业务代码或断言。头部 commit 为协议冻结提交，登记与本回执另提交。

## 基线与范围

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/remote-protocol`，分支 `feat/remote-protocol`。开工已合入 integration/phase1@`8d2058f43f7bd94028b4d3fd1fd2bac65e6b1992`，merge `2c839b1e402d52e585ab9afd8d4edb5b74145c34`，无冲突。scope_touched 以8d2058f计算，不把授权合并带入文件算成本轮修改。apps/**、docs/** diff为空；未合回integration。

完整阅读方案v0.4 §11；旧mirror/handover/syncExcluded方向未实现。D46原编号保留，D47覆盖作废方案，D48/D49编号未占用，均按指定编号登记。服务端仍只是认证、设备与内容副本/指令通信工具，不调用模型、不保存模型凭据。

## 冻结内容与取舍

1. **修订隔离**：remote-sync.json的RemoteV2*定义和三个顶层union对应CODECS[2]，包含原27类帧的修订2版本及新增同步/门闩控制。没有通过放宽旧wireRevision常量或additionalProperties复用。服务端支持[1,2]，hello包版本仅作诊断。
2. **D49闭包**：新增RemoteWire1ErrorCode/RemoteWire1Error/RemoteWire1ApprovalView，旧27个帧仅替换批准的错误/审批payload引用。枚举固定为0.6.3注册表，包括denialCode在内的旧校验范围不变；HTTP/rev2用公共注册表新增码。110份旧Fixture原样保留。
3. **全文分段**：每片≤16000 Unicode码点、UTF-8≤64000字节、整帧≤256KiB；segmentIndex/Count、messageRevision、messageSequence、字节数和SHA256绑定一版完整文本，拼齐验证后才发布。消息全文无32K截断；配额故障明确失败，不伪装历史补传完成。历史每批≤100事件/1MiB，≤16帧/1MiB未确认窗口，并有高水位、批次和complete标记。
4. **真删除与连续确认**：reset/电脑删除/撤销清理投影、暂存和可重放正文。新增独立ContentRedaction控制，以原eventId/seq/eventSha256登记无正文覆盖；不是修改原事件，也不是普通omitted。仅退役内容可覆盖，接单、grant、控制结果和忙碌快照不能吞掉。proof的generation是删除栅栏代次，允许覆盖旧代次但不越过栅栏。
5. **忙碌不持锁**：电脑重连及每次变化发完整集合，超过100个ID可拆同一快照，拼齐后整体覆盖。服务端离线/重启或新快照未齐时busyFresh=false；新发送可报STATE_NOT_READY，但取消不受busy或fresh约束。recoveryRequired只提醒，不算忙碌。
6. **30秒不误执行**：直接复用“电脑接单即执行”会在accepted丢失时产生假失败，因此新增command.received与delivery_granted。电脑先持久不可调度收件/顺序预留；服务端事务竞争deadline与grant；无grant到期failed，晚到收件不能再grant。电脑持久消费匹配grant才正式接单。ACK不是许可；已grant不因缺回执又被定时器判未送达失败。迟到新grant由电脑拒执行后用真实证据终结。完整时序、重放与时钟规则见契约§6。
7. **两端继续**：authority仅兼容来源，不是本机写门禁。电脑保留原conversation→run→Task→Session；服务器的公开ID按设备/store映射到本机ID，下行localConversationId不能由浏览器指定。远程conversationSeq只作手机命令排序，所有消息顺序由电脑messageSequence决定。
8. **手机创建也由电脑写**：增加conversation.create控制帧，POST /conversations改202回执；否则服务端仍在创建权威对话，违背唯一写入。服务端只能先预留传输ID，电脑同步后产生副本。conversation.update同样无执行seq，expectedVersion校验后以同步元数据及confirmed/metadata_committed回报，不虚构Run。
9. **可见性只影响显示**：both/pc_only/mobile_only都完整同步；手机所有视图/事件过滤pc_only，本机列表默认过滤mobile_only，可includeHidden恢复。同步开关默认true，字段mirrorEnabled只是兼容命名，没有只读镜像含义。
10. **本机入口复用**：同步设置在v1 Bearer和v2 Cookie下提供等价GET/PUT；可见性复用UpdateLocalConversationInput及expectedVersion，补v1 GET/PATCH对话，与v2同一管理器。没有另造角色或模型配置入口。
11. **消息分页**：浏览器用RemoteSyncMessagePage，最新完整消息优先，before独占旧页边界，签名游标绑定设备/store/对话与固定截止点；hasMore=true必须有before。新到消息按messageId/revision合并并按messageSequence排序，不按offset挪页。副本损坏/缺失由电脑补传。
12. **兼容范围**：新HTTP写入要求rev2；rev1仍可连接/对账，但不能承诺不具备的grant机制。旧在途命令不改wireRevision或hash，双向排空/对账及持久切换水位后才切2。没有把旧accepted强行标失败来落实新离线规则。

详细规范：[R1.5-contract.md](../../packages/protocol/remote/R1.5-contract.md)。旧R1-contract明确标为历史基线并链接新规则。字段之外的归属、完整集合、hash/字节数、跨字段期限及事务竞争必须由业务层校验，Schema通过不等于这些业务语义已实现。

## 新增类型清单

共63个新类型，每种各一份Fixture；其中39个修订2具体帧（含不新增seq的redaction控制）。总量258→321类型、110→173 Fixture。

修订1冻结类型（3）：

```text
RemoteWire1ApprovalView
RemoteWire1Error
RemoteWire1ErrorCode
```

修订2具体帧（39）：

```text
RemoteV2ApprovalDecisionCommand
RemoteV2ApprovalEvent
RemoteV2BackfillProgress
RemoteV2BusySnapshot
RemoteV2CancelCommand
RemoteV2CatalogEvent
RemoteV2CommandAccepted
RemoteV2CommandCompleted
RemoteV2CommandFailed
RemoteV2CommandReceived
RemoteV2CommandRejected
RemoteV2CommandWithdrawalCommand
RemoteV2ContentRedaction
RemoteV2ControlObserved
RemoteV2ConversationCreateCommand
RemoteV2ConversationDeleted
RemoteV2ConversationGap
RemoteV2ConversationSkip
RemoteV2ConversationUpdateCommand
RemoteV2ConversationUpserted
RemoteV2DeliveryGrant
RemoteV2EventAck
RemoteV2MessageEvent
RemoteV2MessageSegment
RemoteV2OmittedEvents
RemoteV2PauseCommand
RemoteV2ProgressEvent
RemoteV2ResumeCommand
RemoteV2RetryCommand
RemoteV2RunStateEvent
RemoteV2RunSubmitCommand
RemoteV2ServerHeartbeat
RemoteV2SkipRecorded
RemoteV2SyncReset
RemoteV2SyncedRunState
RemoteV2WorkerHeartbeat
RemoteV2WorkerHello
RemoteV2WorkerHelloAck
RemoteV2WorkerHelloRejected
```

修订2联合与控制值对象（9）：

```text
RemoteV2CommandEnvelope
RemoteV2CommandReceipt
RemoteV2ControlConfirmed
RemoteV2ControlResult
RemoteV2ExecutionEvent
RemoteV2ServerOutboundFrame
RemoteV2VisibleWorkerEvent
RemoteV2WorkerEvent
RemoteV2WorkerOutboundFrame
```

同步载荷、本机及浏览器类型（12）：

```text
RemoteBrowserConversationDeleted
RemoteBrowserStoreReset
RemoteBrowserV2WorkerEvent
RemoteSyncConversation
RemoteSyncConversationInput
RemoteSyncConversationUpdate
RemoteSyncMessagePage
RemoteSyncMessageSegment
RemoteSyncRedactedSlot
RemoteSyncRunState
RemoteSyncSettingsInput
RemoteSyncSettingsView
```

## 错误码

| 新增错误码 | HTTP | retryable | 用途 |
| --- | --- | --- | --- |
| REMOTE_CONVERSATION_BUSY | 409 | true | 电脑已有queued/running/waiting_approval轮次，保留输入 |
| REMOTE_STATE_NOT_READY | 409 | true | 当前连接完整忙碌状态未就绪，不能沿用旧锁 |
| REMOTE_SYNC_CONFLICT | 409 | false | 分段/版本/快照内容冲突，不能发布半条正文 |
| REMOTE_SYNC_DISABLED | 409 | false | 同步关闭、副本已删除，不能对其继续提交 |
| REMOTE_DELIVERY_EXPIRED | 409 | true | 送达期限过且无执行许可；设备离线，发送失败 |
| REMOTE_REVISION_REQUIRED | 409 | false | 写操作要求rev2，不得降级绕过门闩 |
| REMOTE_SYNC_RESOURCE_LIMIT | 413 | false | 全文同步资源配额不足，显式失败、不截断 |

复用REMOTE_DEVICE_OFFLINE，语义改为立即失败不排队；CONVERSATION_AUTHORITY_MISMATCH保留历史/真实归属错误，但“remote本机只读”的语义废止。没有handover专用码。新增码在rev1帧内被拒绝，仅HTTP/rev2接受。

## 生成器与测试调整

- 首次出现需独立Fixture的严格字符串枚举。生成器为x-wire-strict字符串枚举增加model_validate/model_dump接口，内部仍是同一个StrEnum/TypeAdapter，线上仍是裸字符串，不包装对象、不改枚举值域。只有新冻结错误枚举使用该标记。
- 新增test_remote_sync_contract.py，覆盖全部新Fixture、rev1形状及错误闭包、110份旧Fixture不变、新旧错误接受矩阵、双修订互斥、30秒字段、非执行命令不分seq、长Unicode分段、空/分片忙碌集合、本机两种鉴权与includeHidden、HTTP真实引用和分页/创建绑定、删除覆盖范围。
- 加入送达门闩的协议参考状态机，枚举收件、grant、超时、ACK顺序，检查不存在“服务端送达失败且电脑执行”。这是协议模型测试，不冒充P1/P2事务和断网验收。
- FZ-R1.1/1.2/1.3里只针对某个版本“仅改这一个字段/版本号”的静态发布审计改为读取当时冻结SHA `500bf1f`；没有拿它们验证0.7.0范围。对应的**当前**rev1闭包、Fixture、快照与认证校验由新增live测试承担，运行期round-trip和负向验证仍使用当前生成包。否则新增已授权HTTP字段会与“0.6.2文件必须完全一样”的历史审计自相矛盾。业务测试和断言未改。

## 本轮真实验证输出

下述最终结果均在本worktree串行运行，未启动Vitest，未出现0xC0000142。前端验证交主代理。apps/**和docs/**未写入。

根目录将.venv/Scripts放当前进程PATH，执行 `pwsh -NoProfile -File scripts/protocol/generate.ps1`：

```text
protocol 0.7.0: 生成 321 个类型 -> ts / python / go
```

离线重装（未联网）：

```powershell
.venv/Scripts/python.exe -m pip install --no-index --no-build-isolation --force-reinstall --no-deps -e packages/protocol
```

```text
Successfully built hqagent-protocol
Successfully installed hqagent-protocol-0.2.0
```

0.2.0仍是已有Python分发元数据；协议VERSION和三端常量为0.7.0，未顺手更改分发配置。

根目录 `pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated`：

```text
协议校验通过：321 个类型，173 个 Contract Fixture
```

根目录 `.venv/Scripts/python.exe -B -m pytest scripts/protocol/tests -q -p no:cacheprovider --tb=short`：

```text
304 passed in 12.09s
```

apps/hub 目录 `../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --tb=short`：

```text
285 passed, 4 warnings in 79.41s (0:01:19)
```

apps/server 目录同一相对Python/pytest命令：

```text
FAILED tests/test_controls_storage.py::test_http_binding_completeness
1 failed, 110 passed, 1 warning in 29.94s
```

Hub/server的TEMP/TMP/PYTEST_DEBUG_TEMPROOT均位于worktree内 `.venv/r15-*-<随机标识>`；生成校验使用 `.venv/r15-validation`。warning为已有Starlette/httpx与websockets弃用提示。生成、安装、校验、三套最终测试及初次日志在 `.hqagent/reviews/R15-P0-*.log`；只规范末尾换行及pytest错误输出的行末空白，未删改错误或警告内容。

### 失败逐项及归属

**最终仅1项，归P1**：`tests/test_controls_storage.py::test_http_binding_completeness`。现有业务ROUTES与新OpenAPI不符：

- 缺PATCH `/api/v2/conversations/{conversationId}`，实际断言在路由key集合处失败。
- 同一检查继续执行还将发现GET messages旧输出RemoteMessagePage vs新RemoteSyncMessagePage。
- POST conversations旧201 RemoteConversationView vs新202 RemoteQueuedReceipt。

后两项由只读AST提取路由表与OpenAPI比较确认，不另冒报成两个已运行失败测试。P1应实施这些绑定与对应业务，再复跑；本轮没有改apps/server或放宽该断言。

**已修复的首轮失败，非剩余P2缺陷**：Hub最初 `1 failed, 284 passed`，`test_all_frozen_contract_fixtures_validate_and_round_trip` 遇到新字符串枚举没有model_validate。已在协议生成层补严格标量统一接口，最终285全过；未改Hub测试。首轮协议300 passed是补删除覆盖前版本，不能当最终结果，最终为304。

`R15-P0-error-code-probe.log`及其脚本/旧compatibility-review保留为v0.3历史证据，已明确标记作废；脚本仅适用于9bb608d旧基线，不是本轮测试。D49现行为由当前live协议测试验证，不再使用旧“追加码会扩大rev1”的复现结果描述0.7.0。

## 下游实施要点

### P1 服务端

- 新增CODECS[2]并保留1，版本选择只看wireRevision；未知新码不能发送到rev1。双向升级栅栏涵盖旧命令、回执与未确认事件，不把wire.encode覆盖版本当迁移。
- 浏览器提交先查在线，离线不建离线队列；在线建30秒attempt。command.received与deadline计时器在同一事务竞争，grant一旦持久即不因丢accepted撤销。临时断流不能伪造执行状态。
- 同步映射以owner/worker/store/localId分区；pc_only在所有列表、直接ID、审批/运行/快照及事件处过滤，不能仅前端隐藏。创建/修改由电脑同步回报，不直接改权威副本。
- 拼段按messageId/revision验证，完整后发布；分页固定签名cut与before独占边界，最新优先。删除覆盖投影、暂存、可重放正文，保留无正文去重证据，不吞执行许可/控制事实。
- busy只存最新完整快照投影，重连/Server重启先置fresh=false，收齐后整体替换。服务端不持对话锁，不从手机页面生命周期恢复锁。
- 补上述1项失败涉及的三个HTTP绑定差异；完整行为另需断网、崩溃、错序、重复段、删除重传及跨设备集成测试。

### P2 Worker

- 电脑唯一写入：取消本机authority只读拦截，远程submit绑定已有本地对话与原Session；手机/电脑在同一本机事务检查并排序，后到者BUSY，不新增Attempt。
- 忙碌来源：LocalChatRepository.local_runs 的queued/running/waiting_approval，结合TaskService.state.get('task_spec:'+executionTaskId)的实际内核状态与recoveryRequired。不得读错误字符串、浏览器缓存或只看残留running标签；恢复核对项只提醒。重连先恢复核对再发完整空/非空集合，变化就发新集合，不能发累积加锁记录。
- 送达期限：收到时用serverTime+单调时钟/RTT界限保守校验deliverBy；过期首次命令拒绝且不上内核。期限内只持久provisional及不可调度顺序预留，不能提前执行取消/审批或模型；显式grant校验摘要、store和receivedEventId后同事务正式接单。连续ACK绝不放行。无grant到期、本机取消或恢复不明要释放预留，不能永久占忙碌；重复已执行命令返回原事实，不再执行。
- 实施syncGeneration、历史高水位与有界Outbox窗口、完整分段和redaction控制；关闭同步不继续上传旧正文，控制事实仍如实对账。原消息全文与模型上下文留在电脑，不让服务端持有模型凭据。
- 本机v1/v2设置与对话修改复用同一状态和expectedVersion；includeHidden恢复mobile_only。成功改开关只代表本机持久化，离线时提示服务器删除待确认。

### 前端

- D46扫码仅前端，fragment读后清除；登录和预览确认不省略。
- 手机先选电脑，再项目/对话；online不等于允许发送，兼看线路2能力、fresh/恢复状态。离线、BUSY或送达失败保留输入，不自动重复执行；取消不受busy限制。
- 电脑去掉authority只读假设；默认隐藏mobile_only，可“显示已隐藏”修改。显式说明可见性只作显示，完整内容仍同步到服务器。
- 消息首次最新页，before向前；按ID/revision合并，不按offset。半条分段永不显示。收到删除/reset清缓存，不保留可见旧副本。
- 202创建/修改是传输回执，等待电脑同步；不得立即当成新对话/修改已成功。显示传输、控制结果、执行状态三层。

## 交付状态

独立只读复核已登记真实会话身份并复用，见codex-sessions.md和R15-P0-v04-review.md；没有把父session当独立thread。冻结SHA见头部；INTERFACES旧needs-decision段已标作废，并新增“R1.5协议0.7.0已冻结，P1/P2/前端可开工”。本次仅协议可开工，不宣称新功能已实现或部署。

提交信息只描述改动，每次提交后执行git log -1 --format=%B自查，无署名、Co-Authored-By或生成工具标记。工作保持在feat/remote-protocol，不合并回integration。
