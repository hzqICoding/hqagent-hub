# PI Runtime 契约（PI-P0 / D53）

包版本 **0.11.1**（补冻1）；线路仍为 **wireRevision 5**；服务端支持 **[1,2,3,4,5]**。
基线：PI适配方案 v0.2。第一期调度、安全与图片；第二期原生会话读取、导入与续接。
本文件同时冻结两期类型，不宣称第二期读取器或第一期 Runtime 已实现。无新增 HTTP 路由。

## 1. 冻结线与升级

`NativeAgentType` 原 claude/codex 被线路3、4递归引用，直接加 pi 会改变旧报文接受域。
因此保留该类型与所有线路1–4引用闭包，新增 `RuntimeNativeAgentType=claude|codex|pi`。
`remote-pi.json` 中独立的 `RemoteV5*` / `RemoteWire5*` 为完整修订5 codec，包含修订4全部消息种类；
旧字段类型可直接复用，凡变更的枚举、原生索引、格式、图片目标和catalog均引用新定义。
不采用放宽 additionalProperties 或在旧帧上改 wireRevision 的方式复用数据。

4→5复用R1.5/R3/R1.6的双向升级栅栏：旧修订在途命令已终结，Worker与Server可靠队列已连续ACK并应用，
持久化双方修订切换事实后启用5。结构化 `unconfirmed` 是控制尝试的终态，可使栅栏推进，**不证明执行停止**；
残留执行仍依D41保护。Worker周期探测（约30秒加抖动），不只在启动时探测。hello包版本只诊断，协商以线路为准。
不改旧seq/hash/epoch/grant，不将旧报文改成5重放。服务端升级窗口至少并存N/N−1，本次登记支持全部1–5。

未完成5协商时，PI关联的场景catalog、PI原生索引、PI会话/运行/消息/审批投影和图片能力不向旧线路发送；
电脑仍可按本机能力使用PI，界面提示“等待远程线路升级”，持久记录补传意图，升级后完整补传。
PI场景指任一角色实际绑定PI（含后备链可能选择PI）；不能以catalog旧缓存或Agent ID字符串可通过校验为由绕过门禁。
无法隔离PI相关数据的完整快照必须延迟，不截掉真实busy集合后宣称完整。旧线路可继续同步其原有资源和对账。
已产生修订5记录后不得未经完整降级栅栏降回4；断线重连仍使用持久修订，不能丢弃5的未确认事件。

### HTTP旧客户端

旧本机v1/v2及云端浏览器可能严格校验枚举，不能默认向它们发送pi。三个OpenAPI均声明可选请求头
`X-HQ-Client-Features: pi-v1`。这是**解码/展示能力声明**，不替代认证、审批、配额或模型费用确认。
缺省投影保持0.10.1：不返回PI实例/场景/对话/原生索引及其关联运行、消息、审批、能力；
不带新增guard/模型绑定/格式诊断字段。直接寻址PI资源返回既有NOT_FOUND；不能伪称claude/codex。
新客户端必须在首次列表/快照、写操作及轮询中一致携带该头。既有非PI流程与认证不变。
列表和事件游标绑定能力集，切换能力后重新取快照；仅本机 `/api/v1/auth/ws-ticket` 签发时将能力集绑定到一次性ticket，
流式事件使用该投影，不能收到HTTP过滤后的资源又从事件中泄露。跳过展示项仍推进扫描游标，不能永远卡在PI事件上。
云端没有浏览器WS ticket接口，云端P1只绑定HTTP列表/事件游标及其请求能力集；本机ticket属于Hub/P2。
Header不能通过服务器猜测User-Agent或包版本代替；旧端收到正常非PI数据不需升级。
HTTP兼容窗口保留N/N−1既有请求形状；本次是可选能力扩展，旧枚举结果保持原域。

## 2. 实例与模型选择器

Adapter ID沿开放字符串使用 `pi`，实例ID仍由Hub产生（示例 local.pi.synthetic）；厂商不绑定职责。
`AgentTaskSpec`、Adapter失败/审批/取消端口、RoleId、TaskStatus和D40身份链不增加分支或Attempt。
`AdapterIntegrationKind=cli_stream` 用于受控Node RPC进程；启动不经过shell，不把npm shim当可执行文件硬跑。

PI的**同一个 modelId 标量**编码为 `provider/modelId`，在**第一个斜线**处分割：

