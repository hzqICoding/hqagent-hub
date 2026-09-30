---
wp: R16-P0
status: done
scope_declared: [packages/protocol/**, .hqagent/**]
scope_touched: [".hqagent/DECISIONS.md", ".hqagent/INTERFACES.md", ".hqagent/handoffs/R16-P0-protocol.md", ".hqagent/reviews/R16-P0/api-contract.txt", ".hqagent/reviews/R16-P0/cli-input-check.md", ".hqagent/reviews/R16-P0/protocol-tests.txt", ".hqagent/reviews/R16-P0/type-index.md", ".hqagent/reviews/R16-P0/validate.txt", "packages/protocol/VERSION", "packages/protocol/fixtures/contracts/manifest.json", "packages/protocol/fixtures/contracts/r16.AgentInputAttachment.json", "packages/protocol/fixtures/contracts/r16.AttachmentDeletedView.json", "packages/protocol/fixtures/contracts/r16.AttachmentLimits.json", "packages/protocol/fixtures/contracts/r16.AttachmentManifestItem.json", "packages/protocol/fixtures/contracts/r16.AttachmentTargetCapabilities.json", "packages/protocol/fixtures/contracts/r16.ImageInputCapability.json", "packages/protocol/fixtures/contracts/r16.LocalAttachmentView.json", "packages/protocol/fixtures/contracts/r16.MessageAttachmentView.json", "packages/protocol/fixtures/contracts/r16.NativeImageCapability.json", "packages/protocol/fixtures/contracts/r16.RemoteAttachmentLimitsView.json", "packages/protocol/fixtures/contracts/r16.RemoteAttachmentView.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ApprovalDecisionCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ApprovalEvent.json", "packages/protocol/fixtures/contracts/r16.RemoteV4BackfillProgress.json", "packages/protocol/fixtures/contracts/r16.RemoteV4BusySnapshot.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CancelCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CatalogEvent.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CatalogView.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CommandAccepted.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CommandCompleted.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CommandEnvelope.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CommandFailed.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CommandReceipt.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CommandReceived.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CommandRejected.json", "packages/protocol/fixtures/contracts/r16.RemoteV4CommandWithdrawalCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ContentRedaction.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ControlConfirmed.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ControlObserved.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ControlResult.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ConversationCreateCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ConversationDeleted.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ConversationGap.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ConversationSkip.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ConversationUpdateCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ConversationUpserted.json", "packages/protocol/fixtures/contracts/r16.RemoteV4DeliveryGrant.json", "packages/protocol/fixtures/contracts/r16.RemoteV4DirectoryQuery.json", "packages/protocol/fixtures/contracts/r16.RemoteV4EventAck.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ExecutionEvent.json", "packages/protocol/fixtures/contracts/r16.RemoteV4MessageEvent.json", "packages/protocol/fixtures/contracts/r16.RemoteV4MessageSegment.json", "packages/protocol/fixtures/contracts/r16.RemoteV4NativeConfirmationRecorded.json", "packages/protocol/fixtures/contracts/r16.RemoteV4NativeImportCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4NativeIndexDeleted.json", "packages/protocol/fixtures/contracts/r16.RemoteV4NativeIndexUpserted.json", "packages/protocol/fixtures/contracts/r16.RemoteV4NativeReadQuery.json", "packages/protocol/fixtures/contracts/r16.RemoteV4OmittedEvents.json", "packages/protocol/fixtures/contracts/r16.RemoteV4PauseCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ProgressEvent.json", "packages/protocol/fixtures/contracts/r16.RemoteV4QueryFailed.json", "packages/protocol/fixtures/contracts/r16.RemoteV4QueryPayload.json", "packages/protocol/fixtures/contracts/r16.RemoteV4QueryResultSegment.json", "packages/protocol/fixtures/contracts/r16.RemoteV4RedactedSlot.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ResumeCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4RetryCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4RunStateEvent.json", "packages/protocol/fixtures/contracts/r16.RemoteV4RunSubmitCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteV4RunSubmitPayload.json", "packages/protocol/fixtures/contracts/r16.RemoteV4SceneSummary.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ServerHeartbeat.json", "packages/protocol/fixtures/contracts/r16.RemoteV4ServerOutboundFrame.json", "packages/protocol/fixtures/contracts/r16.RemoteV4SkipRecorded.json", "packages/protocol/fixtures/contracts/r16.RemoteV4SyncConversation.json", "packages/protocol/fixtures/contracts/r16.RemoteV4SyncMessageSegment.json", "packages/protocol/fixtures/contracts/r16.RemoteV4SyncReset.json", "packages/protocol/fixtures/contracts/r16.RemoteV4SyncedRunState.json", "packages/protocol/fixtures/contracts/r16.RemoteV4VisibleWorkerEvent.json", "packages/protocol/fixtures/contracts/r16.RemoteV4WorkerEvent.json", "packages/protocol/fixtures/contracts/r16.RemoteV4WorkerHeartbeat.json", "packages/protocol/fixtures/contracts/r16.RemoteV4WorkerHello.json", "packages/protocol/fixtures/contracts/r16.RemoteV4WorkerHelloAck.json", "packages/protocol/fixtures/contracts/r16.RemoteV4WorkerHelloRejected.json", "packages/protocol/fixtures/contracts/r16.RemoteV4WorkerOutboundFrame.json", "packages/protocol/fixtures/contracts/r16.RemoteV4WorkspaceRegisterCommand.json", "packages/protocol/fixtures/contracts/r16.RemoteWire4ApprovalView.json", "packages/protocol/fixtures/contracts/r16.RemoteWire4Error.json", "packages/protocol/fixtures/contracts/r16.RemoteWire4ErrorCode.json", "packages/protocol/fixtures/contracts/r16.RoleImageCapability.json", "packages/protocol/fixtures/contracts/r16.SyncAttachmentItem.json", "packages/protocol/fixtures/contracts/r16.image-manifest.json", "packages/protocol/fixtures/contracts/r16.image-submit.json", "packages/protocol/fixtures/contracts/r16.input-preparation-cancelled.json", "packages/protocol/fixtures/contracts/r16.verified-image-capability.json", "packages/protocol/generated/go/protocol.go", "packages/protocol/generated/python/models.py", "packages/protocol/generated/ts/index.ts", "packages/protocol/openapi/local-chat.v2.yaml", "packages/protocol/openapi/local-hub.v1.yaml", "packages/protocol/openapi/remote-hub.v2.bundle.json", "packages/protocol/openapi/remote-hub.v2.yaml", "packages/protocol/registry/error-codes.yaml", "packages/protocol/remote/R1.6-contract.md", "packages/protocol/remote/api-contract.py", "packages/protocol/remote/api-guide.md", "packages/protocol/remote/http-error-guidance.yaml", "packages/protocol/schema/adapter-port.json", "packages/protocol/schema/local-chat.json", "packages/protocol/schema/remote-attachments.json", "packages/protocol/schema/remote.json", "packages/protocol/tests/test_attachment_contract.py", "packages/protocol/tests/test_devices_api.py", "packages/protocol/tests/test_local_native_contract.py", "packages/protocol/tests/test_native_protocol.py"]
build: pass
tests: pass
commit: fa1b327ddb10742d7a90a09de78a624f7a8f1ee5
open_questions: 0
---

# R1.6-P0 对话附件协议冻结回执

冻结0.10.0 / wireRevision 4 / D52，待主代理审核，未合回integration。基线9770e4e，上一轮7a88a76的needs-decision只记录Q1，现已按主代理裁决关闭。本回执覆盖旧状态，不能用协议完成代替业务上线。

## 冻结内容与取舍

- 方案§8/§11的修订3已被R3占用，实际开4，支持[1,2,3,4]；3→4双向栅栏，结构化unconfirmed为控制尝试终态，不伪造执行已停；Worker每30s周期探测并退避。旧1/2/3传递引用闭包和全部289份既有Fixture不变。
- 新增80类型（remote-attachments.json 79个，adapter-port.json的AgentInputAttachment 1个）、48个修订4具体帧、84份合成Fixture。完整清单见../reviews/R16-P0/type-index.md及fixtures manifest。三端重新生成，Go新增限制与清单类型；未手改生成物。
- 核心新类型：AttachmentLimits/RemoteAttachmentLimitsView、AttachmentManifestItem/SyncAttachmentItem/MessageAttachmentView、RemoteAttachmentView/LocalAttachmentView/AttachmentDeletedView、ImageInputCapability/RoleImageCapability/NativeImageCapability/AttachmentTargetCapabilities、AgentInputAttachment以及独立RemoteV4*和RemoteWire4*。
- 手机先raw流上传，发送仅attachmentIds，命令只带不可变清单；Worker grant正式接单后、任何Agent启动前下载大小/hash校验。下载3次上限、单次60s、整轮300s；准备阶段在忙碌集合中，失败和重启明确终结/显式重试，不永久busy。准备取消新增input_preparation_cancelled证据，必须已确认I/O停止且无Agent启动，否则走D41。
- 限额固定十进制10,000,000图片字节、20,000,000文档/代码字节、每条5个、账号5,000,000,000逻辑字节、未发送86,400秒。query下发数值/白名单/已用与预留，前端不硬编码。采用raw application/octet-stream，必带长度、规范显示名、SHA256和幂等键；不是multipart/JSON/base64。
- 账号按逻辑附件大小计量（同一附件多次引用一次计量，重复上传为不同记录则分别计量）；物理按hash去重、引用归零删blob。uploaded→reserved→attached，过期/删除404；pin有期限，GC不可与提交竞争复活旧资源。PDF/图片内容检测，文本源码流式UTF-8校验及明示后缀白名单，不执行文件。非空文件及严格类型边界见契约。
- 电脑先同步用户消息的pending_upload清单，服务器才接受绑定该消息的Worker上传；完成后新messageRevision发布available，失败unavailable及原因。模型产物自动回传仍属第二期，不注册为本期输入附件。原生历史临时query仍不包含附件字节。
- **Q1已关闭**：暂停只禁浏览器上传和手机发送；Worker对已有本机用户消息的附件同步继续，仍验证设备凭据、owner/store/generation、消息引用、配额、sync开关和删除栅栏；不允许用此端点代发用户消息。两端已有下载不受暂停影响。这是D50直接适用；方案“暂停不能上传”限定手机上传。
- 图片能力分CLI入口、Runtime已实现、实际路径/模型已验证，未知不能填supported。场景必须所有角色满足，原生按Agent类型。已只读查看本机help/version：exec及精确ID resume有-i/--image；Claude仅确认stream-json输入，现有Adapter仍普通文本stdin。未调用模型，没有真实图片识别验收；P2验证前默认unknown/unsupported。记录见cli-input-check.md。
- 本机v1/v2附件库（上传/查询/删除/原文件/服务端缩略图代理/限制值/目标能力）同时冻结，避免再发生桌面接口缺口。AgentTaskSpec.inputAttachments是内部受控路径，不进HTTP/WSS。未配对仍可本机用附件，云端同步状态单独显示。
- Cookie浏览器写入带CSRF/Origin，Worker设备凭据，PAT范围仅预留。所有原文件及缩略图下载attachment/nosniff/no-store，缩略图只服务端受限重编码PNG，失败不回退原图。删除对话、reset、设备删除清对应元数据/引用/分段/缓存/temp/缩略图，最后引用物理删除必须直接查存储证明。

## HTTP与错误码

新增云端8个操作：GET /attachments/limits；POST /conversations/{conversationId}/attachments；GET/DELETE /attachments/{attachmentId}；GET /attachments/{attachmentId}/content、/thumbnail；POST /worker/attachments；GET /worker/attachments/{attachmentId}/content（可选variant=thumbnail）。完整参数、鉴权、成功/错误示例、raw上传下载和curl在remote-hub.v2.yaml、自包含bundle、api-guide §14。API检查器明确区分JSON信封与二进制成功响应，不以跳过所有验证的方式支持二进制。

新增11个错误码（HTTP/4；旧域不扩大）：

| code | HTTP | retryable |
| --- | --- | --- |
| ATTACHMENT_TOO_LARGE | 413 | false |
| ATTACHMENT_TYPE_UNSUPPORTED | 415 | false |
| ATTACHMENT_COUNT_EXCEEDED | 422 | false |
| ATTACHMENT_QUOTA_EXCEEDED | 409 | false |
| ATTACHMENT_HASH_MISMATCH | 422 | false |
| AGENT_IMAGE_UNSUPPORTED | 422 | false |
| ATTACHMENT_DOWNLOAD_FAILED | 502 | true |
| ATTACHMENT_NOT_READY | 409 | false |
| ATTACHMENT_IN_USE | 409 | false |
| ATTACHMENT_THUMBNAIL_UNAVAILABLE | 409 | false |
| ATTACHMENT_PREPARATION_INTERRUPTED | 409 | false |

不存在/已清理/不可见复用NOT_FOUND，避免泄露存在性；契约明确命令失败映射，不添加重复错误名。图片能力变化/未验证也使用AGENT_IMAGE_UNSUPPORTED，不能静默改传文字路径。非图片按本机受控路径交给Agent。

## 验证与真实输出

```text
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：507 个类型，373 个 Contract Fixture

.venv/Scripts/python.exe -X utf8 -B packages/protocol/remote/api-contract.py
API contract verified: 39 current + 8 planned HTTP operations; 92 error codes; self-contained bundle; examples/auth/request IDs consistent

.venv/Scripts/python.exe -X utf8 -B -m pytest packages/protocol/tests scripts/protocol/tests -q -p no:cacheprovider --basetemp=.hqagent/r3-tmp/pytest-r16-delivery
608 passed in 41.45s
```

完整输出保存在../reviews/R16-P0/{validate,api-contract,protocol-tests}.txt。全量测试后只补充了Worker上传描述中的“role=user输入/非产物”范围说明，API/bundle随后重新生成并再次校验通过，Schema/DTO/Fixture没有再变。TEMP/TMP/basetemp均在已忽略的r3-tmp。按要求使用--no-index --no-build-isolation --force-reinstall --no-deps离线重装生成包，未安装新依赖。

测试覆盖旧线路闭包/289份旧Fixture、80新类型往返、48帧的修订隔离、清单禁止路径/字节/URL/owner字段、5个上限、固定限额、内部Adapter路径不触达远程、下载防inline/nosniff/no-store、raw示例长度/hash、暂停鉴权矩阵及新取消证据不进入旧域。没有删/skip/xfail测试。

检查中修复：本机SendLocalMessageInput旧生成校验器未执行已声明maxItems，现启用严格边界；0.9.1整文件不变断言固定到其真实发布提交271c904比对原基线，后续HTTP增量不再被当作历史patch改动，当前1/2/3闭包仍逐项强校验。现有HTTP版本/操作计数断言更新为0.10.0、39现有+8新增；未修改scripts/**或业务测试。末次diff --check通过。

## 下游实施要点 · P1 服务端

实现8个附件操作及本期Schema映射，新增CODECS[4]/升级栅栏，现有文字/1–3对账保留。上传路由绕开JSON整包body读取与普通幂等响应缓存，不能仅放大body上限；代理/应用两层限额，逐块64KiB计数/hash/检测，原子预留配额及幂等回收。BlobStore内部stage_write/commit/open_read/delete/exists/abort接口隔离，DB引用与blob崩溃窗口可恢复，不能因去重存在就免读/免验上传字节。

Worker上传必须已有可靠完整用户消息pending引用；按owner/store/generation/local message/attachment核实，不从HTTP头创建消息。Q1暂停豁免仅此同步路径；Cookie上传及发送仍拒绝。设备下载只授权已grant清单或本设备已同步消息，不授权任意暂存ID。原图流式download、缩略图隔离限内存/像素/首帧重编码、失败明确状态。GC针对未发送24h，命令pin有界、共享hash引用归零才删；reset/deletion与上传提交、读者句柄/重放要有同一删除栅栏。

须直接查CAS文件、缩略图、temp、引用表/元数据/幂等与事件缓存，证明删除和到期没有可查询残留，覆盖共享hash仍被其它有效对象引用、跨owner/pc_only、重复上传、配额并发、重启恢复、20MB真实网络RSS有界及日志无正文/URL/凭据。新准备取消证据经command.updated投影，不塞入旧worker.event修订2DTO。这些业务验收未由P0执行。

## 下游实施要点 · P2 Worker/Hub

实现修订4周期协商与双方水位栅栏，正文/附件清单可用前不改写旧seq/hash。grant正式接单后先持久化准备阶段与忙碌轮次，再下载/校验/原子落盘，全部成功后才能启动任一Agent。有限重试/300s总时限、取消与启动互斥、强杀恢复明确失败或可手动重试；已有启动事实走D41，不能靠无句柄猜取消成功。每次重连发完整busy集合。

用户数据目录按R3.5跨平台规范，本机七个v1/v2附件操作、输入文件按ID落盘不按显示名、受控可读路径交Adapter；原图绝不回退作预览。图片严格区分入口/实现/验证，Codex当前帮助不是App Server输入验证；Claude目前不是已支持，P2实现并验证当前stream-json图片路径后才可改catalog。验证要含实际新建/精确续接、多图混合、错误/取消。非图仅路径输入、不自动执行，不改变用户现有模型凭据/代理配置，不把内部路径或输入块写回远程清单。

本机消息先pending同步再上传、上传后新revision明确available/失败原因，暂停继续Worker上传，关闭sync/删除不上传或复活旧对象。为本机已存在消息绑定上传，不自动回传助手产物；账户云端配额失败不阻止本机工作，只提示同步失败。真实CLI/设备图片识别、文件可读性和崩溃验收交P2，P0只做help/version和合成协议验证。

## 下游实施要点 · P3 前端

手机查询限制/已用与预留额度，选择文件增量hash、raw File/Blob上传（Content-Length由浏览器提供），进度/失败/未发送清理后重新选文件；上传成功仅暂存。按catalog所有角色或native类型保守检查图片能力，缺项/unknown先提示，服务端拒绝时保留文本。发消息只带attachmentIds、不造清单或路径。

显示pending_upload/available/unavailable、缩略图pending/不可用/非图片，原文件使用下载，不直接渲染原图/HTML/SVG。离线发送失败但已上传暂存有24h清理；暂停禁手机上传/发送，但历史下载仍可用。桌面用本机v2接口及附件能力入口，不拿Hub Token/设备secret给浏览器；缩略图由本机认证代理获取服务端产物。区别本机可用与云端同步状态，处理准备失败/取消和真实Task状态，不把command.completed等同任务成功。

## 提交边界

协议冻结提交见头部；后续决策/证据提交不改变协议。全程单线，无子代理、无真实会话或模型调用，未修改apps/**、docs/**、scripts/**，未部署、未合回integration。没有429/0xC0000142/额度错误。Q1裁决已记录D52，无新的needs-decision。等待主代理基于真实diff独立审核。
