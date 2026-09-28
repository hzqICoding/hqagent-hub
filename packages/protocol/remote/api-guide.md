# Hub Server 对外接口规范（协议包 0.8.0）

本文面向远程服务器调用方，覆盖所有HTTP业务接口及Worker WSS。它不是电脑上Local Hub的同名前缀接口。服务端只做认证、设备管理、指令通信和副本保存，不调用模型、不持有模型凭据。设备管理与PAT是0.8新增；落地由P1负责，本文不表示当前部署已完成升级。

事实源：`openapi/remote-hub.v2.yaml`及其Schema引用。公开发布物为自包含的`openapi/remote-hub.v2.bundle.json`，由`remote/api-contract.py`生成；不得通过运行时反射生成另一套不一致的规范。

## 1. 基础约定

- HTTPS Base URL：`https://<部署域名>`，资源前缀`/api/v2`。示例域名`hub.example.invalid`及全部示例ID/令牌均是合成数据，不能用于真实认证。
- `protocolVersion`是协议包版本，当前0.8.0；URI版本仍v2。Worker线路修订仍[1,2]，以wireRevision协商，不能拿包版本相等当接入条件。
- 请求和响应JSON使用UTF-8、camelCase。写入通常`Content-Type: application/json`；无请求体的DELETE不要求伪造JSON。拒绝未声明的输入字段，不接受客户端传owner/账号归属字段。
- 时间统一RFC3339 UTC `Z`，例如`2026-09-27T12:00:00.000Z`。ID是不可解析的有界字符串，按Schema长度限制，拼URL时编码路径段。安全整数上限2^53-1。
- 成功信封：`{success:true,data,requestId,protocolVersion}`；失败：`{success:false,error,requestId,protocolVersion}`。两者互斥，不以HTTP200包装失败，不在失败时返回业务data。
- HTTP错误用RemoteHttpError：`code`、中文`message`、`retryable`、可选`detail`。客户端按code分支，不解析message。detail只允许声明过的字段名列表、授权后的currentVersion、retryAfterSeconds；不得包含输入值、未知字段原名、账号定位信息、凭据、原始异常或请求体。通用ApiEnvelope复用原ApiError，但远程输出还须满足更窄的RemoteHttpError约束。
- `Cache-Control: no-store`用于API响应，包括签发、错误和幂等重放。**例外格式**：GET `/api/v2/openapi.json`直接返回完整OpenAPI JSON，不套信封；静态HTML/assets及升级前WS拒绝也可能非信封，尽量提供X-Request-Id。

示例错误（已授权资源的CAS冲突）：

```json
{"success":false,"error":{"code":"CONFLICT","message":"资源版本或状态已变化，请刷新后重试","retryable":false,"detail":{"fields":["expectedVersion"],"currentVersion":3}},"requestId":"req_0123456789abcdef01234567","protocolVersion":"0.8.0"}
```

## 2. 鉴权矩阵与凭据边界

| 模式 | 使用处 | 规则 |
| --- | --- | --- |
| public | 登录、公开OpenAPI | 不要求已有会话；登录仍需HTTPS、可信Origin、限速、幂等键和账号密码 |
| optional_cookie | GET auth/session | 有效Cookie返回会话，无有效Cookie返回authenticated=false；不接受PAT代替 |
| cookie | 账号、配对确认、对话/运行/审批、PAT管理 | `__Host-hqremote`，HttpOnly/Secure/SameSite=Strict；所有写操作需可信Origin、X-CSRF-Token及Idempotency-Key |
| cookie_or_pat | 下表设备资源白名单 | Cookie沿用上项；PAT用Authorization Bearer，独立scope，不需要CSRF且不检查Origin |
| worker_device | Worker发起/轮询配对、WSS | 独立电脑secret，与PAT/账号Cookie绝不互换；设备创建先由电脑生成secret |

登录使用密码获得Cookie；CSRF token从登录/GET auth/session的data读取。登录无已有CSRF是既有例外；GET不要求CSRF。退出保留现有同会话/同幂等键的有限重放规则，不能用失效Cookie绕过普通接口认证。

同一请求出现`__Host-hqremote` Cookie及Authorization Bearer，或存在多个Authorization/多个同名会话Cookie，统一400 REMOTE_AUTH_AMBIGUOUS；不回退、不静默合并权限。无关Cookie不算第二身份。原始凭据不能进URL、日志或普通错误；仅首次PAT签发的专用secret字段可返回PAT明文。

PAT白名单及精确scope：

| 接口 | PAT scope |
| --- | --- |
| GET /devices；GET /devices/{workerId}；GET /devices/{workerId}/catalog | devices:read |
| PATCH /devices/{workerId} | devices:manage |
| DELETE /devices/{workerId}；POST /devices/{workerId}/revocations（deprecated） | devices:delete |

scope相互独立，manage/delete不自动包含read，不支持`devices:*`。已授权写操作可返回其结果，但不因此获得列表/详情读取权。`devices:read`明确包括设备导出的目录索引。PAT在其它路由均拒绝，不得签发/列出/吊销PAT，不能登录、配对确认、读对话或操作模型。PAT前缀也不能被设备凭据解析器当作Worker secret使用。`X-CSRF-Token`在PAT模式即使存在也不授予权限，Origin不参与PAT验证；这不要求放开浏览器跨站Cookie CORS。

仅在该路由属于PAT白名单且令牌校验及scope通过后，才走无CSRF分支，不能仅凭Authorization头存在就跳过Cookie保护。在浏览器中测试PAT时使用`credentials: 'omit'`，不要让环境Cookie随Bearer一起发送；Cookie业务客户端则不附Authorization。

## 3. 设备资源

创建入口仍为电脑`POST /worker/pairing-requests` → 手机Cookie `POST /pairings/preview` → `POST /pairings/{pairRequestId}/confirm`。不新增POST /devices，PAT也不能代替手机确认绑定。

设备视图保留原deviceName/status/online语义，新增可选remoteAccess（缺省enabled）、服务端displayName别名（缺省显示deviceName）、version（旧记录初始化1）及suspendedAt。0.8生产者返回真实remoteAccess/version；suspendedAt仅暂停期间存在，恢复时省略。显示别名不下发电脑、不覆盖电脑上报的deviceName。

GET列表分页cursor/limit（1..100，缺省50）；remoteAccess筛enabled/suspended，online筛实际连接，includeRevoked缺省false。已删除永不返回；单个未删revoked仍可GET并删除。游标绑定账号、认证可见域和规范化过滤条件，改变过滤重用cursor返回REMOTE_CURSOR_INVALID。online与remoteAccess正交：暂停不等于离线。

remoteAccess或online省略表示不做该项筛选；includeRevoked省略与显式false相同。设备沿既有服务端创建顺序稳定分页，心跳/改别名不重排；limit可调整，不属于筛选作用域。升版导致有效旧游标无法继续时返回REMOTE_CURSOR_EXPIRED，要求重取首页，不能把旧游标解释为新过滤。

