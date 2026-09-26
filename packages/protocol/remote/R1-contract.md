# R1 远程通信契约（协议包0.6.1，线路修订1）

## 1. 定位、事实源与范围

这是通信契约，不是运行服务。唯一结构事实源为 `schema/remote.json`，HTTP绑定为 `openapi/remote-hub.v2.yaml`；本文件规定结构无法独立表达的事务、授权和跨消息约束。D40/D41记录在 `.hqagent/DECISIONS.md`。设计基线为手机远程方案855d871；vNext技术方案§4、§5.1是目标模型，本协议映射现有执行内核，不据其草稿迁移内核。

服务端仅认证、设备配对绑定、消息/状态中转与暂存。禁止服务端调用模型、保存模型凭据或参与AI订阅、安装、分发。账号登录口令仅是Hub Server账号口令。设备Bearer不是模型凭据，也不是本机Hub Token。附件/产物传输、原生会话发现、飞书/通知、小程序签名审批不在R1-P0。已登记Workspace/Scene目录只是选择目标所需的只读索引；本轮不冻结任意目录浏览/注册接口。

现有本地HTTP/HubEvent/TaskStatus/NodeStatus/Adapter Port保持原语义。远程HTTP使用独立HTTPS origin，虽同用/api/v2也不能把本地API暴露到公网。Python/TS消费新增DTO；Go依现有x-go闭包生成版本和错误枚举，不启用远程联合类型。任何生成物不得手改。

## 2. owner、认证与浏览器会话

- owner仅取已认证会话。浏览器业务输入/输出无ownerId/userId/accountId/tenantId字段，不能指定“替哪个账号”操作。
- 所有已绑定设备、Conversation、Command、消息、投影、Outbox、游标及幂等记录按owner分区。外键按owner+worker/store+resource关联，不能只校验根资源后全局查子资源。
- 跨owner与不存在的资源统一NOT_FOUND；不返回其他账号的名称、ID、路径或存在性。读取、分页、撤回、审批、WS连接均不可省略隔离。
- 账号由运营者安全初始化/管理工具建立，无公开默认密码、无AI账户开户接口；这是P1实现职责，非模型服务管理。
- 浏览器cookie为`__Host-hqremote; Secure; HttpOnly; SameSite=Strict; Path=/`，禁止Domain；认证成功轮换，logout注销本会话。令牌只在Set-Cookie头，不进JSON/localStorage/日志。
- 所有浏览器写请求校验精确Origin；登录前按同源Origin及限流保护，登录后还校验`X-CSRF-Token`与当前会话绑定。JSON的csrfToken仅用于CSRF，不具备独立认证能力。
- 写请求带Idempotency-Key，绑定认证主体、操作资源、规范化请求。重放前仍要鉴权；同键异内容409。登录/退出用独立安全认证存储实现重放，不把密码、Cookie或完整认证响应塞进普通命令缓存。登录重复意图不重复创建账号/会话，允许安全地重发同一会话Cookie。
- 认证响应、配对码响应Cache-Control:no-store，设备/账号认证失败信息泛化并限速；REMOTE_RATE_LIMITED同时返回Retry-After。密码、Authorization、Cookie、配对码均从访问日志和错误输入回显中移除。

## 3. 设备配对与撤销

1. Worker在本机生成至少256-bit随机设备secret，并保存到本机受保护存储。仅经TLS Authorization头提交首次登记和后续认证，正文/响应体/WS帧绝不含原值。
2. 服务端存不可逆验证材料（例如带服务端pepper的HMAC），不存原文或可逆加密副本。初始未认证设备请求只能产生TTL 300秒的待配对认证挑战，不能成为可路由设备。
3. 未认领挑战属于认证暂存而非已绑定业务记录，不进入任何用户设备列表；不包含账号业务数据。用户已登录浏览器提交8位短码预览，核对设备后confirm，事务内消费短码并建立owner非空的设备绑定。
4. 一个Worker只属于一个owner，不做共享或转移。已绑定credential不能重新认领；异owner重放不泄露原owner。同一请求同幂等键返回原结果，不延长有效期或创建第二设备。过期后须用户显式发起新配对。
5. 注册secret必须由Worker持有；浏览器仅见短码、设备信息及绑定结果，不得读取设备凭据或本机Hub Token。Worker轮询只允许登记该挑战的secret，已过期/撤销挑战不能开执行连接。
6. revoke事务中废止认证与投递资格，并封锁旧连接。尚未派发命令拒绝并保存相应序号跳过记录；可能已派发/accepted的命令保持已知事实及待核对说明，不伪造停止。`executionMayStillBeRunning=true`明确撤销不是停止操作。设备重新配对不得自动转移旧命令或旧对话。

