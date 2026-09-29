# R3 / 0.9.0：原生会话与授权根目录项目登记

基线：手机远程接入方案 v0.5 §8、§8.3a、§13，D40–D51。服务端是通信和副本服务，不调用模型、不持有模型凭据。本文新增 wireRevision 3，修订 1/2 Schema、Fixture 及其引用闭包不变。所有样例都是合成数据。

## 1. 修订、身份与升级

CODECS[3] 使用 `RemoteV3WorkerOutboundFrame`、`RemoteV3ServerOutboundFrame`、`RemoteV3CommandEnvelope`。独立复制修订 2 帧再扩展；不把旧严格类型改成接受新字段。`RemoteWire3ErrorCode` 固定本次线路可用错误集合，不包含 D50 的 HTTP-only 错误；未来注册表增加值不得自动扩展任何已冻结线路。服务端本次支持 **[1,2,3]**，保留 1 是历史对账需要；N/N−1 至少保留 3/2 的升级窗口，不把这个要求误当成强制移除 1。

hello 只以整数 wireRevision 协商，protocolVersion=0.9.0 仅诊断；15s 心跳、45s 判离线、首帧10s、每帧序列化 UTF-8 ≤256KiB 不变。新R3功能要求当前连接为3；旧功能仍可在2运行，新功能不得降级。2→3沿用R1.5双向升级栅栏：停止创建旧线路命令，核实双方旧命令最终回执、Outbox事件与连续ACK，持久化双方水位后切换。保留原修订、epoch、seq、摘要，不改写旧报文；不能只凭电脑Outbox暂空就切换。存在未明副作用时继续旧线路对账。

Worker原生索引ID是不透明 `nativeSessionId`，绑定 Runtime实例/数据根引用/Agent/精确原生ID及规范化cwd。供应商原生ID保存在电脑绑定中，不要求公开它，更不能用路径或`latest`充当ID。云端按(owner,workerId,workerStoreId,localNativeId)映射公开ID；workspace/conversation同理。HTTP参数只收公开ID，Worker帧只收已映射本机ID。查询结果在校验完整后才映射成公开ID。跨设备/store不可复用游标、确认或查询关联ID。

## 2. 发现与版本化读取插件

只发现**用户在终端直接开启、真实cwd在已登记workspace内**的会话。多个workspace重叠时选择最长真实路径前缀，不能字符串startswith误匹配兄弟目录。注册目录的访问权限、真实路径和文件身份都重新校验；记录文件仅允许来自对应Runtime配置的数据根，不接受手机指定transcript路径。排除Hub已管理绑定、sidechain/subagent和已确认的非终端来源。只知道“文件存在”不能证明终端来源；来源不能确认时本机诊断，不上传为符合范围的会话。

读取插件优先使用其**实际探测可用**的官方历史接口；文件fallback在Runtime插件内，不写进Worker核心。history.list/read/adopt 是能力接口，本包不声称这些插件已实现。读取必须有版本化、合成样例测试过的readerId/profile；CLI semver或事件结构不在已测集合时为unsupported，不依版本大小猜兼容。安全信封能确认ID/cwd时仍上报不可读索引与脱敏reason；连cwd/来源也确认不了则不上传，电脑显示读取能力缺口。

2026-09-28只读抽查本机每家最近3个JSONL文件，最多1600行/文件及约6MiB，**仅看键、类型、结构标签和CLI版本**，未输出/保存文件名、ID、cwd、消息或工具参数。观察不是插件已验证支持清单：

| 来源 | 观察到的结构 | 索引与规范化依据 |
| --- | --- | --- |
| Claude Code | 记录sessionId/cwd/timestamp/version/type/uuid/parentUuid/isSidechain/isMeta；message.role/content（string或块数组）；块有text/tool_use/tool_result/thinking；观察版本2.1.261、2.1.272、2.1.283 | 按已测profile取一致sessionId及cwd；主链uuid/parentUuid决定顺序，不能混合sidechain；取非meta user/assistant文本。没有从本次抽查证明终端来源，P2须补来源探测或官方接口证据，不能从目录名猜测 |
| Codex | session_meta.payload.id/cwd/timestamp/cli_version/source/originator；response_item中的message/role/content，input_text/output_text；独立reasoning/function_call/custom_tool_call等；观察版本0.153.4，source出现cli及vscode | 以session_meta确认精确ID/cwd；cli profile才属于本轮终端范围，vscode不得混入。以已测规范消息通道排序，不能把event_msg.agent_message和response_item.message重复计入 |