PATCH必带expectedVersion及至少一个remoteAccess/displayName；null非法，displayName修剪后空串表示清除别名。版本仅在管理字段实际变化或撤销等生命周期变化时递增，心跳、同步、busy不增版本。先授权及检查生命周期，再处理同键重放；新意图CAS冲突409 CONFLICT。无变化且版本匹配不增版本。revoked不能通过PATCH恢复，返回REMOTE_DEVICE_REVOKED；要恢复只能电脑重新配对。

DELETE可以处理正常或历史revoked设备；首次200返回workerId/deletedAt/executionMayStillBeRunning=true，之后包括相同/不同幂等键DELETE在内的访问统一404 NOT_FOUND。定义为**副作用幂等，不重放首次响应**；调用方执行“确保删除”可把404视为已不存在。已删除ID不得复用，新配对得到新workerId。墓碑不对调用方可见。

“404表示已不存在”只适用于已确认支持该DELETE接口的服务端；若旧0.7服务没有这条路由，必须提示升级，不能把未知接口的404当成删除成功。前端应依据响应protocolVersion/公开规范判断能力，不可悄悄改调用旧revocations。

暂停是远程写门禁，不清历史、不关闭Worker、不停止同步/目录/忙碌快照，也不暂停本机任务。手机发消息、创建/修改对话、批准审批、run.pause/resume/retry等被拒绝为REMOTE_DEVICE_SUSPENDED；只有run.cancel和approval.decide(reject)免除此门禁。command.withdraw不是额外豁免。设备管理、旧撤销及Cookie令牌管理不被暂停门禁挡住，否则无法恢复；这些管理操作也不需要电脑在线。撤销入口仍存在但deprecated，保持撤销后记录存在的旧行为，新UI使用删除。

暂停切换事务使当时**所有**尚未grant的30秒窗口命令失败（包括之前排队的cancel/reject）；暂停完成后新的cancel/reject可提交。已grant不能伪装成未执行，不由暂停计时器回滚许可；恢复不会重放此前失败命令。详见R1.5-contract“设备管理与开放接口”。

## 4. PAT签发、读取与吊销

只允许已登录Cookie会话管理 `/api/v2/api-tokens`；写操作与其它Cookie写接口一样需要Origin、CSRF和Idempotency-Key。名称修剪后非空且≤120字符；scopes为1..3个不同的允许值。expiresAt省略默认90天，首次签发时必须严格晚于当前时间，最长365天（31,536,000秒），不能签无限期令牌。

格式：`hqr_pat_<24位小写hex公开selector>_<43位base64url秘密>`。selector是12字节随机公开定位符，secret是独立32字节CSPRNG随机值，无`=`填充。tokenId=`pat_<selector>`；列表只提供tokenPrefix=`hqr_pat_<selector>`，不提供任何secret片段。

服务端只存元数据和域隔离HMAC校验值，例如HMAC(serverKey, `api-token-v1\0` + 完整PAT)，恒定时间比较；不存明文、可逆密文或可恢复随机种子。serverKey轮换必须有明确策略，不能无意让吊销凭据复活。有效性每次请求检查，不允许过期的正向认证缓存绕过吊销；写入权限检查与副作用提交须有同一事务边界。

POST首次201为RemoteApiTokenIssuedView，包含metadata及一次secret；同键同体重放200为RemoteApiTokenIssueReplayView，仅metadata，secret字段不存在（不是null），不会创建第二条或重算有效期。异体409 IDEMPOTENCY_MISMATCH。**不能用通用response_json幂等缓存保存签发结果**；专用意图只存请求摘要及tokenId，明文仅在首次处理内存及首次响应中短暂存在。首次响应丢失后不能取回secret，应从列表找到该tokenId吊销，再以新key签发。重放可返回当前expired/revoked metadata，不重新验算成一次新签发；最小幂等意图保留到账号清理，避免旧key后来二次签发。

GET列表返回metadata，含name、tokenPrefix、scopes、createdAt、可选lastUsedAt、expiresAt、status和可选revokedAt；lastUsedAt指最近一次通过鉴权和scope校验的请求，不代表业务成功，也不用于安全有效性判断。支持cursor/limit和includeRevoked=false，游标绑定此过滤；从未使用时省略lastUsedAt。

DELETE /api-tokens/{tokenId}是吊销而非删除元数据，返回固定revokedAt，重复吊销幂等200；他人/未知ID为404。过期令牌也可吊销，revoked优先于expired。请求时先验证秘密，再区分过期；无效或已吊销401 INVALID，合法但过期401 EXPIRED，scope不足/该路由不接受PAT为403 SCOPE_INSUFFICIENT。

## 5. 设备与令牌 curl 示例

变量由调用方填写。勿将凭据写进URL或开启shell跟踪；PAT放安全凭据存储，不放前端localStorage。以下命令只说明协议，不会在本工作包执行。

```bash
BASE='https://hub.example.invalid'
WORKER='worker_demo'
# 交互输入PAT，避免把字面值写入历史。以下设备操作需各自scope。
read -rs PAT

# 公开规范，不附PAT。
curl -fsS "$BASE/api/v2/openapi.json"

# 列表、筛选和后续页（cursor须与完全相同过滤条件搭配）。
curl -fsS -G "$BASE/api/v2/devices" -H "Authorization: Bearer $PAT" \
  --data-urlencode 'remoteAccess=enabled' --data-urlencode 'online=true' \
  --data-urlencode 'includeRevoked=false' --data-urlencode 'limit=20'
curl -fsS -G "$BASE/api/v2/devices" -H "Authorization: Bearer $PAT" \
  --data-urlencode 'remoteAccess=enabled' --data-urlencode 'online=true' \
  --data-urlencode 'includeRevoked=false' --data-urlencode "cursor=$CURSOR"
curl -fsS "$BASE/api/v2/devices/$WORKER" -H "Authorization: Bearer $PAT"
curl -fsS "$BASE/api/v2/devices/$WORKER/catalog" -H "Authorization: Bearer $PAT"

# 暂停并设置服务器别名；expectedVersion取刚才GET的version。
curl -sS -X PATCH "$BASE/api/v2/devices/$WORKER" \
  -H "Authorization: Bearer $PAT" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: device-pause-001' \
  --data '{"expectedVersion":1,"remoteAccess":"suspended","displayName":"办公室电脑"}'
# 恢复时使用最新version和新的意图key，不使用toggle。
curl -sS -X PATCH "$BASE/api/v2/devices/$WORKER" \
  -H "Authorization: Bearer $PAT" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: device-resume-001' \
  --data '{"expectedVersion":2,"remoteAccess":"enabled"}'

# 删除（devices:delete）；后续404可按已不存在处理。
curl -sS -X DELETE "$BASE/api/v2/devices/$WORKER" \
  -H "Authorization: Bearer $PAT" -H 'Idempotency-Key: device-delete-001'
# 独立的旧接口示例，不要对刚删的ID调用；撤销不能代替DELETE。
LEGACY_WORKER='another_worker_demo'
curl -sS -X POST "$BASE/api/v2/devices/$LEGACY_WORKER/revocations" \
  -H "Authorization: Bearer $PAT" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: legacy-revoke-001' --data '{}'
```

