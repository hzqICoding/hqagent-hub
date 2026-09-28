---
wp: R15-P0-DEV
status: done
scope_declared: [packages/protocol/**, .hqagent/**]
scope_touched: [".hqagent/DECISIONS.md", ".hqagent/INTERFACES.md", ".hqagent/codex-sessions.md", ".hqagent/handoffs/R15-P0-devices.md", ".hqagent/reviews/R15-P0-devices-resume-api-validation.log", ".hqagent/reviews/R15-P0-devices-resume-protocol-validation.log", ".hqagent/reviews/R15-P0-devices-resume-tests.log", "packages/protocol/README.md", "packages/protocol/VERSION", "packages/protocol/fixtures/contracts/devices.RemoteApiTokenCreateInput.json", "packages/protocol/fixtures/contracts/devices.RemoteApiTokenIssueReplayView.json", "packages/protocol/fixtures/contracts/devices.RemoteApiTokenIssuedView.json", "packages/protocol/fixtures/contracts/devices.RemoteApiTokenPage.json", "packages/protocol/fixtures/contracts/devices.RemoteApiTokenRevocationView.json", "packages/protocol/fixtures/contracts/devices.RemoteApiTokenScope.json", "packages/protocol/fixtures/contracts/devices.RemoteApiTokenView.json", "packages/protocol/fixtures/contracts/devices.RemoteDeviceDeletionView.json", "packages/protocol/fixtures/contracts/devices.RemoteDevicePatchInput.json", "packages/protocol/fixtures/contracts/devices.RemoteHttpError.json", "packages/protocol/fixtures/contracts/devices.RemoteHttpErrorDetail.json", "packages/protocol/fixtures/contracts/devices.RemoteWire2ApprovalView.json", "packages/protocol/fixtures/contracts/devices.RemoteWire2Error.json", "packages/protocol/fixtures/contracts/devices.RemoteWire2ErrorCode.json", "packages/protocol/fixtures/contracts/devices.device-enabled.json", "packages/protocol/fixtures/contracts/devices.device-suspended.json", "packages/protocol/fixtures/contracts/manifest.json", "packages/protocol/generated/go/protocol.go", "packages/protocol/generated/python/models.py", "packages/protocol/generated/ts/index.ts", "packages/protocol/openapi/remote-hub.v2.bundle.json", "packages/protocol/openapi/remote-hub.v2.yaml", "packages/protocol/registry/error-codes.yaml", "packages/protocol/remote/R1.5-contract.md", "packages/protocol/remote/api-contract.py", "packages/protocol/remote/api-guide.md", "packages/protocol/remote/http-error-guidance.yaml", "packages/protocol/schema/remote-devices.json", "packages/protocol/schema/remote-sync.json", "packages/protocol/schema/remote.json", "packages/protocol/tests/test_devices_api.py"]
build: pass
tests: pass
commit: 739756f423dff891963925f75ae24534497e0d6c
open_questions: 0
---

# 设备管理与Hub Server开放接口：0.8.0

本轮从磁盘未提交改动继续，没有回滚。开始最小命令返回environment-ok；git status/diff复核后，全部213个JSON及相关YAML/Python可完整解析，没有发现中断造成的截断文件。基线为ea63a7293db4097d2a0be5084f29bbbd2dc5c8d2，工作区remote-protocol，分支feat/remote-protocol。没有修改apps/**、docs/**或scripts/**，没有合并回integration。

头部commit是包含全部协议内容和校验的冻结SHA；本回执/日志登记随后提交，避免SHA自引用。status=done表示协议交付完成，不表示新服务端功能已经实现或部署。本轮只有主代理在执行，没有启动子代理。

## 冻结内容

- 包版本0.8.0，Worker线路仍为1/2，无新帧、无线上字段变化。HTTP新增错误通过独立RemoteHttpError输出，rev2错误/审批类型引用固定到0.7的旧错误集合，防止公共注册表追加意外放宽Worker。rev1原样，173份旧Fixture内容不变。
- 设备标准GET列表/详情、PATCH管理、DELETE删除；列表支持remoteAccess/online/includeRevoked，元数据version做CAS，displayName仅服务器别名；原revocations deprecated并保持旧行为。
- Cookie-only的PAT签发/列表/吊销，六个设备操作允许Bearer并分别要求devices:read/manage/delete，不包含其它资源权限。
- 完整Hub Server HTTP规范覆盖27条现有和6条规划操作，逐操作鉴权、参数、Schema、请求/成功/错误示例、X-Request-Id与错误码清单齐全。Worker WSS单列索引并指向既有Schema。
- 主文档packages/protocol/remote/api-guide.md；OpenAPI事实源remote-hub.v2.yaml，自包含发布物remote-hub.v2.bundle.json。api-contract.py生成/检查接口索引、72行错误总表与bundle，防止手写表格或服务端发布物漂移。
- 335个类型、189份Contract Fixture，TS/pydantic/Go生成物已更新。新增14个类型，各有Fixture，另加设备enabled/suspended两份视图样例。

新增类型：

```text
RemoteDevicePatchInput
RemoteDeviceDeletionView
RemoteApiTokenScope
RemoteApiTokenCreateInput
RemoteApiTokenView
RemoteApiTokenPage
RemoteApiTokenIssuedView
RemoteApiTokenIssueReplayView
RemoteApiTokenRevocationView
RemoteHttpErrorDetail
RemoteHttpError
RemoteWire2ErrorCode
RemoteWire2Error
RemoteWire2ApprovalView
```

新增HTTP错误：REMOTE_DEVICE_SUSPENDED（409/false）、REMOTE_API_TOKEN_INVALID（401/false）、REMOTE_API_TOKEN_EXPIRED（401/false）、REMOTE_API_TOKEN_SCOPE_INSUFFICIENT（403/false）、REMOTE_AUTH_AMBIGUOUS（400/false）。它们不进入任一Worker错误域。暂停提示为“这台电脑的远程操作已暂停”。总表状态/retryable来自registry，中文提示、原因和建议在http-error-guidance.yaml，脚本检查集合及示例一致。

## 明确的取舍

1. DELETE首次200，后续包括同键DELETE统一404，属于副作用幂等而非响应重放；认证/授权先于墓碑查找。保留不含正文的最小墓碑，不复活workerId。旧0.7不支持新DELETE时的未知接口404不能冒充已删除，前端须先确认能力。
2. 暂停与online/status独立，Worker连接、目录、同步、busy、历史继续；管理操作自己不被暂停挡住。暂停时全部已有未grant窗口失败，之后新run.cancel/审批reject放行；已grant事实不伪造回滚。暂停在普通业务写的offline/fresh/旧版本错误之前判断，安全动作跳过暂停但不跳过权限/在线/期限。
3. PAT是账号令牌，默认90天、最多365天，格式hqr_pat_加公开selector和256-bit随机秘密。只存域隔离HMAC和元数据；首次201含secret，同键同体200只有metadata，无法取回丢失的首次明文，需吊销后新建。不能复用当前Service.replay直接缓存完整签发结果。
4. Cookie与Bearer同现拒绝，不回退不合并。PAT仅六条设备路由，read包括catalog，delete包括旧revocations；无scope隐含关系，PAT不能管理PAT。Cookie写需CSRF/Origin；PAT校验及scope通过后才豁免这些检查，写仍需幂等键和来源限速。
5. 设备版本只因管理/生命周期变化递增，心跳/busy不增。新意图检查expectedVersion；相同请求重放不重复CAS。PATCH不改Worker deviceName，清空别名应移除displayName，而非存空串/null破坏输出Schema。
6. HTTP detail独立安全白名单，不扩共享Worker RemoteError。公开OpenAPI是原始JSON、不套ApiEnvelope；其他API的success/data/error互斥，bundle明确禁止相反字段。
7. X-Client-Request-Id选择小写UUIDv4，只记录、不替代服务端requestId。每HTTP响应的X-Request-Id和信封同值，日志只记固定operation、状态、错误码、耗时及合法关联ID，不记凭据/正文/未脱敏异常。
8. 保留HTTP N/N−1既有请求/字段及deprecated路由，新字段可选；HTTP读者须容忍新增字段，旧严格SDK不能盲校验未来JSON。包0.8/0.7兼容与线路[2,1]是不同层次，不产生wireRevision3。

上述取舍已明确，无needs-decision。D50已登记。

## 本轮示例逐项复核

已逐条读取33个操作的请求及成功示例，并检查每个错误示例与注册表、鉴权、状态码及requestId一致。修正不触碰旧173份Fixture，只更新新HTTP示例及本轮两份设备状态Fixture：

- 所有新202传输回执改queued_online、workerOnline=true、30秒期限；只有POST messages的新RemoteQueuedReceipt带conversationSeq。
- 创建、元数据修改、运行控制、审批决定的回执不分配执行序号。撤回返回原run.submit投影，保留其原槽，标withdrawalState=requested及不同的withdrawalCommandId，不冒充新控制命令分配序号。
- PATCH设备的成功例反映suspended/version2，并保存x-before作为前态；不再回enabled/version1。suspendedAt不晚于observedAt。
- 配对confirm返回尚未连接的offline/capabilityRevision0，不伪造已上线或已设置别名。
- 高风险git_push审批默认成功请求改reject；SUSPENDED错误例注明只对应approve等受限分支，取消/reject豁免不被错误示例误导。
- 快照包含有效pending审批和waiting_approval运行；消息页例补messageSequence/messageRevision。离线仍显示running的读例明确不能推断任务已停止。
- 路径参数与返回ID对应；列表初页示例不带伪造旧cursor/before；仅PATCH的CAS冲突例带expectedVersion/currentVersion细节。
- 对照现有ready/create/enqueue守卫补NOT_FOUND、REMOTE_SCENE_VERSION_MISMATCH、REMOTE_DELIVERY_EXPIRED及发送序号资源上限错误例；无游标GET移除不适用游标错误。
- curl的旧撤销改用独立设备ID，不在DELETE后对同一ID继续撤销；明确read/manage签发例不含delete，执行破坏性例需另行授予scope。

api-contract.py增加实时示例语义检查；专项测试增加6个负向回归：离线排队、控制序号、过长期限、暂停回包状态错误、高风险approve、过期快照审批。公开bundle、接口索引与错误表已重新生成。

## 本轮真实验证

临时目录统一为worktree内.venv/devices-resume-validation，设置TEMP/TMP/PYTEST_DEBUG_TEMPROOT；PATH选本worktree的.venv/Scripts。使用上一轮已离线安装的0.8生成包；本轮完整CheckGenerated重新生成并比对三端。没有联网安装、没有启动Vitest或应用全量测试。

```powershell
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
.venv/Scripts/python.exe -X utf8 -B packages/protocol/remote/api-contract.py
.venv/Scripts/python.exe -X utf8 -B -m pytest packages/protocol/tests/test_devices_api.py -q -p no:cacheprovider --tb=short
```

最终真实输出：

```text
协议校验通过：335 个类型，189 个 Contract Fixture
API contract verified: 27 current + 6 planned HTTP operations; 72 error codes; self-contained bundle; examples/auth/request IDs consistent
43 passed in 5.35s
```

日志为.hqagent/reviews/R15-P0-devices-resume-{protocol-validation,api-validation,tests}.log。本回执使用本轮最后一次完整验证结果，不以上一轮37 passed代替；上一轮0xC0000142发生后未重试，本轮工具恢复后未再次出现。应用侧新路由、认证、暂停/删除及追踪尚待P1/P3实施，协议测试不等于业务已上线。

## 下游实施要点 · P1服务端

- 实施六个新增HTTP操作、列表过滤/CAS字段及PAT六路由白名单；保持旧revocations。补GET /api/v2/openapi.json，发行包随带仓库bundle，以JSON等价测试保证一致，不能依赖部署机源码路径。可选文档UI用随包离线资源，不用外网CDN。
- 鉴权中间件先区分Cookie/PAT/设备凭据，拒绝歧义身份，不能只凭Authorization存在绕过CSRF。PAT仅在指定设备路由和scope下生效；令牌管理始终Cookie。DELETE也要走写请求Origin/CSRF/幂等保护，不能沿用目前只识别POST/PATCH的分支。
- PAT签发专用事务只持久校验值、元数据与意图摘要/tokenId，不缓存secret响应；同键重放不重新签发、不返回秘密。及时检查吊销/过期，避免认证缓存绕过；列表不泄露校验值。账号/资源归属检查先于幂等缓存返回。
- 设备PATCH只更新管理字段，CAS与状态变化同事务；心跳/同步不得用旧对象覆盖remoteAccess/displayName/version。暂停与grant原子竞争，全部未grant窗口失败；cancel/reject的豁免必须贯穿ready/conversation/enqueue等层。不得把HTTP新码下发到Worker，也不得用revoke实现暂停。
- 删除调用撤销清理，清全部store副本、busy、暂存/可重放正文及凭据；列表与关联资源统一过滤deleted，保留无正文最小墓碑。已grant可能仍执行，不伪造停止或成功取消，旧rev1事实也需保留真实不确定性。
- 分离HTTP错误映射与Worker错误域，补本轮新码及标准CONFLICT/BAD_REQUEST映射。detail仅白名单已声明字段名，不直接输出Pydantic异常里的输入值/未知键名。
- 入口生成requestId，成功和所有提前拒绝的body/header同值；请求结束一条结构化日志，覆盖限速、鉴权失败、静态与未匹配路径。可选关联ID严格UUID校验；禁凭据/请求响应体/原始异常泄露。实现后用requestId贯通测试、HTTP绑定完整性、幂等重放和并发grant竞争测试验收。

## 下游实施要点 · P3前端

- 设备列表显示online与remoteAccess两种状态，提供筛选、暂停/恢复、别名编辑和删除。操作前取version，冲突刷新确认意图后用新key重提；删除提示可能仍有本机任务运行。确认服务端支持0.8后才能把DELETE 404视为已不存在，禁止用旧撤销代替暂停/删除。
- 暂停时禁受限操作，但不要一刀切禁取消运行和拒绝审批；设备管理自身仍能恢复。暂停不是离线、不清历史；操作结束重新读取状态，避免幂等旧快照覆盖更新状态。
- 令牌管理页走Cookie/CSRF，scope独立选择，delete不能隐式授予。secret只在首次成功弹窗的临时内存显示/复制，关闭后清理，不进localStorage、分析事件、日志或错误上报。首次响应丢失按metadata找到tokenId吊销后重建。
- 诊断展示requestId并按error.code处理；curl示例与公开规范可用于排查。浏览器PAT测试用credentials:omit，不能和环境Cookie一起发送。可视化规范页面为可选项，不依赖外网CDN。

## 下游实施要点 · P2 Worker

**无需改动。** 没有新增Worker帧或状态通知，线路修订仍为1/2；修订2内部错误类型引用固定旧值域，线上字段及旧报文行为不变。暂停由服务端准入和grant门禁处理，同步/目录/busy照常；删除沿用凭据失效/撤销和连接fence处理，不把HTTP资源404映射为新Worker错误。

## 提交

- 6a9ce91：Schema、注册表、Fixture及三端生成物。
- 0a54fab：完整OpenAPI/发布bundle、指南、错误表、校验与专项测试、D50。
- 739756f：按实际守卫完善各路由错误示例及语义检查，为最终协议冻结SHA。
- 本回执、验证日志及冻结登记另提交。每次提交后git log -1 --format=%B自查，未添加署名或生成工具标记；未合回integration。
