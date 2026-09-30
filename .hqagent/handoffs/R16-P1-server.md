---
wp: R16-P1
status: done
scope_declared: [apps/server/**, .hqagent/handoffs/R16-P1-server.md]
scope_touched: [apps/server/README.md, apps/server/nginx-attachments.conf.example, apps/server/pyproject.toml, apps/server/requirements.txt, apps/server/scripts/smoke.py, apps/server/scripts/smoke_attachments.py, apps/server/server/app.py, apps/server/server/attachment_types.py, apps/server/server/attachments.py, apps/server/server/blobstore.py, apps/server/server/events.py, apps/server/server/events_sync.py, apps/server/server/native.py, apps/server/server/native_events.py, apps/server/server/queries.py, apps/server/server/replica.py, apps/server/server/repository.py, apps/server/server/repository_attachments.py, apps/server/server/resources/http-errors.json, apps/server/server/resources/remote-hub.v2.bundle.json, apps/server/server/service.py, apps/server/server/service_sync.py, apps/server/server/thumbnail_child.py, apps/server/server/wire.py, apps/server/server/worker.py, apps/server/tests/test_attachment_races.py, apps/server/tests/test_attachment_wire.py, apps/server/tests/test_attachments.py, apps/server/tests/test_controls_storage.py, apps/server/tests/test_devices_tokens.py, apps/server/tests/test_protocol.py, apps/server/tests/test_r15_policy.py, apps/server/tests/test_r3_guards.py, apps/server/tests/test_test_dependencies.py, .hqagent/handoffs/R16-P1-server.md]
build: pass
tests: pass
commit: a8c5b82ea44a711b03eae4758a06308bb522b5fb
open_questions: 0
---

## 基线与范围

基于 `90a38c9 merge: sync integration with attachments protocol 0.10.0`，分支feat/remote-server。开工简单命令输出environment-ok，工作区干净。已读R1.6-contract全文、R16-P0下游要点、用户附件方案及§10、api-guide §14、8条OpenAPI附件操作和11个新错误。没有修改协议、Hub、前端或共享根文件，没有合回integration、推送GitHub、联网安装或部署。

交付为云端47个HTTP操作与修订[1,2,3,4]。Pillow 12.3.0已写入requirements和pyproject；使用预装依赖。WSS只传清单，不传字节/下载URL/本机路径。Agent输入准备、真实图片识别及本机文件库由P2完成，不由服务器执行模型。

## 规则落点与取舍

| 契约规则 | 实现落点 | 验证 |
| --- | --- | --- |
| 修订4/升级栅栏 | `wire.py` CODECS[4]；`worker.py`、`service_sync.py`延续双方ACK/Outbox/未决检查；3→4把已持久最终观测的unconfirmed视为控制尝试终态，已在2→3通过的历史rev2终态也不重新卡住；原执行不确定性不改写 | `test_v3_to_v4_unconfirmed_control_fence`包含rev2/rev3历史、已确认/未确认；旧协议全量测试 |
| 8个HTTP操作 | `app.py.ROUTES`显式绑定；附件独立`Attachments.http/upload`分支在JSON整包读取前返回，原JSON限额不变；元数据使用生成DTO，下载明确为raw流 | `test_http_binding_completeness`覆盖47项，二进制media/schema分支保留严格检查 |
| raw上传/检测 | `attachment_types.py` + `blobstore.Stage`；≤64KiB分块计数/hash/UTF-8、NUL/二进制伪装检查；图片/PDF magic，安全NFC显示名与规范扩展名；长度谎报立即终止，非空/20M/图片10M限制 | 伪装exe、SVG、HTML、NUL、空文件、伪装后缀、大小、hash、Content-Length多/少字节、重复上传重新验内容 |
| BlobStore/崩溃窗口 | `blobstore.py`内部Protocol及本地实现stage_write/commit/open_read/delete/exists/abort；sha256 CAS，原子create-if-absent，不覆盖同hash赢家；`repository_attachments.py`只在仓储层使用SQL | 跨账号同hash保留有效引用，最后引用exists=false/open_read失败；模拟CAS提交后DB失败及启动清孤儿/temp |
| 状态与计量 | `attachments.py`；uploaded/reserved/attached与availability正交。每账号逻辑used/reserved独立；事务预留、每账号并发≤2，同键一个writer；同一附件多消息绑定按message集合去重，只计一次逻辑大小 | 配额/并发/同键竞争、Worker同附件两个消息、limits用量断言 |
| TTL/pin/维护 | 上传完成+86400秒；API即刻拒绝到期，启动和每5秒维护清理。发送原子reserve到commandId；未grant失败/拒绝/到期释放，grant后pin最多600秒，消息绑定后attached | 24h到期、启动恢复、600秒pin释放、发送预留/删除IN_USE |
| 手机发送清单 | `service_sync.send_message`调用prepare_send/reserve_send；同owner/同对话/可见/可用/未过期，顺序不变且互异≤5；图片核对所有目标角色或native能力；清单入payload后再算commandDigest | 清单精确匹配、发送>5映射ATTACHMENT_COUNT_EXCEEDED、未知图片能力拒绝及所有角色支持后带capabilityRevision |
| Worker上传下载 | 必须已有完整role=user消息的pending绑定；HTTP不创建消息；owner/store/generation及当前对话复检；originAttachmentId必须有同一grant命令清单及run绑定。Worker下载只能正式接单的grant清单或该设备已同步消息 | 未pending拒绝、旧generation/reset拒绝、origin绑定、未接单不可下载、已attached可下载 |
| 暂停Q1矩阵 | Cookie上传/发送被暂停门禁拒绝；Worker已有消息同步上传继续；历史下载两端可用 | `test_worker_pending_upload_and_suspension_matrix`，pc_only直接ID404；原D50回归 |
| 缩略图 | `thumbnail_child.py`独立进程；并发1、160MiB硬内存、8秒父进程期限，Linux CPU6秒/输出文件512KiB；40M像素/首帧/最长边512/新PNG无源元数据。失败unavailable，不回退原图 | Pillow真实PNG缩放/去元数据、错误图片不可用且thumbnail接口明确拒绝；生成/删除物理缩略图 |
| 真删除/并发栅栏 | `erase_replica`挂附件清理，覆盖各状态、预留、绑定、引用和临时块；原有sync_erase同时清命令/消息/Outbox/浏览器清单正文。事务提交后先关闭读者/终止解码，再按最新引用GC，不错删新引用 | 删除对话/reset/设备直接查metadata、blob-ref、upload、upload-intent、temp、CAS exists/read；读者句柄关闭；删除打断在途上传 |
| 恢复删除约束 | SQLite保留无正文attachment-deletion意图，`blobs/deleted/`持久身份日志；启动先应用保留的最新日志，退休旧快照文件/引用和可重放清单；未执行的journal回调由DB意图补齐 | `test_retained_deletion_journal_prevents_old_snapshot_blob_resurrection` |
| 下载头/期限 | attachment、nosniff、no-store、X-Request-Id、Content-Length；原文件octet-stream、缩略图PNG；Range为BAD_REQUEST；总120秒、send无进展30秒，中途失败不拼JSON | 原文件/缩略图测试、真实httpx增量下载hash/长度 |
| 日志与固定错误 | 沿requestId单条固定operation/status/errorCode/耗时，不写文件名、正文、URL、凭据；11个新错误纳入随包映射，旧wire错误域保持严格 | 捕获日志检查文件名/正文/Cookie/设备secret不存在；92错误映射及OpenAPI等价 |
| 新准备取消证据 | `events.py.finish_matrix`仅修订4接受input_preparation_cancelled，必须已确认无存活执行/孤儿；经command.updated发布，不塞入旧worker.event DTO | `test_cancel_preparation_evidence_is_projected_without_old_wire_event` |

## 存储、并发与安全边界

复用schema4的owner-scoped records和仓储事务，不新增SQL到业务层，不需要ALTER TABLE。新kind为attachment、blob-ref、upload（quota预留/在途身份）、upload-intent（摘要与ID）、upload-retired（无正文幂等墓碑）、attachment-binding（message/localAttachment复合授权映射）、attachment-local（同对话同本机附件多消息共享身份）、attachment-deletion（无正文删除意图）。物理引用数由blob-ref行集合表示；跨owner物理GC检查仅内部使用，不提供按hash访问HTTP。

路径沿HQREMOTE_DATA_DIR，实例数据库旁的 `blobs/cas/` 存原文件及重编码缩略图，`blobs/temp/`存临时块，`blobs/deleted/`存无正文删除身份。显示名不作路径。原子hard-link创建CAS目标，去重存在也重新读取并校验整个上传；失败/输者只abort自己stage。DB提交前已产生的CAS孤儿，异常路径及启动GC回收；GC/新增引用在同一仓储锁/事务栅栏复查。删除作用域后的原上传key只有不可逆摘要墓碑，不能自动重放复活文件。

上传开始先做认证/归属与额度预留，再读body；提交前再次检查Cookie/设备凭据、对话、store/generation、删除栅栏。Worker暂停豁免严格限定于已有本机消息的同步上传，不用于代发手机消息。pending仅元数据不计usedBytes，上传开始计reserved，提交转used；同hash新附件独立计逻辑量，重复同绑定不重复收费。

读者句柄登记在附件ID作用域；删除后关闭句柄并停止后续迭代，不等待整文件下载。无法收回已送出的字节，也不宣称擦除客户端副本。文件操作异常会保留未确认错误，不把留文件说成成功。恢复旧备份前必须保留/合并最新外部删除日志；只有旧DB和旧blobs、且最新删除日志丢失时，程序无法推断丢失的删除历史，不能宣称安全恢复。

缩略图父进程不导入Pillow解码图像；实际子进程使用基础Python解释器加预装Pillow路径，绕过Windows venv launcher，确保kill/wait目标是真正解码进程。Windows Job Object限制每进程内存；Linux RLIMIT_AS/CPU/FSIZE；安装限制失败即退出不解码。160MiB较保守，大图即使不超40M也可能因内存失败而无缩略图，原文件不被当作缩略图回退。后台维护5秒间隔满足每分钟清理要求；不引入并行图像解码池。

## 最终真实验证

所有测试串行；TEMP/TMP/--basetemp在worktree已忽略的 `.tmp`，避免默认WinError 5。未联网安装、未遇到0xC0000142或工具/API额度/限流错误。预期业务并发额度/限速错误在测试里按原契约断言，不是执行环境限流。

在apps/server：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q --tb=short -p no:cacheprovider --basetemp=.tmp/r16-delivery-final
```

```text
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 81%]
................................................                         [100%]
=============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-server\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
264 passed, 1 warning in 96.28s (0:01:36)
```

新增33项附件专项，全部生成DTO检查。任务给出的三个基线红灯：HTTP完整绑定、公开bundle等价、registry/guidance错误映射，均已修绿。旧版本计数/支持列表更新为0.10.0、47操作、92错误、[1,2,3,4]、未知修订5；Pillow精确依赖断言同步新增。没有删除、skip或xfail旧测试。二进制成功响应明确校验raw schema/media，其余原信封断言不放松。warning为既有Starlette/httpx弃用提示，未安装额外httpx2。

```powershell
../../.venv/Scripts/python.exe -B scripts/smoke.py
```

```text
Account created
uvicorn listening on loopback: PASS
browser login and secure session: PASS
pairing preview and confirmation: PASS
fake Worker revision 2, create/grant/sync, offline refusal and reconnect: PASS
20MB streaming RSS: baseline=93708288 peak=94666752 delta=958464 bytes; upload/download SHA256: PASS
revision 3 index, ephemeral queries, resource grant and imported history: PASS
ephemeral query body and selection absent from database: PASS
packaged public OpenAPI and request IDs: PASS
PAT issuance, device pause/resume/delete and immediate revocation: PASS
Consistent backup created
server output credential redaction: PASS
SMOKE PASS
```

20MB按十进制20,000,000字节，httpx generator每块≤65,536字节；下载使用iter_bytes(65536)，客户端/服务端均不整块组装。RSS采样实际uvicorn Python PID，Windows GetProcessMemoryInfo working set；本轮baseline 93,708,288、peak 94,666,752、delta 958,464字节（约0.914MiB）。脚本断言增量<16MiB，测量时只运行这一服务进程及客户端/采样线程，不与pytest或图像解码并行。它证明该本机合成文件传输有界，不等于线上Linux缩略图/cgroup总负载已经实测。

仓库根：

```powershell
$env:PATH=(Join-Path $PWD '.venv/Scripts')+';'+$env:PATH
$env:TEMP=(Join-Path $PWD 'apps/server/.tmp')
$env:TMP=$env:TEMP
pwsh scripts/protocol/validate.ps1 -CheckGenerated
```

```text
协议校验通过：507 个类型，373 个 Contract Fixture
```

协议文件/生成物没有修改。31个服务端模块标准库compile语法检查通过；git diff --check无空白错误（仅Git的CRLF→LF提示）。完整输出位于忽略目录 `.tmp/r16-delivery-final-output.txt`、`.tmp/r16-delivery-smoke-output.txt`、`.tmp/r16-delivery-protocol-output.txt`。

## serverD nginx：仅附件上传location

仓库文件：`apps/server/nginx-attachments.conf.example`。主代理部署时放进现有TLS server块，保留其它API既有限额；代码没有访问或修改服务器。413为代理拒绝时生成自己的安全requestId，信封和头同值；应用返回的错误仍沿上游原样透传。

```nginx
location ~ ^/api/v2/(conversations/[^/]+/attachments|worker/attachments)$ {
    client_max_body_size 20000000;
    client_body_buffer_size 64k;
    proxy_request_buffering off;
    proxy_buffering off;
    proxy_max_temp_file_size 0;
    proxy_cache off;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_read_timeout 125s;
    proxy_send_timeout 30s;
    client_body_timeout 30s;
    proxy_pass http://127.0.0.1:8080;
    proxy_intercept_errors off;
    access_log off;
    error_log /dev/null crit;
    error_page 413 = @attachment_too_large;
}
location @attachment_too_large {
    internal;
    default_type application/json;
    add_header X-Request-Id $request_id always;
    add_header Cache-Control no-store always;
    add_header X-Content-Type-Options nosniff always;
    return 413 '{"success":false,"error":{"code":"ATTACHMENT_TOO_LARGE","message":"附件超过大小限制","retryable":false},"requestId":"$request_id","protocolVersion":"0.10.0"}';
}
```

## 部署/联调仍需验证的项

1. 主代理为serverD Python3.11离线下载Pillow12.3.0匹配wheel并发布全部server代码/资源；实际运行账号对 `/var/lib/hqremote/blobs` 的权限、硬链接/rename/fsync和磁盘余量。未构建Docker镜像、未部署。
2. 在真实nginx站点测试20MB上传、超限代理413头/信封、关闭request buffering、其它API限额不变、TLS及可信代理IP配置；本机冒烟只用可信loopback代理头模拟TLS终结后链路，没有验证线上nginx配置语法/加载。
3. 在Linux/systemd MemoryMax=384M下测父进程+受限解码子进程的总峰值，验证RLIMIT和异常图片退出；本轮实际缩略图测试运行在Windows Job Object限制下，160MiB为实现预算，不冒充线上测量。
4. P2真实Worker：正式接单后下载、长度/hash失败不启动Agent、有限重试、300秒准备期限、取消/启动互斥、强杀恢复与busy清除。服务端只验证协议/授权/结构化结果，不能替代本机运行验收。
5. 用户方案§10真实截图识别、PDF/源码内容回答、桌面与手机缩略图展示、所选模型/CLI多图能力，需要P2/P3和真实设备联调；本包没有模型调用，不声称这些端到端效果已验收。
6. 上线前演练DB Backup API快照与CAS对应备份、保留最新deleted日志的恢复过程、存储快照销毁规则、代理/APM正文采集关闭。程序不会抹掉用户历史备份或已下载副本。

本包服务端实施与上述本地验收已完成；这些部署/其它端边界不以合成Worker测试代替。无新增协议问题，open_questions=0。

## 提交

- `f9cfbe6`：流式附件库、引用/额度/清理、缩略图子进程、修订4与HTTP接线、Pillow依赖和发布资源。
- `a8c5b82`：附件安全/竞争/恢复/线路测试、绑定/版本断言更新、真实20MB网络RSS冒烟。
- README、nginx上传示例和本回执另作文档提交。头部commit指最后实现/测试提交。每次提交后用git log -1 --format=%B自查，信息仅描述改动，无署名。未合回integration、未推送、未实际部署。