令牌由浏览器管理页签发，或用已登录的Cookie jar调用以下接口。`COOKIE_JAR`是调用方自己的登录会话文件；CSRF取该会话响应，Cookie模式不要同时加Authorization。

下面按最小权限只签发read/manage令牌。要执行删除或旧撤销示例，须另行明确授予devices:delete，不自动包含该破坏性权限。

```bash
CSRF=$(curl -fsS -b "$COOKIE_JAR" "$BASE/api/v2/auth/session" | jq -r '.data.csrfToken')
curl -sS -b "$COOKIE_JAR" -X POST "$BASE/api/v2/api-tokens" \
  -H "Origin: $BASE" -H "X-CSRF-Token: $CSRF" \
  -H 'Idempotency-Key: token-create-001' -H 'Content-Type: application/json' \
  --data '{"name":"ops-cli","scopes":["devices:read","devices:manage"]}'
# 仅上述首次201的data.secret包含明文；复制到安全存储，别写调试日志。
curl -fsS -b "$COOKIE_JAR" "$BASE/api/v2/api-tokens?limit=20"
TOKEN_ID='pat_0123456789abcdef01234567'
curl -sS -b "$COOKIE_JAR" -X DELETE "$BASE/api/v2/api-tokens/$TOKEN_ID" \
  -H "Origin: $BASE" -H "X-CSRF-Token: $CSRF" -H 'Idempotency-Key: token-revoke-001'
```

## 6. 幂等、并发、回执与限速

所有写请求带1..200字符Idempotency-Key；认证/授权/生命周期检查必须先于缓存重放。普通同键同体返回原结果，同键异体409；body hash使用未注入默认值的规范化JSON。作用域至少含账号、操作及目标；PAT再含tokenId，防止不同集成方的key相撞。吊销/过期PAT不得靠命中缓存继续访问。PATCH同意图重放不重复CAS或增版本；返回可能是历史快照，前端随后GET刷新当前状态。

显式例外：设备DELETE统一后续404；PAT签发重放不返回secret。这些都不产生第二次副作用。不能为“让重试成功”重建已删除workerId。版本冲突先GET核对，再用新expectedVersion和新key；不得悄悄覆写别人的管理改动。

202只表示有界传输意图/回执持久化，不是电脑已接单或任务成功。在线状态、暂停门禁、busy和grant是不同事实。暂停时现有未grant窗口失败但并非停止已运行任务；已grant结果按D41真实报告。令牌设备管理接口通常200/201，没有替代执行grant。

来源限速沿用服务器配置（当前默认每60秒30次；部署可调整）；登录/配对现有独立桶保留，PAT所有请求含GET都受来源桶约束，失败鉴权也计数。Cookie写请求沿用现有写桶；不以更换令牌/造selector绕过来源额度。可信代理才能提供客户端来源，不信任任意X-Forwarded-For。429提供REMOTE_RATE_LIMITED及Retry-After秒数；按其退避并保留幂等键。配额不是接口永久常量，不能写死客户端轮询频率。

## 7. 分页与游标

- `cursor` / `nextCursor`：列表分页，绑定账号、资源、过滤条件及稳定排序。hasMore=true必须有下一游标；换过滤应重新从首页取。
- 消息`before`：最新一页优先，独占向前边界；`snapshotCursor`标记固定分页截止点。按messageId/revision合并新消息，不能按offset移动旧页。
- `serverCursor` / `nextServerCursor`：浏览器增量事件的不透明序列，不是Worker seq。游标过期410后重建快照再接续，不静默归零重播。
- 每页上限按operation声明，普通列表100、事件200。Worker seq只在WSS连续确认中使用，不能拿来替换浏览器游标。

## 8. requestId与排查

服务端在请求入口生成唯一不透明requestId，长度16..128、字符`[A-Za-z0-9_-]`；不采信调用方X-Request-Id。每个信封与响应头`X-Request-Id`必须同值，覆盖成功、限速、鉴权、参数错误和未匹配路径。静态资源及WS握手拒绝尽量提供同头，但不强行把HTML/WS响应变成信封。

可选`X-Client-Request-Id`只接受小写UUIDv4（36字符）；仅日志关联，不替换服务端ID、不参与鉴权或幂等，不回显不合法原值。API非法值返回BAD_REQUEST。选择UUID而非任意字符串可阻止日志换行注入及常见凭据误贴；不得把Header值直接拼进未转义日志。

每个HTTP请求恰好一条结构化完成记录，含requestId、operation（本规范operationId，未匹配为unmatched，静态为static）、HTTP状态、errorCode或null、单调时钟elapsedMs，可选合法clientRequestId。**不记录**请求/响应体、Cookie、Authorization/PAT/设备secret、认证查询参数、未经脱敏的异常内容；PAT首次签发响应也不例外。不要用带输入值的异常traceback或访问URL日志取代审计记录。

```bash
# REQUEST_ID取响应X-Request-Id或error信封，核对两者相同。
journalctl -u hqremote --since '30 minutes ago' --no-pager | grep -F -- "$REQUEST_ID"
```

调用方提交requestId、operation、时间、HTTP状态和error.code即可定位。不要向排障人员粘贴令牌/Cookie/完整消息内容。查到日志后：401检查凭据类型/期限，403检查scope/CSRF/风险规则，409按版本/暂停/busy分支，410重建游标或新意图，429退避，5xx保留ID交管理员。请求未到达应用时可能没有requestId，应再查反向代理网络日志，仍不得记录凭据查询。

## 9. 全部HTTP接口索引

以下由api-contract.py生成；每条请求/响应/错误的完整合成示例、参数和Schema引用见OpenAPI。

各HTTP示例是独立情景，不应串成一条顺序工作流；错误示例覆盖该操作的不同输入/状态。新202的合成观测时点见x-observed-at，期限至多30秒、设备在线，只有提交消息的RemoteQueuedReceipt带新conversationSeq。撤回接口返回的是原run.submit命令投影，其conversationSeq仍是原消息槽，withdrawalCommandId才引用新控制命令，不新分配执行序号。高风险审批的成功例使用reject；SUSPENDED错误例明确仅对应approve等受限分支。