createdAt/updatedAt来自可靠源时间；源不提供会话时间时可用记录文件stat，但插件须记录其依据，不能伪造CLI时间。内容单条缺时间时省略createdAt。sourceRevision是读取插件生成的不可逆版本摘要，包含文件身份、有效切点与版本信息，不能只用秒级mtime；变化时indexVersion递增。文件写到一半只读取已验证完整记录，未知/损坏结构明确unsupported或NATIVE_SESSION_CHANGED，不能吞掉后报空历史。

标题取首条真正用户文本，经同一脱敏后截断至120个Unicode码点；没有安全文本用“原生会话”。**标题本身是会被持久化的索引内容**，不是零内容上传。文件路径、工具参数和私有推理不得作标题。保留在索引中的仅为ID、项目、Agent、时间、短标题、版本、可读性、活跃状态，不上传正文。

## 3. 活跃状态、确认与写互斥

NativeActivity：unknown / likely_active / closed_confirmed。结构化证据包含observedAt、processMatch（present/absent/unknown）、recentlyModified。匹配会话的存活CLI、最近记录变化等支持likely_active；仅发现同名CLI进程不等于精确匹配，证据不足为unknown。**unknown按活跃，只读；mtime安静或没有看到进程不自动变closed_confirmed。**

手机imports必须带terminalClosedConfirmed=true、expectedIndexVersion、sourceRevision。服务端验证当前索引与显式确认，生成confirmationId/confirmedAt/requestId；电脑在收件和grant后再验证绑定、版本、源文件及进程。用户声明允许解除“不知道终端是否关闭”的保守只读，但不能覆盖已发现的精确活跃进程、确认后源变化或工具内写锁。拒绝分别为NATIVE_SESSION_ACTIVE/CHANGED/WRITER_CONFLICT。此确认不是操作系统互斥，不承诺阻止用户在外部重新打开终端。

电脑只有检查通过才持久化closed_confirmed与 `native.closure.confirmed` 审计事件；事件含确认及不透明ID，不含内容。每次开始写仍检查进程与源。由本工具已核实写入的连续变化更新绑定水位；未经本工具归因的变化使旧确认失效。后续需要重新确认时，Hub对话的nativeActivity/nativeSourceRevision用于展示，发送消息可带nativeConfirmation={terminalClosedConfirmed:true,sourceRevision}，由服务端重新生成审计确认并放入修订3 run.submit。已有效的确认可复用，不能无限复用过期证据。

所有电脑入口共用持久绑定键(Runtime实例、数据根、Agent、精确原生ID)的写互斥，包含手机、桌面、重试和恢复，最多一个本工具启动的写进程。锁不能只锁conversationId，否则重复导入可启动两个写者。崩溃恢复先inspect/核对句柄，unknown不能直接释放并另起进程；遵循D41结构化取消/未确认结果，不解析报错文本。

## 4. 导入与接续

`native.import`与`workspace.register`均为**无conversationSeq的资源命令**，按30秒deliverBy→provisional command.received→持久grant→正式accepted→completed/failed流程执行。修订3这些回执/grant的conversationId可省略，仅资源命令允许省略；原对话命令仍必须匹配。校验commandId/digest/store/receivedEventId不变，不虚构对话、Run、Task或序号。HTTP202用RemoteResourceQueuedReceipt；既有GET /commands/{commandId}可对账。

导入本身不启动CLI或模型：在电脑准备经校验的完整历史快照，检查配额、过滤和版本，保存消息、精确会话绑定、唯一导入映射及同步意图。失败不得发布半个“导入完成”的对话；大历史可本机分批暂存，最终事务发布，崩溃按commandId恢复。不可把送达30秒当作导入计算截止时间；只有未获许可才受送达失败规则。重复导入同一精确绑定返回既有结果，不生成第二个Hub对话；删除后不能未经新的用户意图复活旧对话。

成功回执resourceRef含workspaceId/conversationId/nativeSessionId，resultStatus=confirmed、controlResult.evidence=metadata_committed；没有运行就没有resultRef.runId。Server只从电脑同步得到对话及全文，completed是电脑导入已提交，不等于云端历史已经全部补齐。沿R1.5补传进度完成标记展示同步状态。`native.index.deleted(reason=imported)`删除未导入索引（含残留内容重放），不删除新Hub对话；终端源文件绝不删除。