| 用途 | 选择器示例 | 传给PI的provider | 传给PI的model |
| --- | --- | --- | --- |
| 规划/审核建议 | `1aicode/deepseek/deepseek-v4-pro` | `1aicode` | `deepseek/deepseek-v4-pro` |
| 执行建议 | `1aicode/deepseek/deepseek-v4-flash` | `1aicode` | `deepseek/deepseek-v4-flash` |
| 看图建议 | `1aicode/deepseek/deepseek-v4-flash-vision-exp` | `1aicode` | `deepseek/deepseek-v4-flash-vision-exp` |

`PiModelSelection`约束该编码；角色modelId、LocalAgentModel.id、AgentTaskSpec.modelId、验证作业modelId、
修订5角色/原生图片能力中的modelId完全一致。不另建含渠道信息的Provider配置接口。
使用区分大小写的精确匹配；拒绝空段、`.`/`..`、URL、文件路径、内嵌认证、不属于本机
`get_available_models`清单的provider/model组合；不能用模型名后缀或latest模糊匹配。
默认建议不是强制配置，不存在就显示不可用，不自动下载/安装/订阅或切换到别的provider。
未传modelId代表本机默认模型；先取得实际provider/model并纳入targetRevision、catalog capabilityRevision和验证绑定，
默认值变化即失效。验证键覆盖实例、CLI版本、配置指纹、准确模型及transport，不跨角色模型复用旧通过记录。
本机PI自行使用本机凭据；Hub/服务器协议中没有模型密钥、渠道URL、环境变量值或原始配置文件。
`LocalAgentModel.efforts`仅使用当前PI/模型实际提供的选项；无法验证时返回空列表，不能照搬其它Runtime的推理等级。
修订5生产者必须在catalog.runtimes列出PI实际候选实例并提供guard；缺省视为unverified，不是允许启动。

## 3. 图片与实际传输

标识 `PiImageTransport=pi-rpc-images-v1`。Adapter在附件下载、大小/hash核对及批准之后读取受控图片，
构造PI RPC `prompt.images=[{type:"image",data:<base64>,mimeType:<detected type>}]`。
这只发生在**本机Adapter→PI stdio**，Worker↔Server仍仅清单。普通文件保持D52本机安全路径输入。
CLI入口支持、Runtime实现、实际五probe验证三层不混同。方案的单次图片实测仅证明入口，
在当前实例/CLI/model/transport完成 new、resume、mixed-five、cancel、error 之前，catalog为unknown/unsupported，
P1/P2/P3发送前均拒绝图片（AGENT_IMAGE_UNSUPPORTED）；不得由模型名包含vision推断supported。
复用0.10.1本机验证矩阵与作业、显式acknowledgeModelUsage、取消、互斥和失效语义，不增加云端付费入口。
`RuntimeRoleImageCapability` / `RuntimeNativeImageCapability`追加精确agentType/agentId/modelId/transport，
modelId缺省仅表示默认；缺少可核对的实例绑定时不得给PI支持结论。catalog只结论，绝无probe模型输出。
原生导入绑定在PI内切换模型后，重新get_state核对并使旧能力失效，不能拿看图模型的验证给纯文本模型使用。

## 4. hub-guard 与审批

首期采用**自有进程stdin/stdout的RPC extension UI对话**，无需新HTTP、云端消息类型或监听端口。
本机安装包只读核对：PI 1.0.1 `dist/cli/args.js`声明 `--no-extensions` 关闭自动发现/内置扩展，显式`-e`仍可加载。
启动必须使用该隔离参数并且只显式加载Hub安装目录中的固定hub-guard扩展；不加载用户/项目扩展，不运行它们来“检查是否安全”。
适配器先核对已支持CLI版本、扩展内容hash、启动参数/进程及工具清单，再接受握手。
此开关对其它版本、SDK启动方式的效果必须另有验证；不能确认时即guard unverified/blocked并拒绝启动任务，
包括只读任务。仅guard自报ready不足以证明隔离。

`AgentView.guard`和修订5 catalog.runtimes[].guard只含 `RuntimeGuardView` 的安全状态、原因、版本与时间。
状态ready必须isolation=hub_extension_only、reasons=[]；存在未受控扩展返回PI_UNCONTROLLED_EXTENSIONS，
保护未加载/超时/策略不可用返回PI_GUARD_UNAVAILABLE。不得给手机扩展源码、扩展路径或原始参数。

### 内部消息

扩展使用 `ctx.ui.editor(title, prefill)` 的等待式RPC入口：