<!-- BEGIN API_INDEX -->
| 方法与路径 | operationId | 鉴权 / PAT scope | 成功 data |
| --- | --- | --- | --- |
| `POST /api/v2/auth/login` | `remoteLogin` | public  | 200 RemoteAuthenticatedSession |
| `GET /api/v2/auth/session` | `getRemoteSession` | optional_cookie  | 200 RemoteBrowserSessionView |
| `POST /api/v2/auth/logout` | `remoteLogout` | cookie  | 200 RemoteAnonymousSession |
| `POST /api/v2/worker/pairing-requests` | `requestRemotePairing` | worker_device  | 201 RemotePairingChallenge |
| `GET /api/v2/worker/pairing-requests/{pairRequestId}` | `getRemotePairingStatus` | worker_device  | 200 RemotePairingStatusView |
| `POST /api/v2/pairings/preview` | `previewRemotePairing` | cookie  | 200 RemotePairingPreview |
| `POST /api/v2/pairings/{pairRequestId}/confirm` | `confirmRemotePairing` | cookie  | 200 RemoteDeviceView |
| `GET /api/v2/devices` | `listRemoteDevices` | cookie_or_pat devices:read | 200 RemoteDevicePage |
| `GET /api/v2/devices/{workerId}` | `getRemoteDevice` | cookie_or_pat devices:read | 200 RemoteDeviceView |
| `PATCH /api/v2/devices/{workerId}` | `updateRemoteDevice` | cookie_or_pat devices:manage | 200 RemoteDeviceView |
| `DELETE /api/v2/devices/{workerId}` | `deleteRemoteDevice` | cookie_or_pat devices:delete | 200 RemoteDeviceDeletionView |
| `POST /api/v2/devices/{workerId}/revocations` | `revokeRemoteDevice` | cookie_or_pat devices:delete | 200 RemoteDeviceRevocationView |
| `GET /api/v2/devices/{workerId}/catalog` | `getRemoteWorkerCatalog` | cookie_or_pat devices:read | 200 RemoteCatalogView |
| `GET /api/v2/conversations` | `listRemoteConversations` | cookie  | 200 RemoteConversationPage |
| `POST /api/v2/conversations` | `createRemoteConversation` | cookie  | 202 RemoteQueuedReceipt |
| `GET /api/v2/conversations/{conversationId}` | `getRemoteConversation` | cookie  | 200 RemoteConversationView |
| `PATCH /api/v2/conversations/{conversationId}` | `updateRemoteConversation` | cookie  | 202 RemoteQueuedReceipt |
| `POST /api/v2/conversations/{conversationId}/messages` | `sendRemoteMessage` | cookie  | 202 RemoteQueuedReceipt |
| `GET /api/v2/conversations/{conversationId}/messages` | `listRemoteMessages` | cookie  | 200 RemoteSyncMessagePage |
| `GET /api/v2/conversations/{conversationId}/runs` | `listRemoteRuns` | cookie  | 200 RemoteRunPage |
| `GET /api/v2/conversations/{conversationId}/commands` | `listRemoteCommands` | cookie  | 200 RemoteCommandPage |
| `GET /api/v2/runs/{runId}` | `getRemoteRun` | cookie  | 200 RemoteRunView |
| `POST /api/v2/runs/{runId}/commands` | `controlRemoteRun` | cookie  | 202 RemoteQueuedReceipt |
| `GET /api/v2/commands/{commandId}` | `getRemoteCommand` | cookie  | 200 RemoteCommandView |
| `POST /api/v2/commands/{commandId}/cancellations` | `withdrawRemoteCommand` | cookie  | 202 RemoteCommandView |
| `GET /api/v2/approvals/{approvalId}` | `getRemoteApproval` | cookie  | 200 RemoteApprovalView |
| `POST /api/v2/approvals/{approvalId}/decisions` | `decideRemoteApproval` | cookie  | 202 RemoteQueuedReceipt |
| `GET /api/v2/events` | `listRemoteEvents` | cookie  | 200 RemoteBrowserEventPage |
| `GET /api/v2/conversations/{conversationId}/snapshot` | `getRemoteConversationSnapshot` | cookie  | 200 RemoteConversationSnapshot |
| `POST /api/v2/api-tokens` | `issueRemoteApiToken` | cookie  | 201 RemoteApiTokenIssuedView; 200 RemoteApiTokenIssueReplayView |
| `GET /api/v2/api-tokens` | `listRemoteApiTokens` | cookie  | 200 RemoteApiTokenPage |
| `DELETE /api/v2/api-tokens/{tokenId}` | `revokeRemoteApiToken` | cookie  | 200 RemoteApiTokenRevocationView |
| `GET /api/v2/openapi.json` | `getRemoteOpenApi` | public  | 200 原始OpenAPI文档 |
<!-- END API_INDEX -->

## 10. 错误码总表

表中code/HTTP/retryable来自唯一registry，中文提示/原因/处理建议来自http-error-guidance.yaml，由校验脚本保证集合一致。共享枚举还包含Local Hub/Worker子系统码，已标适用域，不意味着每个HTTP操作都主动产生全部码；各路由精确可能值见x-error-codes。错误描述是规范要求，P1需补齐HTTP映射，不能继续以裸code代替中文message。HTTP新码不能进入任何Worker线路。

