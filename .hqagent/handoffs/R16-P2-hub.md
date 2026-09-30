---
wp: R16-P2
status: done
scope_declared: [apps/hub/**, .hqagent/handoffs/R16-P2-hub.md]
scope_touched: ["apps/hub/adapters/attachment_input.py", "apps/hub/adapters/claude_adapter.py", "apps/hub/adapters/codex_adapter.py", "apps/hub/adapters/path_guard.py", "apps/hub/api/app.py", "apps/hub/api/local_chat.py", "apps/hub/orchestrator/runtime.py", "apps/hub/orchestrator/sessions.py", "apps/hub/pyproject.toml", "apps/hub/requirements.local-lock.txt", "apps/hub/runtime/attachments/__init__.py", "apps/hub/runtime/attachments/api.py", "apps/hub/runtime/attachments/capabilities.py", "apps/hub/runtime/attachments/content.py", "apps/hub/runtime/attachments/library.py", "apps/hub/runtime/attachments/service.py", "apps/hub/runtime/attachments/sync.py", "apps/hub/runtime/attachments/transport.py", "apps/hub/runtime/attachments/verification.py", "apps/hub/runtime/cli.py", "apps/hub/runtime/local_chat.py", "apps/hub/runtime/remote/commands.py", "apps/hub/runtime/remote/delivery.py", "apps/hub/runtime/remote/projection.py", "apps/hub/runtime/remote/queries.py", "apps/hub/runtime/remote/resources.py", "apps/hub/runtime/remote/sync.py", "apps/hub/runtime/remote/wire.py", "apps/hub/runtime/remote/worker.py", "apps/hub/runtime/tasks.py", "apps/hub/storage/attachments.py", "apps/hub/storage/local_chat.py", "apps/hub/storage/migrations.py", "apps/hub/tests/remote_support.py", "apps/hub/tests/test_r15_joint_server.py", "apps/hub/tests/test_r15_recovery.py", "apps/hub/tests/test_r16_attachments.py", "apps/hub/tests/test_r3_wire.py", "apps/hub/tests/test_remote_worker.py", ".hqagent/handoffs/R16-P2-hub.md", "apps/hub/adapters/prompt.py", "apps/hub/runtime/descriptor.py", "apps/hub/security/worktrees.py", "apps/hub/tests/test_r16_joint_repair.py", "apps/hub/tests/test_attachment_shell_reads.py", "apps/hub/adapters/manager.py", "apps/hub/orchestrator/domain.py", "apps/hub/runtime/execution_selection.py", "apps/hub/runtime/native/service.py", "apps/hub/tests/test_image_target_resolution.py"]
build: pass
tests: pass
commit: 0ba51aa2e62787eef6e80480beffa90ca4cb7805
open_questions: 0
---

## 基线与范围

基线 `dac8b3c`（已含协议 0.10.0 / D52 和 P1 `cc17608`），分支 `feat/remote-worker`。未修改 packages/protocol、apps/server、apps/desktop、根共享文件，未合回 integration。已读 R1.6-contract 全文、P0/P1 回执、附件方案指定章节和 CLI 输入只读核实记录。

本包实现本机文件库、线路 4、输入准备门闩、Adapter 输入、上传同步和显式图片验证命令。真实服务端测试使用工作区内 P1 create_app、回环 TLS、真实 Worker/TaskService、FakeAdapter；不是外网或真实模型验证。真实 CLI 图片识别尚未执行，默认能力不会因此标为 verified。

## 模块与持久化

- `runtime/attachments/content.py`：流式长度/hash 检查、文件名清洗、图片/PDF magic、受限图片校验、UTF-8/源码后缀规则。没有 PDF 正文提取、附件执行或本机缩略图生成。
- `library.py`：用户数据目录 attachments 下的随机文件名、原子 rename、raw 流上传、设备下载、原文件与服务端缩略图读取、过期/孤儿清理。通常直接以本机对话 ID 作子目录；异常路径字符/超长 ID 用不可逆的目录键，绝不当路径拼接。
- `service.py`：LocalRun 绑定、准备/启动/取消互斥、启动恢复、准备失败后的显式重试。`CURRENT_INPUTS` 是仅本机 Task 创建边界的 ContextVar，不扩展公开 CreateTaskInput。
- `sync.py`：消息完整可靠 ACK 后的 HTTP 上传队列、更高 messageRevision 的 available/unavailable、有限重试、reset/解绑停止上传。
- `capabilities.py` / `verification.py`：版本、模型和 transport 绑定的本机验证记录；目录中的验证 JSON 不含图片正文或凭据。
- `api.py`：同一 Router/服务层挂到 v1 Bearer 与 v2 Cookie。7 个操作均 no-store，写入沿用既有鉴权/Origin/幂等规则；二进制下载额外有 attachment、nosniff、长度、requestId。
- `transport.py`：仅在附件 HTTP 请求上下文内过滤 httpx/httpcore 的 URL/头部调试日志，不改变无关 HTTP 流量的日志策略。
- `storage/attachments.py` 和追加 migration 10：`local_attachments`（清单/状态/文件键/同步视图）、`local_attachment_messages`（顺序绑定）、`attachment_preparations`（持久门闩/来源/错误/取消证据）、`attachment_upload_keys`（幂等摘要）、`attachment_sync_jobs`（store/generation/message/attachment、次数、ACK 栅栏、结果）。1–9 迁移未修改。

本机库不实现账号额度计量，不把云端 5GB 限制误用成本机磁盘额度。单文件/类型/数量限制一致。文件名不用作落盘路径，POSIX 目录 0700 / 文件 0600；Windows 沿用用户数据目录权限。文件内容没有写进 SQLite。

## 接单、准备、取消与恢复

手机仍走 deliverBy → provisional → 显式 grant → accepted。provisional 只绑定本机清单/不可调度 LocalRun，门闩为 `ungranted`；grant 与 `pending` 转换同事务。没有把 ACK 当 grant。

`pending → preparing → ready → starting → started`；准备失败进入 failed。cancel 只有在 pending/preparing/ready 且准备任务及文件 I/O 已停止后，才提交 cancelled 和 `input_preparation_cancelled`。它和 starting 转换使用同一按 run 锁；starting/started 不走准备取消证明，继续 D41。LocalRun 在准备时 queued/running，复用原忙碌推导。

所有文件准备完且重新校验后才调用原 TaskService。下载每次 60 秒、最多 3 次、退避 1/2 秒、整轮 300 秒，仅网络和临时 5xx 重试；403/404、重定向、hash/长度/类型错误不重试。固定配对 origin 和资源路径，显式禁止跟随重定向。下载前等待 accepted 回执的 ACK：P1 只有应用 accepted 后才允许 command-bound HTTP 读取；这只是 HTTP 授权前置条件，且仍在 300 秒总时限中。

Hub 启动先清理 .part，并把上一进程 pending/preparing/ready 明确失败为 ATTACHMENT_PREPARATION_INTERRUPTED，不等待服务器连接。已越过 starting 的轮次保持既有恢复核对语义。重连继续发送完整 busy 集合。

准备失败时尚不存在执行 Task；显式 retry 原子生成新的 LocalRun/附件引用，再经原 TaskService 创建其第一个 Task。远程 retry 的后台控制任务等待真实 executionTaskId 才回 retry_enqueued；不捏造 Task ID，也不把尚在准备中的 LocalRun 冒充已经执行。已有 Task 的 retry 仍由 _create_child 创建子 Task，并继承附件输入，不改重试内核语义。

没有 Task 的准备重试会使用新的本机附件引用，避免把原 sourceCommandId 错绑到新 runId；相同字节可由 P1 CAS 物理去重，云端新附件记录仍按 P1 的逻辑计量规则计费。已有 Task 的内核重试不复制附件文件。

## 同步与修订兼容

Worker 支持 [1,2,3,4]，每 30 秒继续探测最高修订，沿用单调时钟、重连退避和双向持久水位栅栏。native provisional/admitted 和真实未决 delivery 阻塞升级；completed/failed/rejected/unconfirmed 终态不阻塞，不抹除 recoveryRequired。未确认 Outbox 和历史补传仍须完成。

修订 <4 时含附件的整个用户消息不入可靠 seq，不用删掉附件的文字冒充完整消息。升级后重新捕获补传水位。R3 原生目录、临时查询及未决资源恢复在修订 4 仍运行，查询回传当前修订。

电脑消息清单先 pending_upload；最后一个消息段可靠 ACK 后，才向 P1 上传带完整 store/generation/localConversationId/localMessageId/localAttachmentId 绑定的字节。HTTP 成功后增加 messageRevision 发 available，失败发 unavailable + 安全错误码；不会无限重试或影响本机执行。历史 complete 等附件结算。暂停远程不阻止该同步上传；关闭同步立即取消上传任务、清空本机云端状态并发 reset。

手机来源清单只在原 store/generation 内引用 originAttachmentId/sourceCommandId。reset 后重开或重新配对，已下载的本机文件按新的本机消息绑定重新上传，不复用被删除的云端 ID；旧 ID 仍 404。避免 reset 后原命令正文已被清除而导致重新同步冻结。消息中的受控附件路径在上行正文中替换为占位，不把 AgentTaskSpec/localPath 放进帧。

已存在的对话删除触发器标记附件删除，维护器关闭本机读取句柄并清文件/清单/绑定/同步任务。没有新增未冻结的本机删除对话路由；当前无本机删除 HTTP 入口，回归通过实际数据库删除路径检查触发器。未发送附件在到期时 API 立即拒绝，启动及独立于连接的维护器至少每分钟清理；下载的文件在 prepare 失败后不擅自自动执行。

## Adapter 与现有内核的最小改动

`PathGuard` 新增仅限本轮、逐文件精确路径且重新核验 hash 的**只读**授权；allows 写白名单不扩大，目录也不授予。文件保存在用户数据目录，不复制进 Git worktree，因此无需改 .git/info/exclude。

即使工作区包含 Hub 数据目录，附件本身也优先拒绝写入，不被 `**` 覆盖；Windows 路径键按系统大小写规则归一化。

非图片由 Adapter 在提示词中引用受控路径，不提取正文，不授予执行权限。Claude 使用 `--input-format stream-json` 与 Messages image/source/base64 块；新建和 `--resume <精确 ID>` 共用纯参数/编码函数。Codex 实际走 App Server 的 `localImage` 输入；exec/exec resume 的 --image 参数也有纯函数校验。续接时替换 spec 和 PathGuard，下一轮无附件即撤销上一轮文件授权。

TaskService 只在本机持久执行规格里保存 inputAttachments，并在 NodeDispatchRequest 传递；_create_child 保留输入。WorkflowRuntime/SessionManager 仅转交生成 AgentTaskSpec、重查实际 Adapter 版本/模型验证并更新本轮续接规格。LocalChat 在原 create_task 之前调用准备服务，取消/准备重试增加薄入口；不迁移 Task/Attempt、不改暂停/取消 D41 内核、reviewer 隔离或 worktree 策略。

## 图片验证入口与保守能力

显式入口：

```powershell
python -m runtime.cli agents verify-image --agent claude [--model <model-id>]
python -m runtime.cli agents verify-image --agent codex [--model <model-id>]
```

命令先通过本机认证 API 发现 Agent，随后由操作者明确触发一次本机 Adapter 探测流程（会调用模型），不是 Worker 自动调用模型。生成色块排列各不相同的 PNG/JPEG/GIF/WebP 和带随机标记的文本；混合测试必须依次答对全部 16 个颜色及文本标记，不能只识别第一张图即通过。覆盖新建、精确续接、5 附件混合、取消和坏 hash 拒绝。保存 Agent、CLI 版本、模型、transport、时间、子项结果；只有所有子项通过且当前版本/模型/transport 匹配才 verified=true。目录能力使用现有 detect 缓存周期刷新版本，实际派发前另行 detect，CLI 更新不会沿用旧通过记录执行图片输入。

本轮只用注入的 FakeAdapter 测试入口，未运行真实 verify-image，也没有任何外网/模型调用。未验证的 Agent/角色、角色缺失、类型/大小不匹配均保守拒绝。

## 本机接口对接

同一组路径位于 `/api/v1`（Bearer）和 `/api/v2`（本机 Cookie）：

| 操作 | 路径 | 返回 |
| --- | --- | --- |
| 限制 | GET /attachments/limits | AttachmentLimits |
| 上传 | POST /conversations/{id}/attachments | 201 LocalAttachmentView |
| 元数据 | GET /attachments/{id} | LocalAttachmentView |
| 删除未引用附件 | DELETE /attachments/{id} | AttachmentDeletedView；重复删除 404 |
| 原文件 | GET /attachments/{id}/content | 原始 octet-stream |
| 当前目标图片能力 | GET /conversations/{id}/attachment-capabilities | AttachmentTargetCapabilities |
| 缩略图代理 | GET /attachments/{id}/thumbnail | 服务端生成 PNG；离线/未配对明确 unavailable |

raw 上传使用 Content-Length、Content-Type=application/octet-stream、X-Content-Sha256、百分号编码 X-File-Name、Idempotency-Key。消息发送只加 attachmentIds，本机清单 ID 与云端 ID 分开，客户端不填写本机路径或自行编清单。LocalAttachmentView 的 syncStatus 为 not_synced/pending_upload/available/unavailable，syncError 是安全错误码；本机可用性不等于云端可下载。

未明确选择 Agent 的场景角色不会猜测图片能力；前端应先完成角色 Agent 选择和相应版本/模型验证。P1 下载携带 commandId；上传携带 X-Worker-Store-Id / X-Sync-Generation / X-Local-Conversation-Id / X-Local-Message-Id / X-Local-Attachment-Id，并复用上传幂等键。服务器是云端附件 ID 与缩略图的权威。

## 测试及旧断言调整

新增 `test_r16_attachments.py`，覆盖真实 TLS P1 手机文件/图片输入、坏 hash/长度不启动 Agent、取消/重启/显式重试、busy 释放、pending→available 版本顺序、暂停、同步关闭及重开、3→4 延迟补传、修订 4 原生临时读取、Cookie/Bearer 鉴权与敏感值不回显、过期/删除物理清理、有限重试及重定向拒绝、图片纯编码/参数、验证记录失配、续接输入权限替换。真实 P1/Worker 的收发帧继续由生成 DTO 校验；LocalAttachment/Message/Page/Capability 等边界使用生成 DTO。

旧测试只改协议演进前提，不放宽业务断言：

- `test_remote_worker.py` 未知修订号从 4 改 5：4 已成为本次支持的合法修订，该例仍验证不支持的修订冻结而非重连风暴。
- `test_r15_recovery.py` / `test_r3_wire.py` 首次探测最高修订由 3 改 4，保留实际只支持 1/2/3 的回退断言。
- `remote_support.py` 为严格 DTO 校验表新增 4。
- `test_r15_joint_server.py` RealPair 根据显式 revision 限制真实服务端支持表，保留原 R1.5/R3 场景；all_server_codecs 的 R3 专项夹具仍显式最多 3。服务端迁移版本断言改成真实 MIGRATIONS 上界（P1 已追加附件迁移），未删数据或业务断言。

验证过程曾暴露并修复：LocalMessageView 必须使用纯 AttachmentManifestItem；accepted ACK/HTTP 下载授权竞态；provisional 用户消息不能先于 accepted 上报 origin 引用；准备重试必须等待 executionTaskId；Codex 已存在 Session 的 resume 需更新输入；reset 后 origin 绑定不能沿用；修订 4 下 R3 查询/恢复旧判断。中间一轮全量 3 failed / 510 passed 均为新增重试测试的 paired 夹具漏填必需 lastConnectedAt，已补正确 DTO 数据，没有放宽断言。最终结果见下节。

## 依赖与环境

Hub 增加并锁定 Pillow 12.3.0（无额外传递依赖）以做图片格式验证及合成测试图。当前 venv 原来缺 Pillow；从相邻 remote-server **已安装**的 Pillow 12.3.0 离线复制 PIL 和 dist-info 到本 worktree .venv，两者均 Python 3.13.7 / Windows amd64，随后导入与真实 P1 图片测试通过；未联网安装、未改相邻 worktree。CI/打包需按更新后的 Hub requirements 安装 Pillow。

所有 pytest 串行，TEMP/TMP/--basetemp 指到本 worktree 已忽略的 .tmp，避免默认 WinError 5。未启动 vitest。Windows 之外的真实文件权限/rename/钥匙串行为仍由三平台 CI 验证；本次没有把 Windows 通过说成 POSIX 真机已测。未遇到工具 429、额度不足或 0xC0000142。

## 需主代理实测

1. 在已登录的真实 Claude CLI 上执行 verify-image，检查 stream-json 图片块、PNG/JPEG/GIF/WebP、新建、精确续接、5 附件混合、取消和错误处理；确认实际 CLI 接受现有启动参数组合。尚未实测前保持 unknown，不能手工写通过记录。
2. 对真实 Codex App Server 执行同一验证，确认 localImage 路径、精确 thread resume、多图/混合与取消；不能用 exec --help 代替实际 transport 验证。
3. 在真实场景及原生会话里上传 PDF/源码/文本，检查 Agent 的 Read 路径授权确实可用，且附件父目录/邻近文件/写入仍被拒绝；验证下一轮纯文字不会携带旧附件权限。
4. CLI 升级或角色模型改变后，确认界面回到未验证；用明确 --model 重跑对应验证后才能再次支持图片。
5. 前端进行手机/电脑附件选择、缩略图代理、云端配额失败展示的联调；本包没有运行前端测试。真实 Agent 图片识别和真实文件读取未在本轮完成。

## 最终验证

### Hub 全量

在 `apps/hub`：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r16-hub-reviewed --tb=short
```

```text
........................................................................ [ 13%]
..................................................s................sssss [ 27%]
sss..................................................................... [ 41%]
........................................................................ [ 54%]
........................................................................ [ 68%]
........................................................................ [ 82%]
........................................................................ [ 96%]
远程送达预留清理暂未完成，将重试
....................                                                     [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_ws_close_codes_real_handshake.py::test_bad_ticket_closes_with_4401_not_a_handshake_rejection
tests/test_ws_close_codes_real_handshake.py::test_bad_origin_closes_with_4403_and_is_distinguishable_from_bad_ticket
tests/test_ws_close_codes_real_handshake.py::test_expired_cursor_closes_with_4410_and_sends_snapshot_url_first
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\websockets\exceptions.py:137: DeprecationWarning: ConnectionClosed.code is deprecated; use Protocol.close_code or ConnectionClosed.rcvd.code
    warnings.warn(  # deprecated in 13.1 - 2024-09-21

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
SKIPPED [1] tests\test_posix_credentials.py:166: POSIX mode bits
SKIPPED [1] tests\test_posix_path_guard.py:50: POSIX absolute redirect path
SKIPPED [1] tests\test_posix_path_guard.py:68: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:76: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:84: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:101: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:108: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:115: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:122: POSIX executable symlink and directory-fd semantics
515 passed, 9 skipped, 4 warnings in 264.01s (0:04:24)
```

### server 全量

在 `apps/server`：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r16-server --tb=short
```

```text
........................................................................ [ 25%]
........................................................................ [ 51%]
........................................................................ [ 77%]
................................................................         [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
280 passed, 1 warning in 89.30s (0:01:29)
```

### 协议生成物

在仓库根，将 .venv/Scripts 加入本进程 PATH，TEMP/TMP 保持本 worktree .tmp：

```powershell
pwsh scripts/protocol/validate.ps1 -CheckGenerated
```

```text
协议校验通过：507 个类型，373 个 Contract Fixture
```

完整原始输出亦保留在本 worktree 已忽略的 `.tmp/r16-hub-reviewed.txt`、`.tmp/r16-server.txt`、`.tmp/r16-protocol.txt`。9 项 skip 为既有 POSIX 专属测试在 Windows 上跳过；4 条 Hub warning 为既有 Starlette/httpx 和 websockets 弃用提示。测试输出另有固定的预留清理重试日志，未将其改写或隐藏。`git diff --check` 通过。

## 提交

- `5f1129b`：本机附件库、准备/恢复门闩、Adapter 输入与显式验证。
- `b4522ea`：线路 4、同步、本机接口及真实服务端回归。

每次代码提交后已运行 `git log -1 --format=%B`，没有署名/Co-Authored-By/Generated with；回执提交另行自查。没有合并回 integration。


## 返修 1：真实联调反馈

### 基线与结论

先执行 `git merge integration/phase1`，输出 `Already up to date.`；基线为 `a770761 merge: sync integration after attachment CI green`，含主代理已合入的三平台 CI 结果。未调用任何真实模型、未执行真实 verify-image，未修改 server / protocol / desktop，也未合回 integration。

问题 1、2、4、5 已完成代码修复和回归。**问题 3 的原真实失败根因尚不能闭环**：旧验证记录只有布尔值，没有 cancel.start 的 AdapterFailure 或 cancel.stop 的结构化结果。不能把假 App Server 成功当成那一次真实失败已消除的证明。本轮已增加可定位到阶段的安全诊断；需要主代理用真实 CLI 重跑后确认。回执暂记 blocked / open_questions=1，测试通过不等于该证据缺口已解决。

### 1. 附件提示词授权冲突

原 `prompt.py` 的“所有读取均受根目录约束”和结尾“只在当前授权目录内读取”否定了附件授权；`file_prompt` 只有路径，且 JSON 编码导致 Windows 双反斜杠。新增共用 `attachment_read_scope`，在角色约束处明确精确文件的额外只读许可、禁止读同目录其他文件、禁止执行/修改、附件内容不能扩大权限。路径逐行原样呈现。

新建及完整提示词续接通过 `build_task_prompt` 获得该说明；只发送新轮消息的原生/精确续接通过 `file_prompt` 获得非图片文件许可。图片仍经原有结构化图片通道，不用路径文本冒充图片。没有附件时保持原提示词字节不变，新增测试与原字符串快照比较。PathGuard 未修改，仍只允许指定文件，未给父目录授权。

### 2. 旧连接 EOF 污染新回合

不是把 `item/completed:agentMessage` 直接判断成回合完成：该分支原本只记录消息/进度，正常完成仍来自 `turn/completed`。实际可复现缺陷是 `_CodexConnection.force_close` 仅等待进程退出，不回收 stdout/stderr reader 和 server-request 任务。旧回调闭包引用可重用的 `AdapterSessionState`；resume 重置 queue/finished/expected_termination 后，旧进程迟到 EOF 会在新 state 上调用 `_handle_disconnect`，生成 `exitCode=-9` 的失败并提前结束新的事件流。原生回合可能仍在继续，因此可以看到过程消息后被后续清理打断。

新增假 App Server JSON-RPC 测试，在修复前得到真实红灯：

```text
assert not result.done(), 'old EOF or intermediate message ended the resumed turn'
AssertionError: old EOF or intermediate message ended the resumed turn
... result=AdapterFailure(... 'exitCode=-9')
1 failed, 1 warning in 0.21s
```

修法：连接关闭串行化；进程终止确认后取消并 join 旧读取/请求任务，跳过正在执行 close 的当前任务；若进程仍活着则保留观察能力，不谎称已清理。通知、服务请求和断连回调另以 connection 对象身份隔离；resume 在重置 state 前执行旧连接清理栅栏，未确认则拒绝续接。没有把任意过程消息当成结束，也没有放宽最终 AgentResult JSON 校验。

测试按“首轮最终 JSON → 旧连接延迟 EOF → 续接过程消息 → 工具完成 → 最终 turn/completed JSON”执行，最终结果必须为本轮最终 JSON，而不是过程消息或旧结果。

### 3. 独立取消会话与待补证据 Q1

新测试使用真正的 Adapter/_CodexConnection 和假 stdio App Server，覆盖新建、精确续接、混合及取消探测：前三轮共用同一精确 thread ID，取消探测另开第二个 Hub Session / 原生 thread，确认四个连接均已回收。另注入第二次 start 失败、cancel refused、非空 orphanProcessIds，均必须保持 cancel=false / passed=false；没有放宽判定。

验证记录及 CLI 输出新增内部 `diagnostics` 元数据：new/resume/mixed-five/cancel 的 start、collect、recognition、stop 阶段；耗时、AdapterFailure kind/code/retryable；启动失败的 process.start / initialize / model/list / thread/start / thread/resume / turn/start 阶段、可用的 OS 错误号；cancel outcome / orphanProcessIds。**不保存原生错误正文、模型输出、提示词、路径或凭据。** 不修改任何冻结的 API/线路 DTO。

目前没有原真实 cancel.start/stop 的数据，不能断言它是 Session ID 复用、上轮未结束、资源不足，或取消结果拒绝。已向主代理请求该结构化信息；交付时仍待补证据。请主代理使用联调 Hub 的同一用户数据目录执行：

```powershell
python -m runtime.cli agents verify-image --agent codex
```

若仍 cancel=false，请回传 `diagnostics.cancel.start` 和（若有）`diagnostics.cancel.stop`；不需要任何会话正文。若五项全通过，再关闭 Q1 并更新本回执状态。主代理此前报告的真实 Claude 五项通过是主代理结果，不冒充本轮实测。

### 4. 探测图可辨识度

四色图由 128×128 增至 512×512；白色外边框和明显十字分隔，各图仍采用互不相同的随机色序。新建/续接仍严格匹配第一张图的四种颜色顺序，混合仍须匹配四图共 16 个颜色及文件随机标记。新增图像尺寸/分隔像素和交换颜色必失败测试。没有用“近似正确”把能力标为 supported。

### 5. Windows 文本解码

全仓扫描同步 subprocess 文本读取，发现 `runtime/descriptor.py` 的 whoami / icacls 未声明编码；这两条命令在 Hub 启动写 runtime descriptor、设置目录及临时文件 ACL 时反复执行。`-X utf8` 会让原来的 text=True 选择 UTF-8，无法保证兼容 Windows 本地化命令输出。显式使用 Windows OEM 编码及 errors=replace；SID 的解析字段仍是 ASCII。`security/worktrees.py` 的 Git 保留 UTF-8 并补 errors=replace。异步 Adapter ProcessRunner 已按 bytes 读取并容错，不重复改动。

所有调用继续 check=True，真实非零退出码仍抛 CalledProcessError。测试用真实 Python 子进程在 `-X utf8` 下输出合成 GBK stderr 并返回 7，验证无解码线程异常且保留退出码和非空 stderr。另验证 whoami 的显式编码参数及命令失败传播。

本轮对忽略目录内合成文件执行 icacls 的输出为 ASCII，未在当前 shell 重现主代理的中文 GBK 输出；这里只能确定存在不安全解码调用并验证修复机制，不能据此杜撰主代理那条日志的精确命令时间线。

### 测试与交付

新增 `apps/hub/tests/test_r16_joint_repair.py` 9 项；没有删除或放宽既有断言。临时文件与 TEMP/TMP/--basetemp 全部位于本 worktree .tmp，Hub/server 串行执行，不运行 vitest、不调用真实模型。不接触主代理运行中的联调进程。未遇到 429、额度不足或 0xC0000142。

#### Hub 全量

在 `apps/hub`：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r16-repair-hub-final --tb=short
```

```text
........................................................................ [ 13%]
..................................................s................sssss [ 27%]
sss..................................................................... [ 40%]
........................................................................ [ 54%]
........................................................................ [ 67%]
........................................................................ [ 81%]
........................................................................ [ 94%]
远程送达预留清理暂未完成，将重试
.............................                                            [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_ws_close_codes_real_handshake.py::test_bad_ticket_closes_with_4401_not_a_handshake_rejection
tests/test_ws_close_codes_real_handshake.py::test_bad_origin_closes_with_4403_and_is_distinguishable_from_bad_ticket
tests/test_ws_close_codes_real_handshake.py::test_expired_cursor_closes_with_4410_and_sends_snapshot_url_first
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\websockets\exceptions.py:137: DeprecationWarning: ConnectionClosed.code is deprecated; use Protocol.close_code or ConnectionClosed.rcvd.code
    warnings.warn(  # deprecated in 13.1 - 2024-09-21

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
SKIPPED [1] tests\test_posix_credentials.py:166: POSIX mode bits
SKIPPED [1] tests\test_posix_path_guard.py:50: POSIX absolute redirect path
SKIPPED [1] tests\test_posix_path_guard.py:68: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:76: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:84: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:101: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:108: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:115: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:122: POSIX executable symlink and directory-fd semantics
524 passed, 9 skipped, 4 warnings in 265.86s (0:04:25)
```

#### server 全量

在 `apps/server`：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r16-repair-server --tb=short
```

```text
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
........................................................................ [ 96%]
..........                                                               [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
298 passed, 1 warning in 94.71s (0:01:34)
```


返修提交：`fd65763`（授权提示词、连接生命周期和本地命令解码）、`a079901`（较大探测图、安全诊断及9项回归）。逐次执行 `git log -1 --format=%B` 自查，无署名。`git diff --check` 通过。原始输出保留在本 worktree `.tmp/r16-repair-hub-final.txt` 和 `.tmp/r16-repair-server.txt`。

## 返修 2：附件的只读 shell 访问

### 基线与前轮闭环

开工执行 `git merge integration/phase1`，输出 `Already up to date.`；基线 `90dedee merge: sync integration after repair 1`。主代理已用真实 CLI 确认 markdown 读取、GBK 日志、新建/续接/取消/error 探测通过，取消证据为 force_killed 且 orphanProcessIds=[]。据此关闭返修 1 的 Q1，恢复顶部 done / open_questions=0。这些真实结果来自主代理，本轮没有调用模型。

### 根因核实与改动

`CodexAdapter._handle_server_request` 的 `item/commandExecution/requestApproval` 调用 `PathGuard.inspect_tool_call('shell', ...)`；旧 shell 分支收集路径后交给 `violations()` / `allows()`。附件刻意不可写，因此只读 Get-Content/cat 也被拒绝；随后 Adapter 返回 PATH_NOT_ALLOWED，与主代理的 mixed-five.collect 诊断一致。Read 工具走 contains，故不会经过这个写路径判断。

只修改 `adapters/path_guard.py`：有本轮 input_files 且工具为 shell/bash/powershell/exec_command 时，先尝试一个严格、完整的只读命令识别分支。没有附件时完全不进入新分支，原分支、写权限 allows、Read contains 及审批策略均不修改。

- 精确文件判定使用与 contains 相同的 Path.resolve / os.path.normcase，再调用 contains，复用现有 symlink 与长度/SHA256 校验。另明确拒绝路径中的 `..` 和通配符。
- Windows 支持单条 Get-Content、type、cat、head；Get-Content 支持 LiteralPath/Path、Raw 和明确列出的只读 Encoding 值；head 支持 `-n N`。路径不做 JSON 转义，Windows 分词不吞反斜杠。
- POSIX 支持单条 cat、head / head -n N，命令名大小写敏感。沿用 PATH 实际发现的 bash/sh/zsh -c 解包；env 读取例外只接受明确的 locale/TERM 设置。
- 文件必须恰好是本轮清单项。父目录、邻居、通配符、越界遍历、符号别名、hash 变化、未知参数/脚本均不获得该例外；附件目录即使恰在工作区内也不会因此获得 shell 访问授权。
- 写命令、重定向、管道、复合命令不能继承只读例外。包括 Remove-Item / Set-Content / Out-File / rm / mv / cp / tee，以及先读附件再重定向到工作区的形式；写白名单仍明确不包含附件。
- 解包前检查外层控制运算符，避免 env/-c 解包丢失 `;`、`&&` 等语义；涉及附件的未证明安全的环境设置和包装明确拒绝。无关命令继续沿用原逻辑，不把“有附件”解释为给任意 shell 更大的权限。

这不是完整 shell 解释器，不承诺任意 Python、脚本块、多命令或所有只读工具都可用；不能证明安全的形式按要求保守拒绝。没有改 Agent 的工具风险分类、审批流程或执行内核，也没有授予整个用户目录或使用 bypass。

### 回归覆盖

新增 `tests/test_attachment_shell_reads.py` 共 56 项参数化测试，覆盖：

- Get-Content -LiteralPath（含 Raw/Encoding）、type 的双引号路径、cat、head -n 5 的精确文件读取；文件变更后拒绝。
- 写命令及重定向、管道、邻居文件、目录、通配符、`..`、未知脚本拒绝；即使 allowed_paths=['**'] 也不能写附件。
- 已发现的 PowerShell、bash/sh/zsh、env 包装；未发现的 shell 拒绝；POSIX 大小写区别；外层控制运算符和 LD_AUDIT 等不确定设置不能借只读例外通过。
- 无附件时用禁止调用新分支的桩验证原调用路径未变，并保留既有 shell/审批测试。
- POSIX CI 使用真实 symlink；Windows 无创建权限时模拟同样的 resolve/is_symlink 结果，仍运行拒绝断言，不增加 skip。

旧断言没有修改。开发中补充的包装拒绝测试曾发现“退回旧解析器”不足以表达明确拒绝，已修成针对附件的拒绝结果，没有放宽断言。最终专项为 56 passed。

### 验收与需主代理复跑

Hub/server 串行执行，TEMP/TMP/--basetemp 都在本 worktree 已忽略的 .tmp；未运行 vitest、未调用模型、未操作主代理的联调进程，未遇到 429、额度不足或 0xC0000142。实际 Windows PowerShell 与 POSIX 的命令文本解析均在本机测试执行；POSIX 真实文件系统行为仍由三平台 CI 验证。

请主代理沿用联调 Hub 的同一用户数据目录重跑真实 `agents verify-image --agent codex`，确认 mixed-five 通过，并复核真实 shell 读取没有访问相邻文件。本轮不把模拟命令解析通过冒充真实模型识别通过。

最终输出如下。

#### Hub 全量

在 `apps/hub`：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r16-repair2-hub-verified --tb=short
```

```text
........................................................................ [ 12%]
........................................................................ [ 24%]
..................................s................ssssssss............. [ 36%]
........................................................................ [ 48%]
........................................................................ [ 61%]
........................................................................ [ 73%]
........................................................................ [ 85%]
........................................................................ [ 97%]
远程送达预留清理暂未完成，将重试
远程送达预留清理暂未完成，将重试
.............                                                            [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_ws_close_codes_real_handshake.py::test_bad_ticket_closes_with_4401_not_a_handshake_rejection
tests/test_ws_close_codes_real_handshake.py::test_bad_origin_closes_with_4403_and_is_distinguishable_from_bad_ticket
tests/test_ws_close_codes_real_handshake.py::test_expired_cursor_closes_with_4410_and_sends_snapshot_url_first
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\websockets\exceptions.py:137: DeprecationWarning: ConnectionClosed.code is deprecated; use Protocol.close_code or ConnectionClosed.rcvd.code
    warnings.warn(  # deprecated in 13.1 - 2024-09-21

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
SKIPPED [1] tests\test_posix_credentials.py:166: POSIX mode bits
SKIPPED [1] tests\test_posix_path_guard.py:50: POSIX absolute redirect path
SKIPPED [1] tests\test_posix_path_guard.py:68: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:76: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:84: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:101: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:108: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:115: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:122: POSIX executable symlink and directory-fd semantics
580 passed, 9 skipped, 4 warnings in 256.15s (0:04:16)
```

#### server 全量

在 `apps/server`：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r16-repair2-server --tb=short
```

```text
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
........................................................................ [ 96%]
..........                                                               [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
298 passed, 1 warning in 77.78s (0:01:17)
```

代码提交 `cd5cc320249dd2ae9409ea35e6b0a5b934e872ad`。提交后已执行 `git log -1 --format=%B` 自查，无署名；`git diff --check` 通过。未合回 integration，未修改 server/protocol/desktop。

## 返修 3：图片能力与实际执行目标共用解析

### 基线与根因

开工执行 `git merge integration/phase1`，输出 `Already up to date.`，基线 `6f6b13a merge: sync integration after repair 2`。主代理已确认两种真实 CLI 的五项图片探测通过，这是主代理实测结果；本轮未调用模型。

旧 ImageCapabilities 直接按 role.agent_instance_id 查 AgentView，空配置被当成未知。但 LocalChat 实际会生成本轮 Profile，空 primaryAgentId/空 override 合法地进入 RoleResolver 的自动能力匹配。因此默认场景出现“实际能选 Agent，图片目录却永远 unknown”的分歧。

### 共用入口及内核改动

- `runtime/execution_selection.py::scene_execution` 共用本机场景 Profile、roleOverrides、roleExecutions 的构造。LocalChat 的真实 Task 输入和能力预览都调用它；没有把解析结果写回场景配置。显式模型保持原值，未指定/空模型规范为 None，匹配验证记录 model=null。
- `WorkflowRuntime.resolve_agent` 从原 dispatch 中抽出权限要求与 RoleResolver 调用，真实 dispatch 和能力预览共用。能力预览不独立排序、不另选“某个已验证 Agent”，仍遵循既有任务覆盖/Profile/能力匹配/回退规则及硬能力要求。多个候选能由既有稳定排序确定时正常解析；实例 ID 不唯一或无可用目标时同一入口返回 ResolutionGap。
- `ImageCapabilities.refresh` 从执行目录取真实 AgentCandidate，使用上述入口取得实际 instance_id，再用对应 AgentView 的 CLI 版本和共享 roleExecutions 的模型查验证记录。缺状态、解析失败或验证不匹配返回 unknown 和原因。原规划会话验收的 reviewer 预览固定到规划阶段解析出的实例，与真实验收路径一致。
- 不改变 TaskService 的 resolved_agent_id 保存、Session 隔离、执行/取消/重试语义，不迁移内核，不增加协议字段。新增共用入口是只读解析，不在预览时建 Task/Session/Profile。

### 原生实例与刷新

原生续接实际绑定 native_sources.runtime_id。新的 native_execution_candidate 同时供 NativeService.task_input 和能力查询使用，校验实例唯一/ready、session_resume 及同一执行策略；不会因同类型还有另一个已验证 Agent 而替换原实例。

catalog 按当前原生插件的 runtime_id 绑定确定类型对应的实例，因此同类型 Agent 列表有多条、但原生绑定唯一时不再一律 unknown。若该类型确实有多个原生 Runtime 绑定，类型级 catalog 无法精确表达，保持 unknown；本机具体对话的能力查询则按持久化 runtime_id 逐一判断。没有自造 per-instance 线路字段。

AdapterManager 的 list_agents 与执行目录共用完整发现快照，沿用默认 60 秒缓存周期自动刷新版本、可用性和能力；手动 discovery 可立即刷新。刷新加互斥并逐个探测 Adapter，避免每次 GET 反复启动 CLI 或并行探测增加内存压力。CLI 探测仅版本/健康检查，不调用模型。不能声称可用性变化是零延迟：自动发现为该缓存周期，catalog 发布沿原 5 秒周期。

场景配置和验证记录的变化在下一次能力 refresh 生效。本机发送/能力 GET、远程图片收件及 grant、图片准备前后使用同一缓存结果；变化时即时发布 catalog，require 使用同一结果和 capabilityRevision。CLI/实例状态的本机指纹使 unknown→unknown 的版本变化也递增 revision；指纹只在本机参与摘要，不上传模型配置。真正派发前仍保留现有的直接 detect/验证校验，未验证的运行时不能借缓存开始图片执行。

### 新测试

新增 `tests/test_image_target_resolution.py` 7 项：

1. 默认 analyze/plan/develop 未绑定 Agent 时，未验证 unknown、默认解析目标已验证 supported；多个可排序候选不误当成未知；真实 Task.resolved_agent_id 与目录一致，默认模型为 None。
2. 显式模型只匹配该模型验证记录；CLI 版本失配、Agent offline 回到 unknown。
3. 无候选及重复实例 ID 保持 unknown，并有原因。
4. 同类型多个实例按原生 runtime_id 选择；具体对话不借用另一实例的验证/可用性。
5. 验证、场景、CLI 版本变化递增 capabilityRevision，require 与目录一致；不变化时不重复增加 revision；模型配置不出现在上传帧。
6. 发现快照到期同时更新目录与执行候选，不每次读取都探测。
7. 真实本机 P1 TLS 服务端 + Worker + FakeAdapter：在未改默认场景绑定、版本仍为 1 的情况下，手机上传图片并发送成功，最终执行 Agent 与 catalog 一致。

旧测试未放宽。新增默认场景测试最初的模拟 Agent 缺少 developer 所需 file_write 硬能力，解析器正确拒绝；补齐合成能力后通过，没有修改解析规则绕过硬要求。

### 验收与后续

Hub/server 全量串行，TEMP/TMP/--basetemp 在本 worktree .tmp；未跑 vitest，未调用模型，未改 server/protocol/desktop，未合回 integration。未遇到 429、额度不足或 0xC0000142。

请主代理保留默认 agentInstanceId 为空、modelId=null 的场景配置，复跑真实手机图片发送，并检查目录中的实际 agentId、supported/verified 及 Task 的 resolved_agent_id 一致。本轮本机真实服务端配 FakeAdapter 的通过，不替代这项真实 CLI 端到端验证。

最终真实命令输出如下。

#### Hub 全量

在 `apps/hub`：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r16-repair3-hub --tb=short
```

```text
........................................................................ [ 12%]
........................................................................ [ 24%]
.........................................s................ssssssss...... [ 36%]
........................................................................ [ 48%]
........................................................................ [ 60%]
........................................................................ [ 72%]
........................................................................ [ 84%]
........................................................................ [ 96%]
远程送达预留清理暂未完成，将重试
....................                                                     [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_ws_close_codes_real_handshake.py::test_bad_ticket_closes_with_4401_not_a_handshake_rejection
tests/test_ws_close_codes_real_handshake.py::test_bad_origin_closes_with_4403_and_is_distinguishable_from_bad_ticket
tests/test_ws_close_codes_real_handshake.py::test_expired_cursor_closes_with_4410_and_sends_snapshot_url_first
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\websockets\exceptions.py:137: DeprecationWarning: ConnectionClosed.code is deprecated; use Protocol.close_code or ConnectionClosed.rcvd.code
    warnings.warn(  # deprecated in 13.1 - 2024-09-21

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
SKIPPED [1] tests\test_posix_credentials.py:166: POSIX mode bits
SKIPPED [1] tests\test_posix_path_guard.py:50: POSIX absolute redirect path
SKIPPED [1] tests\test_posix_path_guard.py:68: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:76: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:84: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:101: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:108: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:115: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:122: POSIX executable symlink and directory-fd semantics
587 passed, 9 skipped, 4 warnings in 259.38s (0:04:19)
```

#### server 全量

在 `apps/server`：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r16-repair3-server --tb=short
```

```text
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
........................................................................ [ 96%]
..........                                                               [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
298 passed, 1 warning in 78.19s (0:01:18)
```

返修代码提交：`2908437`（共用执行选择/发现快照）、`0ba51aa`（能力映射、刷新和回归）。逐次运行 `git log -1 --format=%B` 自查，无署名。`git diff --check` 通过。原始输出在 `.tmp/r16-repair3-hub.txt` / `.tmp/r16-repair3-server.txt`。