| title（精确值） | prefill UTF-8 JSON DTO | 响应value |
| --- | --- | --- |
| `hqagent.guard.handshake.v1` | PiGuardHandshake | `ready`，或cancelled拒绝 |
| `hqagent.guard.check.v1` | PiGuardCheckInput | PiGuardDecision 的JSON字符串，或cancelled阻止 |

底层沿PI `extension_ui_request{id,method:"editor",title,prefill}` / `extension_ui_response{id,value|cancelled}`。
只处理本适配器独占进程的请求，外部UI请求不能变成人工批准；握手限10秒，调用判定/人工审批总上限5分钟，
超时、EOF、错误、未知版本或未完成握手一律block。超时要取消对应待处理审批，迟到允许答复不可恢复执行。
不把内部消息发到浏览器作为自由文本或工具输出；Hub将它映射为既有安全活动/审批事件。

`tool_call`输入只在本机内部通道传递：argumentsJson为精确工具参数JSON字符串，UTF-8≤64KiB，
拒绝重复key、非object、非有限数值、过大输入；argumentsSha256是原始UTF-8字节hash。
Hub重新计算hash，解析后复用PathGuard及shell解析；不使用字符串includes伪装目录/命令安全。
请求绑定sessionId/nodeId/toolCallId、进程世代、policyRevision、toolInventorySha256及期限。
工具清单、策略、cwd、附件许可或参数有任何变化，旧批准失效并重新校验。
返回allow前再次核对结构化批准及原始参数不变；扩展消费精确requestId一次，检查hash/session/call/policy与期限，
不能把另一调用的批准或timeout后的答复套用。审批时使用已有externalRequestId→approvalId映射；
批准仅解决dangerous action许可，不会覆盖path或只读限制。

只读场景通过setActiveTools限制到经核实的read/grep/find/ls；bash/edit/write不启用。
嵌套tool_call同样校验；未登记工具、动态工具变化、模型可写安装扩展、未知执行语法均阻止。
准确的输入附件是只读例外，不扩大父目录；禁止读模型凭据或Hub凭据路径。复杂shell变量/管道/重定向无法安全解析就拒绝。
本地进程内扩展不是OS沙箱；允许的命令仍必须沿Hub既有审批与进程权限边界。不得宣称安装此扩展后任意不可信代码都被隔离。

动作级拒绝使用PI_TOOL_CALL_BLOCKED，结构化PiGuardReason记录path_outside_scope、unsupported_shell、
approval_rejected/expired、read_only_tool等；公开只给代码和安全说明。AdapterFailure沿既有kind：
guard/extension失败=capability_missing，路径违反=path_violation，其余受阻调用=agent_error，不自动回退到无guard运行。
三项新错误进入HTTP公共注册表和RemoteWire5ErrorCode，绝不进入旧1–4错误域；多数发生在异步执行结果，不新增HTTP路由。
高风险git_push/deploy/delete/db_migrate及Worker策略动作远程不可approve，手机仍能reject；D50取消/拒绝豁免不变。

## 5. 会话、完成与取消

RPC get_state取得sessionId与sessionFile，两者绑定在本机，sessionFile不上传。
精确续接用 switch_session{sessionPath:已验证绑定路径}，核对返回sessionId及真实文件身份；
路径/ID不一致、CLI失败、会话变化均明确失败，不用latest、不搜索近似标题、不悄悄新建。
模型prompt必须在guard握手、绑定、附件准备及grant（远程时）之后，导入/发现/模型列表查询不调用模型。
agent_end只是底层一次run结束；只有对应agent_settled（无待续自动工作）或确证进程终止才可报告停止。
abort RPC应答本身不能报告取消成功；继续等待settled，超时走现有进程组终止与D41证据路径。
transport丢失不能当停止，保留executionMayStillBeRunning/orphanProcessIds/recoveryRequired，
不得用“任务失败”猜测无进程。同一原生绑定唯一写锁包括续接、验证和临时会话操作。

## 6. 第二期原生格式与分支

冻结readerId **pi.jsonl.v3.tree** / PiNativeFormatProfile；版本是会话header.version=3，**不是CLI包版本**。
当前只读证据来自安装的1.0.1 `session-manager.d.ts/.js`，没有读取真实会话正文或私有models.json。
正式reader应在其支持版本/结构测试通过后声明readable；第一期可返回unsupported/reader_not_implemented。
未知版本/结构、损坏记录/树、无法判断分支分别使用RuntimeNativeUnsupportedReason，安全reason不能包含正文或路径。

