---
wp: R15plus-P1
status: done
scope_declared: [apps/server/**, .hqagent/handoffs/R15plus-P1-server.md]
scope_touched: [apps/server/README.md, apps/server/pyproject.toml, apps/server/scripts/package_contract.py, apps/server/scripts/smoke.py, apps/server/server/app.py, apps/server/server/common.py, apps/server/server/devices.py, apps/server/server/events_sync.py, apps/server/server/http.py, apps/server/server/public_contract.py, apps/server/server/repository.py, apps/server/server/repository_devices.py, apps/server/server/resources/http-errors.json, apps/server/server/resources/remote-hub.v2.bundle.json, apps/server/server/security.py, apps/server/server/service.py, apps/server/server/service_sync.py, apps/server/server/tokens.py, apps/server/server/wire.py, apps/server/server/worker.py, apps/server/tests/conftest.py, apps/server/tests/test_controls_storage.py, apps/server/tests/test_devices_tokens.py, apps/server/tests/test_security.py, apps/server/tests/test_spa_static.py, .hqagent/handoffs/R15plus-P1-server.md]
build: pass
tests: pass
commit: a36370b717f32c94ade1d27a541245761e2ca64b
open_questions: 0
---

## 基线与交付边界

在 `feat/remote-server` 的 `27871ba`（已同步协议 0.8.0）上实施。已读设备协议冻结回执、api-guide、OpenAPI/发布 bundle、R1.5-contract §9、D50；协议为事实源，没有改协议、其它应用、根配置或旧回执。没有合回 integration，没有访问阿里云或执行部署，也没有联网安装依赖。

完整实现 33 个 HTTP 操作及既有 Worker 修订 1/2。新增设备管理和 PAT 仅发生在服务端；没有模型调用、模型凭据或新 Worker 帧。现有 SQLite 仓储事务与生成 DTO 继续作为边界。

## 模块与规则落点

| 规则 | 实现 | 验证 |
| --- | --- | --- |
| 设备列表/过滤/分页/详情 | `devices.py`、`repository_devices.py`、`app.py`；创建 ordinal 稳定排序，游标绑定 owner、身份域和规范化过滤；limit 不入过滤域，旧有效设备游标返回 expired | `test_device_filters_cursor_scope_stable_order_and_defaults` |
| CAS、别名清除、版本与生命周期 | `devices.py.patch_device`；`service.py.save` 保护当前管理字段，旧 Worker 对象不能覆盖；旧记录按 enabled/version1 读取，后续保存写实值；撤销实际变化增版本 | `test_device_cas_idempotency_alias_lifecycle_and_stale_observation` |
| 暂停门禁与优先级 | `app.py` 缓存前检查 owner/可见性、revoked/suspended；`service_sync.py.ready/conversation/enqueue_v2` 的 cancel/reject 豁免贯穿各层 | `test_suspension_admission_exemptions_sync_and_resume`、`test_suspended_precedes_offline_freshness_and_revision_and_is_durable` |
| 暂停/grant 原子竞争 | `devices.py` 与 `service_sync.py.received` 共用仓储事务；只看修订2且未 grant 的窗口，包含原有 cancel/reject；失败记录保留，序号用既有 skip 退役 | `test_pause_grant_transaction_order_and_late_receipt`（两种顺序）、`test_real_concurrent_pause_and_grant_have_one_transaction_order`（真实双线程竞争） |
| 暂停后新拒绝 | `service_sync.py.approval` 允许新 HTTP 意图替代暂停所关闭的无许可窗口；旧 key 仍重放旧结果；`events_sync.py` 接受 Worker 对这些旧窗口的正常拒绝事实，不覆盖服务端失败原因 | `test_pause_closes_existing_safe_windows_but_new_reject_can_be_granted` |
| 删除、旧撤销、真擦除 | `delete_device` 先复用撤销/全部 store 清理，再由 `repository_devices.py.delete_device_content` 擦除显示对象、busy、暂存、可重放正文及配对元数据；同 key 后续 DELETE 也在缓存前 404；凭据保留不可逆拒绝材料 | `test_delete_erases_all_stores_bodies_staging_alias_and_credentials` 直接读全部表；`test_revoked_delete_cannot_resurrect_and_keeps_other_device` |
| grant/rev1 不确定性 | 删除保留必要 command-tombstone 中的摘要、grant、dispatch、状态/对账事实；停止投递，不声明停止本机任务 | `test_delete_dispatched_command_respects_wire_grant_semantics`（修订1和2），已 grant 清理用例 |
| PAT 签发/列表/吊销 | `tokens.py`；域隔离 HMAC、12字节 selector、独立32字节 secret；Cookie 管理，默认90天/最多365天；专用意图只存摘要/tokenId | `test_pat_issue_once_expiry_replay_metadata_and_no_plaintext`、约束参数化测试、列表分页/owner 测试 |
| 六路由精确 scope / 当前鉴权 | `tokens.py.PAT_SCOPES`、`Security`、`app.py`；无 scope 继承，PAT 写操作事务内重检有效性；校验后单独提交 lastUsedAt，即使业务失败也记录使用；业务事务再次校验防止并发吊销 | `test_pat_scopes_authentication_revoke_and_idempotency_namespace`、`test_pat_catalog_legacy_revocation_cross_owner_and_maximum_lifetime` |
| Cookie/PAT/设备身份、DELETE CSRF | `http.py.identity_headers` 在业务前拒绝歧义；只有 PAT 白名单且认证/scope 通过才免 Origin/CSRF；DELETE 纳入写请求；设备解析器拒绝 PAT 前缀 | `test_ambiguous_identity_and_cookie_delete_csrf`，旧账号/配对安全测试 |
| 来源限速与失败鉴权 | `http.py.RequestAudit` 在 PAT 校验前使用来源桶，GET 和失败鉴权同样计数；Cookie 原有限速保留 | `test_pat_failed_auth_uses_source_bucket_and_request_id`，既有限速测试 |
| requestId/审计日志/安全错误 | `http.py` 的 ASGI 入口和 ContextVar；信封/响应头同值，严格小写UUIDv4关联ID，每请求一条 JSON 完成记录；operation 来自随包规范。`common.py.http_view` 输出固定中文及可选安全 detail | `test_request_ids_completion_logs_errors_and_openapi`、`test_validation_never_echoes_unknown_names_inputs_or_raw_exceptions`、静态请求参数化测试 |
| 公开规范及错误映射 | `public_contract.py` 从包资源读取；`scripts/package_contract.py` 复制冻结 bundle 和 registry/guidance 的72条映射；`pyproject.toml` 声明 package-data | JSON 等价、完整错误映射测试、`test_publication_runs_from_standalone_package_without_checkout` |
| HTTP/Worker 错误隔离 | `common.py` 分开 HTTP 带 detail 输出与原 Worker 视图；`wire.py` 按两版固定错误 DTO 校验拒绝帧，HTTP 新码不会进入 Worker 线路 | `test_new_http_codes_cannot_enter_worker_error_domain`（修订1和2）；既有两版帧测试 |
| 全量绑定 | `app.py.ROUTES` 含全部33项；公开规范为 raw JSON 特例，PAT签发首次201/重放200各校验对应生成 DTO | `test_http_binding_completeness`，全部边界测试使用生成 DTO |

## 存储与设计取舍

- 不引入新数据库方言到业务层。仍使用 schema4 的通用 owner-scoped `records` 和 `auth`，没有 ALTER TABLE 需求。新增 `records.kind=api-token` 保存元数据/HMAC，`pat-intent` 保存永久摘要/tokenId；全局 `auth` 中公开 selector 只负责定位 owner，业务读取仍按 owner。未增加运行时依赖。
- PAT 一次秘密不会进入 `Service.replay`。首次响应丢失不可恢复；同键重放返回当前元数据（含 expired/revoked），不重新计算有效期。同键异体拒绝。普通 PAT 写操作幂等域额外含 tokenId；Cookie 沿原 owner/operation/target 域。
- 暂停保留连接及副本；管理操作不受在线/busy/暂停状态限制。已有 grant 不回滚，旧 rev1 可能已执行的事实不能套用 rev2 的“无 grant 即未获许可”。每次暂停切换关闭当时所有未 grant 窗口，新意图的 cancel/reject 仍可执行。未向 Worker 添加新 reason 或 HTTP 错误码。
- 删除在同一事务擦除所有 store 内容，再留下隐藏的设备最小墓碑、凭据拒绝验证值、命令身份/摘要/许可状态、事件身份/水位。配对预览、确认和管理幂等缓存也退休，避免从缓存返回旧设备快照。在线逻辑表直接查询无正文残留；不宣称物理擦除旧 WAL、空闲页或历史备份，延续 README 中既有备份生命周期边界。
- 管理版本只在实际管理/生命周期变化时递增；`save` 从当前事务行保留管理字段并阻止已删除 ID 复活。列表采用仓储 ordinal 游标，避免删除/修改导致 offset 重排。
- 规范资源随服务端发行，约1.1MB的 bundle 不在运行时反射生成。错误 JSON 从冻结来源导出，测试比对，避免部署目录下缺少源码或 PyYAML 时接口失败。Docker 原有整个 server 目录复制已包含资源；普通 wheel 由 package-data 携带。
- `test_http_binding_completeness` 原有所有信封型绑定断言保留；只给新公开 OpenAPI 操作新增明确的 raw schema 断言。旧 Worker 夹具的发起/轮询请求显式排除自动 Cookie，以符合新的歧义身份规则；没有放宽或删除既有业务断言。HTTP helper 改用新 RemoteHttpError，并区分 PAT 首次/重放的两个生成 DTO。

## 真实验证

所有验证串行，没有 pytest 并行 worker。TEMP/TMP/`--basetemp` 指向本 worktree 内被 git 忽略的 `apps/server/.tmp`；默认临时目录的 WinError 5 没有被当作代码故障。没有发生 0xC0000142 或额度错误。

在 `apps/server` 执行：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q --tb=short -p no:cacheprovider --basetemp=.tmp/devices-final
```

真实最终输出：

```text
........................................................................ [ 36%]
........................................................................ [ 73%]
...................................................                      [100%]
=============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-server\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
195 passed, 1 warning in 51.89s
```

这是195项全量结果；其中本包新增29项设备/PAT/发布测试与4项静态审计参数化测试。警告为预装 Starlette/httpx 的既有弃用提示，没有安装清单外 httpx2。早期回归曾发现游标版本判别、旧删除命令 skip 对账、夹具附带 Cookie 等问题，已修复后重跑；上述为最后全量结果。

```powershell
../../.venv/Scripts/python.exe -B scripts/smoke.py
```

真实输出：

```text
Account created
uvicorn listening on loopback: PASS
browser login and secure session: PASS
pairing preview and confirmation: PASS
fake Worker revision 2, create/grant/sync, offline refusal and reconnect: PASS
packaged public OpenAPI and request IDs: PASS
PAT issuance, device pause/resume/delete and immediate revocation: PASS
Consistent backup created
server output credential redaction: PASS
SMOKE PASS
```

该冒烟只在本机启动真实 uvicorn，用可信 loopback 代理头模拟 TLS 终结后的 HTTP/WSS 转发，账号由 CLI stdin 创建，Worker 为按生成 DTO 校验的假 Worker。新增 PAT 不打印到终端，进程完成日志落在忽略目录避免 Windows 管道缓冲堵塞，退出后检查所有凭据和配对码未出现在日志中。这不是公网部署或真实 Worker 的新一轮验收。

在仓库根执行：

```powershell
$env:PATH=(Join-Path $PWD '.venv/Scripts')+';'+$env:PATH
$env:TEMP=(Join-Path $PWD 'apps/server/.tmp')
$env:TMP=$env:TEMP
pwsh scripts/protocol/validate.ps1 -CheckGenerated
```

```text
协议校验通过：335 个类型，189 个 Contract Fixture
```

另外 `git diff --check` 无输出；对22个服务端 Python 模块调用标准库 `compile`，输出 `Syntax validation: 22 server modules passed`。独立 ZIP 发行资源导入包含在全量测试中。没有构建 Docker 镜像或实际部署。完整本地命令输出保存在忽略目录 `.tmp/devices-final-output.txt`、`.tmp/devices-smoke-output.txt`、`.tmp/devices-protocol-output.txt`。

## 接线与部署说明

- P3 可直接按0.8规范调用设备 PATCH/DELETE、筛选分页和 PAT 管理；详情/列表返回真实 remoteAccess/version。CAS 冲突读取授权后的 currentVersion 并刷新；同键重放可能是历史快照。删除后404表示已不存在，首次回执仍提醒本机执行可能继续。
- Cookie 流程需要 Origin/CSRF/幂等键（包括 DELETE）。测试 PAT 时显式 `credentials: omit`，只给精确设备路由附 Bearer；PAT 没有对话/审批或令牌管理权限。首次201显示 secret；重放200不得假装还有可复制秘密。scope 独立，不因 manage/delete 隐式授予 read。
- P2 不需要改帧。暂停照常接收同步、目录和 busy；未获 grant 的旧预留按原截止/skip处理，事件 ACK 不授予执行。删除关闭连接并拒绝旧凭据；新配对需新 secret 和新 workerId。
- 启动、账号创建、备份、代理可信来源配置延续 README。`/opt/hqremote/app` 发布时必须一并部署 `server/resources/*.json`，或者安装完整 wheel；只复制 Python 文件不够。公开规范无需账号，可用于部署后确认0.8能力。未改任何远端文件。

## 提交与未完成项

- `6a4a511`：设备管理、暂停/grant 门禁、PAT、HTTP追踪、错误域及随包资源。
- `a36370b`：契约/安全/并发/擦除/发行资源测试、绑定测试与真实进程冒烟。
- README 与本回执另作说明提交；头部 commit 指最后实现/测试提交。每次提交后执行 `git log -1 --format=%B` 自查，提交信息无署名。

必做范围无未完成项，无协议裁决请求。可选离线可视化文档 UI 没有实现；仅提供约定的原始公开 OpenAPI，不依赖外网 CDN。未执行镜像构建、部署或真实云端联调，不能用本机冒烟替代这些操作。