LocalConversationView、RemoteConversationView及RemoteV3SyncConversation用conversationKind（缺省scenario）、agentType、nativeSessionId区分。native省略sceneId/sceneVersion；LocalRunView原sceneSnapshot对native可省略，新增可选conversationKind/agentType。场景对话仍提供全部原场景字段；不填虚假场景或多角色。Task/Run继续D40身份映射，没引入Attempt。

已导入对话发送仍走run.submit，修订3的RemoteV3RunSubmitPayload支持无场景native分支。Worker核对三类字段与绑定一致；native只能sessionMode=continue，精确会话无法恢复返回SESSION_NOT_RESUMABLE，不静默创建新上下文。“接着说”在前端是先导入成功/同步对话，再发送现有消息入口；202导入不代表可以跳过绑定、检查或grant。

## 5. 内容规范化与可靠索引同步

原生历史只保留用户/助手公开文本和安全tool_summary。丢弃系统/developer指令、thinking/reasoning/redacted_thinking/encrypted_content、隐藏分析；工具只给已识别工具名及安全状态摘要，不传播原始命令、输入、stdout、路径、审批参数或附件字节。旧终端审批只作历史摘要，绝不重建为可消费审批。未知块不猜测成文本，插件报告读取缺口。

复用电脑现有`runtime/remote/security.py::safe_text`及`adapters/events.py`私有块过滤语义：已知设备/Hub/模型凭据、Authorization/Bearer、私钥、环境赋值、token/key/password/secret等全部先过滤再分段/截标题。结构化过滤在文本拼接前，字符串过滤在完整消息上做，不能按每段处理使跨段凭据漏出。读取器额外排除嵌套工具参数和未闭合私有块。过滤不能保证识别所有用户自写秘密，协议不承诺“任意文本绝无秘密”；不能以此为由发送已知凭据。查询、导入和标题走同一条过滤管线。

`native.index.upserted/deleted`有workerStoreId/workerEpoch/seq/syncGeneration，走持久Outbox、服务端Inbox和连续ACK。只有**索引**走此通道，正文读取不走。版本冲突/倒序不能覆盖新索引。原生索引历史沿R1.5每批≤100事件/1MiB、未确认≤16帧/1MiB窗口，sync.backfill.progress覆盖捕获水位内Hub内容及原生索引，所有之前批次连续ACK后才complete。

sync.reset同时删除Hub副本和所有原生索引；设备删除/撤销同样；workspace移除逐个生成索引deleted及目录更新。电脑必须确认是移除而非暂时扫描失败，不能将扫描异常视为空集合全部删掉。重新启用同步用新generation重扫；导入映射仍在电脑，不能再次上传为未导入索引。

修订3删除覆盖额外允许native.index.upserted槽。native.index.deleted作为持久删除栅栏，ContentRedaction.nativeSessionId限定单个索引；不能同时给conversationId，也不能覆盖新Hub历史。reset可覆盖该store所有内容槽。审计确认、grant/执行事实永不作为内容槽删除。保留不含正文的哈希/seq/tombstone以防迟到旧索引复活；清理Server索引表、重放事件、缓存和查询内存。workspace移除也不再允许该会话的新查询或续接，已导入内容的保留服从既有Hub工作区移除规则，不臆造远程级联删除授权。

## 6. 在线临时查询：不落盘、不进入事件流

`query.native.messages`、`query.directory.list`带queryId、requestId、当前connectionId/workerEpoch、目标worker/store、expiresAt。固定10秒总期限（服务端开始受理起算，含拼装），同时每设备最多4个、每账号最多16个在途查询；超出REMOTE_RATE_LIMITED。不持久化查询结果，不给seq/eventId，不分配conversationSeq，不使用grant。断线立即REMOTE_DEVICE_OFFLINE，超时REMOTE_QUERY_TIMEOUT；Worker按hello时间界限校验到期，迟到/未知queryId/旧连接片段丢弃，不影响可靠事件ACK。

结果为NativeMessagePage或DirectoryListingPage的UTF-8 JSON，过滤完再序列化；≤1MiB，每段≤16000码点且UTF-8≤64000字节，每帧≤256KiB，最多128段。`query.result.segment`携segmentIndex/segmentCount/totalUtf8Bytes/contentSha256与完整关联身份及resultType。按字符边界分，不截断；所有段元数据一致，重复相同段幂等，冲突REMOTE_SYNC_CONFLICT并销毁缓存。收齐0..N−1、核对字节数/hash、反序列化到对应**强类型**并核对资源映射后才HTTP200；否则query.failed或请求失败，不把半页送到浏览器。错误必须脱敏、不得带源文本。每设备/账号按并发上限有界内存，停止/超时/撤销/reset时销毁buffer。