索引按R3仅终端直接创建且cwd属于已登记workspace：session header的id为精确vendor ID，cwd用于本机归属校验，
timestamp为createdAt；完整记录中的最新合法时间用于updatedAt，异常时间不伪造排序。
Hub索引ID仍为本机opaque ID，文件真实路径、dev/inode或Windows文件ID映射只留本机。
标题优先合法session_info.name，否则所选分支首条用户文本；先过滤凭据/私有内容，再截至120字符。
排除Hub管理的临时验证会话与重复导入，不能将一次目录扫描失败解释为全部删除。

### 当前分支线性化（重开可恢复的已落盘分支）

PI1.0.1 `_buildIndex()`按文件顺序把最后一条非header entry设为leafId；`branch()`只改内存指针，
无后续持久entry时该指针不在文件中。因此读取器只承诺**从磁盘重开可恢复的分支**，
不宣称知道仍活跃终端中的未保存分支选择。界面标注“已保存分支”；活跃不明仍只读。
闭合文件快照先完整验证所有entry ID唯一、parentId存在/无环、时间与header一致、选中链到null终止；
选最后一条完整有效非header记录，沿parentId回溯，再反转为根到叶顺序。分支可能从null开始新根，不强行合并多个根。
有损坏/截断末行时不直接选上一行并允许导入：返回invalid_record或NATIVE_SESSION_CHANGED，刷新后再确认。
不按时间猜最新叶、不拼接旁支、不取整个文件的message顺序；branch_summary的fromId不是额外需要遍历的parent。

所选链只输出R3规范化用户/助手公开text和安全tool_summary；message.role/content按识别的结构读取。
context_edit按选中链的后续编辑覆盖目标内容，replacement=null隐藏该目标；不能导出已被编辑隐藏的旧文本。
compaction、branch_summary、systemMessage、thinking、custom/扩展私有数据默认不作为公开消息；
不从压缩摘要“还原”不存在历史；未知可见消息结构报告unsupported_structure，而不是猜测成正文。
完整脱敏的所选终端分支历史在导入前后保持一致，不只导出模型当前压缩上下文。
分页sourceRevision包含header/记录快照/叶ID/过滤版本；同一页不混合两条分支。

未知活跃状态按活跃只读，用户明确terminalClosedConfirmed留审计后才可导入/续接，Hub再次检查对应进程/文件变化。
导入沿R3同一精确绑定唯一写锁、不启模型、原子绑定与完整历史；本机201和云端grant路径共享规则。
导入后conversationKind=native、agentType=pi，不填虚假scene/roles；后续只使用绑定ID/文件的精确续接。
同步、可见性、D50暂停、D51按需读取不落云端正文、D52附件与删除规则全复用。

## 7. 接口与实施验收

本机继续既有Agent发现/列表、GET agents/{agentId}/models、场景编辑、图片验证作业、原生列表/详情/messages/imports；
云端继续catalog、native-sessions、对话/消息/运行/审批。没有新路由，没有PAT权限扩张。
HTTP和事件必须统一pi-v1投影；cookie/Bearer/CSRF/Origin/Idempotency-Key、no-store、requestId沿api-guide。
模型清单在本机获取；服务器只认证、中转和保存允许的投影，绝不调用PI、读取凭据或承担订阅/安装。

P2必须实际验证：无shell启动、guard握手与超时fail-closed、未知扩展被禁用、嵌套/变参/过期批准不可绕过、
只读工具限制、abort到settled/强杀证据、精确续接、模型切换失效、五项图片验证、树旁支/编辑/截断/活跃并发。
P1必须验证：1–4同一旧样本接受/拒绝域不变、4→5栅栏、离线/暂停/安全取消、旧客户端事件不收到PI。
前端默认模型建议必须来自可用列表，显示保护状态和图片验证，而非提供忽略风险按钮。
这些是下游业务与真CLI验收要求；本包只做合成Contract Fixture和协议测试，不作模型调用实测声明。

## 8. 补冻1：修订5审批事实到浏览器事件的投影

### 8.1 版本与边界

0.11.0的RemoteBrowserEvent只接受旧线路形状的worker.event，直接嵌入修订5审批不能通过校验。
本补冻0.11.1只扩展HTTP事件联合：新增 `RemoteBrowserPiApprovalEvent` 变体，并以
`RemoteBrowserLegacyApprovalEvent` 命名已有旧形状的**浏览器专用投影**。无新增HTTP路由、错误码或Worker帧，
wireRevision仍为5；所有线路1–5及递归引用保持不变。新变体只给pi-v1，因此无需提高线路号或更换能力声明。