<!-- BEGIN ERROR_TABLE -->
| code | HTTP | retryable | 中文提示 | 典型原因 | 调用方处理 | 适用域 |
| --- | --- | --- | --- | --- | --- | --- |
| `BAD_REQUEST` | 400 | false | 请求格式不合法 | 请求格式或参数不合法 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `VALIDATION_FAILED` | 422 | false | 请求参数不合法 | 请求体通过了格式检查但违反业务约束，detail 里给字段级原因 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `UNAUTHORIZED` | 401 | false | 缺少或错误的 Bearer token | 缺少或错误的 Bearer token；token 只能来自 hub.json | 重新登录或更换正确凭据；不要盲目重试 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `ORIGIN_NOT_ALLOWED` | 403 | false | Host 或 Origin 不在白名单 | Host 或 Origin 不在白名单。与 UNAUTHORIZED 区分开：那条是「没带对 token」， 这条是「token 对但来源不对」。混用会让排障时分不清是凭据问题还是来源问题。 HTTP 与 WebSocket 两种传输必须用同一语义，WS 侧以关闭码 4403 表达。 | 检查授权范围和允许的操作 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `NOT_FOUND` | 404 | false | 资源不存在 | 目标资源不存在 | 确认资源和账号；设备删除场景可视为已不存在 | Hub Server HTTP |
| `CONFLICT` | 409 | false | 资源版本或状态已变化，请刷新后重试 | 资源状态与请求冲突 | GET最新version，核对修改意图后以新expectedVersion和新幂等键提交 | Hub Server HTTP |
| `IDEMPOTENCY_MISMATCH` | 409 | false | 幂等键已用于不同请求 | 相同 Idempotency-Key 复用于不同请求体 | 不要更改重试请求体；新意图使用新幂等键 | Hub Server HTTP |
| `PROTOCOL_VERSION_MISMATCH` | 426 | false | 客户端协议大版本与 Hub 不兼容，必须升级后再试 | 客户端协议大版本与 Hub 不兼容，必须升级后再试 | 保留requestId，按retryable退避或联系管理员 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `HUB_NOT_READY` | 503 | true | Hub 正在启动或恢复中，尚未就绪 | Hub 正在启动或恢复中，尚未就绪 | 保留requestId，按retryable退避或联系管理员 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `HUB_MAINTENANCE` | 503 | true | Hub 处于维护/排空状态，拒绝创建新任务 | Hub 处于维护/排空状态，拒绝创建新任务；前端据此显示全局 Gate | 保留requestId，按retryable退避或联系管理员 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `EVENT_CURSOR_EXPIRED` | 410 | false | 客户端携带的 seq 已超出事件保留窗口，无法补发 | 客户端携带的 seq 已超出事件保留窗口，无法补发。必须重新 bootstrap 拉取 Snapshot 后再订阅，不允许静默丢事件继续跑 | 重建快照或发起新请求 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `FEATURE_UNAVAILABLE` | 503 | true | 依赖的工作包尚未就绪（例如 Adapter 未接入、Update Agent 未运行） | 依赖的工作包尚未就绪（例如 Adapter 未接入、Update Agent 未运行）。 必须返回明确原因，不允许用空成功伪装成功能可用 | 保留requestId，按retryable退避或联系管理员 | Hub Server HTTP |
| `AGENT_NOT_FOUND` | 404 | false | 指定的 Agent 实例不存在 | 指定的 Agent 实例不存在 | 确认资源和账号；设备删除场景可视为已不存在 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `AGENT_OFFLINE` | 409 | true | Agent 当前离线，可等待或走 fallback | Agent 当前离线，可等待或走 fallback | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `AGENT_NOT_LOGGED_IN` | 409 | false | Agent 已安装但未登录，需要用户在对应工具里登录 | Agent 已安装但未登录，需要用户在对应工具里登录 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `AGENT_INCOMPATIBLE` | 409 | false | Agent 版本低于适配器要求的最低版本 | Agent 版本低于适配器要求的最低版本 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `CAPABILITY_MISSING` | 409 | false | 目标角色要求的硬能力在候选 Agent 上缺失，detail 里列能力缺口 | 目标角色要求的硬能力在候选 Agent 上缺失，detail 里列能力缺口 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `ROLE_UNRESOLVED` | 409 | false | 主选和备用链都无法解析出可用 Agent，需要用户选择或暂停节点 | 主选和备用链都无法解析出可用 Agent，需要用户选择或暂停节点 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `SESSION_NOT_RESUMABLE` | 409 | false | 外部会话已失效或适配器不支持恢复，只能新建会话 | 外部会话已失效或适配器不支持恢复，只能新建会话 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `TASK_NOT_CANCELLABLE` | 409 | false | 任务已处于终态，无法取消 | 任务已处于终态，无法取消 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `TASK_ACTION_INVALID` | 409 | false | 当前任务状态不支持该动作 | 当前任务状态不支持该动作 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `WORKTREE_BUSY` | 409 | true | 目标 worktree 被占用 | 目标 worktree 被占用 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `PATH_NOT_ALLOWED` | 403 | false | 修改路径超出任务 allowedPaths 或角色 writablePaths，detail 里列越界路径 | 修改路径超出任务 allowedPaths 或角色 writablePaths，detail 里列越界路径 | 检查授权范围和允许的操作 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `APPROVAL_REQUIRED` | 409 | false | 该动作需要审批且尚未批准 | 该动作需要审批且尚未批准 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `APPROVAL_EXPIRED` | 410 | false | 审批已超时失效 | 审批已超时失效 | 重建快照或发起新请求 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `APPROVAL_ALREADY_DECIDED` | 409 | false | 该审批已被处理，不能重复决定 | 该审批已被处理，不能重复决定 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `UPDATE_NOT_AVAILABLE` | 409 | false | 当前没有可用更新 | 当前没有可用更新 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `UPDATE_BUSY` | 409 | true | 升级流程正在进行中，不接受新的升级动作 | 升级流程正在进行中，不接受新的升级动作 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `UPDATE_VERIFY_FAILED` | 422 | false | 大小、SHA-256 或 Ed25519 签名校验失败 | 大小、SHA-256 或 Ed25519 签名校验失败；没有忽略并继续的入口 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `UPDATE_DRAIN_TIMEOUT` | 409 | true | 任务排空超时，需要用户选择继续等待、取消任务或退出应用 | 任务排空超时，需要用户选择继续等待、取消任务或退出应用 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `INTERNAL` | 500 | true | 服务内部错误，请稍后重试 | 未分类的内部错误，detail 里带 requestId 供查日志 | 保留requestId，按retryable退避或联系管理员 | Hub Server HTTP |
| `REMOTE_AUTH_REQUIRED` | 401 | false | 请先登录 | 远程账号会话缺失或失效；与本机Hub Token鉴权分离 | 重新登录或更换正确凭据；不要盲目重试 | Hub Server HTTP |
| `REMOTE_CSRF_REJECTED` | 403 | false | 请求来源或CSRF校验失败 | 远程浏览器写请求的Origin或会话CSRF校验失败 | 检查授权范围和允许的操作 | Hub Server HTTP |
| `REMOTE_DEVICE_OFFLINE` | 409 | true | 设备离线，发送失败 | 目标设备离线；R1.5浏览器提交立即失败，不排队；修订1历史记录只读保留 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_DEVICE_REVOKED` | 403 | false | 设备绑定已撤销 | 设备配对已撤销，禁止新连接与后续命令；不宣称已停止本机执行 | 检查授权范围和允许的操作 | Hub Server HTTP |
| `REMOTE_DEVICE_AUTH_FAILED` | 401 | false | 设备凭据无效 | 设备凭据验证失败；响应不区分其他所有者设备的存在性 | 重新登录或更换正确凭据；不要盲目重试 | Hub Server HTTP |
| `REMOTE_PAIRING_EXPIRED` | 410 | false | 一次性配对请求或配对码已过期 | 一次性配对请求或配对码已过期 | 重建快照或发起新请求 | Hub Server HTTP |
| `REMOTE_PAIRING_CONFLICT` | 409 | false | 配对已消费或设备凭据已绑定 | 配对已消费或设备凭据已绑定；不得重新归属另一用户 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_PAIRING_INVALID` | 404 | false | 无效配对码或请求 | 无效配对码或请求；不泄露已绑定账号信息 | 确认资源和账号；设备删除场景可视为已不存在 | Hub Server HTTP |
| `REMOTE_COMMAND_EXPIRED` | 410 | false | 命令接单前已过期，不再执行 | 命令接单前已过期，不再执行；已分配执行序号须留跳过记录 | 重建快照或发起新请求 | Hub Server HTTP |
| `REMOTE_COMMAND_WITHDRAWN` | 409 | false | 命令在未派发时撤回或经Worker核实撤回 | 命令在未派发时撤回或经Worker核实撤回；拒绝迟到重复执行 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_WITHDRAWAL_UNCONFIRMED` | 409 | false | 已可能派发，不能仅删服务端记录宣称撤回 | 已可能派发，不能仅删服务端记录宣称撤回；须Worker核实 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `REMOTE_STORE_CHANGED` | 409 | false | Worker存储世代变化，冻结旧世代未决命令自动投递等待对账 | Worker存储世代变化，冻结旧世代未决命令自动投递等待对账 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_EPOCH_STALE` | 409 | false | 非当前已认证连接或旧Worker启动实例的帧被拒绝 | 非当前已认证连接或旧Worker启动实例的帧被拒绝 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_PROTOCOL_UNSUPPORTED` | 409 | false | 协议版本不兼容 | 协议版本不兼容；不静默降级远程命令语义 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_EVENT_CONFLICT` | 409 | false | 同事件ID或存储世代序号/覆盖区间对应不同不可变内容 | 同事件ID或存储世代序号/覆盖区间对应不同不可变内容 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_ACK_CONFLICT` | 409 | false | 确认位置错误、跨存储世代或服务端确认回退，需要对账而非裁剪Outbox | 确认位置错误、跨存储世代或服务端确认回退，需要对账而非裁剪Outbox | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_SEQUENCE_GAP` | 409 | true | 执行对话序号存在缺口，先补命令或跳过记录，控制命令不占执行序号 | 执行对话序号存在缺口，先补命令或跳过记录，控制命令不占执行序号 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_APPROVAL_FORBIDDEN` | 403 | false | 该操作不能远程批准 | R1禁止远程批准此高风险或Worker策略禁止的动作；本机可处理 | 检查授权范围和允许的操作 | Hub Server HTTP |
| `CONVERSATION_AUTHORITY_MISMATCH` | 409 | false | 0.7起不再用于本机remote只读拦截 | 0.7起不再用于本机remote只读拦截；保留历史/真实归属冲突。原语义：本地写接口不能写remote对话，必须走权威服务端；旧local对话不自动转换 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_TARGET_MISMATCH` | 409 | false | 命令目标、对话固定Worker或执行引用不匹配 | 命令目标、对话固定Worker或执行引用不匹配；跨owner资源统一NOT_FOUND | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_SCENE_VERSION_MISMATCH` | 409 | false | Worker场景版本与已排队请求不一致，不静默换用最新角色配置 | Worker场景版本与已排队请求不一致，不静默换用最新角色配置 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_CURSOR_EXPIRED` | 410 | false | 游标已过期，请重新加载 | 浏览器opaque游标已失效，需重新获取owner范围快照 | 重建快照或发起新请求 | Hub Server HTTP |
| `REMOTE_CURSOR_INVALID` | 400 | false | 游标无效或不属于当前查询 | 游标无效或与当前资源/认证范围不符，不泄露游标归属 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_RATE_LIMITED` | 429 | true | 请求过于频繁，请稍后重试 | 远程登录/配对/提交限流，按Retry-After重试，不能绕过单次码或幂等规则 | 遵循Retry-After退避，复用原幂等键 | Hub Server HTTP |
| `REMOTE_FRAME_TOO_LARGE` | 413 | false | 远程帧超过256KiB，拒绝而不是截断关键内容后继续 | 远程帧超过256KiB，拒绝而不是截断关键内容后继续 | 减小请求或检查资源配额；不得截断后伪装成功 | Hub Server HTTP |
| `REMOTE_WITHDRAWAL_TOO_LATE` | 409 | false | 原提交已形成可见Run或已执行结束，不能声称撤回从未执行 | 原提交已形成可见Run或已执行结束，不能声称撤回从未执行；已知Run应按runId控制 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_PAIRING_IN_PROGRESS` | 409 | false | 本机已有配对请求进行中 | 本机已有配对请求进行中；同幂等请求可重放，新请求须先取消旧配对 | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `REMOTE_SERVER_UNREACHABLE` | 503 | true | 配置的远程服务无法连接或响应未确认 | 配置的远程服务无法连接或响应未确认；不得伪造配对或服务端撤销成功 | 保留requestId，按retryable退避或联系管理员 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `REMOTE_SERVER_ORIGIN_INVALID` | 422 | false | serverOrigin不是允许的HTTPS origin，或未获本机开发模式允许的localhost/127.0.0.1 HTTP origin | serverOrigin不是允许的HTTPS origin，或未获本机开发模式允许的localhost/127.0.0.1 HTTP origin | 刷新或修正请求后使用新幂等键 | 共享注册表；仅在所属子系统/Worker事实中出现，不表示每个HTTP接口都可返回 |
| `REMOTE_CONVERSATION_BUSY` | 409 | true | 对话正在忙碌，请稍后再发送 | 电脑已有queued/running/waiting_approval轮次；保留输入，取消不受此限制 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_STATE_NOT_READY` | 409 | true | 电脑状态尚未同步完成 | 等待当前连接的完整忙碌快照；不是持久锁 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_SYNC_CONFLICT` | 409 | false | 同步分段/版本/快照内容冲突，不得发布部分正文 | 同步分段/版本/快照内容冲突，不得发布部分正文 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_SYNC_DISABLED` | 409 | false | 该电脑关闭内容同步，不能向已删除副本提交 | 该电脑关闭内容同步，不能向已删除副本提交 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_DELIVERY_EXPIRED` | 409 | true | 设备离线，发送失败 | 送达期限已过且未获执行许可；设备离线，发送失败 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_REVISION_REQUIRED` | 409 | false | 电脑端需升级后使用此操作 | 该操作要求线路修订2，不能降级执行 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
| `REMOTE_SYNC_RESOURCE_LIMIT` | 413 | false | 全文同步资源配额不足，明确失败，不截断伪装成功 | 全文同步资源配额不足，明确失败，不截断伪装成功 | 减小请求或检查资源配额；不得截断后伪装成功 | Hub Server HTTP |
| `REMOTE_DEVICE_SUSPENDED` | 409 | false | 这台电脑的远程操作已暂停 | 这台电脑的远程操作已暂停 | 先明确恢复远程操作；取消运行/拒绝审批仍可尝试 | Hub Server HTTP |
| `REMOTE_API_TOKEN_INVALID` | 401 | false | API令牌无效或已吊销 | API令牌无效或已吊销 | 核对令牌有效期、吊销状态和精确scope；Cookie管理页重签或调整调用路由 | Hub Server HTTP |
| `REMOTE_API_TOKEN_EXPIRED` | 401 | false | API令牌已过期 | API令牌已过期 | 核对令牌有效期、吊销状态和精确scope；Cookie管理页重签或调整调用路由 | Hub Server HTTP |
| `REMOTE_API_TOKEN_SCOPE_INSUFFICIENT` | 403 | false | API令牌权限不足或此接口不接受令牌 | API令牌权限不足或此接口不接受令牌 | 核对令牌有效期、吊销状态和精确scope；Cookie管理页重签或调整调用路由 | Hub Server HTTP |
| `REMOTE_AUTH_AMBIGUOUS` | 400 | false | 请求同时提供了多种身份凭据 | 请求同时提供了多种身份凭据 | 刷新或修正请求后使用新幂等键 | Hub Server HTTP |
<!-- END ERROR_TABLE -->

## 11. Worker WebSocket（不是PAT接口）

端点`/ws/v2/worker`，仅独立设备凭据Authorization Bearer。先确认已配对且未撤销/删除，10秒内首帧hello，协商整数wireRevision，当前支持1与2；15秒心跳/45秒失联，单连接fence旧连接。包版本仅诊断；最多256KiB一帧。未知修订拒绝并返回支持列表，不能按包版本猜测。

修订1/2分别选择原有WorkerOutboundFrame/ServerOutboundFrame，详见OpenAPI的x-worker-websocket.revisions与下表Schema索引。seq只确认连续持久事实，事件ACK不是执行grant。暂停不影响握手、同步或忙碌/目录；删除沿既有凭据失效/撤销及连接关闭处理。资源HTTP的404不代替未认证Worker的401/403/4401/4403。HTTP错误detail、API令牌和remoteAccess字段都不新增到Worker帧。

<!-- BEGIN WIRE_INDEX -->
| 线路修订 | type | 类型 | 事实源 |
| --- | --- | --- | --- |
| 1 | `worker.hello` | `RemoteWorkerHello` | `remote.json#/$defs/RemoteWorkerHello` |
| 1 | `worker.hello_ack` | `RemoteWorkerHelloAck` | `remote.json#/$defs/RemoteWorkerHelloAck` |
| 1 | `worker.hello_rejected` | `RemoteWorkerHelloRejected` | `remote.json#/$defs/RemoteWorkerHelloRejected` |
| 1 | `worker.heartbeat` | `RemoteWorkerHeartbeat` | `remote.json#/$defs/RemoteWorkerHeartbeat` |
| 1 | `server.heartbeat` | `RemoteServerHeartbeat` | `remote.json#/$defs/RemoteServerHeartbeat` |
| 1 | `worker.events_ack` | `RemoteEventAck` | `remote.json#/$defs/RemoteEventAck` |
| 1 | `conversation.gap` | `RemoteConversationGap` | `remote.json#/$defs/RemoteConversationGap` |
| 1 | `run.submit` | `RemoteRunSubmitCommand` | `remote.json#/$defs/RemoteRunSubmitCommand` |
| 1 | `run.pause` | `RemotePauseCommand` | `remote.json#/$defs/RemotePauseCommand` |
| 1 | `run.resume` | `RemoteResumeCommand` | `remote.json#/$defs/RemoteResumeCommand` |
| 1 | `run.cancel` | `RemoteCancelCommand` | `remote.json#/$defs/RemoteCancelCommand` |
| 1 | `run.retry` | `RemoteRetryCommand` | `remote.json#/$defs/RemoteRetryCommand` |
| 1 | `approval.decide` | `RemoteApprovalDecisionCommand` | `remote.json#/$defs/RemoteApprovalDecisionCommand` |
| 1 | `command.withdraw` | `RemoteCommandWithdrawalCommand` | `remote.json#/$defs/RemoteCommandWithdrawalCommand` |
| 1 | `conversation.skip` | `RemoteConversationSkip` | `remote.json#/$defs/RemoteConversationSkip` |
| 1 | `conversation.skip_recorded` | `RemoteSkipRecorded` | `remote.json#/$defs/RemoteSkipRecorded` |
| 1 | `command.accepted` | `RemoteCommandAccepted` | `remote.json#/$defs/RemoteCommandAccepted` |
| 1 | `command.rejected` | `RemoteCommandRejected` | `remote.json#/$defs/RemoteCommandRejected` |
| 1 | `command.completed` | `RemoteCommandCompleted` | `remote.json#/$defs/RemoteCommandCompleted` |
| 1 | `command.failed` | `RemoteCommandFailed` | `remote.json#/$defs/RemoteCommandFailed` |
| 1 | `command.control_result` | `RemoteControlObserved` | `remote.json#/$defs/RemoteControlObserved` |
| 1 | `run.state_changed` | `RemoteRunStateEvent` | `remote.json#/$defs/RemoteRunStateEvent` |
| 1 | `message.appended` | `RemoteMessageEvent` | `remote.json#/$defs/RemoteMessageEvent` |
| 1 | `approval.state_changed` | `RemoteApprovalEvent` | `remote.json#/$defs/RemoteApprovalEvent` |
| 1 | `run.progress` | `RemoteProgressEvent` | `remote.json#/$defs/RemoteProgressEvent` |
| 1 | `capability.changed` | `RemoteCatalogEvent` | `remote.json#/$defs/RemoteCatalogEvent` |
| 1 | `events.omitted` | `RemoteOmittedEvents` | `remote.json#/$defs/RemoteOmittedEvents` |
| 2 | `approval.decide` | `RemoteV2ApprovalDecisionCommand` | `remote-sync.json#/$defs/RemoteV2ApprovalDecisionCommand` |
| 2 | `approval.state_changed` | `RemoteV2ApprovalEvent` | `remote-sync.json#/$defs/RemoteV2ApprovalEvent` |
| 2 | `run.cancel` | `RemoteV2CancelCommand` | `remote-sync.json#/$defs/RemoteV2CancelCommand` |
| 2 | `capability.changed` | `RemoteV2CatalogEvent` | `remote-sync.json#/$defs/RemoteV2CatalogEvent` |
| 2 | `command.accepted` | `RemoteV2CommandAccepted` | `remote-sync.json#/$defs/RemoteV2CommandAccepted` |
| 2 | `command.completed` | `RemoteV2CommandCompleted` | `remote-sync.json#/$defs/RemoteV2CommandCompleted` |
| 2 | `command.failed` | `RemoteV2CommandFailed` | `remote-sync.json#/$defs/RemoteV2CommandFailed` |
| 2 | `command.rejected` | `RemoteV2CommandRejected` | `remote-sync.json#/$defs/RemoteV2CommandRejected` |
| 2 | `command.withdraw` | `RemoteV2CommandWithdrawalCommand` | `remote-sync.json#/$defs/RemoteV2CommandWithdrawalCommand` |
| 2 | `command.control_result` | `RemoteV2ControlObserved` | `remote-sync.json#/$defs/RemoteV2ControlObserved` |
| 2 | `conversation.gap` | `RemoteV2ConversationGap` | `remote-sync.json#/$defs/RemoteV2ConversationGap` |
| 2 | `conversation.skip` | `RemoteV2ConversationSkip` | `remote-sync.json#/$defs/RemoteV2ConversationSkip` |
| 2 | `worker.events_ack` | `RemoteV2EventAck` | `remote-sync.json#/$defs/RemoteV2EventAck` |
| 2 | `message.appended` | `RemoteV2MessageEvent` | `remote-sync.json#/$defs/RemoteV2MessageEvent` |
| 2 | `events.omitted` | `RemoteV2OmittedEvents` | `remote-sync.json#/$defs/RemoteV2OmittedEvents` |
| 2 | `run.pause` | `RemoteV2PauseCommand` | `remote-sync.json#/$defs/RemoteV2PauseCommand` |
| 2 | `run.progress` | `RemoteV2ProgressEvent` | `remote-sync.json#/$defs/RemoteV2ProgressEvent` |
| 2 | `run.resume` | `RemoteV2ResumeCommand` | `remote-sync.json#/$defs/RemoteV2ResumeCommand` |
| 2 | `run.retry` | `RemoteV2RetryCommand` | `remote-sync.json#/$defs/RemoteV2RetryCommand` |
| 2 | `run.state_changed` | `RemoteV2RunStateEvent` | `remote-sync.json#/$defs/RemoteV2RunStateEvent` |
| 2 | `run.submit` | `RemoteV2RunSubmitCommand` | `remote-sync.json#/$defs/RemoteV2RunSubmitCommand` |
| 2 | `server.heartbeat` | `RemoteV2ServerHeartbeat` | `remote-sync.json#/$defs/RemoteV2ServerHeartbeat` |
| 2 | `conversation.skip_recorded` | `RemoteV2SkipRecorded` | `remote-sync.json#/$defs/RemoteV2SkipRecorded` |
| 2 | `worker.heartbeat` | `RemoteV2WorkerHeartbeat` | `remote-sync.json#/$defs/RemoteV2WorkerHeartbeat` |
| 2 | `worker.hello` | `RemoteV2WorkerHello` | `remote-sync.json#/$defs/RemoteV2WorkerHello` |
| 2 | `worker.hello_ack` | `RemoteV2WorkerHelloAck` | `remote-sync.json#/$defs/RemoteV2WorkerHelloAck` |
| 2 | `worker.hello_rejected` | `RemoteV2WorkerHelloRejected` | `remote-sync.json#/$defs/RemoteV2WorkerHelloRejected` |
| 2 | `sync.conversation.upserted` | `RemoteV2ConversationUpserted` | `remote-sync.json#/$defs/RemoteV2ConversationUpserted` |
| 2 | `sync.message.segment` | `RemoteV2MessageSegment` | `remote-sync.json#/$defs/RemoteV2MessageSegment` |
| 2 | `sync.run.state` | `RemoteV2SyncedRunState` | `remote-sync.json#/$defs/RemoteV2SyncedRunState` |
| 2 | `sync.conversation.deleted` | `RemoteV2ConversationDeleted` | `remote-sync.json#/$defs/RemoteV2ConversationDeleted` |
| 2 | `sync.reset` | `RemoteV2SyncReset` | `remote-sync.json#/$defs/RemoteV2SyncReset` |
| 2 | `sync.busy.snapshot` | `RemoteV2BusySnapshot` | `remote-sync.json#/$defs/RemoteV2BusySnapshot` |
| 2 | `sync.backfill.progress` | `RemoteV2BackfillProgress` | `remote-sync.json#/$defs/RemoteV2BackfillProgress` |
| 2 | `command.received` | `RemoteV2CommandReceived` | `remote-sync.json#/$defs/RemoteV2CommandReceived` |
| 2 | `command.delivery_granted` | `RemoteV2DeliveryGrant` | `remote-sync.json#/$defs/RemoteV2DeliveryGrant` |
| 2 | `conversation.update` | `RemoteV2ConversationUpdateCommand` | `remote-sync.json#/$defs/RemoteV2ConversationUpdateCommand` |
| 2 | `conversation.create` | `RemoteV2ConversationCreateCommand` | `remote-sync.json#/$defs/RemoteV2ConversationCreateCommand` |
| 2 | `sync.content.redaction` | `RemoteV2ContentRedaction` | `remote-sync.json#/$defs/RemoteV2ContentRedaction` |
<!-- END WIRE_INDEX -->