**禁止持久化**：服务端数据库、可靠Inbox/Outbox、浏览器增量事件、通用幂等响应缓存、日志/APM、反向代理磁盘buffer/cache均不得保存查询正文；按需读取者浏览器仅当前页内存，不存IndexedDB/localStorage/service-worker缓存。服务端与代理HTTP请求/响应正文采集关闭，代理buffer要配置为无磁盘溢出，Cache-Control:no-store不能替代这些配置。临时游标/选择令牌也不记录；服务器可持久化不含参数值/正文的requestId、operation、状态、错误码、耗时。

电脑可以保留本机源文件及读取快照/绑定元数据，它不属于云端正文持久化。Server重启丢查询关联，浏览器重发；不尝试恢复或重放旧结果。Worker读完和Server回HTTP前都再次校验设备、同步开关、workspace、可见性、根授权；重置后不把“刚读完”的旧内容返回。取消浏览器HTTP等待即可取消本机读取工作，清理关联；实现无需新增执行取消命令。

原生分页 `before` 是电脑签发、绑定源文件身份/sourceRevision、固定完整记录切点、过滤版本和15分钟期限的不透明游标。NativeReadInput.sourceRevision可选；首页由电脑捕获当前版本，带before时以电脑游标中的版本为准，Server不能把最新索引版本硬塞给旧页；同时提供时必须一致。缺省最新消息开始，消息倒序、同消息分段升序，limit按**消息片段**计≤100，页≤1MiB，hasMore时必须提供before。单条超页的消息跨页拆NativeMessagePart，浏览器按messageId/hash/段号收齐后才显示完整；不能强行截短长助手回复。追加记录不挪动既有页，变动已捕获前缀/文件轮换返回NATIVE_SESSION_CHANGED；换新首页后按稳定消息ID去重，不能混合不同sourceRevision的半条消息。tool_summary角色导入Hub时映射system公开摘要，不恢复执行指令。

## 7. 授权根目录与本机接口

电脑GET/PUT `/api/v1/remote/authorized-roots`（本机Bearer）及 `/api/v2/remote/authorized-roots`（本机Cookie）共用LocalAuthorizedRootsView/Input、CAS和本机既有Origin/幂等规则。默认version=1、roots=[]，最多32根。只有电脑本机可设置，不增加云端写根接口，云端Cookie/PAT不能调用本机路由。

PUT全量替换，existing rootId归属必须匹配；新增ID由电脑分配。根真实路径/授权改变递增根version；全局版本递增并事务撤销相关选择令牌。根删除后ID不复用。displayName长度≤120且不能只空白。配置与catalog同步意图原子提交。已登记项目不因根移除而注销，但未来目录浏览/登记立即失效。

catalog修订3与HTTP视图使用RemoteV3CatalogView，authorizedRoots只返回rootId/displayName/version，**不返回绝对根路径**。旧HTTP缺字段按空数组处理，修订3生产者总是填真实列表。原workspace.displayPath是既有已登记项目字段，不因此暴露未登记目录。手机拿到根标签不等于根仍授权，每次电脑检查。

## 8. 逐层浏览与登记安全

DirectoryListingInput只收rootId/rootVersion/directoryToken/cursor/limit，不收绝对或相对路径。省略directoryToken只可列根自身一层；结果目录条目仅name/isGitRepository/directoryToken，含当前目录token供选中登记。缺省50、最多100条，稳定文件夹名和本机目录身份排序，分页游标绑定目录快照/根版本，变化返回REMOTE_DIRECTORY_CHANGED而不是跳过条目。令牌绑定本机store、rootId/版本、真实目录身份、相对组件和15分钟期限；电脑认证加密/签名或本机查表，不允许客户端改路径后伪造。它是短期选择引用，绝非绕过当前账号/根授权的能力。