Server先校验/持久化原Worker事实并更新审批视图，再生成或读取浏览器投影，二者职责不同。
**Inbox/可靠Outbox中的原wireRevision、seq、epoch、hash、ACK、grant及审计事实绝不改写**。
下文浏览器兼容对象的wireRevision=2只是旧浏览器解码形状标签，并非声称Worker使用了修订2。
只允许在browser projection层新建副本；禁止把投影重新送入Worker codec入站、可靠重放或计算源事实hash。

### 8.2 审批投影与可见性

按认证owner、当前设备/store、对话归属及visibility先过滤，再按可信会话/执行绑定判定PI关联：
沿§1的PI场景/原生及历史绑定标记；不能根据浏览器参数、标题、是否包含pi字符串或仅审批action猜测。
无法证明非PI的绑定不得按非PI公开；保留待核实/按既有PI保守门禁处理，不能偷偷将pi改称其它Runtime。

| 源事实 | 浏览器能力 | 发出的浏览器事件 |
| --- | --- | --- |
| 非PI approval.state_changed（修订5） | 无pi-v1或有pi-v1 | RemoteBrowserLegacyApprovalEvent：外层worker.event，内层approval.state_changed且兼容标签wireRevision=2 |
| PI相关 approval.state_changed（修订5） | pi-v1 | RemoteBrowserPiApprovalEvent：外层worker.event，内层RemoteV5ApprovalEvent，wireRevision=5 |
| PI相关事件 | 无pi-v1 | 无事件、无替代conversation.updated、无快照刷新提示；推进内部扫描位置及不透明nextServerCursor |
| 其它owner/pc_only/已删除且不可见资源 | 任意 | 依既有可见性/删除门禁跳过，不发泄露资源ID的替代通知 |

非PI正常审批**不得只发conversation.updated，也不得跳过**，否则现有前端不会刷新审批。
RemoteBrowserLegacyApprovalEvent结构是旧RemoteBrowserV2WorkerEvent的子集，冻结0.10.1客户端无需修改即可处理；
本次不把新字段混入旧形状。新客户端对PI变体仍走worker.event→approval.state_changed，处理语义一致。
pending按approvalId upsert；approved/rejected/expired移除待处理项，不把command.completed等同审批消耗。

投影字段映射（只读事实副本，不从展示结果反向修改Worker状态）：

| 字段 | 来源/处理 |
| --- | --- |
| 外层type | worker.event |
| serverCursor / recordedAt | Server owner+能力集作用域的不透明事件游标/记录时间；不使用Worker seq作为游标 |
| 内层type | 保持approval.state_changed |
| wireRevision | 非PI旧形状固定2；PI新变体保留5；仅浏览器兼容标签 |
| eventId、workerId、workerStoreId、workerEpoch、seq、occurredAt | 保留来源诊断字段；seq不用于浏览器排序/断点，缺口不解释为PI数量或事件类别 |
| conversationId | 由已验证owner/worker/store下的本机ID映射成公共对话ID |
| payload.approvalId | 同一作用域下的公共审批ID，与GET approval/snapshot/decisions一致 |
| payload.resultRef | runId、executionTaskId、nodeId、sessionId等按既有命名空间规则映射；无对应资源不能伪造关联 |
| action、riskLevel、status、requestedAt、expiresAt、remoteApprovalAllowed、workerPolicyRevision | 保留真实值及类型；不得为投影放宽审批权限、延期或把终态改pending |
| targetSummary | 既有脱敏摘要，不回显原始工具参数、路径、凭据或私有推理 |
| denialCode | PI新变体保留线路5错误；非PI按下述兼容规则映射 |

denialCode为空则仍缺省；非PI且值在RemoteWire2ErrorCode中则原样保留。
对于已确认非PI、remoteApprovalAllowed=false且denialCode为旧域无法表示的拒绝原因，浏览器副本使用
`REMOTE_APPROVAL_FORBIDDEN`，**原原因完整保留在原事实及有权限的GET审批/快照视图中**。
这是明确的保守拒绝投影，不是删除错误后宣称可批准。不得改remoteApprovalAllowed为true，或把PI专用错误误分到非PI后掩盖。
不一致状态（如允许批准同时带禁止原因）、失配资源引用等按既有事实校验拒绝/对账，不“修复”为成功审批。

