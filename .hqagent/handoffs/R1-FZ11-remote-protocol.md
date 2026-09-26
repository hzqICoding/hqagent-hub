---
wp: R1-FZ11
status: done
scope_declared: [packages/protocol/**, scripts/protocol/**, .hqagent/**]
scope_touched: [".hqagent/DECISIONS.md", ".hqagent/INTERFACES.md", ".hqagent/handoffs/R1-FZ11-remote-protocol.md", ".hqagent/reviews/R1-FZ11-desktop-tests.log", ".hqagent/reviews/R1-FZ11-desktop-typecheck.log", ".hqagent/reviews/R1-FZ11-hub-tests.log", ".hqagent/reviews/R1-FZ11-protocol-tests.log", ".hqagent/reviews/R1-FZ11-protocol-validation.log", "packages/protocol/VERSION", "packages/protocol/events/event-dictionary.md", "packages/protocol/fixtures/contracts/local-conversation.remote-authority.json", "packages/protocol/fixtures/contracts/manifest.json", "packages/protocol/fixtures/contracts/remote-link.RemoteLinkFrozenView.json", "packages/protocol/fixtures/contracts/remote-link.RemoteLinkPairedView.json", "packages/protocol/fixtures/contracts/remote-link.RemoteLinkPairingInput.json", "packages/protocol/fixtures/contracts/remote-link.RemoteLinkPairingView.json", "packages/protocol/fixtures/contracts/remote-link.RemoteLinkRevokedView.json", "packages/protocol/fixtures/contracts/remote-link.RemoteLinkUnpairedView.json", "packages/protocol/fixtures/contracts/remote-link.RemoteLinkView.json", "packages/protocol/fixtures/contracts/remote-link.changed-event.json", "packages/protocol/fixtures/contracts/remote.RemoteApprovalDecisionCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteApprovalEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteBrowserEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteBrowserWorkerEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteCancelCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteCatalogEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandAccepted.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandCompleted.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandEnvelope.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandFailed.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandReceipt.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandRejected.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandWithdrawalCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteControlObserved.json", "packages/protocol/fixtures/contracts/remote.RemoteConversationGap.json", "packages/protocol/fixtures/contracts/remote.RemoteConversationSkip.json", "packages/protocol/fixtures/contracts/remote.RemoteEventAck.json", "packages/protocol/fixtures/contracts/remote.RemoteMessageEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteOmittedEvents.json", "packages/protocol/fixtures/contracts/remote.RemotePauseCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteProgressEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteResumeCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteRetryCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteRunStateEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteRunSubmitCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteServerHeartbeat.json", "packages/protocol/fixtures/contracts/remote.RemoteServerOutboundFrame.json", "packages/protocol/fixtures/contracts/remote.RemoteSkipRecorded.json", "packages/protocol/fixtures/contracts/remote.RemoteVisibleWorkerEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerHeartbeat.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerHello.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerHelloAck.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerHelloRejected.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerOutboundFrame.json", "packages/protocol/generated/go/protocol.go", "packages/protocol/generated/python/models.py", "packages/protocol/generated/ts/index.ts", "packages/protocol/openapi/local-hub.v1.yaml", "packages/protocol/registry/error-codes.yaml", "packages/protocol/remote/R1-contract.md", "packages/protocol/schema/local-chat.json", "packages/protocol/schema/remote-link.json", "packages/protocol/schema/remote.json", "scripts/protocol/generate.py", "scripts/protocol/tests/test_remote_link_contract.py"]
build: pass
tests: pass
commit: 7bfbe953df9cbdfca74cee81e9db6632db69f8d2
open_questions: 2
---

# FZ-R1.1 / 0.6.1 交付回执

基线 `872a909`，工作区 `E:/OtherPro/HQAgent-Hub-worktrees/remote-protocol`，分支 `feat/remote-protocol`。头部 commit 为契约、生成器、测试及 D42/D43 的冻结提交；登记、日志及回执另提交，避免 SHA 自引用。未合并 integration/phase1。

本轮从磁盘草稿继续，仅补前端验证和交付记录，未再修改协议源文件。上一轮内存不足导致的 0xC0000142 发生在启动前端验证前；本轮最小命令及前端验证成功。没有把环境问题当成业务缺陷修改。

## 新增类型

| 类型 | 内容与取舍 |
| --- | --- |
| RemoteLinkUnpairedView | 无绑定；serverOrigin 可省略或保留非敏感偏好；lastErrorCode 可表达服务端撤销未确认 |
| RemoteLinkPairingView | 真实 serverOrigin/deviceName/pairRequestId/pairCode/expiresAt；没有取得挑战时不伪造短码 |
| RemoteLinkPairedView | workerId/deviceName、online/connecting/offline、lastConnectedAt；从未连通时 lastConnectedAt 明确为 null |
| RemoteLinkRevokedView | connectionStatus 固定 offline，保留原绑定识别信息 |
| RemoteLinkFrozenView | 保留真实连接状态；socket 在线不等于可以投递命令 |
| RemoteLinkView | 以上五个对象的严格联合，避免状态字段混用 |
| RemoteLinkPairingInput | serverOrigin/deviceName，不接受设备凭据或 Hub Token |

7 个新类型各有 Fixture，另增 remote.link.changed 的 HubEvent Fixture、authority=remote 的 LocalConversationView Fixture。总计 258 类型 / 109 Fixture，比 0.6.0 新增 7 类型、9 Fixture。

## 变更与理由

- D42/D43 编号未占用，已按原编号登记 DECISIONS.md。只实施两个裁决，没有增加 Attempt、retryOfRunId 或模型凭据字段。
- 27 个具体 Worker 帧改为整数 wireRevision=1，联合与嵌套 Fixture 同步更新。hello 的 protocolVersion 仅接受合法 semver 作诊断；helloAck 回显修订；helloRejected 统一必填 supportedWireRevisions，使所有拒绝形状一致，REMOTE_PROTOCOL_UNSUPPORTED 不会漏报列表。
- 严格帧中增加可选字段也会被旧端拒绝，任何帧结构变化开新修订。升级窗口支持 N/N-1，初始仅支持 [1]。包版本升级与线路修订分离。
- LocalConversationView 只增可选 authority=local/remote，不注入序列化默认值，消费者将缺省视为 local，兼容既有手写对象和 round-trip。持久的 remote 标记不能因此降级。
- 本机新增 GET /api/v1/remote/link、POST/DELETE /api/v1/remote/pairing、POST /api/v1/remote/unlink，沿用 v1 Bearer、Host/Origin、Envelope 与写操作 Idempotency-Key。WS 使用既有 Ticket，remote.link.changed 的 payload 为同一 RemoteLinkView；该事件是本机 HubEvent，不是 Worker 线路帧，不改 Adapter 的固定事件映射。
- HTTPS origin 默认允许；仅 Worker 明确开启开发模式时允许 HTTP 127.0.0.1/localhost。Schema 排除 userinfo、非根路径、query、fragment 和非法端口。P2 仍须 URL 解析、host 校验和规范化；请求者不能打开开发例外，跨 origin 重定向不能携带认证信息。
- 配对请求只在获得真实挑战后返回 pairing；取消清理候选凭据。已 paired/revoked/frozen 要显式 unlink，不能借取消接口解绑。幂等与操作世代必须阻止迟到响应复活绑定。
- unlink 先完成本机凭据删除与断开，再如实表达尽力通知服务端的结果；本机清理失败不能返回成功。已 remote 对话仍 remote、本机只读，后续接续策略不在本版发明。
- 生成器仅补严格整数判断，防止 Python Literal[1] 接受 True/1.0；仅作用于严格新对象，旧 DTO 行为未改变。TS/Python/Go 由生成器输出，Go 保持现有 x-go 闭包，未另扩展远程联合。
- remote-hub.v2.yaml、apps/hub、apps/desktop、apps/server、docs/vnext 未修改；没有修改或放宽已有测试断言。新增协议测试对基线 872a909 的结构范围做保护。

## 新增错误码

| 错误码 | HTTP | retryable | 语义 |
| --- | --- | --- | --- |
| REMOTE_PAIRING_IN_PROGRESS | 409 | false | 配对已进行，不能重复创建候选绑定 |
| REMOTE_SERVER_UNREACHABLE | 503 | true | 服务端不可达 |
| REMOTE_SERVER_ORIGIN_INVALID | 422 | false | origin 不合法或不符合开发例外策略 |

其他复用已有 REMOTE_AUTH_REQUIRED、REMOTE_PROTOCOL_UNSUPPORTED、CONVERSATION_AUTHORITY_MISMATCH 等，不新增重复语义。

## 验证来源与真实输出

上一轮已重新生成，并用 `--no-index --no-build-isolation --force-reinstall --no-deps -e packages/protocol` 离线重装。下列前三项沿用上一轮最终运行；本轮没有修改对应源文件，按主代理要求不重复运行。时间为日志文件显示的机器本地时间（2026-09-26），未转换时区。

| 项目 | 来源日志（.hqagent/reviews/） | 结果 |
| --- | --- | --- |
| validate -CheckGenerated | 上轮 21:53，R1-FZ11-protocol-validation.log | 通过 |
| 协议专用测试 | 上轮 21:53，R1-FZ11-protocol-tests.log | 187 passed |
| Hub 全量 pytest | 上轮 21:54，R1-FZ11-hub-tests.log | 199 passed，4 warnings |
| 前端 typecheck | 本轮 22:57，R1-FZ11-desktop-typecheck.log | exit 0 |
| 前端 test | 本轮 22:57–22:58，R1-FZ11-desktop-tests.log | 41 文件 / 201 passed |

保存输出的原文摘要：

```text
协议校验通过：258 个类型，109 个 Contract Fixture
187 passed in 3.18s
199 passed, 4 warnings in 26.52s
```

本轮在 apps/desktop 执行 `pnpm typecheck`，退出码 0：

```text
$ vue-tsc --noEmit
```

同一目录执行 `pnpm test --maxWorkers=2 --minWorkers=1`，限制并发降低内存压力，退出码 0：

```text
$ vitest run "--maxWorkers=2" "--minWorkers=1"
 Test Files  41 passed (41)
      Tests  201 passed (201)
   Start at  22:57:54
   Duration  21.51s (transform 1.85s, setup 0ms, collect 8.40s, tests 5.97s, environment 19.09s, prepare 2.94s)
```

Hub warning 是已有依赖弃用提示；前端 stderr 的 HUB_NOT_READY 来自已有重连测试的模拟错误，完整保留在日志。Hub 临时目录位于 worktree 的 .venv/r1fz11-随机标识，设置 TEMP/TMP/PYTEST_DEBUG_TEMPROOT，避开默认临时目录的沙箱权限问题。日志只统一末尾换行，未删除 warning 或模拟错误内容。

复跑入口：根目录 `pwsh scripts/protocol/validate.ps1 -CheckGenerated`；根目录 `.venv/Scripts/python.exe -B -m pytest scripts/protocol/tests -q -p no:cacheprovider`；apps/hub 下 `../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --tb=short`（先设置上述 worktree 临时目录）；apps/desktop 命令如上。

## 下游接线

**P1 服务端**：在 WSS 握手预解析、线路 dispatcher、DTO 选择、helloAck/helloRejected 构造与相关测试中，把包版本相等判断改为支持的 wireRevision 判断。有限读取版本后选解析器，不支持时返回 supportedWireRevisions。protocolVersion 只作诊断。未来保留 N/N-1 解析器和序列化器；不要把旧 0.6.0 草稿的原始事件改写成修订 1 后继续沿用原内容哈希。浏览器 HTTP 不变，本次未新增设备 Bearer 自撤销授权。

**P2 Worker**：按生成 DTO 收发 wireRevision=1，hello 版本取生成常量，不能取 CLI 或 Python 分发包元数据。实现四个本机操作、持久连接状态、凭据生命周期、URL 校验、幂等、候选操作世代及迟到回调隔离；持久化后发 remote.link.changed，重复幂等回放不再发事件。GET/事件共用 Mapper。持久化 authority 并在本机写入口拒绝 remote，解绑不降级。D41 证据仍来自 CancelResult/CancelOutcome、orchestrator/runtime.py 的 CancellationOutcome，以及 TaskService.state 的 task_spec:<executionTaskId> 中 recoveryRequired/pauseRequested；orphanProcessIds 沿用 FZ-2，不解析报错文字或从 failed/paused 猜测。

**P3 / P3-B**：本机配对页面以四个 v1 操作和 remote.link.changed 为准；展示五种绑定状态、真实连接状态、短码过期、取消、解绑、最近错误。lastConnectedAt=null 不表示成功连过；frozen+online 仍显示冻结限制。remote 对话解绑后只读。处理 GET 快照与事件先后，防止慢请求覆盖新状态。远程浏览器 HTTP 不变，传输状态、控制结果、执行状态分别展示。

## open_questions：2 项后续业务接线，非 D42/D43 阻断项

1. **P1/P2 解绑通知接线**：现有云端撤销入口需要 owner 浏览器会话，设备 Bearer 无该权限。P2 需确认是否有现成合法通知上下文；没有时只完成本机解绑并如实显示服务端撤销未确认，复用错误码，不发明接口或转交浏览器 Cookie。未来若要求设备自撤销，另立协议变更。
2. **P2/P3-B 本机 v1 鉴权接线**：本机配对要复用现有 v1 Gateway/桌面壳鉴权，v2 浏览器 Cookie 不是 v1 Bearer。下游需确认现有入口如何接线，不能为了 UI 打通而把 Hub Token 放进响应、事件或前端持久化存储。本轮仅契约，没有应用实现。

提交信息只描述改动本身，提交后用 git log -1 --format=%B 自查。交付登记与日志另提交，未合并或部署。