根和目标都先规范化再解析真实路径。Windows按文件系统语义统一大小写、分隔符与真实卷身份，不能用大小写敏感或纯字符串前缀比较。拒绝`..`、绝对注入、其它盘符、UNC、设备命名空间、ADS、驱动器相对路径、NUL及模糊尾部点/空格。解析symlink/junction/reparse点和可支持的目录快捷方式，最终路径必须在授权根内；无法安全解析明确拒绝，不执行快捷方式。`.lnk`是文件，本轮不枚举它为目录，也不返回任何文件列表。目录名仅作显示，不能直接信任成下次路径参数。

每次列当前目录、生成子目录令牌、消费选中令牌、grant后的登记都重校验；链接/目录替换要以句柄/稳定文件身份做TOCTOU防护，不能“检查一次再拼接路径”执行。越界返回REMOTE_PATH_OUTSIDE_ROOT；根未开放/移除REMOTE_ROOT_NOT_AUTHORIZED；过期/变更REMOTE_DIRECTORY_CHANGED。错误不回显真实路径。根移除立即使旧token与在途读取失效，不等待云端catalog更新。

登记调用电脑**相同**WorkspaceService验证/事务，允许非Git项目登记但canWrite=false，不暗中init-git、mkdir、clone或跑命令。同一真实目录已登记返回既有workspaceId，配套catalog可靠同步。若根在grant前移除拒绝；与本机移除/替换根在同一授权事务边界线性化。登记只写电脑注册信息，服务端不造workspace记录冒充成功。

## 9. HTTP、安全门禁、日志与兼容

六个新HTTP路由在remote-hub.v2定义，只接受Cookie；写POST保持Origin、CSRF、Idempotency-Key。PAT不扩权；native-sessions:read/import、directories:read、workspaces:create仅保留命名约定，**不加入可签发scope**。设备catalog沿已有devices:read可读根标签，不能因此获得目录浏览或原生内容。

目录POST虽然只读仍校验CSRF/幂等键；只保存账号作用域请求摘要和必要去重身份，不保存完整参数/结果。同键同摘要可重新查询，必须重新授权和校验期限；同键不同摘要IDEMPOTENCY_MISMATCH。不能走当前Service.replay的通用响应落库。imports/workspaces回执可重放命令元数据，不含历史内容或目录列表。请求ID响应头/信封一致；电脑目录操作也写无正文审计事件（requestId、operation、rootId、结果码），不将目录token/文件名/路径写入服务端请求日志。

优先级延续D50：认证/CSRF/归属与可见性→删除NOT_FOUND/撤销→对受限操作检查suspended→offline→revision3/store→同步/根/格式/索引版本→活跃/写互斥。目录浏览虽只读，依用户规则也属于suspended禁止项；未导入原生历史只读不在暂停禁止项。暂停原子失败全部尚未grant的导入/登记，已grant如实处理；取消运行/拒绝审批豁免不变。原生导入没有Run，所以不受别的对话busy锁影响，只受自身精确绑定写锁；发送导入Hub对话沿既有busyFresh/busy门禁。

索引GET可离线且可在暂停时读取。sync关闭/设备删除/workspace移除清理索引后GET返回NOT_FOUND；已知路由的在线查询仍先执行不泄露资源的认证/归属校验。Server使用索引缓存不代表电脑已授权某次读，Worker必须复查。

HTTP包N/N−1保留0.8字段/请求/旧撤销/PAT；0.9增加可选来源字段、原生专用操作和场景字段按类型可选。旧客户端不能展示无场景native时应提示升级或将它作为只读未知类别，不能合成场景；新客户端对旧scenario缺conversationKind按scenario。旧线路不能承载native元数据；双向栅栏完成前不得创建需同步的R3对象。0.8的注册表测试升级包版本断言不等于放宽旧线路兼容验收。

## 10. 下游验收边界

协议测试验证严格形状、旧引用闭包、合成Fixture、错误域、完整HTTP索引与示例及大小/身份约束。**不代表**读插件已经能安全读取任意CLI版本，不代表目录TOCTOU或外部进程识别已实测。P2必须以合成记录/临时目录/符号链接与真CLI终端做E10/E11和§13.4验收，失败按能力缺口报告；P1必须验证临时正文零落库、并发上限、断线超时、删除在途读、升级栅栏；P3验证长消息跨页、显式确认、离线只读索引和暂停浏览门禁。

旧vNext接口文档“导入只创建索引”由本次用户§8.3a的完整历史导入要求明确替代；E09旧离线排队由D48替代；E10中的Attempt按D40现有执行身份映射。本工作包不改docs/，主代理负责同步旧目标文档。
