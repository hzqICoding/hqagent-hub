---
wp: R3-P0
status: done
scope_declared: [packages/protocol/**, .hqagent/**, scripts/protocol/tests/test_remote_contract.py, scripts/protocol/tests/test_remote_link_browser_contract.py, scripts/protocol/tests/test_remote_sync_contract.py]
scope_touched: [".hqagent/.gitignore", ".hqagent/DECISIONS.md", ".hqagent/INTERFACES.md", ".hqagent/handoffs/R3-P0-protocol.md", ".hqagent/reviews/R3-P0/091-api-contract.txt", ".hqagent/reviews/R3-P0/091-tests.txt", ".hqagent/reviews/R3-P0/091-validate.txt", ".hqagent/reviews/R3-P0/api-contract.txt", ".hqagent/reviews/R3-P0/baseline-failures.txt", ".hqagent/reviews/R3-P0/baseline-integrity.txt", ".hqagent/reviews/R3-P0/legacy-tests.txt", ".hqagent/reviews/R3-P0/repair1-api-contract.txt", ".hqagent/reviews/R3-P0/repair1-tests.txt", ".hqagent/reviews/R3-P0/repair1-validate.txt", ".hqagent/reviews/R3-P0/specialist-tests.txt", ".hqagent/reviews/R3-P0/validate.txt", "packages/protocol/VERSION", "packages/protocol/fixtures/contracts/local-native.page.json", "packages/protocol/fixtures/contracts/manifest.json", "packages/protocol/fixtures/contracts/r3.active-native-evidence.json", "packages/protocol/fixtures/contracts/r3.confirmed-native-evidence.json", "packages/protocol/fixtures/contracts/r3.directory-entry.json", "packages/protocol/fixtures/contracts/r3.directory-listing-input.json", "packages/protocol/fixtures/contracts/r3.directory-listing-page.json", "packages/protocol/fixtures/contracts/r3.local-authorized-root-input.json", "packages/protocol/fixtures/contracts/r3.local-authorized-root.json", "packages/protocol/fixtures/contracts/r3.local-authorized-roots-input.json", "packages/protocol/fixtures/contracts/r3.local-authorized-roots-view.json", "packages/protocol/fixtures/contracts/r3.native-activity-evidence.json", "packages/protocol/fixtures/contracts/r3.native-activity.json", "packages/protocol/fixtures/contracts/r3.native-agent-type.json", "packages/protocol/fixtures/contracts/r3.native-closure-confirmation.json", "packages/protocol/fixtures/contracts/r3.native-continuation-confirmation.json", "packages/protocol/fixtures/contracts/r3.native-format-status.json", "packages/protocol/fixtures/contracts/r3.native-format-view.json", "packages/protocol/fixtures/contracts/r3.native-import-payload.json", "packages/protocol/fixtures/contracts/r3.native-local-conversation.json", "packages/protocol/fixtures/contracts/r3.native-message-page.json", "packages/protocol/fixtures/contracts/r3.native-message-part.json", "packages/protocol/fixtures/contracts/r3.native-read-input.json", "packages/protocol/fixtures/contracts/r3.native-remote-conversation.json", "packages/protocol/fixtures/contracts/r3.native-run-submit-payload.json", "packages/protocol/fixtures/contracts/r3.native-session-index.json", "packages/protocol/fixtures/contracts/r3.native.import-completed.json", "packages/protocol/fixtures/contracts/r3.remote-authorized-root.json", "packages/protocol/fixtures/contracts/r3.remote-native-import-input.json", "packages/protocol/fixtures/contracts/r3.remote-native-session-page.json", "packages/protocol/fixtures/contracts/r3.remote-native-session-view.json", "packages/protocol/fixtures/contracts/r3.remote-resource-queued-receipt.json", "packages/protocol/fixtures/contracts/r3.remote-resource-result-ref.json", "packages/protocol/fixtures/contracts/r3.remote-v3-approval-decision-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-approval-event.json", "packages/protocol/fixtures/contracts/r3.remote-v3-backfill-progress.json", "packages/protocol/fixtures/contracts/r3.remote-v3-busy-snapshot.json", "packages/protocol/fixtures/contracts/r3.remote-v3-cancel-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-catalog-event.json", "packages/protocol/fixtures/contracts/r3.remote-v3-catalog-view.json", "packages/protocol/fixtures/contracts/r3.remote-v3-command-accepted.json", "packages/protocol/fixtures/contracts/r3.remote-v3-command-completed.json", "packages/protocol/fixtures/contracts/r3.remote-v3-command-envelope.json", "packages/protocol/fixtures/contracts/r3.remote-v3-command-failed.json", "packages/protocol/fixtures/contracts/r3.remote-v3-command-receipt.json", "packages/protocol/fixtures/contracts/r3.remote-v3-command-received.json", "packages/protocol/fixtures/contracts/r3.remote-v3-command-rejected.json", "packages/protocol/fixtures/contracts/r3.remote-v3-command-withdrawal-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-content-redaction.json", "packages/protocol/fixtures/contracts/r3.remote-v3-control-confirmed.json", "packages/protocol/fixtures/contracts/r3.remote-v3-control-observed.json", "packages/protocol/fixtures/contracts/r3.remote-v3-control-result.json", "packages/protocol/fixtures/contracts/r3.remote-v3-conversation-create-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-conversation-deleted.json", "packages/protocol/fixtures/contracts/r3.remote-v3-conversation-gap.json", "packages/protocol/fixtures/contracts/r3.remote-v3-conversation-skip.json", "packages/protocol/fixtures/contracts/r3.remote-v3-conversation-update-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-conversation-upserted.json", "packages/protocol/fixtures/contracts/r3.remote-v3-delivery-grant.json", "packages/protocol/fixtures/contracts/r3.remote-v3-directory-query.json", "packages/protocol/fixtures/contracts/r3.remote-v3-event-ack.json", "packages/protocol/fixtures/contracts/r3.remote-v3-execution-event.json", "packages/protocol/fixtures/contracts/r3.remote-v3-message-event.json", "packages/protocol/fixtures/contracts/r3.remote-v3-message-segment.json", "packages/protocol/fixtures/contracts/r3.remote-v3-native-confirmation-recorded.json", "packages/protocol/fixtures/contracts/r3.remote-v3-native-import-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-native-index-deleted.json", "packages/protocol/fixtures/contracts/r3.remote-v3-native-index-upserted.json", "packages/protocol/fixtures/contracts/r3.remote-v3-native-read-query.json", "packages/protocol/fixtures/contracts/r3.remote-v3-omitted-events.json", "packages/protocol/fixtures/contracts/r3.remote-v3-pause-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-progress-event.json", "packages/protocol/fixtures/contracts/r3.remote-v3-query-failed.json", "packages/protocol/fixtures/contracts/r3.remote-v3-query-payload.json", "packages/protocol/fixtures/contracts/r3.remote-v3-query-result-segment.json", "packages/protocol/fixtures/contracts/r3.remote-v3-redacted-slot.json", "packages/protocol/fixtures/contracts/r3.remote-v3-resume-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-retry-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-run-state-event.json", "packages/protocol/fixtures/contracts/r3.remote-v3-run-submit-command.json", "packages/protocol/fixtures/contracts/r3.remote-v3-run-submit-payload.json", "packages/protocol/fixtures/contracts/r3.remote-v3-server-heartbeat.json", "packages/protocol/fixtures/contracts/r3.remote-v3-server-outbound-frame.json", "packages/protocol/fixtures/contracts/r3.remote-v3-skip-recorded.json", "packages/protocol/fixtures/contracts/r3.remote-v3-sync-conversation.json", "packages/protocol/fixtures/contracts/r3.remote-v3-sync-reset.json", "packages/protocol/fixtures/contracts/r3.remote-v3-synced-run-state.json", "packages/protocol/fixtures/contracts/r3.remote-v3-visible-worker-event.json", "packages/protocol/fixtures/contracts/r3.remote-v3-worker-event.json", "packages/protocol/fixtures/contracts/r3.remote-v3-worker-heartbeat.json", "packages/protocol/fixtures/contracts/r3.remote-v3-worker-hello-ack.json", "packages/protocol/fixtures/contracts/r3.remote-v3-worker-hello-rejected.json", "packages/protocol/fixtures/contracts/r3.remote-v3-worker-hello.json", "packages/protocol/fixtures/contracts/r3.remote-v3-worker-outbound-frame.json", "packages/protocol/fixtures/contracts/r3.remote-v3-workspace-register-command.json", "packages/protocol/fixtures/contracts/r3.remote-wire3-approval-view.json", "packages/protocol/fixtures/contracts/r3.remote-wire3-error-code.json", "packages/protocol/fixtures/contracts/r3.remote-wire3-error.json", "packages/protocol/fixtures/contracts/r3.remote-workspace-register-input.json", "packages/protocol/fixtures/contracts/r3.unsupported-native-index.json", "packages/protocol/fixtures/contracts/r3.workspace.register-completed.json", "packages/protocol/generated/go/protocol.go", "packages/protocol/generated/python/models.py", "packages/protocol/generated/ts/index.ts", "packages/protocol/openapi/local-chat.v2.yaml", "packages/protocol/openapi/local-hub.v1.yaml", "packages/protocol/openapi/remote-hub.v2.bundle.json", "packages/protocol/openapi/remote-hub.v2.yaml", "packages/protocol/registry/error-codes.yaml", "packages/protocol/remote/R1.5-contract.md", "packages/protocol/remote/R3-contract.md", "packages/protocol/remote/api-contract.py", "packages/protocol/remote/api-guide.md", "packages/protocol/remote/http-error-guidance.yaml", "packages/protocol/schema/local-chat.json", "packages/protocol/schema/local-native.json", "packages/protocol/schema/remote-native.json", "packages/protocol/schema/remote.json", "packages/protocol/tests/test_devices_api.py", "packages/protocol/tests/test_local_native_contract.py", "packages/protocol/tests/test_native_protocol.py", "scripts/protocol/tests/test_remote_contract.py", "scripts/protocol/tests/test_remote_link_browser_contract.py", "scripts/protocol/tests/test_remote_sync_contract.py"]
build: pass
tests: pass
commit: 271c9046e3bb9d7be62e563c2962a2a7dd3e030e
open_questions: 0
---

# R3-P0 协议冻结回执

协议0.9.0、wireRevision 3冻结，等待主代理审核，未合回integration。初次交付时旧测试集有三个基线失败，现已在返修1修复，全量495项通过；下文保留原始复现记录，最终结果见返修1。无needs-decision。基线为2b3377ccec33029f0976ffe42d9cab1ad69f930e。

## 冻结内容与取舍

- 独立remote-native.json，共91个新类型、48个修订3具体帧、99份合成Fixture；旧189份Fixture及修订1/2传递引用闭包不变。支持[1,2,3]，包版本不参与线路协商；3/2升级采用双向对账栅栏。
- 未导入终端会话只同步索引；正文以10秒、1MiB有界临时查询读取，不进可靠事件流、不落云端数据库/日志/幂等缓存。索引标题脱敏后最多120码点，明确属于上传内容。
- 导入沿30秒命令/provisional/grant，电脑提交完整脱敏历史与精确会话绑定，不自动启动模型。之后单Agent run.submit必须continue；native省略场景，旧scenario继续原语义。资源命令无伪造conversationId/runId/执行序号。
- unknown只读，显式关闭确认留审计，正向活跃证据不能被勾选覆盖；每次续接再检查，同一精确原生ID最多一个工具内写进程。新外部修改需要重新确认。
- 授权根只在电脑GET/PUT配置，默认空、最多32根；云端只见rootId/名称/版本，不见绝对根路径。逐层目录查询最多100条，不接收路径，仅接收电脑签发的短期选择引用；每次真实路径校验、根移除撤销、grant时再次检查。
- 六个新云端HTTP操作仅Cookie，PAT范围不扩展；目录浏览/导入/登记被暂停门禁禁止，原生历史只读允许。索引随设备删除、同步关闭、workspace移除清理；导入后的Hub内容沿R1.5。
- 新增错误码：REMOTE_QUERY_TIMEOUT（504/可重试）、REMOTE_QUERY_TOO_LARGE（413）、NATIVE_SESSION_ACTIVE（409）、NATIVE_SESSION_UNSUPPORTED（422）、NATIVE_SESSION_CHANGED（409）、NATIVE_SESSION_WRITER_CONFLICT（409）、REMOTE_ROOT_NOT_AUTHORIZED（403）、REMOTE_PATH_OUTSIDE_ROOT（403）、REMOTE_DIRECTORY_CHANGED（409）；后八项retryable=false。仅HTTP/修订3，旧错误域不扩大。
- 完整新类型列表在schema/remote-native.json的$defs，逐类型Fixture由manifest登记；接口、示例、错误总表及curl在api-guide.md和bundle，语义约束见R3-contract.md，D51已登记。

只读真实会话结构抽查观察到元数据/版本/消息块等，未保存真实消息、ID、cwd或文件名。观察不是读取插件已验证支持的保证；未知格式unsupported，来源无法确认不上传为终端会话。旧docs“导入仅索引”由用户v0.5 §8.3a覆盖，Attempt依D40映射，未修改docs。

## 本轮重跑命令与真实输出

```text
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：426 个类型，288 个 Contract Fixture

.venv/Scripts/python.exe -X utf8 -B packages/protocol/remote/api-contract.py
API contract verified: 33 current + 6 planned HTTP operations; 81 error codes; self-contained bundle; examples/auth/request IDs consistent

.venv/Scripts/python.exe -X utf8 -B -m pytest packages/protocol/tests -q -p no:cacheprovider --basetemp=.hqagent/r3-tmp/pytest-resume
191 passed in 13.36s
```

输出存档仅清理pytest空白行的行尾空格，测试内容及结果未改。命令的完整输出在../reviews/R3-P0/{validate,api-contract,specialist-tests}.txt。所有314个JSON、8个YAML均完整解析，生成物逐字节验证通过。协议包已在上轮按离线参数重装；本轮未改schema/生成物，无需再装。TEMP/TMP/PYTEST_DEBUG_TEMPROOT指向worktree内，r3-tmp已由.hqagent/.gitignore忽略，没有提交临时基线或测试文件。

## 旧测试三个失败：已证明与R3无关

上轮最终全量旧集命令：`.venv/Scripts/python.exe -X utf8 -B -m pytest scripts/protocol/tests -q -p no:cacheprovider --tb=short --basetemp=.hqagent/r3-tmp/pytest-legacy-final`，输出`3 failed, 301 passed in 16.17s`；保留legacy-tests.txt，之后没有修改协议内容。本轮重跑基线失败三项并保存baseline-failures.txt：`3 failed in 2.02s`。

| 测试 | 当前及基线共同原因 |
| --- | --- |
| test_remote_contract.py::test_rest_scope_and_references | 把OpenAPI本地component `PublishedOpenApiDocument`当成全局DTO；0.8已含该引用 |
| test_remote_link_browser_contract.py::test_d44_does_not_change_schema_error_registry_events_v1_or_cloud | 遍历当前schema再git show 500bf1f；旧提交没有remote-devices.json，git返回128 |
| test_remote_sync_contract.py::test_new_type_fixture_coverage_and_version | 固定断言0.7.0；基线已为0.8.0，本次为0.9.0 |

复现未用stash：上轮用`git archive 2b3377c packages/protocol scripts/protocol`在.hqagent/r3-tmp/baseline解包，PYTHONPATH指向其packages；本轮同样运行三项测试。baseline-integrity.txt记录7个关键基线文件逐字节对比git show及SHA256，包含VERSION、生成models和三个测试，证明使用的是0.8基线而非R3。复制目录在原仓库内，所以历史git show仍从同一仓库取冻结提交。

原失败属于历史测试兼容问题，不修改scripts/、不skip、不xfail。包内0.8专项对当前版本/路由数量断言按0.9更新；被允许变化的HTTP DTO以新增精确delta测试约束，旧线路闭包另逐项验证，未放松冻结线形状。

## 下游实施要点 · P1 服务端

增加CODECS[3]和双向升级栅栏，保留[1,2]；新错误不能写回旧线路。六个Cookie路由、索引过滤/映射、resource命令的grant与结果、查询关联/10秒超时/上限/断线清理、索引删除栅栏及目录授权失效均需实现。资源命令不要求conversationId，旧对话命令仍严格要求。目录POST绕开通用Service.replay正文缓存，只留摘要；代理磁盘buffer/APM/数据库/Outbox均禁止落盘临时结果。请求ID贯通；页面发布的OpenAPI与仓库bundle一致。已grant如实对账，不能把送达超时当导入计算超时。

## 下游实施要点 · P2 Worker/Hub

新增版本化Runtime history.list/read/adopt插件及实际能力探测。按精确vendor ID、Runtime实例和数据根保存绑定；识别terminal来源，排除Hub绑定/sidechain/非terminal来源；workspace真实路径过滤。确认闭合、实时活跃检查、原生写锁与崩溃恢复跨桌面/手机/重试入口共享，不能仅锁conversationId。复用现有凭据和私有推理过滤，全文过滤后再分段，导入历史事务发布且完整补传，未识别格式如实报错。

本机v1/v2根目录管理共享持久CAS；默认空，根移除立即作废token。逐层目录扫描只返回目录元数据，规范化、symlink/junction/快捷方式及Windows卷/大小写检查，句柄或稳定目录身份防TOCTOU。登记复用本机WorkspaceService，非Git允许只读，不暗中init-git。目录操作记requestId等无正文审计。新临时查询不能写可靠Outbox，回执仍保留可靠seq。真正的E10/E11及目录越界验收由P2完成，本协议测试不代替业务验收。

## 下游实施要点 · P3 前端

独立原生分类及Agent标识、unsupported原因、offline仅索引、unknown只读；明确关闭确认不可默认勾选。导入202对账，等待电脑提交/历史补传后进入无场景单Agent对话；精确continue，不用latest，不回退新会话。历史按before加载，跨页消息按ID/hash/段号拼齐才显示，临时正文只在内存。电脑端根目录设置，手机只选根和目录token；无根隐藏添加入口，暂停禁浏览/登记。目录过期/移除刷新，保留输入；界面区分送达状态、导入结果和真实执行状态。

## 提交与限制

协议冻结提交见头部commit；随后决策/回执提交不改协议。未合并integration。未改apps/**、docs/**、scripts/**，未启动其它代理或Vitest；未宣称插件、业务或线上部署完成。待主代理独立审核。

## 返修 1：消除三个历史测试失败（2026-09-29）

主代理审核通过协议内容，要求合入前修复历史测试债。本次按指定测试项扩展写范围：实际文件在`scripts/protocol/tests/`，而非话术中的packages/protocol。只改三个测试文件及交接证据；协议冻结SHA及业务内容不变。

| 测试 | 原断言/前提 | 修正与冻结保护 |
| --- | --- | --- |
| test_rest_scope_and_references | 所有$ref末段都当全局DTO名 | 区分OpenAPI内部JSON Pointer与schema引用；内部引用必须逐段在OpenAPI内解析，外部引用必须位于schema目录、指向$defs且在全局DTO索引存在；递归检查引用目标并按文档/指针去重防循环。不再把本地component误作DTO，也没有放过悬空引用 |
| test_d44_does_not_change_schema_error_registry_events_v1_or_cloud | 从当前目录枚举全部schema，随后读取D44历史提交；后来新增文件在旧提交不存在 | 用git ls-tree枚举两份历史树，断言文件集合相等；冻结schema逐项比较且不得从当前树删除。后来新增schema必须不在两份历史树中，且不得重定义冻结类型名。原remote.json仅D45 approvals允许增量、注册表/events/v1/cloud的逐项比较、27帧/修订1断言全部保留 |
| test_new_type_fixture_coverage_and_version | VERSION与生成物必须等于0.7.0 | 仍要求VERSION=生成物；版本必须是规范三段非负整数且不低于(0,7,0)。这是引入版本下界而非锁死未来包版本。原set(SYNC)==Fixture类型集合的精确覆盖检查一字未改 |

未删测试、未skip、未xfail、未放宽旧线路形状/值域。发现的协议测试入口为packages/protocol/tests下2个文件和scripts/protocol/tests下5个文件，以下全量命令覆盖全部7个文件；其余校验入口另跑生成门禁和api-contract。

```text
.venv/Scripts/python.exe -X utf8 -B -m pytest packages/protocol/tests scripts/protocol/tests -q -p no:cacheprovider --basetemp=.hqagent/r3-tmp/pytest-repair1
495 passed in 28.98s

pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：426 个类型，288 个 Contract Fixture

.venv/Scripts/python.exe -X utf8 -B packages/protocol/remote/api-contract.py
API contract verified: 33 current + 6 planned HTTP operations; 81 error codes; self-contained bundle; examples/auth/request IDs consistent
```

真实输出：../reviews/R3-P0/repair1-tests.txt、repair1-validate.txt、repair1-api-contract.txt。TEMP/TMP/pytest临时目录仍在已忽略的r3-tmp。本次不再保留已知失败作为合入条件，定长头tests改为pass。单独主题提交，未合回integration。

## 补冻 0.9.1（主代理裁决，本机原生会话接口）

P2 Q1已关闭，无needs-decision。冻结提交：`271c9046e3bb9d7be62e563c2962a2a7dd3e030e`。包0.9.1，wireRevision仍3；不修改remote/remote-sync/remote-native/remote-devices既有Schema或旧Fixture。新增LocalNativeSessionPage及合成Fixture，读取NativeMessagePage，导入复用RemoteNativeImportInput。默认列表/读取limit=50，最多100。

两套等价本机路由（v1 Bearer / v2 localSession Cookie）：

- GET /api/v{1,2}/native-sessions：workspaceId、agentType、cursor、limit。
- GET /api/v{1,2}/native-sessions/{nativeSessionId}：NativeSessionIndex。
- GET /api/v{1,2}/native-sessions/{nativeSessionId}/messages：sourceRevision、before、limit；NativeMessagePage。
- POST /api/v{1,2}/native-sessions/{nativeSessionId}/imports：同步提交，201 LocalConversationView，conversationKind=native；无送达/grant/202回执。

**P2 Worker/Hub**：实现上述本机路由，沿本机鉴权/Origin/Idempotency-Key；Hub签发NativeClosureConfirmation并审计，云端签发路径不变，二者共享精确会话写锁及活跃/版本再检查。未配对、离线、远程暂停或sync关闭不妨碍本机使用。同键同体返回同一已提交对话，不能重复导入/签发确认；所有响应（含错误/重放）no-store，日志无正文。导入不启动模型，提交完整历史与绑定后返回201。

**P3 桌面**：使用本机v2 Cookie四项接口，单独原生分类及明确终端关闭确认，导入成功进入无场景native对话；本机ID不可混用云端公开ID。电脑未配对/离线/仅线路2也可操作。等待期间如实显示“已在本机导入，待支持修订3的连接同步”，区分未配对、离线和sync关闭；不能显示同步成功，手机此时看不到未上传对话。

**延迟同步裁决**：更正旧“栅栏前不得创建R3对象”为不得上传。native索引与完整对话只走3；2或升级栅栏期间保留电脑待补传意图，不改成scenario、不占旧线路不可填补的seq槽、不经旧执行事件泄漏。栅栏完成且同步开启后按R1.5补传完整历史。D51及R3-contract §11已补充。本机接口不是云端Base URL路由，云端路由/security未增加，更新云端规范/bundle的包版本仅供诊断。

### 验证

新增3个协议测试覆盖8个本机操作：鉴权/DTO等价、同步201/no-store、参数/分页Fixture、旧线路Schema逐字节不变。旧精确版本断言从0.9.0升级至0.9.1，不减弱Fixture或线路断言。首次全量发现新增YAML锚点与旧文档重名，已修正命名并重跑全部测试，最终结果如下：

```text
.venv/Scripts/python.exe -X utf8 -B -m pytest packages/protocol/tests scripts/protocol/tests -q -p no:cacheprovider --basetemp=.hqagent/r3-tmp/pytest-091-final
498 passed in 27.63s

pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：427 个类型，289 个 Contract Fixture

.venv/Scripts/python.exe -X utf8 -B packages/protocol/remote/api-contract.py
API contract verified: 33 current + 6 planned HTTP operations; 81 error codes; self-contained bundle; examples/auth/request IDs consistent
```

输出存档：../reviews/R3-P0/091-tests.txt、091-validate.txt、091-api-contract.txt。已重新生成三端并按--no-index --no-build-isolation --force-reinstall --no-deps离线重装。临时目录仍忽略；未改业务代码、未运行应用/Vitest、未合回integration。待主代理独立审核。