## 4. Worker WSS与存储世代

`/ws/v2/worker`只接受已配对、未撤销的设备Authorization头；不接受URL token、浏览器cookie或本机Hub Token替代。10秒内首帧hello。按D42仅以整数wireRevision协商，本轮修订号为1。hello.protocolVersion是协议包semver诊断值，不参与接入或兼容性判断。hello_ack回显已接受的wireRevision；hello_rejected返回supportedWireRevisions，初值[1]，不能只返回错误文字。

hello绑定workerId、workerStoreId、workerEpoch、platform、architecture、capabilityRevision与lastServerAck。当前连接的workerId必须匹配credential绑定。每个Worker只允许一个有效连接，新认证连接获得connectionId并fence旧连接；连接标识是传输栅栏，不是本地Session/Workspace锁。

- Worker每15秒发heartbeat；服务端45秒没收到有效Worker流量标offline。心跳、HTTP202、写入socket均不等于事件或命令持久确认。
- 普通重启保持workerStoreId和持久seq，换workerEpoch。Outbox重传保持原始事件内容、eventId、occurredAt和发布该事件的epoch，不重写成新epoch。重传旧epoch事件允许通过当前连接，旧连接的心跳/新投递不允许。
- 数据库恢复旧备份、回滚、重建必须换workerStoreId，lastServerAck=null。不能因Inbox回滚就把旧命令再执行一遍。
- server hello_ack包含serverTime、当前存储世代连续确认位置、pendingCommandCursor、15/45常量。commandDelivery=frozen时reason必填；frozen禁止投递任何执行或审批放行命令，允许传输对账所需观测。
- 发现store变化、跨store ack、确认回退或Worker无法证明其持久序号连续性时冻结旧世代未决命令。R1没有远程force-unfreeze接口；由本机/服务端运营者核对持久接单和实际执行记录后处理。缺乏证据就保持冻结，可显式撤销旧绑定并建立新设备/新对话，绝不自动迁移旧命令。
- hello_ack确认位置高于Worker持久分配序号上界时不得处理其后命令或裁剪Outbox，须停止连接并按恢复/对账处理。上界取持久分配高水位，不能用已裁剪事件表的当前MAX(seq)代替。
- WS关闭建议：4401认证失败，4403撤销/权限失败，4409协议/世代冲突，1009超帧。结构化错误仍用registry code；客户端不能靠关闭原因文本判业务状态。

## 5. 身份链与命令入队（D40）

`conversationId → runId(LocalRun) → executionTaskId / nodeId / sessionId`。

- 远程runId是用户可见控制句柄。executionTaskId只映射现有LocalRunView.taskId；父执行引用只映射已有Task.parentTaskId。禁止添加attemptId或retryOfRunId，包括空占位字段。
- 当前Worker仍每轮创建执行Task；模型会话继续按准确Session映射。服务器不创建执行Task、Run或虚构模型Session。
- submit payload引用已登记workspaceId、sceneId及sceneVersion，显式new/continue。Worker按冻结版本验证，不静默使用新角色配置。模型/effort实际解析仍在Worker，服务端只有场景摘要，无模型凭据。
- 浏览器消息正文只能提供clientMessageId、text、sessionMode、可选expiresAt；目标Worker/Store/目录/场景来自owner范围的Conversation，不允许客户端额外给出owner、seq或风险等级。
- 用户消息、Command、conversationSeq分配与服务端Outbox在同一事务持久化后返回202。服务端离线队列显示queued_offline，不显示运行中。
- commandId + 规范化命令内容唯一去重；Worker保存Inbox和接单回执后才发送accepted。P2必须在同一本机事务中保存Inbox/顺序槽/LocalRun排队/接单事件，再交现有TaskEngine；不能用代理调用本机HTTP再补记Inbox的方式让外部执行提前发生。相同命令重投返回原回执；相同ID不同内容拒绝，不能覆盖已消费记录。
- 请求规范化使用camelCase字段、UTF-8、JSON对象键排序、无多余空白、保留字符串内容、不注入默认字段、不保留未提供的可选字段。所有数值是安全整数。可沿用当前storage.idempotency.request_hash的规范化方式；设备/owner属于去重作用域，不作为浏览器可输入字段。凭据从不参与普通请求日志/缓存正文。
- submit默认有效期24小时，上限7天；run控制默认5分钟、上限15分钟；审批不晚于Worker审批自身expiresAt，远程决定默认最多5分钟；撤回控制默认5分钟。不得续投时改expiresAt。过期只影响未接单命令，accepted后的正常长任务不因TTL到期被取消。

