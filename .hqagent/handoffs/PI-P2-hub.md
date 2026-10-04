---
wp: PI-P2
status: done
scope_declared: [apps/hub/**, .hqagent/handoffs/PI-P2-hub.md]
scope_touched: [".hqagent/handoffs/PI-P2-hub.md", "apps/hub/adapters/builtins.py", "apps/hub/adapters/manager.py", "apps/hub/adapters/pi_adapter.py", "apps/hub/adapters/pi_guard.py", "apps/hub/adapters/pi_rpc.py", "apps/hub/adapters/process.py", "apps/hub/adapters/resources/pi/hub-guard.mjs", "apps/hub/api/app.py", "apps/hub/api/envelopes.py", "apps/hub/api/pi_projection.py", "apps/hub/conftest.py", "apps/hub/core/security.py", "apps/hub/orchestrator/role_resolver.py", "apps/hub/packaging/windows/hqagent-core.spec", "apps/hub/runtime/attachments/capabilities.py", "apps/hub/runtime/attachments/service.py", "apps/hub/runtime/attachments/verification.py", "apps/hub/runtime/attachments/verification_jobs.py", "apps/hub/runtime/attachments/verification_target.py", "apps/hub/runtime/cli.py", "apps/hub/runtime/composition.py", "apps/hub/runtime/conversation_deletion.py", "apps/hub/runtime/execution_selection.py", "apps/hub/runtime/instance.py", "apps/hub/runtime/native/api.py", "apps/hub/runtime/native/service.py", "apps/hub/runtime/pi_visibility.py", "apps/hub/runtime/remote/busy.py", "apps/hub/runtime/remote/commands.py", "apps/hub/runtime/remote/delivery.py", "apps/hub/runtime/remote/projection.py", "apps/hub/runtime/remote/sync.py", "apps/hub/runtime/remote/wire.py", "apps/hub/runtime/remote/worker.py", "apps/hub/runtime/services.py", "apps/hub/storage/local_chat.py", "apps/hub/storage/team_profiles.py", "apps/hub/tests/fixtures/pi/cli.mjs", "apps/hub/tests/remote_support.py", "apps/hub/tests/test_pi_adapter.py", "apps/hub/tests/test_pi_primary_only.py", "apps/hub/tests/test_pi_projection_wire.py", "apps/hub/tests/test_r15_joint_server.py", "apps/hub/tests/test_r15_recovery.py", "apps/hub/tests/test_r16_attachments.py", "apps/hub/tests/test_r3_wire.py", "apps/hub/tests/test_remote_worker.py"]
build: pass
tests: pass
commit: 6494e32741163c756f804e4ed0dc7c1fdfa66de2
open_questions: 0
---

# PI-P2 Hub 第一期实施回执

## 交付状态及续作基线

**返修 1 已按主代理裁决完成，Q1 关闭，状态 done。** 本期禁止 PI 后备，仅允许显式主选 PI；主选不可用时不回退到其他 Runtime。以下 Q1 段落保留最初问题与复现依据，当前处理及最终验证见文末「返修 1」。没有新增协议字段或修改服务端。

本轮从 `9a8b259` 和上一轮未提交的 38 项工作继续；先 `git status` / `git diff --stat`，命名 stash 保护已落盘成果，`git merge integration/phase1` 后原样恢复，未发生冲突。合入的服务端/前端/协议改动均来自 integration，本轮自行修改只在 scope_touched 内。

离线执行用户指定的安装命令：

```text
.venv/Scripts/python.exe -m pip install --no-index --no-build-isolation --force-reinstall --no-deps ./packages/protocol
Successfully installed hqagent-protocol-0.2.0
```

Python distribution 的历史包版本仍是 0.2.0；实际生成常量已另行核实：`PROTOCOL_VERSION=0.11.1`，线路为 5。0.11.1 的浏览器审批补冻由已合入 P1 实现；Hub 不改审批可靠事实的 wireRevision/hash/seq。

## Q1（历史问题，返修 1 已关闭）：PI 后备候选关联没有可传递的冻结字段

依据 PI-contract §1，PI 场景包括后备链可能选择 PI 的场景，旧客户端不得见到这类资源；§3 的 roleImageCapabilities 又必须绑定实际执行实例/模型。

使用合成 AgentView、真实 RoleResolver、真实 Hub catalog Mapper 和已合入的 P1 `ClientProjection.pi_scene`，没有运行模型，得到：

```json
{"configuredPrimary":"local.pi.default","workerPiScene":true,"actualRoleBindings":[{"roleId":"analyst","agentId":"local.codex.default","agentType":"codex"}],"serverPiScene":false,"sceneFields":["name","readOnly","roleImageCapabilities","sceneId","version"]}
```

构造条件：场景明确配置 PI，PI 实例 offline，正常实例 ready；现有解析器按能力回退到正常实例。Hub 保留配置归属，正确认为它与 PI 关联，但 `RemoteV5SceneSummary` 只携带实际角色图片绑定。全局 runtimes 即使列出 PI 也没有该场景与 PI 候选之间的关联。服务端因此会把该场景当作非 PI。

同样的问题也涉及先前正常场景在不改变 sceneId 的情况下引入 PI 后备候选。不能把实际正常实例谎报为 PI，不能给同一角色制造假图片能力项，也不能按设备一刀切隐藏所有场景。

建议协议明确场景级所需客户端能力或候选 Runtime 关联，由 P1 用它持久保留 PI 归属；如协议线选择其它既有字段表达，请给出冻结语义。**本轮未自行采取该建议。** 原交付时该边界待裁决；现主代理已决定本期禁用 PI 后备，并通过主选固定及离线绑定保留闭环，见返修 1。

## 模块与结构

| 职责 | 文件/实现 |
| --- | --- |
| PI Runtime | `adapters/pi_adapter.py`、`pi_rpc.py`；注册于 builtins，npm shim 解析复用 process.py |
| 安全检查 | `adapters/pi_guard.py`；固定资源 `adapters/resources/pi/hub-guard.mjs`，独立 hash 核验 |
| 装配 | `runtime/composition.py` 配置用户数据目录、敏感目录、当前策略、审批失效、PI 入场门禁 |
| 图片 | attachments 的 target / capabilities / verification / jobs / service 共用实例、版本、模型和配置指纹 |
| 本机能力投影 | `runtime/pi_visibility.py`、`api/pi_projection.py`、envelopes / app / core.security |
| 线路 5 | remote 的 wire / worker / sync / busy / delivery / commands / projection |
| 原生读取一期声明 | native API 使用 RuntimeNativeAgentType，新公共 Mapper 使用 RuntimeNativeSessionIndex；PI 明确 reader_not_implemented |
| 打包/CLI | onedir spec 带入守卫资源；本机 CLI 请求统一携带 pi-v1 |

build=pass 表示 Python 模块导入、假进程守卫资源加载与测试通过；不表示已重打 PyInstaller 包。

没有新增迁移或修改已有迁移。复用 remote_state 保存 `pi-deferred` 补传意图和仅含 SHA-256 标识的 `pi-resource-tombstones`，防止删除后的历史资源从旧客户端事件重现。

PI 文件在 Hub 用户数据根下：`pi/sessions/<随机目录>/` 是 PI 自身管理的会话；`pi/bindings/<vendorId摘要>.json` 保存精确 vendor ID、文件路径、文件身份、workspace 与 active 事实；`pi/writers/<vendorId摘要>.lock` 用现有跨进程锁。绑定文件采用现有 atomic_write/敏感权限规则。文件路径不进入远程帧。正常会话保留供精确续接；发现用临时目录和五 probe 用临时会话在确证停止后清理。

`runtime/instance.py` 只加可选“不删除锁文件”模式，避免 POSIX 原生 ID 锁释放时 unlink 产生双 inode 竞争；Hub 原有单实例默认行为不变。

## RPC 与守卫

- 只支持已核对隔离参数的 PI CLI 1.0.1。根据 npm package metadata 解析 Node 真入口，不运行 shell/shim。指定 `--mode rpc --no-extensions -e <安装内固定扩展> --session-dir <管理目录>`，任务模型明确传 provider/model。
- 清除 Node 预加载及 shell 启动脚本环境入口；Hub 不读取 `~/.pi/agent/` 密钥文件。get_available_models/get_state 只经 PI 自身 RPC 查询元数据，无 prompt。
- get_state 校验空闲及模型，prompt 前握手；每次 switch_session 后再次握手、核对 vendor ID / 路径 / 文件身份 / 实际模型。不能 latest，不能静默新建。未解决的 active 绑定在重启后仍拒绝续接。
- PI 1.0.1 的 session_start 在 stdin reader 安装前触发，若直接等待 editor 应答会死锁。守卫让握手异步进行并先保持工具关闭，适配器等握手成功才 prompt。
- 核验八个 builtin 工具（含 powershell）的来源及工具清单，拒绝 shellPath/shellCommandPrefix 覆盖。只读只启用 read/grep/find/ls；动态工具变化、安装扩展可写、未知版本均拒绝。
- 内部消息使用生成 DTO，参数原始 UTF-8 SHA-256、64KiB 限额、重复 key/非 object/非有限数值拒绝。绑定进程所持 session/node/policy/inventory/期限。扩展和适配器各自复核；嵌套调用、参数改变、迟到批准不能复用许可。
- PathGuard 保持精确附件只读特例；敏感目录和守卫/安装目录额外拒绝。复杂变量/管道/重定向、无法证明安全的包装命令保守拒绝。本期仅支持明确列举的简单 shell 语法；这不是 OS 沙箱，不能宣称任意进程内代码隔离。
- shell 走既有危险动作审批；远程是否可批仍由 Worker 当前策略和既有高风险禁批决定。审批超时通过现有协调器使 pending 失效；错误/EOF/超时默认阻止。
- `agent_end`、abort response 不算停止，等对应 `agent_settled`。取消超时用现有进程树终止；保留 outcome/orphanProcessIds 等 D41 结构化证据，不改内核取消、暂停、重试语义。
- prompt 请求包含 AgentResult schema；最终仅从 settled 后的 get_last_assistant_text 取结果、按已有过滤器脱敏。PI 私有事件、原始工具参数和 stderr 不向用户/云端原样透传。

## 模型和图片

modelId 在第一个斜线分割，精确匹配当前 get_available_models。Hub 未自动安装、订阅或改用户模型配置；按用户约定真实联调只使用 1aicode 的 DeepSeek 模型。未核实 thinking 选项，因此模型 efforts 返回空，任务显式要求未验证推理等级时拒绝。

默认模型先解析实际 provider/model，纳入 targetRevision/configuration 指纹；显式模型与默认模型、实例、CLI 版本、transport 不交叉复用验证记录。PI RPC `prompt.images` 使用已校验文件的 base64 和嗅探 MIME；普通附件继续使用精确只读路径。`PI_IMAGE_TARGET` 在执行前复核，模型或版本变化会令旧通过记录失效。

沿用 0.10.1 的付费确认、new/resume/mixed-five/error/cancel 五 probe、取消和清理；没有云端付费验证入口。修订 5 catalog 仅在 PI 能力具有精确实例绑定时上报它，无实例/多候选不制造虚构绑定。runtimes 给出 guard 与 `nativeSessionsSupported=false`。

## 线路与 HTTP / WS

- 支持严格生成 codec 1–5；4→5 沿用旧命令终结、两端连续 ACK/应用及持久栅栏，约 30 秒周期探测。unconfirmed 仍是控制终态，不据此宣称进程停止。原 Outbox 不改版本/hash/epoch。
- 升级前 PI 场景/会话/消息/审批/索引不分配旧线路事件；记补传意图。无法隔离 PI 的完整 busy 集合延迟，绝不删掉 PI 后宣称完整。升级捕获水位并完整补传。
- 收件与 Task 启动两层门禁；后者也从既有 `local-profile:<runId>` 绑定反查远程命令，覆盖 LocalRun 尚未写回 task_id 的窗口。
- v1/v2 同一投影：无 pi-v1 时隐藏 PI 资源及新字段，直接寻址返回 NOT_FOUND；已删除标识仍受历史门禁。保留既有鉴权/Origin/Idempotency-Key。
- 事件、列表/原生/验证矩阵游标绑定能力；能力变化要求重取快照。隐藏事件仍推进扫描位置。任务/消息/审批按可信持久绑定关联，不靠 ID 字符串包含 pi。
- **主代理裁决的 WS ticket Q1 已落实**：`/api/v1/auth/ws-ticket` 签发时绑定一次性票据记录中的 features/owner，WS replay/live 使用票据能力；握手另带 feature 头不能提升或降低已签发能力。原 TTL/一次性消费不变。这里的 Q1 与本回执新提出的 catalog Q1 是两件事。

## 实联测发现并修复的接线问题

1. 无 PI 实例时仍发布无 agentId 的 PI nativeImageCapabilities，真实 P1 在 NativeEvents.catalog 的绑定校验返回 REMOTE_SYNC_CONFLICT。改为不发布无法核对的实例能力，保留本机 unknown。未放宽 P1 校验。
2. 修改场景 Agent/model 后，sync metadata 的 sceneVersion 变化，但对应对话 version 未变化；补传会成为同版本不同元数据。`storage/local_chat.py::save_scene` 现在在同一事务推进关联 scenario 对话的 version/updatedAt，原生对话不变、既有运行快照不变，触发现有增量同步。此项是使配置 PI 后同步可用所需的最小存储修复。

## 测试与断言改动

新增假 PI Node RPC 进程，加载真实 hub-guard 资源但绝不连接模型/读取用户 PI 配置。覆盖：启动参数、guard 缺失/超时/错误握手、未知版本拒绝、精确续接与模型恢复不匹配、唯一 writer/崩溃 active 绑定、取消 settled/强杀证据、路径/通配符/管道/只读/安装资源/动态工具、审批批准/拒绝/失效/当前策略变化、参数篡改与嵌套调用、附件精确只读、图片编码与五 probe 记录/清理/版本和默认模型失效。

新增本机 HTTP 资源与事件投影、ticket 能力锁定、能力切换 410、旧修订补传意图、完整 busy 延迟；真实 P1 TLS 服务端 + Worker 测试覆盖 4→5 在途阻塞、完成后升级、原结果保持 4、PI catalog 在 5 正常接收与场景 CAS 版本推进。

已有断言只作协商版本相应更新，业务断言不放宽：

- test_remote_worker 的“无共同修订” peer 从 `[5]` 改为 `[6]`（5 现已支持）；仍断言冻结/停止重连风暴。
- test_r15_recovery 首选协商 `[4,1]`→`[5,1]`、`[4,2,1]`→`[5,2,1]`；原修订1执行/不上传同步/升级栅栏断言原样保留。
- test_r3_wire 首选 `[4,2]`→`[5,2]`；原 native 延迟与升3补传断言原样保留。
- test_r15_joint_server 的兼容握手条件按当前最高 Worker codec 判断；原真实修订2/3测试继续显式限制服务端支持集合。
- test_r16_attachments 的3→4专项把服务端 codec 显式限制≤4；仍严格要求升级到4及所有补传段为4。新增专项另测4→5。
- tests/remote_support 仅登记5生成codec；conftest 默认将 PI 可执行入口指到临时不存在路径，只有假 RPC 测试显式覆盖，避免测试碰用户真实 CLI。

Windows 沙箱 taskkill 对合成进程不可依赖：取消分支单测只对无子进程的自有假 Node 进程注入 kill/wait；生产仍使用原进程树终止。真实 PI 子进程树停止与 orphan 行为不能由此声称已经真机验证。

## 串行验证输出

TEMP、TMP、pytest --basetemp 全部设在 worktree 忽略目录 `.tmp`，规避默认临时目录 WinError 5。不启并行 pytest，不跑 vitest，不调用模型。

首轮 Hub：`4 failed, 746 passed, 9 skipped, 4 warnings in 328.09s`，四项均为上述旧版本前提；修正后相关专项：`58 passed, 1 warning in 61.76s`。中间完整 Hub：`759 passed, 9 skipped, 4 warnings in 320.70s`。补充启动前门禁检查后最终输出另附如下。

实际最终命令（PowerShell；分别在 apps/hub、apps/server 下执行；未并行）：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/pi-hub-delivery --tb=short
# server 另用 --basetemp ../../.tmp/pi-server-final
```

Hub 最终真实输出：

```text
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 28%]
........................................................................ [ 37%]
...........s................ssssssss.................................... [ 46%]
........................................................................ [ 56%]
........................................................................ [ 65%]
........................................................................ [ 75%]
........................................................................ [ 84%]
........................................................................ [ 93%]
远程送达预留清理暂未完成，将重试
远程送达预留清理暂未完成，将重试
................................................                         [100%]
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
759 passed, 9 skipped, 4 warnings in 320.48s (0:05:20)
```

Server 真实输出（与 Hub 串行；本轮没有自行修改 apps/server）：

```text
........................................................................ [ 20%]
........................................................................ [ 41%]
........................................................................ [ 62%]
........................................................................ [ 83%]
.......................................................                  [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
343 passed, 1 warning in 88.61s (0:01:28)
```

附加冻结检查（cwd 为 worktree 根、PATH 指向 .venv/Scripts）：

```text
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：608 个类型，492 个 Contract Fixture
```

9 项 skipped 均为原有 POSIX 专属测试在 Windows 下跳过；没有新增 skip/xfail。日志中两条“远程送达预留清理暂未完成，将重试”来自已有重试路径，最终全部断言通过。原始日志留在忽略目录 `.tmp/pi-hub-delivery.txt`、`.tmp/pi-server-final.txt`、`.tmp/pi-protocol-final.txt`，此处逐字摘录。`git diff --check` 通过。


## 需主代理实测（未在本轮执行）

1. 真实 PI 1.0.1 + 1aicode DeepSeek：启动前 guard ready；只读分析、受审批修改；用户/项目扩展确未运行；复杂 shell 被拒不能误当功能成功。
2. 本机/手机新建与精确续接，核对 vendor sessionId/file 一致；禁止模型恢复成不同选择器后拿旧图片结论放行。
3. abort→agent_settled，长工具执行强杀、进程树残留及 Hub 崩溃后的恢复核对；不得仅凭 abort 应答认定停止。
4. 对实际可用且支持图片的精确 DeepSeek 选择器，从运行中 Hub 用现有 CLI `agents verify-image --agent <实例ID> --model <精确provider/model> --acknowledge-model-usage` 显式执行五 probe；先核对本机可用清单，未通过前 catalog 保持 unknown。
5. 真实附件文件可读、目录/邻居文件/写入被拒；真实图片 new/resume/mixed-five 识别；验证作业取消与临时会话文件清理。
6. 打包版 PI guard 路径、资源 hash、npm Node 入口、Linux/macOS 路径及跨进程锁；本轮只更新 spec，未重新生成安装包或跑三平台 CI。
7. 已按“PI 仅主选”的裁决完成旧客户端/旧线路隔离，以及同一设备混合 PI/非 PI 审批的真 P1 / Worker 自动化投影测试（见返修 1）；真实 PI CLI 与前端端到端仍由主代理联调。未来若支持 PI 后备链，另由 W0 增加冻结表达。

未读取用户 PI 密钥文件或真实会话正文；没有真实 PI/DeepSeek 模型调用，没有把测试失败替换成 skip/xfail。PI 原生树读取/导入属于第二期，当前明确 unsupported，不虚报 readable。

## 提交

- `6adc84c`：受控 PI RPC、固定守卫、模型和图片验证绑定、假进程测试及打包资源。
- `b1bb370`：线路5协商与门禁、本机能力投影、WS ticket绑定、真实P1联调测试及旧协商前提更新。
- `23656cc`：场景变更在同一事务推进对应对话元数据CAS版本。
- 本回执另作 docs 提交；头部 commit 指最终实施提交。

每次提交后执行 `git log -1 --format=%B` 自查，无署名。未合并回 integration、未推送、未部署。初次交付未冒称完成；Q1 现已在返修 1 关闭。


## 返修 1：PI 仅主选，Q1 关闭

### 裁决落实与最小改动

- `runtime/execution_selection.py` 集中定义 PI 后备校验和候选筛选。PI 身份来自实际 AgentView/AgentCandidate.adapter_id 或已登记 Runtime 实例映射，不看 ID 字符串；用 opaque-runtime 合成 ID 验证这一点。
- `orchestrator/role_resolver.py` 只在现有解析入口调用该共用筛选，后续六级解析和非 PI 行为不变。显式 PI 主选只保留这个精确实例；不可用、被排除或能力不足就返回 ResolutionGap，不能回退到另一个 Runtime。没有 PI 主选时排除 PI 自动匹配/后备/临时手动后备。
- 固定主选是关闭旧 Q1 必需的一环：只禁止列表里的 PI fallback，仍无法防止“主选 PI 离线→自动改用正常 Runtime→catalog 丢失 PI 归属”。现在该情况不执行，catalog 仍保留 PI 目标且图片能力 unknown，给出已有解析错误原因。
- `runtime/attachments/capabilities.py` 的预览走同一 RoleResolver；离线主选保留准确 agentId/agentType/transport/modelId，不谎报为其它 Runtime，不宣称图片 supported。
- `api/pi_projection.py` 在已鉴权的 JSON 写请求进入 DTO/业务前递归检查结构字段 fallbackAgentIds，命中 PI 返回 `422 VALIDATION_FAILED`、`PI 暂不支持作为后备 Agent`。不会解析 instructions 等正文字符串。覆盖场景保存、模板应用形状、角色模板创建、导入 JSON 等同一入口；旧 DTO 本身也不允许为场景/模板私加后备字段。
- `runtime/services.py` + `storage/team_profiles.py` 在服务及其仓储写入处共享校验，防止绕开 HTTP 的配置保存/导入。首次默认团队生成也去掉 PI 后备候选，不影响正常 Agent 的后备。
- 实際已冻结路由中，场景/角色模板位于本机 v2（支持本机 Bearer 与 Cookie），v1 角色主选/后备配置位于 team-profiles。没有新增不存在的 v1 scenes 路由，也没有新增导入路由。

### 已有数据的处理

现有合法数据里，后备列表位于 TeamProfile.roleBindings；LocalSceneView/角色模板 DTO 从未包含后备链字段。已有团队配置若含 PI 后备，读取时保留原配置，解析返回现有 `ResolvedTeamView.hasGaps=true` 与 `gaps[].reason=PI 暂不支持作为后备 Agent`；同一运行解析器也返回 Gap，不能启动该角色。测试直接写入旧配置后核对原始 payload_json 逐字节不变，没有静默删改用户设置。没有自造 runnable/status 协议字段。

以后如果开放 PI 后备链，必须由 W0 冻结候选关联字段后另行实施，本轮不扩协议。Q1 已关闭，没有新增 needs-decision。

### 验证

新增 `tests/test_pi_primary_only.py`：

- PI 显式后备拒绝；自动匹配不能选 PI；PI 主选可选、离线主选不回退。
- 服务保存与直接仓储保存拒绝；默认团队不生成 PI 后备；旧配置 hasGaps 且原始数据不改。
- 本机 Bearer 的 v1 team-profiles、v2 场景保存/创建/角色模板，以及真实本机 Cookie 会话同样返回明确中文错误，场景版本不变。
- 离线 PI 主选的 catalog 绑定仍是 PI，P1 的真实 `ClientProjection.pi_scene` 能识别；本机旧客户端隐藏，执行失败且没有启动正常 Agent。
- 真 P1 TLS 应用 + 真实 Worker + 合成 Agent 流：同一设备两个对话分别主选 PI 与正常 Agent；旧 catalog 不含 PI 场景、正常场景仍在，新 catalog 有准确 PI 绑定，并通过生成 DTO 校验。
- 同一设备审批 pending 的实时可靠上传与浏览器投影：旧客户端恰好一个非 PI 兼容事件，新客户端恰好两个（含 RemoteBrowserPiApprovalEvent）；无隐藏 PI 的 ID 或替代刷新通知。分别覆盖 approved/rejected/expired 的后续投影。

混合审批测试先固定合成运行的 waiting_approval 状态再观察审批增量，以免把契约允许的 run-state 快照对账混进审批断言。pending 由假 Adapter 的真实审批事件和 Hub 协调器产生，终态通过既有 ApprovalRepository 写入，专测投影；不宣称执行了真实模型或完整的人为审批 UI。上一轮的旧线延迟、4→5 栅栏、HTTP/WS ticket 隔离测试继续全量运行，没有放宽断言。

实际串行命令与输出（TEMP/TMP 均为 worktree 内 `.tmp`，不开并行、不跑 vitest）：

```powershell
# cwd: apps/hub
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/pi-primary-hub --tb=short
```

```text
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
........................................................................ [ 36%]
......................s................ssssssss......................... [ 46%]
........................................................................ [ 55%]
........................................................................ [ 64%]
........................................................................ [ 73%]
........................................................................ [ 83%]
........................................................................ [ 92%]
远程送达预留清理暂未完成，将重试
...........................................................              [100%]
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
770 passed, 9 skipped, 4 warnings in 374.46s (0:06:14)
```

```powershell
# cwd: apps/server（Hub 全量结束后才启动）
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/pi-primary-server --tb=short
```

```text
........................................................................ [ 20%]
........................................................................ [ 41%]
........................................................................ [ 62%]
........................................................................ [ 83%]
.......................................................                  [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
343 passed, 1 warning in 95.50s (0:01:35)
```

Hub 比上一轮增加 11 项测试（759→770），9 项仍为原有 POSIX 专属 skip；未改任何既有测试断言，没有新增 skip/xfail。原始日志在忽略目录 `.tmp/pi-primary-hub.txt`、`.tmp/pi-primary-server.txt`。`git diff --check` 通过，未遇 429/403、0xC0000142 或额度错误。


### 提交与边界

- `6494e32`：PI 仅主选的统一校验/解析、离线能力绑定保留、默认团队后备排除及 11 项回归（含真实 P1 混合审批投影）。
- 本回执另作 docs 提交。每次提交后均执行 `git log -1 --format=%B` 自查，无署名。

未改 packages/protocol、apps/server、apps/desktop，也未修改 hub-0101 的 stdin 工作；没有合并回 integration、推送或部署。没有调用模型，真实 PI + 1aicode DeepSeek 的 CLI/图片/进程树验收仍由主代理执行。
