---
wp: R16-P2
status: done
scope_declared: [apps/hub/**, .hqagent/handoffs/R16-P2-hub.md]
scope_touched: ["apps/hub/adapters/attachment_input.py", "apps/hub/adapters/claude_adapter.py", "apps/hub/adapters/codex_adapter.py", "apps/hub/adapters/path_guard.py", "apps/hub/api/app.py", "apps/hub/api/local_chat.py", "apps/hub/orchestrator/runtime.py", "apps/hub/orchestrator/sessions.py", "apps/hub/pyproject.toml", "apps/hub/requirements.local-lock.txt", "apps/hub/runtime/attachments/__init__.py", "apps/hub/runtime/attachments/api.py", "apps/hub/runtime/attachments/capabilities.py", "apps/hub/runtime/attachments/content.py", "apps/hub/runtime/attachments/library.py", "apps/hub/runtime/attachments/service.py", "apps/hub/runtime/attachments/sync.py", "apps/hub/runtime/attachments/transport.py", "apps/hub/runtime/attachments/verification.py", "apps/hub/runtime/cli.py", "apps/hub/runtime/local_chat.py", "apps/hub/runtime/remote/commands.py", "apps/hub/runtime/remote/delivery.py", "apps/hub/runtime/remote/projection.py", "apps/hub/runtime/remote/queries.py", "apps/hub/runtime/remote/resources.py", "apps/hub/runtime/remote/sync.py", "apps/hub/runtime/remote/wire.py", "apps/hub/runtime/remote/worker.py", "apps/hub/runtime/tasks.py", "apps/hub/storage/attachments.py", "apps/hub/storage/local_chat.py", "apps/hub/storage/migrations.py", "apps/hub/tests/remote_support.py", "apps/hub/tests/test_r15_joint_server.py", "apps/hub/tests/test_r15_recovery.py", "apps/hub/tests/test_r16_attachments.py", "apps/hub/tests/test_r3_wire.py", "apps/hub/tests/test_remote_worker.py", ".hqagent/handoffs/R16-P2-hub.md"]
build: pass
tests: pass
commit: b4522ea11393ddcc36e9b6d4b193f131827f3964
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

