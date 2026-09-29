---
wp: R3-P1
status: done
scope_declared: [apps/server/**, .hqagent/handoffs/R3-P1-server.md]
scope_touched: [apps/server/Caddyfile.example, apps/server/README.md, apps/server/scripts/smoke.py, apps/server/scripts/smoke_native.py, apps/server/server/app.py, apps/server/server/events_sync.py, apps/server/server/http.py, apps/server/server/native.py, apps/server/server/native_events.py, apps/server/server/queries.py, apps/server/server/replica.py, apps/server/server/repository.py, apps/server/server/repository_devices.py, apps/server/server/repository_native.py, apps/server/server/repository_sync.py, apps/server/server/resources/http-errors.json, apps/server/server/resources/remote-hub.v2.bundle.json, apps/server/server/service.py, apps/server/server/service_sync.py, apps/server/server/wire.py, apps/server/server/worker.py, apps/server/tests/r3_support.py, apps/server/tests/test_devices_tokens.py, apps/server/tests/test_protocol.py, apps/server/tests/test_r15_policy.py, apps/server/tests/test_r3_guards.py, apps/server/tests/test_r3_native.py, apps/server/tests/test_native_sync_disabled.py, .hqagent/handoffs/R3-P1-server.md]
build: pass
tests: pass
commit: a854c27dc219178a1491a573df54c5ccaac4321b
open_questions: 0
---

## 基线与范围

基于 `a8eccec`（integration 已同步协议0.9.1），工作分支 `feat/remote-server`。首次简单命令输出 `environment-ok`，工作区初始干净。已读 R3-P0 冻结及0.9.1补冻、R3-contract、remote-native Schema 和对外规范；没有修改协议、P2工作区、前端或共享根配置，没有合回 integration，也没有部署或访问远端服务器。

本包实现云端39个 HTTP 操作和 Worker 修订[1,2,3]。0.9.1新增本机接口属于P2，没有在云端伪造本机同步201接口。服务端不调用模型、不读取电脑文件系统、不保存模型凭据；只处理认证、投影、临时通信和持久命令事实。

## 契约规则落点

| 规则 | 文件及处理 | 主要测试 |
| --- | --- | --- |
| 修订3编解码与旧错误域 | `wire.py` 增加 CODECS[3]；先读取修订判别，再严格生成 DTO 校验；旧线路 error/reason 只用固定旧域，不能发送新增R3或D50 HTTP-only码 | 既有协议测试、`test_upgrade_blocks_unapplied_old_event_and_wire_errors_stay_frozen` |
| 2↔3双向栅栏 | `worker.py` 先持久化升级目标；`service_sync.on_hello` 核对旧命令终态/未明控制结果、Outbox、未应用事件和双方ACK，保存双方水位；`ready` 禁止栅栏期间创建旧线路新命令。旧连接仍可对账，不重写旧修订/epoch/seq/hash | `test_bidirectional_upgrade_fence_blocks_pending_and_requires_ack` 两个方向；旧rev1/rev2全量回归 |
| 六条Cookie路由 | `app.py.ROUTES/browser` 增加列表、详情、消息临时读取、导入、目录浏览、登记项目；沿现有认证/CSRF/幂等/限速/owner检查。catalog HTTP绑定升级为 RemoteV3CatalogView | `test_http_binding_completeness`、PAT逐路由拒绝、R3全流程 |
| 索引与公开ID | `native.py` 按 owner/worker/store 映射本机 native/workspace；`native_events.py` 接收版本化索引，过滤工作区，映射catalog及native对话；列表按updatedAt/ID、过滤绑定签名cursor | `test_r3_index_isolation_paging_and_reset_erasure`、导入全文同步测试 |
| 索引清理/删除栅栏 | `repository_native.py` 擦除索引投影及可靠日志正文，保留哈希/seq/删除栅栏；`events_sync.py` 支持 native.index.deleted、索引限定ContentRedaction及迟到旧索引零正文处理；reset/撤销/删除走现有清理入口 | `test_native_delete_redaction_gap_and_late_index_do_not_resurrect`、`test_late_index_behind_delete_gap_is_erased_before_contiguous_ack`、workspace移除及设备删除直接查库 |
| 临时查询隔离 | `queries.py` 独立内存关联/拼装；`worker.py` 在持久事件事务前分流query结果；不写Inbox/Outbox、浏览器事件、通用幂等结果或正文日志。目录POST仅`query-intent`摘要 | `test_native_read_query_out_of_order_duplicate_no_database_or_logs`、`test_directory_query_digest_only_and_worker_token_rejection`；真实进程冒烟直接查库 |
| 有界查询与清理 | 入口起算10秒总期限；4/设备、16/账号；≤1MiB、≤128片、字符/UTF-8/整帧上限；绑定queryId/requestId/connection/epoch/store，校验重复片、完整hash、DTO及资源身份；返回前再鉴权/检查当前授权并核对期限 | `test_query_failure_cleans_memory_and_never_persists` 五种失败、账号/设备上限、旧连接片段丢弃、根/workspace移除在途查询 |
| resource命令 | `native.enqueue_resource`、`service_sync.received/expire`、`native_events.resource`；没有伪造conversationId/runId/sequence。30秒只约束未获grant的送达窗口，grant之后等待Worker真实结果 | `test_resource_import_confirmation_grant_and_native_full_sync`、deadline两种时序、reset后已grant命令对账、结果先于同步仍可轮询 |
| 导入确认与续接 | `native.py` 依据显式terminalClosedConfirmed和当前版本生成confirmation；正向活跃证据拒绝。`native_events.py`核对并记录Worker确认；native对话省略scene，按本机绑定映射，run.submit只允许continue，必要时重新签发确认 | 显式确认/版本参数化测试、导入完整历史及后续native消息帧生成DTO校验 |
| 暂停门禁 | R3入口复用ready，再要求修订3；原生历史查询read豁免暂停，目录/导入/登记禁止；暂停仓储筛选从修订2扩为≥2，所有未grant资源窗口失败 | `test_pause_read_allowed_resource_blocked_and_workspace_register`、既有D50竞争/豁免回归 |
| 授权根与选择引用 | 只接受DirectoryListingInput/RemoteWorkspaceRegisterInput，不接受路径；服务端核对当前rootId/version，Worker验证引用签名/期限、真实目录、TOCTOU与grant后登记。根移除时拒绝在途查询和尚未grant登记 | 根移除在途查询、`test_root_removed_before_grant_denies_registration`、Worker query.failed的过期/失效错误转达、登记只依据Worker结果/catalog |
| 请求追踪与发布物 | `http.py` 保留单条结构化完成日志；仅内部增加不输出的受理起始时间。资源请求/临时查询/确认使用同一个入口requestId。两份包资源更新为0.9.1、81错误码，OpenAPI原样发布 | 全量requestId/日志测试、独立发行ZIP包资源测试、OpenAPI JSON等价、smoke |

## 存储和取舍

复用schema4的owner-scoped `records`、`sync_ids`、`sync_log` 和现有事务；没有新第三方依赖、没有SQL进入业务模块，也不需要ALTER TABLE。新增记录种类为 `native-index`（安全索引元数据）、`native-fence`（无正文代次/seq）、`native-confirmation`（Worker已记录的确认审计）、`query-intent`（目录请求的域隔离摘要）。ID映射沿现有sync_ids，工作区/原生/对话各有独立kind。设备删除清理新增关联记录；同步关闭删除索引与正文，保留必要审计/去重身份。

临时结果只驻留在当前事件循环的有界future/parts中，没有恢复机制。断线、超时、reset、删除、workspace/根授权移除使关联失败并清空拼段；取消HTTP等待同样清理。旧连接退出不会误伤替换连接的新查询。强类型页完整校验后才映射云端nativeSessionId；消息ID用owner/worker/store/native范围的域隔离HMAC得到稳定公开ID，无需为读取正文建表。完整消息片段校验hash/字节数，跨页消息只传合法连续片段，不伪造完整消息。

目录同键同体可以重新查询，但先重新授权、检查根版本；只保存请求摘要，绝不缓存目录页或选择引用。目录token与真实路径的签名/过期/链接安全由持有本机秘密和文件系统的Worker负责，本包测试模拟Worker返回结构化拒绝，并验证服务器转达与根授权失效。这里不把服务端测试冒充电脑上的真实符号链接/TOCTOU验证。

导入/登记回执及grant是持久资源命令，允许通用幂等缓存保存不含历史正文的202元数据。导入confirmation只由已认证用户的显式动作生成，Worker仍做最终进程/源文件/写锁检查。grant持久化后，不用送达deadline判定导入计算失败。即使completed先于对话upsert，GET command仍可报告已提交resourceRef；对话尚未同步则GET conversation仍404。已导入对话遵循原有完整同步、pc_only过滤、busy、取消和正文删除。

对已grant命令，reset后仍保留无正文执行证据与必要确认关联，允许迟到completed对账并擦除其中展示reason，不复活副本。资源命令无conversationSeq，过期不创建虚假skip；原run.submit仍分配顺序槽并使用其原修订skip。D50暂停的新HTTP码也没有放入任何Worker帧。

HTTP读取参数严格按冻结OpenAPI：云端原生messages支持before/limit，不把最新索引sourceRevision硬塞进Worker读取。0.9.1本机messages的额外sourceRevision参数属于P2。原生分页before由Worker签发，云端不解码其源切点。

旧测试没有删除/skip/xfail。协商的未知修订用4替代现已支持的3，支持列表精确更新到[1,2,3]；发行包断言由0.8/33/72更新为0.9.1/39/81。完整HTTP绑定测试原断言保留，修复实际catalog绑定。曾发现新增的通用epoch校验误拦旧持久事件重放，已移除该错误校验；旧epoch持久事件保持原报文在当前认证连接重放，只有临时查询绑定当前epoch。这由既有断言及新增测试共同验证。

## 真实验收命令与输出

测试全部串行，没有pytest并行worker。并发上限用例仅在同一次测试中发起有限并发HTTP请求，不启动并行测试进程。TEMP/TMP/`--basetemp`全部在worktree内已忽略的 `apps/server/.tmp`；没有用默认临时目录的WinError 5修改业务逻辑。本轮没有出现0xC0000142或额度错误，没有联网安装。

在 `apps/server`：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q --tb=short -p no:cacheprovider --basetemp=.tmp/r3-delivery
```

```text
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
.......                                                                  [100%]
=============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-server\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
223 passed, 1 warning in 63.34s (0:01:03)
```

新增28项R3测试。警告是预装Starlette/httpx的既有弃用提示，没有为了压警告引入httpx2。完整命令输出在忽略目录 `.tmp/r3-delivery-output.txt`。

```powershell
../../.venv/Scripts/python.exe -B scripts/smoke.py
```

```text
Account created
uvicorn listening on loopback: PASS
browser login and secure session: PASS
pairing preview and confirmation: PASS
fake Worker revision 2, create/grant/sync, offline refusal and reconnect: PASS
revision 3 index, ephemeral queries, resource grant and imported history: PASS
ephemeral query body and selection absent from database: PASS
packaged public OpenAPI and request IDs: PASS
PAT issuance, device pause/resume/delete and immediate revocation: PASS
Consistent backup created
server output credential redaction: PASS
SMOKE PASS
```

真实进程冒烟串行创建CLI账号、启动uvicorn，仅访问127.0.0.1；通过可信本机代理协议头模拟TLS终结后的后端连接。连接的是按协议DTO说话的假Worker，不是用户真实原生会话。退出检查日志中没有账号口令、Cookie、Authorization secret、配对码、PAT或查询正文/选择引用，并直接查询SQLite全部表确认临时正文未落库。输出 `.tmp/r3-delivery-smoke-output.txt`。

仓库根目录：

```powershell
$env:PATH=(Join-Path $PWD '.venv/Scripts')+';'+$env:PATH
$env:TEMP=(Join-Path $PWD 'apps/server/.tmp')
$env:TMP=$env:TEMP
pwsh scripts/protocol/validate.ps1 -CheckGenerated
```

```text
协议校验通过：427 个类型，289 个 Contract Fixture
```

输出 `.tmp/r3-delivery-protocol-output.txt`。协议和生成物没有产生修改。服务端26个Python模块还通过标准库compile语法检查；`git diff --check`无空白错误（Git仅提示工作副本CRLF将规范化为LF）。没有执行Docker镜像构建或实际部署。

## P2 / 前端 / 部署接线

- 启动与创建账号仍按 `apps/server/README.md`，没有预设测试账号；CLI交互或stdin输入口令。公开 `/api/v2/openapi.json` 可确认0.9.1及39条操作。发行时带上 `server/resources/*.json`，部署路径 `/opt/hqremote/app` 不需要协议源码目录；运行时仍安装匹配DTO包。
- P2先以3握手；2↔3栅栏失败时继续原修订对账，旧命令/事件最终事实和水位一致后再切换。不要改写已持久Outbox报文。目录catalog的authorizedRoots须为真实完整集合；workspace和native帧ID为本机ID，服务端HTTP返回的是映射ID。
- 临时query帧必须回带queryId/requestId/connectionId/worker/store/epoch，query结果不带seq/eventId，不期待events_ack或grant；10秒内完成完整JSON分段。失败走query.failed，不在message或其它可靠事件里夹带临时正文。根/目录token验签、15分钟期限、真实路径与TOCTOU仍需P2独立验证。
- native.import/workspace.register是无conversationId的资源命令；command.received仅预留，必须等显式持久delivery_granted后执行。目录登记在grant后再次核对授权；导入后completed的resourceRef与后续sync对话使用相同本机ID。原生历史全文只从电脑的修订3同步进入云端。
- 前端列表/详情使用公开ID，读取页只保存在当前内存。目录浏览POST也带CSRF及幂等键。原生unknown可只读，导入明确确认；202只表示传输意图，轮询command并等对话/全文同步，不能把30秒窗口当作已grant导入的计算倒计时。native发送只允许continue。
- `Caddyfile.example`显式流式转发；README列出Nginx的 `proxy_buffering off`、`proxy_request_buffering off`、`proxy_max_temp_file_size 0`、`proxy_cache off`。禁止网关/APM/中间件正文采集和磁盘缓存，no-store本身不够。未修改任何已上线服务或代理配置。

## 提交与剩余边界

- `d98842c`：修订3、索引、临时查询、资源命令、HTTP与包发布物。
- `6d8230e`：R3测试、旧版本断言适配、真实进程冒烟。
- README、Caddy示例及本回执另作文档提交；头部commit指最后实现/测试提交。每次提交后均执行 `git log -1 --format=%B`，提交信息无署名。

本包要求的服务端范围已完成，无协议裁决请求。未做P2本机文件读取插件、真实路径/链接验证、模型执行、前端实现、真实CLI联调、Docker镜像构建或云端部署；这些不能由服务端的合成Worker测试替代。本回执只宣称上述本地命令已实际通过。

## 返修 1（2026-09-29）：已完成，适配协议0.9.2同步关闭语义

上轮因列表/详情缺少错误声明而停止，记录提交为 `cbdaad7`；W0已在0.9.2补冻，原Q1关闭。此次基线为 `4d8ed9a merge: sync integration with protocol 0.9.2`，起始工作区干净。已读R3-P0「补冻0.9.2」和R3-contract §9新规则；三条GET现均声明REMOTE_SYNC_DISABLED及HTTP409，冻结文案为“这台电脑已关闭同步”。没有修改协议，保留集成中的 `970dfbb` workspace映射修复。

### 实现与边界

- `native.py::native_sync_enabled` 先按owner读取存在且未删除的设备，再检查当前workerStoreId的副本enabled状态。列表在同步关闭时返回409，不返回空页；没有同步状态记录时沿既有默认enabled语义处理。
- 详情/读取使用 `native_get(check_sync=True)`：先通过现有 `sync_ids` 的owner/公开ID映射确认worker/store，再检查设备存在、当前store匹配、同步状态，最后读取索引及工作区可见性。未知或跨owner的ID不会被用来猜设备；删除设备/失效映射优先404。同步开启但已无索引时仍404。
- `app.py` 的资源鉴权分支针对native_detail/native_read调用上述路径，避免通用browser_get在reset已擦除投影后提前404；认证仍发生在该分支之前。查询计划也使用同样检查，故同步关闭优先于在线查询/离线状态，不受暂停影响。
- 没有新增表、字段或内容保留。reset后只使用既有无标题/路径/正文的ID归属映射，不重建native-index。重新开启新generation并补传后正常恢复；开启但没有会话仍空页。
- 用现有 `scripts/package_contract.py` 更新服务端随包OpenAPI及错误映射为0.9.2；发布资源继续与协议bundle等价，运行时不依赖源码目录。README同步版本与优先级规则。

本轮实际改动仅：`server/app.py`、`server/native.py`、`server/resources/{http-errors.json,remote-hub.v2.bundle.json}`、`tests/{test_native_sync_disabled.py,test_r3_native.py,test_devices_tokens.py}`（均位于apps/server）、README及本回执。头部scope_touched为累计交付清单；头部commit、tests与完成状态已更新为本轮结果。

### 测试

新增 `tests/test_native_sync_disabled.py` 共5项用例：

- 同步关闭后三接口均409，准确文案、retryable=false、no-store与requestId头/信封一致；同时覆盖暂停、在线及断线后的读取优先级。
- reset直接查库：native-index清空、标题不残留，但无内容ID映射仍可用于确认归属。
- 未登录401、跨owner/未知ID/未知设备404；不能借本账号另一台已关闭同步的设备推测未知ID归属。
- 新generation空补传时列表空页，旧ID详情/读取404；索引补传后列表、详情和实际临时查询恢复200，暂停时也允许历史读取。
- 已删除设备，以及设备记录缺失但残留ID映射的情况，三接口均优先404。

旧reset详情测试的404断言按明确的0.9.2行为变更更新为409并精确检查REMOTE_SYNC_DISABLED；其它删除/workspace移除的404断言不变。独立发布资源测试的包版本精确更新为0.9.2，接口数39、错误码数81断言保留。未skip/xfail或删除测试。

### 本轮真实命令与输出

先定向验证：

```text
15 passed, 1 warning in 4.53s
```

在apps/server设置worktree内临时目录后，串行运行：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q --tb=short -p no:cacheprovider --basetemp=.tmp/r3-repair1-full
```

```text
........................................................................ [ 31%]
........................................................................ [ 63%]
........................................................................ [ 94%]
............                                                             [100%]
=============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-server\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
228 passed, 1 warning in 62.81s (0:01:02)
```

```powershell
../../.venv/Scripts/python.exe -B scripts/smoke.py
```

```text
Account created
uvicorn listening on loopback: PASS
browser login and secure session: PASS
pairing preview and confirmation: PASS
fake Worker revision 2, create/grant/sync, offline refusal and reconnect: PASS
revision 3 index, ephemeral queries, resource grant and imported history: PASS
ephemeral query body and selection absent from database: PASS
packaged public OpenAPI and request IDs: PASS
PAT issuance, device pause/resume/delete and immediate revocation: PASS
Consistent backup created
server output credential redaction: PASS
SMOKE PASS
```

仓库根：

```powershell
$env:PATH=(Join-Path $PWD '.venv/Scripts')+';'+$env:PATH
$env:TEMP=(Join-Path $PWD 'apps/server/.tmp')
$env:TMP=$env:TEMP
pwsh scripts/protocol/validate.ps1 -CheckGenerated
```

```text
协议校验通过：427 个类型，289 个 Contract Fixture
```

完整输出保存在已忽略的 `.tmp/r3-repair1-{targeted,full,smoke,protocol}-output.txt`。测试没有并行worker；并发HTTP仅用于临时查询响应模拟。TEMP/TMP/--basetemp避免默认沙箱临时目录WinError 5。warning为既有Starlette/httpx弃用提示，没有新依赖。没有发生执行限流、0xC0000142或额度错误；预期的业务限速测试按原断言正常通过。

实现/测试/发布物提交：`a854c27`。README及本回执另作说明提交，每次提交后执行 `git log -1 --format=%B` 自查，无署名。未合回integration，未部署；本轮必做范围无未完成项，open_questions=0。
