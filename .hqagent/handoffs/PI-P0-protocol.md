---
wp: PI-P0
status: done
scope_declared:
- packages/protocol/**
- .hqagent/**
scope_touched:
- .hqagent/DECISIONS.md
- .hqagent/INTERFACES.md
- .hqagent/handoffs/PI-P0-protocol.md
- .hqagent/reviews/pi-p0/api-contract.txt
- .hqagent/reviews/pi-p0/pytest.txt
- .hqagent/reviews/pi-p0/validate.txt
- packages/protocol/VERSION
- packages/protocol/fixtures/contracts/manifest.json
- packages/protocol/fixtures/contracts/pi.PiGuardCheckInput.json
- packages/protocol/fixtures/contracts/pi.PiGuardDecision.json
- packages/protocol/fixtures/contracts/pi.PiGuardHandshake.json
- packages/protocol/fixtures/contracts/pi.PiGuardReason.json
- packages/protocol/fixtures/contracts/pi.PiImageTransport.json
- packages/protocol/fixtures/contracts/pi.PiModelSelection.json
- packages/protocol/fixtures/contracts/pi.PiNativeFormatProfile.json
- packages/protocol/fixtures/contracts/pi.PiNativeReaderId.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ApprovalDecisionCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ApprovalEvent.json
- packages/protocol/fixtures/contracts/pi.RemoteV5BackfillProgress.json
- packages/protocol/fixtures/contracts/pi.RemoteV5BusySnapshot.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CancelCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CatalogEvent.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CatalogView.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CommandAccepted.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CommandCompleted.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CommandEnvelope.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CommandFailed.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CommandReceipt.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CommandReceived.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CommandRejected.json
- packages/protocol/fixtures/contracts/pi.RemoteV5CommandWithdrawalCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ContentRedaction.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ControlConfirmed.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ControlObserved.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ControlResult.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ConversationCreateCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ConversationDeleted.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ConversationGap.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ConversationSkip.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ConversationUpdateCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ConversationUpserted.json
- packages/protocol/fixtures/contracts/pi.RemoteV5DeliveryGrant.json
- packages/protocol/fixtures/contracts/pi.RemoteV5DirectoryQuery.json
- packages/protocol/fixtures/contracts/pi.RemoteV5EventAck.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ExecutionEvent.json
- packages/protocol/fixtures/contracts/pi.RemoteV5MessageEvent.json
- packages/protocol/fixtures/contracts/pi.RemoteV5MessageSegment.json
- packages/protocol/fixtures/contracts/pi.RemoteV5NativeConfirmationRecorded.json
- packages/protocol/fixtures/contracts/pi.RemoteV5NativeImportCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5NativeIndexDeleted.json
- packages/protocol/fixtures/contracts/pi.RemoteV5NativeIndexUpserted.json
- packages/protocol/fixtures/contracts/pi.RemoteV5NativeReadQuery.json
- packages/protocol/fixtures/contracts/pi.RemoteV5OmittedEvents.json
- packages/protocol/fixtures/contracts/pi.RemoteV5PauseCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ProgressEvent.json
- packages/protocol/fixtures/contracts/pi.RemoteV5QueryFailed.json
- packages/protocol/fixtures/contracts/pi.RemoteV5QueryPayload.json
- packages/protocol/fixtures/contracts/pi.RemoteV5QueryResultSegment.json
- packages/protocol/fixtures/contracts/pi.RemoteV5RedactedSlot.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ResumeCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5RetryCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5RunStateEvent.json
- packages/protocol/fixtures/contracts/pi.RemoteV5RunSubmitCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteV5RunSubmitPayload.json
- packages/protocol/fixtures/contracts/pi.RemoteV5SceneSummary.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ServerHeartbeat.json
- packages/protocol/fixtures/contracts/pi.RemoteV5ServerOutboundFrame.json
- packages/protocol/fixtures/contracts/pi.RemoteV5SkipRecorded.json
- packages/protocol/fixtures/contracts/pi.RemoteV5SyncConversation.json
- packages/protocol/fixtures/contracts/pi.RemoteV5SyncMessageSegment.json
- packages/protocol/fixtures/contracts/pi.RemoteV5SyncReset.json
- packages/protocol/fixtures/contracts/pi.RemoteV5SyncedRunState.json
- packages/protocol/fixtures/contracts/pi.RemoteV5VisibleWorkerEvent.json
- packages/protocol/fixtures/contracts/pi.RemoteV5WorkerEvent.json
- packages/protocol/fixtures/contracts/pi.RemoteV5WorkerHeartbeat.json
- packages/protocol/fixtures/contracts/pi.RemoteV5WorkerHello.json
- packages/protocol/fixtures/contracts/pi.RemoteV5WorkerHelloAck.json
- packages/protocol/fixtures/contracts/pi.RemoteV5WorkerHelloRejected.json
- packages/protocol/fixtures/contracts/pi.RemoteV5WorkerOutboundFrame.json
- packages/protocol/fixtures/contracts/pi.RemoteV5WorkspaceRegisterCommand.json
- packages/protocol/fixtures/contracts/pi.RemoteWire5ApprovalView.json
- packages/protocol/fixtures/contracts/pi.RemoteWire5Error.json
- packages/protocol/fixtures/contracts/pi.RemoteWire5ErrorCode.json
- packages/protocol/fixtures/contracts/pi.RuntimeCatalogEntry.json
- packages/protocol/fixtures/contracts/pi.RuntimeGuardView.json
- packages/protocol/fixtures/contracts/pi.RuntimeNativeAgentType.json
- packages/protocol/fixtures/contracts/pi.RuntimeNativeFormatView.json
- packages/protocol/fixtures/contracts/pi.RuntimeNativeImageCapability.json
- packages/protocol/fixtures/contracts/pi.RuntimeNativeSessionIndex.json
- packages/protocol/fixtures/contracts/pi.RuntimeNativeUnsupportedReason.json
- packages/protocol/fixtures/contracts/pi.RuntimeRoleImageCapability.json
- packages/protocol/fixtures/contracts/pi.agent-guard-blocked.json
- packages/protocol/fixtures/contracts/pi.catalog-with-runtime.json
- packages/protocol/fixtures/contracts/pi.image-job-input.json
- packages/protocol/fixtures/contracts/pi.image-target.json
- packages/protocol/fixtures/contracts/pi.native-readable.json
- packages/protocol/fixtures/contracts/pi.public-LocalConversationView.json
- packages/protocol/fixtures/contracts/pi.public-LocalRunView.json
- packages/protocol/fixtures/contracts/pi.public-RemoteConversationView.json
- packages/protocol/fixtures/contracts/pi.public-RemoteNativeSessionView.json
- packages/protocol/generated/go/protocol.go
- packages/protocol/generated/python/models.py
- packages/protocol/generated/ts/index.ts
- packages/protocol/openapi/local-chat.v2.yaml
- packages/protocol/openapi/local-hub.v1.yaml
- packages/protocol/openapi/remote-hub.v2.bundle.json
- packages/protocol/openapi/remote-hub.v2.yaml
- packages/protocol/registry/error-codes.yaml
- packages/protocol/remote/PI-contract.md
- packages/protocol/remote/api-contract.py
- packages/protocol/remote/api-guide.md
- packages/protocol/remote/http-error-guidance.yaml
- packages/protocol/schema/agent-instance.json
- packages/protocol/schema/local-chat.json
- packages/protocol/schema/local-maintenance.json
- packages/protocol/schema/local-native.json
- packages/protocol/schema/remote-attachments.json
- packages/protocol/schema/remote-native.json
- packages/protocol/schema/remote-pi.json
- packages/protocol/schema/remote.json
- packages/protocol/tests/test_attachment_contract.py
- packages/protocol/tests/test_devices_api.py
- packages/protocol/tests/test_local_maintenance_contract.py
- packages/protocol/tests/test_local_native_contract.py
- packages/protocol/tests/test_native_protocol.py
- packages/protocol/tests/test_pi_contract.py
build: pass
tests: pass
commit: 36c472eb72a4e7c101db26ec62c355b1007b672a
open_questions: 0
---

# PI-P0 协议冻结回执

协议冻结提交：`36c472eb72a4e7c101db26ec62c355b1007b672a`。基线`6ba7583`（主代理已合入integration），工作树开工时干净。
包版本 **0.11.0**，新增 **wireRevision 5**，D53；未合并回integration。
本回执的commit指协议内容提交；决策/冻结登记/真实日志随独立交接提交交付，避免自引用SHA。

## 冻结内容与取舍

1. 旧NativeAgentType递归进入线路3/4，直接加pi会改变严格校验。保留1–4整个引用闭包和全部393个旧Fixture；新增RuntimeNativeAgentType与独立RemoteV5/RemoteWire5 codec，支持1–5。4→5栅栏、周期探测与unconfirmed控制终态映射沿现有规则。
2. 旧HTTP客户端也可能严格拒绝新枚举，因此增加可选 `X-HQ-Client-Features: pi-v1`，三个OpenAPI逐操作登记。缺省旧投影，PI资源不返回、直接访问NOT_FOUND；列表/事件游标和WS ticket绑定能力集。没有新增路由，Cookie/PAT/本机Bearer权限均不扩张。此门禁需要下游真实实施，并非更新DTO就自动生效。
3. modelId单字段采用provider/modelId、只分首个斜线；本机provider=1aicode而模型本身带deepseek/前缀。PI角色、LocalAgentModel.id、AgentTaskSpec.modelId、验证模型和catalog一致。默认建议需出现在本机可用列表，不能把建议当安装/订阅能力，也不含密钥或渠道URL。
4. pi-rpc-images-v1重用既有五probe、费用确认与取消作业；实例/版本/准确模型/配置/默认模型均绑定targetRevision。图片样例实测只证明CLI入口，不能宣称当前Hub已支持；保守unknown在第一期实测全部通过前拒绝图片。
5. hub-guard走独占PI进程RPC的extension UI请求/响应，不引入HTTP或云端工具判定通道。内部Handshake/CheckInput/Decision有明确DTO，tool原始参数只能留本机。API公开GuardView只有状态/原因/版本/时间。要求--no-extensions加唯一显式Hub扩展、独立核实隔离，无法确认时fail-closed；审批绑定参数hash、请求、会话、策略与时效，一次消费。
6. 第二期reader pi.jsonl.v3.tree与unsupported原因域本轮冻结。按文件重开语义取最后落盘entry→parent链，不猜终端未保存分支，不拼旁支；context_edit隐藏或替换历史必须生效。阶段一未实现如实reader_not_implemented；原生导入沿D51关闭确认/精确绑定/单写锁，phase2实现不阻塞phase1调度。
7. 无修改AdapterTaskSpec/AdapterFailureKind/TaskStatus或执行身份内核；复用existing cli_stream、审批事件与取消证据。agent_end/abort应答不能代表停止，需agent_settled或终止进程证据。

规范：[PI-contract.md](../../packages/protocol/remote/PI-contract.md)；HTTP索引/错误总表/示例在api-guide和自包含bundle。
新增83个类型、92个合成Fixture；类型总数606，Fixture总数485。

## 新错误码

| code | HTTP映射 | retryable | 用途 |
| --- | --- | --- | --- |
| PI_GUARD_UNAVAILABLE | 409 | false | Hub保护未就绪/不可用，禁止开始或继续工具执行 |
| PI_UNCONTROLLED_EXTENSIONS | 409 | false | 存在未受控扩展或无法确认独占加载 |
| PI_TOOL_CALL_BLOCKED | 403 | false | 路径/只读/工具/审批拒绝，结构化原因见PiGuardReason |

只进入公共HTTP错误注册表和线路5错误域，旧1–4不变；主要用于异步结果，不增加云端收费或审批放宽入口。

## 只读事实核对

- 本机安装包 @earendil-works/pi-coding-agent/package.json：版本1.0.1。
- dist/cli/args.js：--no-extensions关闭自动发现和内置扩展；显式-e路径仍生效。
- docs/rpc-extension-ui.md：等待式editor的prefill和extension_ui_response.value/取消语义。
- dist/core/session-manager.d.ts：CURRENT_SESSION_VERSION=3，header含id/cwd/timestamp，entry含id/parentId/timestamp，context_edit可替换或隐藏内容。
- dist/core/session-manager.js：_buildIndex以最后非header entry为leaf，branch仅改内存指针。
- docs/rpc.md / extensions.md：agent_settled才是不会再自动继续的通知，tool_call支持拦截。

没有读取用户models.json/凭据文件或真实会话正文，没有发起CLI会话或模型调用；格式/安全/图片的实际Runtime验证由下游实施。

## 验证：真实输出

使用预装.venv重新生成并按离线参数重装协议包；临时目录均放worktree的.hqagent/.tmp。
生成输出：`protocol 0.11.0: 生成 606 个类型 -> ts / python / go`。
离线重装：`pip install --no-index --no-build-isolation --force-reinstall --no-deps -e packages/protocol`，退出0。

```text
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：606 个类型，485 个 Contract Fixture

python -X utf8 -B packages/protocol/remote/api-contract.py
API contract verified: 47 current + 0 planned HTTP operations; 95 error codes; self-contained bundle; examples/auth/request IDs consistent

python -X utf8 -B -m pytest packages/protocol/tests scripts/protocol/tests -q -p no:cacheprovider --basetemp=.hqagent/.tmp/pi-pytest-final
768 passed in 54.93s
```

原始输出：`.hqagent/reviews/pi-p0/validate.txt`、`api-contract.txt`、`pytest.txt`。
第一轮765通过/1失败：旧本机原生列表测试精确参数集合未计入新增能力头；已精确增加该头并检查required=false和枚举值，没有删除/skip/xfail或放宽旧冻结线。最终全绿。
既有测试只更新当前包版本、支持修订集合及这个新增头；旧线路闭包和旧Fixture断言原样保留，并新增针对本次基线的1–4全闭包/拒绝边界测试。
build=pass指协议生成/漂移检查，不代表应用业务构建或真CLI验收；本轮未跑Hub/前端应用测试，未并行启动测试进程。

## 下游实施要点

### Hub适配器 / hub-guard（P2）

- 注册pi实例，resolve实际Node入口并无shell启动；--mode rpc、Hub管理session-dir、--no-extensions、唯一Hub扩展，精确provider/model参数。
- 实现守卫握手及超时fail-closed、工具清单/策略变化失效、逐调用路径及shell判定、只读setActiveTools、审批映射与单次hash绑定；扩展自报不能替代独立隔离校验。未知扩展不得通过风险提示后照常执行。
- Agent管理/场景模型选择/LocalImageVerificationTarget共享首斜线modelId；复用作业协调器和五probe、模型变更失效、真实费用确认。PI未完成验证的catalog不能supported。
- AgentSessionHandle精确sessionId与本机sessionFile映射；switch_session核对ID，abort等待settled/进程终止，FZ-2/D41结构化回执不变。
- 实现codec5、4→5栅栏、周期探测、PI资源延迟补传、准确busy完整集合；旧修订不能收到PI场景或新枚举，不能改旧outbox版本。
- 实现本机pi-v1投影及事件/WS票据能力绑定；未声明头的旧客户端保持旧DTO域。NativeSessionIndex旧类仅供冻结线路，新公共映射用RuntimeNativeSessionIndex，避免误用旧枚举拒绝pi。
- 第二期读取插件按冻结profile核实树/编辑/截断，过滤私有推理/凭据，索引仅登记workspace、终端来源；关闭确认/活跃再检查/精确绑定单写锁与D51共用。reader未实现可明确unsupported，不虚报格式可读。

### 前端（P3）

- 本机/云端统一pi-v1请求头，切换能力集清理旧游标并重取快照；没有云端Cookie复用到本机等跨服务认证变化。
- 显示PI实例、安全状态/原因；模型选择器保留provider命名空间、仅可选实际列表；不同角色pro/flash/vision建议不自动替用户配置或触发调用。
- 验证按钮沿0.10.1明确真实调用与费用；显示五probe和失效状态。图片发送遵循准确角色/原生绑定能力，unknown不放行。
- 第二期native列表标记PI、已保存分支与unsupported原因，导入确认终端关闭，不套场景角色、不使用latest。模型/路径/扩展源码不得展示为风险诊断。

### 服务端（P1）

- 注册严格codec5，握手支持1–5，保留所有旧错误域，实施4→5栅栏及Store/seq/grant规则。只保存/转发，绝不启动模型。
- current HTTP NativeAgentType映射采用RuntimeNativeAgentType；新catalog提供安全runtimes/模型能力/GuardView。绑定PI场景的提交要求5，不靠字符串AgentId绕门禁。
- 实现pi-v1 HTTP/事件投影、直接寻址NOT_FOUND、游标能力集隔离；公开OpenAPI继续与bundle一致。新码如实映射异步结果，D50暂停/安全取消、D51索引与D52附件真删除不变。
- Phase2原生PI索引、在线读取与导入复用既有HTTP操作，不新增PAT scope，不保存未导入正文；现有高风险远程不可批准规则保持。

## needs-decision

无。遗留的手机删除等其它工作包后续项不属于本轮范围；CLI实际安全/图片/原生读取验收仍是下游交付条件，不冒称已通过。

## 新增类型完整清单

- `RemoteV5ApprovalDecisionCommand`
- `RemoteV5ApprovalEvent`
- `RemoteV5CancelCommand`
- `RemoteV5CatalogEvent`
- `RemoteV5CommandAccepted`
- `RemoteV5CommandCompleted`
- `RemoteV5CommandEnvelope`
- `RemoteV5CommandFailed`
- `RemoteV5CommandReceipt`
- `RemoteV5CommandRejected`
- `RemoteV5CommandWithdrawalCommand`
- `RemoteV5ControlObserved`
- `RemoteV5ConversationGap`
- `RemoteV5ConversationSkip`
- `RemoteV5EventAck`
- `RemoteV5MessageEvent`
- `RemoteV5OmittedEvents`
- `RemoteV5PauseCommand`
- `RemoteV5ProgressEvent`
- `RemoteV5ResumeCommand`
- `RemoteV5RetryCommand`
- `RemoteV5RunStateEvent`
- `RemoteV5RunSubmitCommand`
- `RemoteV5ServerHeartbeat`
- `RemoteV5ServerOutboundFrame`
- `RemoteV5SkipRecorded`
- `RemoteV5VisibleWorkerEvent`
- `RemoteV5WorkerEvent`
- `RemoteV5WorkerHeartbeat`
- `RemoteV5WorkerHello`
- `RemoteV5WorkerHelloAck`
- `RemoteV5WorkerHelloRejected`
- `RemoteV5WorkerOutboundFrame`
- `RemoteV5ConversationUpserted`
- `RemoteV5MessageSegment`
- `RemoteV5SyncedRunState`
- `RemoteV5ConversationDeleted`
- `RemoteV5SyncReset`
- `RemoteV5BusySnapshot`
- `RemoteV5BackfillProgress`
- `RemoteV5CommandReceived`
- `RemoteV5DeliveryGrant`
- `RemoteV5ConversationUpdateCommand`
- `RemoteV5ExecutionEvent`
- `RemoteV5ControlConfirmed`
- `RemoteV5ControlResult`
- `RemoteV5ConversationCreateCommand`
- `RemoteV5ContentRedaction`
- `RemoteV5SyncConversation`
- `RemoteV5CatalogView`
- `RemoteWire5Error`
- `RemoteWire5ErrorCode`
- `RemoteWire5ApprovalView`
- `RemoteV5RedactedSlot`
- `RemoteV5NativeIndexUpserted`
- `RemoteV5NativeIndexDeleted`
- `RemoteV5NativeConfirmationRecorded`
- `RemoteV5NativeImportCommand`
- `RemoteV5WorkspaceRegisterCommand`
- `RemoteV5NativeReadQuery`
- `RemoteV5DirectoryQuery`
- `RemoteV5QueryResultSegment`
- `RemoteV5QueryFailed`
- `RemoteV5QueryPayload`
- `RemoteV5RunSubmitPayload`
- `RemoteV5SyncMessageSegment`
- `RemoteV5SceneSummary`
- `RuntimeNativeAgentType`
- `RuntimeNativeFormatView`
- `RuntimeNativeSessionIndex`
- `RuntimeNativeImageCapability`
- `RuntimeRoleImageCapability`
- `PiModelSelection`
- `PiImageTransport`
- `PiNativeReaderId`
- `PiNativeFormatProfile`
- `RuntimeNativeUnsupportedReason`
- `PiGuardReason`
- `RuntimeGuardView`
- `RuntimeCatalogEntry`
- `PiGuardHandshake`
- `PiGuardCheckInput`
- `PiGuardDecision`