## 6. conversationSeq与撤回

只有run.submit分配新的conversationSeq。pause/resume/cancel/retry/approval.decide/command.withdraw均不占执行消息序号。Worker按conversationId的连续序号持久化入队；缺口发送conversation.gap并等待补传，不按网络到达顺序抢跑。助手/system消息不分配conversationSeq。

| 情况 | 必需行为 |
| --- | --- |
| 明确从未进入派发 | 原Command变rejected，记录REMOTE_COMMAND_WITHDRAWN或REMOTE_COMMAND_EXPIRED；事务保存conversation.skip及原sequence，保留可补传记录 |
| 已写入派发意图或可能发出，尚无Run投影 | 撤回先记requested并下发独立command.withdraw；不能删除原记录冒充成功 |
| withdrawal先于submit到Worker | payload的targetConversationSeq引用原消息序号，不是新分配序号；Worker在同一Inbox/排序事务持久化原commandId的拒执行tombstone并消费原slot。迟到submit永不执行 |
| 原submit已接单但尚未启动 | Worker核对其本地Run/Inbox并按已有控制路径取消；只有实际确认后报告 |
| 原submit已在执行 | Worker确认停止后反映cancelled；已经产生的文件/外部副作用不承诺回滚 |
| 原submit已结束或已有可见Run | 不能声称“撤回从未执行”；已知Run用runId控制，过晚撤回返回REMOTE_WITHDRAWAL_TOO_LATE |
| 无法确认原执行情况 | withdrawalState=requested，控制结果unconfirmed，保留原命令及对账要求 |

服务端仅能拒绝自己尚未派发的入队记录，并发布RemoteBrowserCommandEvent；不能伪造Worker eventId/seq/接单回执。

派发Outbox必须在写socket前持久化dispatching/sent意图；可能写过但丢回执的命令不属于“未派发”。过期且可能已派发时先向Worker核对，不能由服务端定时器覆盖已接单事实。skip不属于新的执行命令，Worker确认其排序记录用conversation.skip_recorded。只重传同一不可变skip；不能把已接单命令改写为未经核实的skip。

## 7. 控制结果及完成矩阵（D41）

执行状态只用原TaskStatus；传输/接单状态、控制结果、执行状态是三层不同事实。

| 命令 | command.completed条件/resultStatus | command.failed或等待 |
| --- | --- | --- |
| run.submit（含追加） | 真实Run成功→succeeded；真实取消→cancelled；resultRef必有runId，已知Task即带executionTaskId | 真实执行失败→failed；不能用接单当成功 |
| run.pause | 真正到节点边界paused→confirmed，controlResult及resultRef必填 | 仅pauseRequested仍accepted；不能提前completed |
| run.resume | 调度已确认解除等待并恢复→confirmed，controlResult及resultRef必填 | 不支持/拒绝→failed/rejected；不能只改标签 |
| run.cancel | 已确认停止或本来已终态→confirmed，controlResult及resultRef必填 | Adapter refused→failed/rejected；无句柄/不明→accepted且发布unconfirmed，不能completed |
| run.retry | 新执行引用已持久化入队→retry_enqueued；resultRef包含runId和executionTaskId | 后续执行结果由新资源报告；失败入队→failed |
| approval.decide | Worker确认有效决定已被执行器消费→approval_consumed，resultRef必填 | 拒绝/过期/不允许批准→rejected或failed；传递结果不明不得重复放行 |
| command.withdraw | 原submit未入队且tombstone持久化→withdrawn、evidence=inbox_tombstone；已启动后确认停止→confirmed并带resultRef | 过晚→failed；不能确认→accepted/unconfirmed |