### 8.3 修订5其余事件的投影矩阵

以下首先执行与审批相同的owner/visibility/pi-v1过滤。任何PI事件被过滤时都不能通过替代事件、计数、原因或ID通知旧端其存在。
源事实仍走可靠ACK；浏览器扫描游标可跨过内部/隐藏记录，返回可见项的数量、hasMore只描述可见投影，
不新增hiddenCount、原始偏移或被跳过类型；不透明游标不可被调用方解码成内部序号。

| 修订5事件组 | 浏览器投影规则 |
| --- | --- |
| command.received / accepted / rejected / completed / failed / control_result | 更新既有RemoteCommandView后发command.updated，携真实控制结果与错误；不直接塞入worker.event的旧命令联合 |
| sync.conversation.upserted | conversation.updated，公共对话视图按能力集裁剪 |
| sync.message.segment | 收齐/校验/应用完整消息后发顶层message.appended；不发布未拼齐片段 |
| sync.run.state / run.state_changed | 先应用/核对既有运行投影；可表示时发旧worker.event形状的对应sync.run.state/run.state_changed（标签2，映射公共引用），不伪造状态。PI关联也先检查pi-v1 |
| run.progress | 脱敏message与映射resultRef后发旧worker.event/run.progress形状（标签2） |
| capability.changed | 更新完整catalog；旧形状通知仅用RemoteV2CatalogEvent已知字段，去PI资源和新字段。pi-v1客户端也通过现有GET catalog取得完整能力；通知不包含任何PI内容时可共用旧形状 |
| sync.busy.snapshot / sync.backfill.progress | Server应用完整集合/批次；既有可见conversation.updated用于busy/同步元数据，不能因此宣称审批已刷新 |
| sync.conversation.deleted / sync.reset | 既有conversation.deleted / store.reset，按既有删除语义和能力集过滤，不附隐藏PI对象的ID或数量 |
| native.index.upserted / deleted / native.closure.confirmed | 保存允许的索引/审计，既有原生列表刷新/轮询获取；不直接放入旧worker.event，不上传未导入正文 |
| conversation.skip_recorded | 完成命令序号对账；可发原有兼容通知（标签2）或不发布浏览器事件，不制造执行成功 |
| query.result.segment / query.failed、握手/心跳、ACK、grant、conversation.gap/skip、events.omitted、sync.content.redaction及下行命令 | 仅对应传输、在线查询、grant/删除栅栏通道；不转为浏览器worker.event，查询结果仍不得持久化 |

禁止通用地给任意修订5帧换成2并尝试发送。上述旧形状必须逐字段白名单构造、映射与校验；例如catalog不能原样塞入新runtimes，命令新控制证据不能被截断。
仅PI变化且旧客户端可见catalog/busy投影没有变化时，不向旧端发送因此产生的替代通知。
对已获授权且可见、确实无法通过旧形状安全表达的状态事件：使用既有公共view通知（表中对应类型）；
若没有合适通知，返回既有 `REMOTE_CURSOR_EXPIRED`（410）要求重新快照对账，**不得静默跳过待处理审批**。
不新增未知顶层事件去赌旧前端的fallback；尤其不能用conversation.updated冒充审批刷新。
410重建取同一已应用水位的快照与新serverCursor，包含当前pending且未过期的审批，之后只接水位之后的事件，避免死循环和遗漏。
只有隐藏/内部事件可无通知跳过并推进游标；不可见PI事件不触发410或快照提示。

### 8.4 下游验收与职责

P1：在浏览器投影层按能力集选择审批变体，审批视图与可恢复投影记录原子提交；过滤先于投影/回放，不能因请求头改变源Inbox。
修复Q2的临时conversation.updated方案；测试非PI+无头/有头都收到pending及三个终态、PI无头完全不可见、
PI有头接受新错误、断线游标回放/快照恢复、公共ID可用于批准/拒绝、原wire5 hash/seq/ACK完全未变。
还要覆盖降级拒绝码、同一worker混合PI/非PI、owner/pc_only/删除、隐藏记录跨页推进且不报告隐藏数量。

P3：更新生成联合以接受RemoteBrowserPiApprovalEvent，复用已有approval.state_changed upsert/删除逻辑；
pi-v1仍是显式解码能力，未知结构走已规定快照对账。非PI审批使用旧形状，不要求旧前端先改代码才能收到。
P2：无Worker线路或审批事实变更；本机ticket能力集绑定仍由Hub负责，云端P1无需新增票据接口。
