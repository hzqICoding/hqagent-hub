---
wp: R3-P2
status: done
scope_declared: [apps/hub/**, apps/server/server/replica.py, apps/server/server/service_sync.py, apps/server/tests/test_r3_guards.py, .hqagent/handoffs/R3-P2-hub.md]
scope_touched: [apps/hub/tests/test_r3_history_shapes.py, apps/hub/tests/test_r3_directory_mixed.py, apps/hub/tests/test_r3_long_history.py, apps/hub/tests/test_r3_roots.py, apps/server/server/service_sync.py, apps/server/tests/test_r3_guards.py, apps/hub/tests/test_r3_upgrade_fences.py, apps/hub/tests/test_r3_upgrade_history.py, apps/hub/tests/test_r3_version_series.py, apps/server/server/replica.py, apps/hub/adapters/history.py, apps/hub/api/app.py, apps/hub/api/local_chat.py, apps/hub/orchestrator/sessions.py, apps/hub/runtime/local_chat.py, apps/hub/runtime/native/activity.py, apps/hub/runtime/native/api.py, apps/hub/runtime/native/roots.py, apps/hub/runtime/native/service.py, apps/hub/runtime/remote/busy.py, apps/hub/runtime/remote/delivery.py, apps/hub/runtime/remote/projection.py, apps/hub/runtime/remote/queries.py, apps/hub/runtime/remote/resources.py, apps/hub/runtime/remote/sync.py, apps/hub/runtime/remote/window.py, apps/hub/runtime/remote/wire.py, apps/hub/runtime/remote/worker.py, apps/hub/runtime/tasks.py, apps/hub/runtime/workspaces.py, apps/hub/storage/local_chat.py, apps/hub/storage/migrations.py, apps/hub/storage/remote.py, apps/hub/storage/workspaces.py, apps/hub/tests/remote_support.py, apps/hub/tests/test_r15_joint_server.py, apps/hub/tests/test_r15_recovery.py, apps/hub/tests/test_r3_api_sync.py, apps/hub/tests/test_r3_guards.py, apps/hub/tests/test_r3_native.py, apps/hub/tests/test_r3_wire.py, apps/hub/tests/test_remote_worker.py, .hqagent/handoffs/R3-P2-hub.md]
build: pass
tests: pass
commit: 5b84af62ed61f5c3849f6d22946dbc4352632c50
open_questions: 0
---

# R3-P2 Hub / Worker 完成回执（协议 0.9.1）

工作区：`E:/OtherPro/HQAgent-Hub-worktrees/remote-worker`；分支：`feat/remote-worker`。首次续作相对主代理合入的 `f3b86f5`；头部 scope_touched 合并了返修 1 / 2 / 3 / 4 的修复文件，其余说明以各阶段为准；commit 指最后实施及测试提交，回执另提交。已保留先前 `8687d15` 的根目录基础、`be82fd5` 的枚举夹具校验和原 15 项根目录测试。首次交付未修改 packages/protocol、apps/server、apps/desktop、docs 或共享根配置；返修 1 的服务端改动见后文；没有安装依赖、启动 Vitest、合并其它分支或合回 integration。

## Q1 已由 0.9.1 关闭

按 R3-contract §11 和 R3-P0「补冻 0.9.1」实现，不再沿用上一版回执的 needs-decision：

- v1 Bearer、v2 本机 Cookie 各提供列表、详情、messages、imports 四条路由；共用 `runtime/native/api.py` / NativeService。列表返回生成的 LocalNativeSessionPage，不填假的 workerId。
- 导入是本机同步事务，返回 **201 LocalConversationView（conversationKind=native）**，不经过远程 provisional/grant。Hub 签发 NativeClosureConfirmation 并原子留审计；重放只保存对话引用，不另存一份历史正文。
- 云端导入继续检查 Server 签发的确认和显式 grant；两条路径共用源再检查、精确绑定唯一约束、确认失效与写锁。
- 本机操作独立于配对、网络、远程暂停、同步开关及线路。所有成功、失败、幂等响应 no-store；POST 沿用 Origin / Idempotency-Key；不记录正文。
- wire2 / 2→3 栅栏内仍可本机导入，但不上传 native 索引、对话或其消息/运行/审批，也不借旧 seq 分配不可发送记录；wire3 确认后捕获水位并补传。

## 模块与存储

| 文件 | 责任 |
| --- | --- |
| adapters/history.py | Runtime 插件层的版本化 FileHistory、能力信息、终端来源证明、完整脱敏历史和源快照；Worker 不解析厂商文件 |
| runtime/native/activity.py | 精确原生 ID 的进程证据探测；无法判断时 unknown |
| runtime/native/service.py | 索引、本机分页、读取快照、原子导入、确认审计、精确 Session 绑定、持久写锁与恢复 |
| runtime/native/api.py | 生成 DTO 的八个本机操作和鉴权组接线 |
| runtime/native/paths.py、roots.py | 已有授权根 CAS、目录身份/句柄、逐层快照、短期选择引用；本轮补线程锁、取消检查、登记审计 |
| runtime/remote/wire.py、worker.py | 1/2/3 编解码、协商栅栏、连接生命周期、资源及查询接线 |
| runtime/remote/queries.py | 临时查询通道，期限/大小/并发限制及断线取消 |
| runtime/remote/resources.py | native.import / workspace.register 的 provisional、显式 grant、幂等和资源结果 |
| runtime/remote/sync.py、window.py、projection.py、busy.py | 修订隔离、可靠 native 索引、完整历史补传、删除/擦除、native 忙碌投影 |
| storage/migrations.py | **只追加 migration 8**；1–7 未改 |

migration 8：

- `native_sources`：opaque 索引 ID，唯一精确 binding，workspace/runtime/Agent，source/index JSON，导入后的唯一 conversation/session 引用，确认及 removed 标记。
- `native_writers`：binding_key 主键，session、owner、state、source_revision、started_at、当前输入摘要；锁的是精确外部会话，不能靠换 conversationId 绕过。
- `native_commands`：store/worker/command 唯一键，规范化摘要、帧、状态、收件回执、grant、结果；不改变已有 run 命令表。
- native_sources 的增改触发器写入既有 remote_sync_changes。授权根仍使用既有 remote_state；未增加协议字段。

## 逐条实现与取舍

### 修订与可靠同步

CODECS 使用三个独立的生成联合类型。初次优先 3，服务端仅支持 2 时按其 supportedWireRevisions 回退；link 如实带 REMOTE_REVISION_REQUIRED 能力事实。升级等待旧可靠流水位、未完成命令和暂存内容收敛，持久化双方栅栏后才发布 wire3 事件。已提交 wire3 的 store 不强行降成 wire2；重传保留原帧 epoch、hash、版本。

修订 3 的 catalog 只增加 rootId/displayName/version，不发路径。未导入会话仅发脱敏后最多 120 码点标题及索引；导入后从未导入索引移除，完整历史按既有分段/有界窗口补传。同步关闭、撤销、workspace 移除处理 native 索引删除或 reset，并对已有待发送索引做原生索引专用擦除证明，不把路径/正文塞进删除事件。关闭同步不删本机会话源、不禁止本机导入。wire2 的 native 本机变更保留为待捕获状态，不伪造 scenario 或 scene。

### 读取插件与能力边界

当前 Adapter 端口没有官方 history 方法，因此实现明确的**文件回退插件**，没有宣称调用不存在的官方历史 API。能力信息来自配置目录和支持的解析 profile。

支持并以合成文件验证的 profile：

- Claude Code：2.1.261、2.1.272、2.1.283。
- Codex：0.153.4。

未知版本、记录形状或内容块返回 unsupported/原因；无法识别到有效索引且存在诊断时，本机列表返回 NATIVE_SESSION_UNSUPPORTED，不用空列表伪装无记录。默认扫描对应 Runtime 的 .claude / .codex 数据根，可注入合成根测试。没有读取、打印或提交用户真实会话。

Codex 必须有 session_meta.source=cli、精确 UUID、绝对 cwd；Claude 必须由交互 history.jsonl 中 sessionId/project/display/timestamp 与会话信封相互印证，不能凭文件名推断终端来源。排除 sidechain、已知非终端来源、已有 Hub Session 的精确 externalSessionId 和已导入绑定；cwd 真实路径必须落在已登记 workspace 中，源文件不能通过符号链接越出 Runtime 数据根。

先脱敏后截标题/分段：仅公开 user/assistant 文本及安全工具名摘要；不包含原始工具参数、输出、系统/开发者注入、analysis/thinking/encrypted 内容、已知 Hub/设备/环境模型凭据或常见密钥形态。时间归一 UTC，使用文件时间回退时保存 timeBasis。单源上限 64MiB、发现文件上限 10000，明确报能力/大小限制；发现阶段只保留元数据，不同时缓存全部全文。未完成的最后一行不作为完整消息解析。

### 按需读取

QueryChannel 不分配可靠 seq，不写 Outbox 或查询正文到数据库。最多 4 个当前查询、保守 10 秒期限、总 1MiB；编码按生成 DTO 校验。分页保持源完整记录切点、文件身份与前缀摘要；新增尾部不改变旧游标，旧前缀被改或替换则失效。正文分段有数量/字符/字节限制，不能截断后冒充完整。

查询体和游标仅存内存，断线/reset/解绑/撤销取消后台读取，线程读循环检查取消标记；远程 scope 绑定 store/syncGeneration，本机读取 scope 独立。查询错误不回显历史/凭据。测试验证超时、过大、断线、源变化都不写可靠正文或改变 Outbox 上界。

### 导入、续接与 E10/E11

导入前重查 workspace、源版本和活动证据；likely_active 不能被勾选覆盖，unknown 不能直接启动写进程，必须取得与当前 sourceRevision 绑定的显式关闭确认。确认、完整脱敏历史、native 对话、唯一绑定、审计和幂等引用一次事务提交；失败没有半个对话，导入不调用模型。真正开始轮次后，使用真实 Task/Node ID 建立 Hub Session，不在导入时虚构执行 Task。

每次 resume 都重新核对源与活动证据，并在 SessionManager 层获取持久精确 binding 锁；桌面、手机、重试、直接 Session 路径共享。Adapter 收到原 exact externalSessionId 的 resume；不找最近历史、不退回新建外部会话。取消确认沿用原规则释放写者；不确认或恢复证据不足保留 recovery/禁止续接，不改变 D41 控制三态。重启将旧写者标为待核对，**不把不可检查的遗留进程自动视为已退出，也没有强制解锁接口**。

自己的已完成轮次可在完整前缀不变、唯一新用户输入摘要匹配、没有外部进程证据时更新 owned_revision；审计中的用户确认不被伪造刷新。其它外部修改必须重新确认。视图按当前来源更新活动/源版本；源不可用时退为 unknown 提醒，不让整个对话列表失败。

执行策略仍使用既有单 Agent、只读 ad-hoc 路径及内部 analyst 权限角色；**不新建 LocalScene，不填场景快照，不扩展文件写权限**。native 对话/轮次公开 Mapper 不暴露场景角色。未进行真实终端进程/真实模型的端到端续接验收；精确请求、互斥、恢复和取消由 FakeAdapter 与合成文件验证。

### 授权目录与登记

保留默认空、最多 32 根的持久 CAS。引用绑定根 ID/版本/真实目录身份，根移除立即失效。目录每页最多 100 个，只含一层目录元数据，不含文件；不执行快捷方式。拒绝 UNC、设备路径、驱动器相对路径、..、ADS 等，真实路径检查处理 symlink/junction、Windows 大小写和卷身份。

Windows 保持目标及祖先目录句柄，拒绝 DELETE 共享以阻止替换；消费前和提交时重查身份及根 CAS。POSIX 用 fd/身份检查，本轮没有 POSIX 真机竞态验收。内存引用最多 4096、15 分钟有效，重启失效。目录快照变化拒绝旧游标。

登记复用 WorkspaceService，非 Git 目录只能 read_only，不做 init/mkdir/clone；持有目录 lease、workspace 保存及 remote 完成回执在同一事务。审计仅 requestId/operation/rootId/resultCode，任意未知 rootId 归为固定标记，不把用户输入路径写进审计。

## 既有内核的最小改动

- runtime/local_chat.py / storage/local_chat.py：native 输入委派与视图字段、隐藏内部标记、不造 sceneSnapshot；后台监督不反复做昂贵原生扫描，HTTP 视图才更新观察。scenario 路径保留。
- runtime/tasks.py：在真实 Task/Node 建立后准备 native session；retry 保留精确原生绑定，避免已取消父节点重试误开新会话。
- orchestrator/sessions.py：resume/finish/close 增加绑定守卫与释放/恢复钩子。原取消执行、暂停/恢复、reviewer 隔离、develop worktree 不改语义。
- runtime/workspaces.py / storage/workspaces.py：增加可选提交回调与外部事务接入，沿用已有登记校验；使目录授权检查和资源回执能原子提交。
- api/app.py / api/local_chat.py：挂同一原生路由实现、统一 no-store；使用原 v1/v2 鉴权。
- storage/remote.py：check_continuity 在同一 DB 锁内读取 identity 和外部 witness。后台目录审计引入的并发场景暴露了旧读窗口：旧 identity 与新 witness 会误判回滚。新测试以线程屏障稳定复现，修复后 store 不误轮换；真正回滚的原测试仍通过。这是连续性读取修正，不改反回滚规则。

## 测试映射及既有断言调整

新增 27 项（含参数化），加之前根目录 15 项；Hub 总数由续作基线 371 到 398：

| 模块 | 验证 |
| --- | --- |
| test_r3_native.py | 两种合成格式、离线导入/精确 resume、作用域/来源/版本、凭据过滤、活动与修改失效、未知块、工具摘要/时间依据、能力缺口不回显 |
| test_r3_guards.py | 幂等/原子回滚、跨管理器原生 ID 锁及重启、源切点、取消/retry、归属水位、连续性并发、查询故障 |
| test_r3_wire.py | 真实本机 TLS 假 WS 的修订 3 索引/临时读取/grant 导入及远程 run、仅 2 回退与升级补传、目录浏览和只读登记 |
| test_r3_api_sync.py | v1/v2 八路由/401/Origin/no-store/关闭同步本机使用、reset/撤销/workspace 索引清理、删除根后 grant 拒绝 |
| test_r3_roots.py（保留） | 根 CAS/幂等、分页/变化、危险路径、junction/symlink 越界、身份替换/过期、Windows 句柄保护 |

既有测试改动逐项说明：

1. remote_support.py：假服务端支持生成的 1/2/3 DTO；未减少已有校验。
2. test_remote_worker.py：无共同修订号测试的 reject_revisions 从 [3] 改为 [4]，因为 3 现在可用；原冻结和无重连风暴断言保留。**不是用它替代旧服务端回退测试**；新增 test_revision2_defers_native_history_then_revision3_backfills 真正先只支持 2。
3. test_r15_recovery.py：首选探测序列 [2,1] 改 [3,1]；延迟升级的序列改 [3,2,1]。旧 R1 回退、栅栏和不重复执行断言保留。
4. test_r15_joint_server.py：Hub 迁移到固定 7 的断言改为 LATEST_SCHEMA_VERSION（新增 8）；帧严格按实际线路 DTO 校验；从第一个接收帧改查第一个成功 hello_ack，允许本次新增的首个不支持 3 探测。真正元数据冲突仍断言失败及错误码，未改 server。
5. 前一阶段 test_contracts.py 的 TypeAdapter 修正留在基线：枚举与 model 均严格完整 round-trip，没有跳过夹具。

## 最终验证（真实输出）

所有测试串行。TEMP/TMP/basetemp 均位于 worktree 忽略的 .tmp，避开默认临时目录 WinError 5。未并行 pytest，未运行 Vitest。本轮未出现 0xC0000142 或额度错误。

Hub，cwd apps/hub：

```powershell
$env:TEMP='E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-final-delivery --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r3-final-delivery.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 18%]
........................................................................ [ 36%]
........................................................................ [ 54%]
........................................................................ [ 72%]
........................................................................ [ 90%]
远程送达预留清理暂未完成，将重试
远程送达预留清理暂未完成，将重试
......................................                                   [100%]
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
398 passed, 4 warnings in 219.50s (0:03:39)
```

协议，cwd worktree 根：

```powershell
$env:TEMP='E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
$env:PATH=(Join-Path (Get-Location) '.venv/Scripts')+';'+$env:PATH
pwsh scripts/protocol/validate.ps1 -CheckGenerated 2>&1 | Tee-Object -FilePath .tmp/r3-protocol-delivery.log
exit $LASTEXITCODE
```

```text
协议校验通过：427 个类型，289 个 Contract Fixture
```

协议退出码 0。git diff --check 通过；Git 的 CRLF→LF 提示不是校验失败。Hub 四个 warning 为依赖弃用提示。全量还出现两条既有“远程送达预留清理暂未完成，将重试”：**没有把它们归因到本次修好的 witness 竞态，也没有宣称通用重试日志已全部消除**；测试没有失败。

## 验证边界与下游事项

- 本轮没有真实 CLI 启动/用户会话读取，没有真实 P1 修订 3 联调；测试使用合成文件、FakeAdapter、假 WS。既有 R1.5 真实 P1 集成用例仍在全量内。
- 只声明上述已识别 profile。真实 Runtime 升级到未知格式要显式 unsupported，需补 profile 与合成回归，不能自动猜测解析。
- Native 执行当前继承只读单 Agent 权限策略；不能据此声称已提供任意原生 CLI 权限配置。
- 桌面用本机 Cookie 八操作、显式终端关闭确认、native 分类；不要混用云端公开 ID。待支持 3 时依据 link/同步设置显示未同步，不凭协议包版本显示已同步。
- P1 接线需支持 wire3 栅栏、可靠索引及删除证明、临时 query/chunk/error、资源 receipt/grant/result；资源 metadata 提交不会自动调用模型。读请求为临时流，不能作为可靠 ACK 放行命令。
- 无法核实的遗留原生写者保守保持恢复待核对；外部进程无法可靠探测时不能用勾选越过正向活动证据。这里没有承诺外部工具与 Hub 共享一把可强制执行的操作系统锁。

## 提交

- f0f324eb48df7dcb0b29af6e5965289fa709449f：版本化历史、原生导入及执行守卫。
- e07a6d66eb1956c166eeb39bec8596a816b43d12：修订 3 查询、资源和同步接线。
- 864e9130ea0115c6494010b688d7e09e845963fc：原生隔离、恢复、延迟同步等测试及连续性修正。
- 809cc5f402fe9d0530ec7f32a07a406bb21cfce6：不可识别历史的结构化能力错误及回归。
- 本回执另提交。每次提交后均执行 git log -1 --format=%B 检查，无署名或生成标记；未合回 integration。

## 返修 1：真实 R3 服务端联调、显式修订 2 回退与升级投影修复

本次基线 `361f363 merge: sync integration with R3 server for joint test fix` 已包含 P1 R3。先确认 git log / clean status，再复现原模块：

```text
FAILED tests/test_r15_joint_server.py::test_real_r1_upgrade_backfill_and_computer_rounds_keep_reply_and_connection[False]
FAILED tests/test_r15_joint_server.py::test_real_r1_upgrade_backfill_and_computer_rounds_keep_reply_and_connection[True]
FAILED tests/test_r15_joint_server.py::test_real_server_rejection_preserves_error_instead_of_inventing_epoch_failure
3 failed, 1 warning in 8.12s
```

三项直接错误均为 RealPair.__aenter__ 的 `hello_ack.wireRevision == 2`，实际为 3。此前回执中“未与真实 P1 修订 3 联调”描述的是首次交付；**本次已用真实 P1 create_app + uvicorn TLS + Worker/core 验证下述 R3 场景**。模型仍用 FakeAdapter，原生文件仍用合成夹具，不宣称真实 CLI 验收。

### 断言与夹具逐项调整

仅修改 Hub 的 `tests/test_r15_joint_server.py`：

1. 原 helper 的 hello_ack=2、identity.wireRevision=2，改为精确等于测试参数；默认参数 **3**。并没有改成“2 或 3 都行”。原三项测试分别在 2、3 下各跑一次，共六项。
2. 修订 2 用 monkeypatch 限制**真实服务端** wire.CODECS 为 [1,2]，没有把 Worker 伪装成旧版或用假 ACK。额外断言真实拒绝帧为 REMOTE_PROTOCOL_UNSUPPORTED、supportedWireRevisions=[1,2]，随后精确协商到 2；修订 3 正常握手不得出现拒绝。
3. 原有 backfill 未完成时接单、两轮回复全文、本机版本为 1、busy=false/busyFresh=true、手机 continue 原 Session、真正元数据冲突 REMOTE_SYNC_CONFLICT、connectionId/epoch 和服务端未错误冻结等业务断言**全部保留**，在两种线路均验证。
4. 新增两项真实 native 联调：合成一个只上传索引的会话及另一个已本机导入的完整历史。直接修订 3 时断言 native.index.upserted 及 native 对话/消息走 3，真实手机 API 可读一个未导入索引及完整导入历史。
5. 显式修订 2 时断言：本机导入仍保存两条消息；服务端无 native 索引/对话；所有发出帧没有 native 类型、native 标记或合成正文；link 如实为 REMOTE_REVISION_REQUIRED。停止 Worker 后，在同一服务端/数据库/store 启用 [1,2,3]，重连通过栅栏后完整补传，未清数据库或重配对绕过升级。
6. 新增升级完整性断言：旧两条 R1 对话均保留标题、metadataVersion=1、每条 12 条历史，其 workspaceId 与新 native 对话使用同一个公开映射。所有 native 帧必须 wireRevision=3，导入本身不调用 Adapter start/resume。
7. 新增消息页按 R1.5-contract §7 的 messageSequence **降序**断言 [2,1]，并精确比对 assistant/user 两条正文。编写新用例时最初按升序期望失败，核对契约后改为正确的降序；这不是删除或放宽既有业务断言。
8. RealPair 在启动 Worker 前将 reader 配到测试临时目录，非 native 场景使用独立空目录。原夹具只在修订 2 下运行，不会发现默认原生数据根；修订 3 开启扫描后暴露这个隔离缺口，现已显式封闭。native 导入请求同时提供接口规定的可信 Origin。没有从真实用户内容构造夹具或在回执记录它。

新增帧仍逐条通过生成的 WORKER_CODECS / SERVER_CODECS 校验；手机页用 RemoteNativeSessionPage / RemoteConversationView / RemoteSyncMessagePage 校验。

### 新测试定位到的真实生产缺陷

修订 2→3 用例不是只改期望就通过：初次新增用例在升级后冻结，持久状态为 `REMOTE_SYNC_CONFLICT`，ACK=43、下一条 seq=44 为旧 scenario 的 `sync.conversation.upserted`，native 历史尚未发送。

原因在 `apps/server/server/replica.py::Replica.conversation`：

- 修订 2 副本持有本机 workspaceId。
- R3 `native_events.conversation` 按契约将相同 workspace 映射为 owner/device/store 范围内的公开 ID。
- 同版本元数据校验直接比较旧本机 ID 和新公开 ID，因此把纯身份投影升级误判为用户修改。

按本次要求“业务断言失败要修代码”，改服务端，不伪造 Worker metadataVersion，也不增加同步 generation 或删旧历史躲过冲突。仅在修订 3、旧 workspaceId 精确等于入站本机 workspaceId、且旧 ID 不是已有公开 workspace 映射时，将旧投影归一化后比较。全部元数据字段仍经过原 require 比较；真正标题/归属等变化仍失败。同时间戳也提交映射升级，updatedAt 取 max 防止回退。没有改协议、数据库迁移或生产 Worker。

### 本次验证

所有测试串行，未开并行 worker、未跑 Vitest、未安装依赖。TEMP/TMP 均放 worktree/.tmp；使用 --basetemp 避开默认临时目录权限问题。

复现及定向命令（cwd apps/hub）：

```powershell
$env:TEMP='E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest tests/test_r15_joint_server.py -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair-repro --tb=short
../../.venv/Scripts/python.exe -B -m pytest tests/test_r15_joint_server.py -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair-joint3 --tb=short
```

修复后定向真实输出：

```text
8 passed, 1 warning in 18.73s
```

此后追加旧对话标题/版本/历史和 workspace 映射断言，最终由下面全量覆盖。

最终 Hub 全量（cwd apps/hub，TEMP/TMP 同上）：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair-full --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r3-repair-full.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 17%]
........................................................................ [ 35%]
........................................................................ [ 53%]
........................................................................ [ 71%]
........................................................................ [ 89%]
远程送达预留清理暂未完成，将重试
...........................................                              [100%]
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
403 passed, 4 warnings in 231.82s (0:03:51)
```

退出码 0，原 398 项扩展为 403 项（原三项额外跑修订 2，加两项 native 联调）。4 个 warning 为依赖弃用提示；仍有一条此前记录的通用预留清理重试日志，不把它宣称为本次修复内容。

由于本次修复服务端生产代码，额外串行跑服务端全量（cwd apps/server，TEMP/TMP 同上）：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair-server --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r3-repair-server.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
.......                                                                  [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
223 passed, 1 warning in 61.00s (0:01:01)
```

退出码 0。git diff --check 通过。本次没有 429、0xC0000142 或额度错误；未变更协议，因此本返修没有重复生成协议，先前协议校验记录保持原样。

本次提交：
- `a3f9726`：真实修订 3、显式修订 2 兼容、native 延迟补传集成测试。
- `970dfbb`：服务端 workspace 身份投影升级修复。
- 回执另提交。每次提交后均 git log -1 --format=%B 自查；未合回 integration。

## 返修 2：旧修订 2 升级收敛与原生读取版本系列

### 基线及诊断边界

开工 git log 为 `507a2db merge: sync integration with R3 server 0.9.2 fix before upgrade repair`，工作区干净；按要求执行 `git merge --no-ff integration/phase1` 返回 `Already up to date.`，确认已经包含 0.9.2 服务端修复。合并日志已自查。

提供的证据数据库使用 SQLite mode=ro 打开返回 OperationalError，未读取到内容，也没有复制或提交证据。以下根因来自真实代码路径与持久化合成数据测试，不宣称已经核实那条生产 accepted 的具体 run/task。测试分别覆盖“已上报最终结果的残留 accepted”和“本机终止但恢复证据仍不确定的 accepted”。

本次没有修改 packages/protocol、apps/desktop、迁移或执行内核；为了让同一个升级栅栏两端一致，按本次裁决最小修改了 server/service_sync.py，并新增服务端守卫测试。没有改掉控制结果的三态或真实进程停止语义。

### 根因与修复

1. **unconfirmed 错算未决**：worker.can_upgrade 的修订 2 查询原来只排除 completed/failed/rejected。DeliveryBridge._finish 实际还持久化 unconfirmed，它是该次控制投递的最终观察，不等于执行成功。本次用真实 FINAL_STATES 四态排除它；waiting、provisional、accepted 和未知异常状态仍阻挡。未删除任何不确定性、orphanProcessIds 或 recoveryRequired。
2. **accepted 双账本历史恢复**：正常成功/失败仍由 SyncService.poll_execution 调 DeliveryBridge._completed/_failed，在同一事务更新 Inbox、delivery 和可靠事件。补强 _cache 同时保存 Inbox 的最终原回执。对历史 accepted 只用原 result_json、receipt_json 或原事件日志中的同 store/worker/command/conversation 最终结果修复，不根据 LocalRun 标签伪造成功；保留原 eventId/epoch/seq/wireRevision，不新发重复结果。已接单原命令不能被同 ID 冲突变体的 command.rejected 误终结，因此该类拒绝不作为 accepted 修复证据。
3. **本机终态仍有恢复疑点**：原 poll_execution 遇 recoveryRequired/unresolvedCancellation 时什么也不做，会永久留 accepted。现在在 LocalRun 已终止的前提下输出结构化 unconfirmed，保留 executionMayStillBeRunning=true、orphan 列表和 recovery_flag，不输出 command.completed。仍在执行的轮次不走此分支。
4. **服务端同样阻挡**：Server 原 on_hello 将任何 controlResult.unconfirmed/orphan 都当作未决；云端 schema 的 command.status 仍可保持 accepted。本次仅对 **2→3**，将 deliveryState=acknowledged 且已有 unconfirmed 结果的控制投递视为已经得到最终观察；命令视图状态和证据原样保留。未收到回执的 accepted、queued、未完成 Outbox、连续 ACK 缺口、未应用事件仍阻挡；其它线路转换保留原规则。
5. **不能换线路重发旧结论**：升级后的 poll_execution 不再以新 wireRevision 重新输出旧线路命令的延迟控制结论。旧结果与不确定性保留供对账；新请求仍走原控制证据检查。真实联调测试验证升到 3 后对遗留未确认运行发 retry，仍返回 unconfirmed、没有启动第二次执行。
6. **在线旧服务端永久失去探测**：原条件要求 server_supported 已含 3 才探测 3，但曾被 [1,2] 拒绝的在线设备不会再获知更新。现在沿用 30 秒节流、在栅栏可通过时重新探测；真实旧服务端仍按拒绝回退，不形成重连风暴。测试只提前探测计时点以缩短等待，没有强改身份或模拟成功 ACK。

### 其它升级条件核查

- **remote_sync_items**：发现真实收敛问题。重连时 phase=synced 会重新 capture，但旧版 capture 未清前次未分配 seq 的暂存项；旧 batch 永远不会被新 batch 的 pump 消费，can_upgrade 却会检查全表。现在新 capture 在同一事务替换暂存快照；对既有 backfilling/waiting_complete_ack，仅退休非当前 backfillId 的旧快照暂存项。当前快照完整覆盖源数据，已进入可靠 Outbox 的帧完全不动。
- **sync-work.phase**：backfilling 必须消费当前批次并等 complete；waiting_complete_ack / waiting_reset_ack 必须等持久 ACK。握手中的 lastServerAck 也调用现有 sync.on_ack，使重启/重连不必等另一条重复 ACK 才推进 synced/disabled。
- **Outbox**：仍要求当前 store 的可靠 Outbox 清空；没有丢弃未确认记录、跳 ACK 或重写原 hash。测试分别证明当前暂存及未确认 Outbox 仍阻挡，真实 ACK 到达后放行。
- 关闭同步原 set_settings 清空待上传暂存并发 reset，只有 reset ACK 后进入 disabled；本次没有放宽 reset/删除证明规则。撤销状态不能作为可升级在线连接使用。

### 文件与版本判定

- runtime/remote/delivery.py：FINAL_STATES、原始结果修复、最终回执一致写入。
- runtime/remote/worker.py：终态栅栏、握手 ACK 接线、定期重新探测。
- runtime/remote/sync.py：旧暂存快照收敛、旧线路结果隔离、已终止但有疑点的最终 unconfirmed 观察。
- server/service_sync.py：2→3 服务端栅栏的“已确认收妥未知结果”判定，不改公开 DTO。
- adapters/history.py：由精确补丁白名单改为经验证主次系列 + 最低补丁 + 逐条结构验证。

读取规则：

| Agent | 已验证系列 | 最低补丁 | 未验证系列 |
| --- | --- | --- | --- |
| Claude Code | 2.1.x | 261 | 2.2、3.x 等返回 unsupported |
| Codex | 0.153.x | 4 | 0.154、1.x 等返回 unsupported |

不低于下限只取得进入结构校验的资格，不直接判可读。继续校验消息块、角色和链；补足每条身份信封的 sessionId/id、cwd、version/cli_version 一致性，Codex 重复 session_meta 及 turn_context 中声明的绑定也检查。损坏 JSONL 和身份字段不一致有具体固定字段/行号原因；未知主次系列或低于下限返回“该 CLI 版本尚未验证”。不在错误里回显原正文或任意路径。

capabilities 新增内部 verifiedSeries、observedVersions、versionPolicy、versionDiagnostics：如实标明最低补丁、实际观察到的版本以及“系列下限 + 结构”判定方式，诊断有界；这不是修改冻结协议中的 capability DTO。实际版本只允许数值版本进入诊断，其它记 unknown，不把任意文件文本伪装成诊断版本。没有在测试里启动真实 CLI 或读取用户实际历史。

### 新增回归与原断言

既有业务断言未修改、未删除。本次新增文件：

- test_r3_version_series.py：22 项；系列下限、新补丁、未知主次版本、结构损坏/身份冲突及能力诊断。
- test_r3_upgrade_history.py：2 项真实 create_app + uvicorn TLS + Worker/core 联调。持久化两个 unconfirmed 和一个已完成但残留 accepted，重建 System 后修复原结果并在线自动升级；另测真实已 grant 正在执行仍阻挡、最终回执与 ACK 后升级。保留不确定性证据，升级后的 retry 仍被核对规则挡住。
- test_r3_upgrade_fences.py：4 项；waiting/provisional、旧 batch 暂存退休而当前暂存与 Outbox 仍阻挡、终态疑点上报 unconfirmed。
- server/tests/test_r3_guards.py：新增 3 项参数化守卫，只有 accepted + acknowledged + unconfirmed 放行，未确认收到和 queued 仍拒绝，原 command.status/controlResult 不改。

所有文件都用合成数据。模型路径仍为 FakeAdapter；“真实”指真实服务端/Worker/协议/TLS/数据库，不指真实 CLI。没有冒称对提供的生产数据库做了修复。

### 验证与提交

先跑新版本及真实历史升级测试：

```text
24 passed, 1 warning in 9.56s
```

随后跑栅栏、既有 native 与恢复测试：

```text
19 passed, 1 warning in 9.31s
```

首轮全量输出 430 passed，但运行中又补了最终疑点收尾回归，因此以下**最终重新运行**的输出才作为交付结果。TEMP/TMP 和 --basetemp 全部在 worktree/.tmp，串行运行，未跑 Vitest、未安装依赖。

Hub，cwd apps/hub：

```powershell
$env:TEMP='E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair2-hub-final --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r3-repair2-hub-final.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 16%]
........................................................................ [ 33%]
........................................................................ [ 50%]
........................................................................ [ 66%]
........................................................................ [ 83%]
远程送达预留清理暂未完成，将重试
.......................................................................  [100%]
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
431 passed, 4 warnings in 242.77s (0:04:02)
```

Server，cwd apps/server，TEMP/TMP/PYTHONIOENCODING 同上：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair2-server-final --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r3-repair2-server-final.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 31%]
........................................................................ [ 62%]
........................................................................ [ 93%]
...............                                                          [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
231 passed, 1 warning in 62.85s (0:01:02)
```

两条命令退出码均 0；git diff --check 通过。依赖弃用 warning 未修改；Hub 仍出现一条此前记录的通用预留清理重试日志，本次不宣称解决该日志。最终 Hub 新增 28 项，Server 新增 3 项；其余业务断言未放宽。没有 429、0xC0000142 或额度错误。此轮未变更协议，也没有重新生成协议。

本次提交：
- `68b83c8`：按已验证版本系列与结构判定原生历史。
- `7f73ce5`：旧投递结果核对、Worker/Server 升级栅栏收敛及回归。
- 本回执另提交。每次提交后均 `git log -1 --format=%B` 自查，无署名或生成标记；未合回 integration。

## 返修 3：混合目录浏览与长期原生会话读取

开工分支为 feat/remote-worker，HEAD=a4f3137，工作区干净。按本次要求未再合并 integration。本轮只修改 Hub 原生目录/历史读取及相关测试，没有修改协议、Server、执行内核或活跃检测。

### 目录浏览

根因是 _listing 对每个子项沿用目标级异常语义，一个越界联接点会中止整个页面。

runtime/native/roots.py 现在在**单个子项**的 stat/目录租约边界内处理失败：根外 symlink/junction、无权限、无法作为目录打开或身份失效的子项静默跳过。只有租约退出时的最终身份复查也通过后才加入响应及分页摘要，不先加入再吞掉退出异常。查询取消、资源配额以及其它错误不在这个吞掉范围中。

请求目标和授权根本身仍在外层租约中严格核验；直接访问越界目标返回 REMOTE_PATH_OUTSIDE_ROOT，失效/无权限目标返回 REMOTE_DIRECTORY_CHANGED。登记继续复用 selected 的身份与边界检查，没有因为 listing 跳过机制放宽登记。普通文件与快捷方式仍不返回。

成功 listing 如有跳过，在原本机 remote.directory.audited 审计中增加一个 skippedCount；只增加数量，保留既有 requestId/operation/rootId/resultCode，不保存子项名称、路径、联接目标或每个错误详情。没有跳过时保留原审计形状。

新增 test_r3_directory_mixed.py：在 Windows 创建真实越界 junction，混入普通目录、带 .git 标记的目录，以及通过目录打开层注入的 PermissionError / NotADirectoryError。验证：

- 远程查询只返回 gitproj/plain，响应中没有三种被跳过子项或根外目标的名称；
- 审计 skippedCount=3，字段集合不含路径/名称；
- 对此前合法签发、后来被替换为越界 junction 的引用，目标读取及 workspace.register 仍拒绝；
- 正常 plain 经收件/grant 登记成功，非 Git 保持只读。

无权限错误采用合成 OS 打开失败注入，未修改主机 ACL；.git 标记只用于目录元数据测试，未声称测试了 Git 仓库创建或执行 git init。

### 长会话读取

根因是 _validate_identity 和 _messages 两处都将所有记录的 cwd/version 与首信封严格相等作为读取前提。

adapters/history.py 改为：

- **规范 cwd 不漂移**：仍由初始信封确定，workspace 过滤、索引、source_json 导入绑定都使用它；后续 cwd 是上下文，只检查所需字段存在且是绝对目录，不再要求等于规范 cwd，也不为了读取上下文去打开后续目录。
- **逐条验证版本系列**：每个声明的 version/cli_version 均独立使用返修 2 的已验证系列和最低补丁规则，允许同一系列内补丁变化；未验证系列明确返回带记录位置和字段的 unsupported 原因。
- **精确会话身份不放松**：sessionId/id/session_id 声明必须一致，Claude 消息仍必有 sessionId；消息块、角色、消息链及来源验证不变。移除 _messages 中重复的 cwd/version 相等判断，保留 sessionId 校验。
- capabilities.observedVersions 收集会话中观察到的已验证版本；索引 cliVersion 仍是源信封版本，不伪装成只使用最新版本。凭据过滤、私有推理过滤、分段、源快照哈希机制未改。

新增 test_r3_long_history.py（两种 Agent 的合成格式）：中途 cwd 改变、版本从 2.1.261→2.1.284 / 0.153.4→0.153.5，完整读取长正文并分段；分段拼接和导入后的全文均精确等于脱敏源结果。验证凭据和私有推理不出现；仅登记后续 cwd 不会错误收录，登记规范 cwd 才收录；导入仍绑定规范 cwd，且不调用模型。

### 旧测试调整清单

1. test_r3_roots.py::test_junction_or_symlink_cannot_escape_authorized_root：原断言“浏览父目录抛 REMOTE_PATH_OUTSIDE_ROOT”按本次明确要求改为“父目录成功，越界子项不出现，响应无名称/指向”；直接打开越界项仍严格断言原错误码，没有取消边界检查。
2. test_r3_version_series.py::test_new_patch_still_requires_consistent_record_identity_and_shapes：cwd 损坏样本从合法的另一个绝对目录改为非法相对路径；版本损坏样本从合法的新补丁改为未验证主次系列（2.2.0 / 0.154.0）。原 unsupported、无正文、原因不泄露内容及字段原因断言保留；新的成功测试专门覆盖本轮准许的跨 cwd/补丁情况。
3. 其它原有断言未修改，包括目录审计字段、分页快照、根移除失效、Windows 句柄保护，以及消息结构/身份损坏/未知系列拒绝。

### 活跃检测限制（本轮不改）

直接以 CLI 启动且命令行没有精确会话 ID、最后写入又已超过 5 秒时，当前探测可能为 unknown 而不是 likely_active。这不表示确认已关闭；unknown 仍只读，写入需明确关闭确认并通过后续再检查，正向活跃证据不能被勾选覆盖。runtime/native/activity.py 无改动。本轮没有读取真实用户会话、启动真实 CLI，不能据合成测试宣称改进了这种活跃探测。

### 最终验证

所有测试串行、未运行 Vitest。TEMP/TMP 和 --basetemp 均指向 worktree/.tmp，避开默认临时目录的 WinError 5。没有改协议或运行生成命令。

Hub，cwd apps/hub：

```powershell
$env:TEMP='E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair3-hub-final --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r3-repair3-hub-final.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 16%]
........................................................................ [ 33%]
........................................................................ [ 49%]
........................................................................ [ 66%]
........................................................................ [ 82%]
........................................................................ [ 99%]
远程送达预留清理暂未完成，将重试
..                                                                       [100%]
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
434 passed, 4 warnings in 263.47s (0:04:23)
```

Server，cwd apps/server，TEMP/TMP/PYTHONIOENCODING 同上：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair3-server-final --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r3-repair3-server-final.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 31%]
........................................................................ [ 62%]
........................................................................ [ 93%]
...............                                                          [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
231 passed, 1 warning in 73.17s (0:01:13)
```

两条命令退出码均 0；git diff --check 通过，范围检查未发现本轮修改 Server/协议/桌面文件。Hub 新增 3 项，既有损坏/越界拒绝断言按前述清单维护。依赖弃用 warning 未修改；Hub 仍有一条此前记录的通用预留清理重试日志，不宣称是本轮已解决的问题。没有 429、0xC0000142 或额度错误。

本次提交：
- `1e90790`：授权目录浏览跳过不安全/不可访问子项、计数审计及登记守卫测试。
- `1335cd7`：规范会话绑定不随 cwd/补丁变化，逐条系列验证及完整历史测试。
- 回执另提交。每次提交后均执行 git log -1 --format=%B 自查；未合回 integration。

## 返修 4：结构化原生历史兼容与安全降级

本轮在 feat/remote-worker 继续，未合并其它分支。仅修改 adapters/history.py、runtime/native/service.py 和 Hub 相关测试；没有修改协议、Server、执行内核、活跃检测或权限规则。

### 根因

旧读取器将 mode/attachment/bridge-session 等辅助记录以及未来未知类型视为错误；主链还要求 parentUuid 必须等于上一条已显示消息的 uuid。隐藏消息和辅助记录可以参与父链接，多个 assistant 块也可共享更早的父节点，所以这两个条件均比实际记录结构严格。旧逻辑还会因为一个 sidechain 记录而排除整个混合文件。

### 实现

- **辅助记录和未知类型**：已知非消息类型不展开正文；未知记录直接忽略，未知 event/item 同样忽略。诊断只保存固定计数键，不保存未知类型的任意原值或负载。bridge-session 的账号、组织字段既不作为消息，也不成为索引属性或标题。
- **标题**：只从明确的 ai-title.aiTitle 取候选，先走现有 public_text/凭据过滤，再截到 120 码点；优先于首条公开用户消息。无候选时原回退不变。NativeService.scan 共用此投影，未增加协议字段。
- **消息**：user/assistant 保留合法 role、content 类型校验；user 的 str/list 都支持。text 输出经脱敏的正文，thinking/reasoning 等私有内容不输出，工具调用与结果只输出安全名称/通用摘要，不输出参数及原始结果。image 使用固定“[图片]”，未知块用固定“[不支持的内容块]”并计数，不猜测块内文本。
- **系统和压缩**：生成的 NativeMessagePart 仅允许 user/assistant/tool_summary，不能自造 system。压缩摘要与显式 compact_boundary 显示固定“对话已压缩”，不上传压缩摘要正文；有 message 的 system 使用安全固定“[系统消息]”，不上传原始系统指令。这些标注走已有 tool_summary，导入时沿用既有 system 映射。system 若不带 message，按辅助记录处理。
- **内部/sidechain**：isMeta/isVisibleInTranscriptOnly 不展示；压缩记录即便同时为内部记录也只显示固定提示。sidechain 按记录跳过，不参与主流身份或父链，也不压掉同文件合法主流。整个文件只有 sidechain 与辅助记录时静默排除，不能因缺少主流信封再报能力错误。
- **链**：主流 UUID 检查覆盖已知消息和辅助/隐藏记录，父节点可指向任意已经出现的主流记录，而非只认紧邻消息。重复/非法 UUID、真正缺少父节点仍拒绝。只有 isCompactSummary=true 或 system/subtype=compact_boundary 且 compactMetadata 为对象的明确边界可以引用已退休前缀；其后的普通消息不能借边界标记绕过缺失父节点检查。未知记录的负载不作链语义猜测。
- **仍严格拒绝**：主流会话身份冲突、已知消息缺失/非法 role、非法 content 或已知 text 块形状、损坏 JSON、未验证版本系列及真实断链继续返回 unsupported。CLI 系列规则、规范 cwd、终端来源和已登记 workspace 过滤未放宽。
- **源指纹**：reader profile 增加 structures-v2 标识，使旧解析结果的确认/读取快照不会冒充本次规范化结果。凭据过滤函数、私有推理过滤和分段代码未改。

structureCounts 为 Runtime 插件内部诊断：ignoredRecords、unknownRecords、unknownItems、unknownEvents、unknownBlocks、sidechainRecords、internalMessages。没有给 HTTP/线路 DTO 自加字段。

### 结构核对与隐私边界

使用内存中的 JSON 解析，仅访问类型、message 的 Python 形状、UUID/parent 关系和计数等结构字段；未使用普通正文读取器展开真实文件，未打印文件名、会话 ID、正文、账号或组织信息，未将真实正文写到临时文件、测试或仓库。

实际输出摘要：

```text
claude files 2
types: queue-operation 4, user 2, attachment 10, atis-latch 2, assistant 2, last-prompt 2
message_shapes: user/dict 2, assistant/dict 2

codex files 2
types: session_meta 2, event_msg 161, response_item 217, unknown 2, turn_context 3
event/item counts:
task_started 3, message 36, item_completed 94, reasoning 67,
custom_tool_call 38, custom_tool_call_output 38, token_count 60,
function_call 19, function_call_output 19, task_complete 3, thread_settings_applied 1

claude larger-sample records 10196
system.message shapes {}
compactMetadata/dict 4
duplicate_uuid 0, parent_not_seen 0, message_without_uuid 0
```

这是有界样本的结构核对，不是读取任意版本的兼容承诺，也不是对主代理那份 11730 条记录正文的验收。所有可执行回归均使用合成数据。

### 测试与原断言变更

新增 test_r3_history_shapes.py 共 9 项：

1. 按提供的类型数量精确构造 11730 条基础记录，版本数量也精确为 None=3959、2.1.261=3129、2.1.281=425、2.1.283=4217；含 user str/list、thinking/tool/image/text，再加入内部记录、sidechain、未知记录/块和 system 消息。断言可读、标注正确、统计计数正确；凭据、账号/组织哨兵、工具参数/结果、图片数据、压缩/内部/私有正文均不进入规范化结果或能力诊断。
2. 两种明确 compact 边界允许退休前缀；后继普通记录 parentUuid 真正缺失仍 unsupported。
3. 两种 Agent 的缺失消息/非法 role 共四项，继续 unsupported。
4. Codex 的未知 record/event/item 安全忽略，未知块使用占位，压缩使用固定提示，敏感负载不外泄。
5. 本机列表和持久索引验证 ai-title 优先、完整脱敏后截 120 码点、bridge 账号/组织信息不落索引。

调整既有断言：

- test_r3_native.py 的未知块用例改为精确断言“可读 + 固定占位 + unknownBlocks=1”，原 MUST_NOT_GUESS 不出现的断言保留；非对象块和损坏 JSON 的 unsupported 断言保留。
- test_r3_version_series.py 中“block 损坏”从合法的未知块改为已知 text 块含非字符串 text，保留原 unsupported/无正文/无泄露断言；身份、版本系列等负向样本未改。
- 给既有全 sidechain 用例增加“无能力错误诊断”断言。其终端来源与不收录断言保留。
- 其它既有断言未放宽。

定向测试真实输出：

```text
42 passed, 1 warning in 2.18s
```

### 最终验证

全部串行，未跑 Vitest、未安装依赖。TEMP/TMP/--basetemp 均位于 worktree/.tmp。全量启动后补了全 sidechain 的静默排除，因此以下以最终版本重跑结果为准。

Hub，cwd apps/hub：

```powershell
$env:TEMP='E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair4-hub-verified --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r3-repair4-hub-verified.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 16%]
........................................................................ [ 32%]
........................................................................ [ 48%]
........................................................................ [ 65%]
........................................................................ [ 81%]
........................................................................ [ 97%]
远程送达预留清理暂未完成，将重试
远程送达预留清理暂未完成，将重试
...........                                                              [100%]
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
443 passed, 4 warnings in 262.77s (0:04:22)
```

Server，cwd apps/server，TEMP/TMP/PYTHONIOENCODING 同上：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-repair4-server-final --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r3-repair4-server-final.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 31%]
........................................................................ [ 62%]
........................................................................ [ 93%]
...............                                                          [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
231 passed, 1 warning in 73.41s (0:01:13)
```

两条命令退出码均 0。git diff --check 和范围检查通过。Hub 新增 9 项；此前的依赖弃用 warning 及通用预留清理重试日志仍存在，不宣称本轮修复这些日志。未遇到 429、0xC0000142 或额度错误；没有变更或重新生成协议。

本次提交：
- `5b84af6`：原生历史结构解析、安全降级、标题投影和合成回归。
- 本回执另提交。每次提交后执行 git log -1 --format=%B 自查，无署名或生成标记；未合回 integration。