resultRef/控制结果等跨命令约束须根据持久的原命令类型验证；仅验证单个DTO形状不足以判定终态。command.completed不等于“代码开发成功”。

三态控制证据：

- confirmed：来自CancelOutcome.stopped_gracefully/force_killed/already_finished、节点边界已paused、Supervisor实际调度或已持久化retry引用等。confirmed取消必须executionMayStillBeRunning=false且orphanProcessIds为空。pause/resume可能仍有活跃进程，不能按confirmed一概推断进程不存在。
- rejected：来自Adapter refused或Worker策略拒绝。Adapter refused时Agent可能仍运行，不能把FZ-2的Task failed当作已停止。策略在执行前拒绝且Worker有证据时可标false。
- unconfirmed：无执行句柄、recoveryRequired、投递回执不明等，executionMayStillBeRunning=true。空PID列表只是未知，不是没有进程。保持待核对而不是伪造command.completed。

证据优先级：recoveryRequired、残留进程或明确未确认信息优先于succeeded/failed/cancelled等标签。P2须在控制动作前后保留结构化观测，不能把resume清掉recoveryRequired视作旧执行已停止。有未核实副作用时远程resume/retry不能绕过本机对账；无Run的撤回观测省略resultRef/executionStatus，不能伪造ID或状态。

P2证据入口：`adapters/base`的CancelResult/CancelOutcome、orchestrator/runtime.py的CancellationOutcome，orphanProcessIds沿用FZ-2；`runtime/tasks.py`通过`self.state.get('task_spec:'+executionTaskId)`取得recoveryRequired/pauseRequested等结构化标记。当前TaskDetailView并未公开这些标记，P2需在业务桥接层暴露给远程映射，P0不修改它。禁止解析reason/stderr/error文字或仅从failed/paused反推。reason仅供展示。

## 8. 上行事件、确认和浏览器游标

Worker事件seq绑定workerStoreId，沿同一本地持久序号空间单调分配。P2把新增远程生命周期事件和Outbox放在同一事务或同一持久序号分配器下；不能使用易失内存网络计数器，也不把新远程类型送进旧Adapter的固定事件映射表。

1. P1先校验认证Worker、当前store、各执行/Conversation引用的归属，再原子保存Inbox事件、投影和浏览器Outbox；最后确认**连续**序号。先看到12而10/11缺失，不得确认12。
2. 同eventId或同store+seq重发且内容相同，幂等返回旧确认；同ID/seq不同内容REMOTE_EVENT_CONFLICT，禁止覆盖。
3. 本地私有对话和历史不能为了补seq全量上传。RemoteOmittedEvents只携带不含内容的[firstSeq,seq]覆盖记录；firstSeq<=seq且区间必须连续、无重叠矛盾，不得覆盖任何远程关键事件或已发布不同内容。保留原范围重传，不能重切片制造不同确认事实。
4. P1将正常事件视为单点覆盖，omitted视为显式连续区间；只有持久区间拼成无缺口前缀才推进ack。omitted不转给浏览器（RemoteVisibleWorkerEvent结构中不包含它）。历史未配对数据只能用无内容覆盖记录，不重放成新任务。
5. Worker收到ack后，仅裁剪匹配workerId/store且不高于本机持久分配上界的已确认Outbox。旧世代ack、回退、未知超前值必须拒绝/对账，不能取最大值凑数。
6. 序号和计数范围1..2^53-1（ack可0）。安全整数耗尽前停机换世代并对账，不能溢出或当作浮点近似数。
7. 浏览器使用服务端独立、owner/资源作用域绑定的不透明serverCursor，不解析为Worker seq。快照与其cursor在同一事务取得；之后补拉事件。cursor失效410要求快照，跨用户或错误作用域游标拒绝且不泄露归属。
8. R1浏览器可以HTTPS轮询/events；本轮只冻结Worker WSS，不要求浏览器WS。已观察在线时间来自服务端连接，不由Worker上行Run payload伪造；RemoteRunView.workerOnline由P1附加。
9. 终态、审批、关键错误不可当进度噪声丢弃；本版omitted仅用于非远程可见事件，不允许掩盖远程缺失结果。日志与文本必须Worker侧脱敏，不能包含环境变量、认证文件或私有思考过程。