## 12. 版本、弃用、发布和后续扩展

HTTP `/api/v2`在包minor升级时不换路径；0.8保留N−1（0.7）既有路由/请求及旧字段语义，新设备字段可选，缺省按兼容值处理，旧撤销保留deprecated。0.8新功能不能在0.7服务上悄悄降级成撤销；旧服务返回未知路由时提示升级。0.7设备列表中新默认includeRevoked=false是本次明确的产品过滤策略。

HTTP读取方须容忍新增响应字段、对未知错误码走通用message/requestId处理；服务器对请求仍严格验证。生成DTO是本包生产/验证边界，旧严格DTO不能假定会校验未来JSON，第三方应使用匹配版本的生成包或做兼容投影；本次不放宽Worker解析器。protocolVersion用于诊断/功能判断，不要求与客户端包字符串相等。

D42的线路N/N−1策略继续为[2,1]，**不等于包0.8/0.7就是wire8/wire7**。修订2旧错误值域现也独立固定，仅类型引用调整，线上字段与接受集合不变；新错误只走HTTP。弃用先标记、保留至少N/N−1升级窗口，公告替代接口并完成调用方迁移后，另行批准破坏性移除，不随部署直接删旧路由。

P1须提供公开GET `/api/v2/openapi.json`，返回仓库bundle的等价JSON且由服务端测试比对；只有类型和合成示例，不注入实际设备、账号、密钥或部署数据。可选托管离线可视化文档页，建议使用随包固定版本的本地静态资源，禁止依赖外网CDN；不是本轮必做。页面也不能自动填入真实PAT或记录Try-it请求体。

文档维护命令：`python packages/protocol/remote/api-contract.py --write`生成bundle和表格；不带参数检查漂移。另跑既有`pwsh scripts/protocol/validate.ps1 -CheckGenerated`检查DTO生成物。不能修改手写表格绕过注册表。

以后资源使用复数名词和稳定URI，例如`/conversations`；权限用`资源:动作`精确命名。新增资源的PAT能力必须单独审批、定义scope及逐路由白名单，不因已有devices:manage而自动开放对话/审批/模型能力。新增危险动作单独scope，不用通配或“管理员”隐式包含。