## 9. 对话权威与审批分级

配对后新建对话为remote；未配对纯本地对话保持现状。既有local对话不自动改权威、不双写、不重放历史。remote对话的消息排序和用户命令入口只有服务端，电脑界面也走RemoteGateway。

P2须持久记录authority，并在本地HTTP发送/追加/重试/恢复等写入口拒绝remote对话，错误码CONVERSATION_AUTHORITY_MISMATCH。拒绝依据持久归属，不能相信客户端自报local或只靠前端隐藏按钮。经过设备认证、去重和顺序验证的远程命令走专用内部消费入口，不冒充本机用户HTTP。0.5.0的LocalConversationView目前没有该字段，业务持久化和拦截由P2实现；本协议不破坏性改它。

审批授权来自Worker实际pending请求和**当前本机策略**，不是服务端声明。git_push/deploy/delete/db_migrate及Worker声明动作的远程approve必须REMOTE_APPROVAL_FORBIDDEN；前端禁止按钮不能替代P1/P2双重校验。无法确定安全分类的通用shell包装不能成为绕过高风险的别名，应按Worker策略拒绝远程批准。可远程reject高风险请求，但不能因此授权执行。R1没有小程序签名或替代强认证入口。

审批ID绑定实际run/node/执行器请求、有效期及消费状态；任务终止、策略变更或已有决定都需重新校验。重复请求只返回同一结果，不重复发送给原生工具；消费不明保持不明，不自动重批。ApprovalView中的remoteApprovalAllowed是Worker可见投影，收到命令时仍要重新读取当前真实请求，服务器即使篡改风险级别也不能改变本地判断。

## 10. 大小、生成器与消费者校验

Worker WS帧最大256KiB（UTF-8字节），超限明确拒绝/1009，不截断后继续。结构字段另有限长/数量限制；组合后仍须检查总字节数。Catalog是有界原子完整快照，超限必须报告而不能偷偷截掉工作区。浏览器历史用有界分页；大历史不一次同步。附件不通过这些帧传送。

oneOf生成TS联合和Python RootModel（通过model_validate()/model_dump()保持裸JSON形状）。只有新远程对象启用x-wire-strict；不改变旧DTO验证语义。显式null仅用于允许的ack位置；可选字段未提供应省略，不以null替代。Python序列化使用mode=json/by_alias=True/exclude_none=True，必填可空ack会保留null。整数、布尔及数组标量严格校验；跨资源、三层状态、期限顺序、firstSeq<=seq、hasMore与cursor等关系仍是P1/P2业务校验责任。

普通重放的内容哈希不含传输重试次数或新epoch；原事件不可变。协议测试覆盖结构与样例，不冒充P1/P2的事务和网络故障验收。P1/P2/P3要按本文件补并发、越权、连续ack、撤回先到、世代变化、审批伪造和恢复故障测试。


## 11. FZ-R1.1 线路修订演进（D42）

- Worker↔Server的27个具体帧使用wireRevision:1，除了hello的诊断protocolVersion外，不再携带协议包版本。
- hello.protocolVersion使用semver pattern，允许0.6.0、0.6.1、未来包版本及合法预发行/构建标识。P1不得拿它与自己的包版本相等比较；P2应填生成常量，而不是模型、CLI或Python分发包元数据版本。
- hello_ack的wireRevision是接受的线路修订。拒绝帧统一带supportedWireRevisions；REMOTE_PROTOCOL_UNSUPPORTED时必须提供列表。先读取有限握手字段判断线路版本，再按对应DTO验证整帧，不能先硬套当前DTO然后丢掉协商信息。
- 同一wireRevision内结构冻结。在x-wire-strict下添加可选字段也会被旧端拒绝，所以任何帧结构变化都新开线路修订；不得悄悄修改修订1的DTO。未来新增修订保留旧修订解析器/序列化器，按连接选择。
- 服务端在升级窗口同时支持N和N-1（修订1首次只有[1]）。老Worker继续说N-1，新Worker使用双方实际支持的修订；未知线路不得按包版本猜测或强行解释。结束兼容窗口需显式运营策略和升级提示。
- 包版本升级（如0.6.1或后续本机接口更新）不改变wireRevision。HTTP的ApiEnvelope.protocolVersion和本机HubEvent.protocolVersion仍是包版本；remote-hub.v2的浏览器HTTP契约此次未修改。
- 旧0.6.0草稿把包版本当线路号，不能自动视为修订1。P1当前开工代码需一次性改字段/校验/构造器及测试；不以数据重写伪造已确认事件的原始哈希。

## 12. FZ-R1.1 本机连接管理（D43）

事实源为schema/remote-link.json、local-hub.v1.yaml新增四个操作。只使用本机v1现有Bearer、Host/Origin和WS Ticket，不引入新认证或把设备secret给UI。本机HTTP只返回ApiEnvelope.data里的RemoteLinkView，状态以GET和remote.link.changed的最新快照为准。

| state | 必需内容与意义 |
| --- | --- |
| unpaired | 无绑定；serverOrigin可作为非secret偏好保留，也可省略。通知服务端未确认可带lastErrorCode |
| pairing | 已取得有效挑战，serverOrigin/deviceName/pairRequestId/pairCode/expiresAt齐备；不是已经绑定 |
| paired | serverOrigin/workerId/deviceName/connectionStatus/lastConnectedAt。刚配对尚未连通过时lastConnectedAt=null，不能伪造成功连接时间 |
| revoked | 保留原绑定识别信息，connectionStatus=offline；不自动重连或冒充执行已停止 |
| frozen | 保留识别信息和真实连接状态。WSS在线也可能因世代/对账而禁止命令投递 |

所有视图可包含的错误仅已登记错误码，不带原始Authorization、secret或Hub Token。lastConnectedAt是最近一次确认成功连接的时间，断线/重试不刷新它。短码只出现在pairing，取消/过期后不继续暴露。

serverOrigin必须是规范化origin，不接受userinfo、任意path、query或fragment；HTTPS可使用合法主机/端口。仅本机Worker明确开启开发调试模式时允许http://127.0.0.1或http://localhost（可带端口），不能通过请求参数打开该例外。P2应使用URL解析器再次验证host/port、归一化scheme/host/default-port/root-slash，不以正则代替完整URL语义。跨origin重定向不得携带设备认证信息。Origin不合法返回REMOTE_SERVER_ORIGIN_INVALID；请求者仍要先通过v1认证。

配对/取消/解绑由P2序列化并持久化操作世代，防止异步晚到响应复活已取消的绑定。POST pairing拿到真实短码才返回pairing；发请求尚未取得挑战属于内部in-flight状态，不能编造pairRequestId/短码。服务端响应不明时保存安全的重试意图并报告错误，幂等重试不创建第二secret或重复配对。

DELETE pairing取消候选配对并清候选凭据/轮询；已paired/revoked/frozen须显式unlink，不能靠取消接口绕过。服务端已看到的短码挑战可能等待过期，不能宣称本机取消一定已在服务端撤销；本地取消后手机确认的迟到结果也不能自动恢复本机连接。

POST unlink先完成本机凭据删除与断开，结束为unpaired；若本机删除失败，不能返回成功。服务器撤销通知是best-effort，不改变本地解绑完成的真实性：remote-hub.v2现有设备撤销需要owner浏览器会话，设备Bearer不是该授权；本轮不新增设备自撤销接口、线路帧或暗中转交浏览器Cookie。只有已有合法通知途径时尝试；离线或没有可用授权时可保留lastErrorCode（REMOTE_SERVER_UNREACHABLE/REMOTE_AUTH_REQUIRED），提示服务端撤销未确认，不谎称已全局撤销。P1的正常owner设备撤销入口保持原样。

已有remote对话在解绑后仍为remote，本机只读。LocalConversationView.authority是可选字段，旧记录缺省视为local；这种兼容默认绝不能用于把已持久标记remote的对话降级。P2必须在本地写入口执行权威检查；未来如何接续已解绑remote对话另行设计，本版不自动迁移/重放。

P3-B须使用现有v1 Gateway/桌面壳提供的本机鉴权能力；不能假定v2的浏览器Cookie自动获得v1权限，更不能为了配对把Hub Token塞进JSON或前端持久化存储。本轮只冻结本机配对界面的接口，不修改既有认证方式。
