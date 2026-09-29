---
wp: R3-P2
status: needs-decision
scope_declared: [apps/hub/**, .hqagent/handoffs/R3-P2-hub.md]
scope_touched: [apps/hub/api/app.py, apps/hub/runtime/remote/api.py, apps/hub/runtime/remote/worker.py, apps/hub/runtime/native/__init__.py, apps/hub/runtime/native/paths.py, apps/hub/runtime/native/roots.py, apps/hub/tests/test_contracts.py, apps/hub/tests/test_r3_roots.py, .hqagent/handoffs/R3-P2-hub.md]
build: pass
tests: pass
commit: 8687d159a30ee492b8e9c8ad6a6910c77711f263
open_questions: 1
---

# R3-P2 阶段回执：授权根目录基础已提交，原生本机接口待裁决

**本工作包没有完成，不能据此合入并宣称 R3 可用。** build/tests 仅表示当前已提交部分的校验结果，不能替代原生会话、线路 3、E10/E11 和项目登记的验收。

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/remote-worker`，分支 `feat/remote-worker`；开工基线 `6fb2340f91f7c32b191eb5f5cf32ca67af6c8e80`。已读 R3-P0 的冻结内容/P2 要点、R3-contract、remote-native Schema 与 api-guide 对应接口/线路/错误说明，以及方案 §8/§8.3a/§13 和 E10/E11。未再合并分支，未修改 packages/protocol、apps/server、apps/desktop 或 docs，未安装依赖。

## Q1：任务要求的本机原生接口未出现在冻结协议中

任务第 8 项要求“本机 API 按契约暴露原生会话列表和导入，供桌面前端使用”。核对当前 **0.9.0** 后，结果是：

```text
local-hub.v1.yaml
  /api/v1/remote/authorized-roots GET,PUT
local-chat.v2.yaml
  /api/v2/remote/authorized-roots GET,PUT
remote-hub.v2.yaml
  /api/v2/devices/{workerId}/native-sessions GET
  /api/v2/native-sessions/{nativeSessionId} GET
  /api/v2/native-sessions/{nativeSessionId}/messages GET
  /api/v2/native-sessions/{nativeSessionId}/imports POST
```

上面是按 paths 中 native-sessions / authorized-roots 过滤的实际结果。**两个本机 OpenAPI 没有原生列表、详情、读取或导入绑定；上面的四个原生路径属于云端服务，不是本机 Cookie 路由。** R3-contract §7 只冻结了本机授权根接口，api-guide §13 也明确自己面向远程服务器。

类型同样不能直接互换：

- `NativeSessionIndex` 可表示一个本机索引，但没有冻结的本机索引分页/列表接口及其响应绑定。
- `RemoteNativeSessionPage.items` 是 `RemoteNativeSessionView`，每个元素必须有云端 workerId / workerOnline。未配对电脑不能靠虚构 workerId 来套用它。
- `RemoteResourceQueuedReceipt` 必须有 targetWorkerId、queued_online、workerOnline=true 和传输 expiresAt，是云端在线传输回执，不是本机导入提交结果。
- `NativeClosureConfirmation` 的 description 和 R3-contract §3 规定由服务端根据显式确认生成 confirmationId / confirmedAt / requestId；尚未规定桌面直接导入时由谁签发、如何接入同一审计语义。

仓库 AGENTS.md §4 要求“三端协议边界 DTO 一律从生成物导入，不许再手写一份”；本包也明确不能修改 packages/protocol。因而没有自行添加一个未登记的本机 HTTP 接口、手写本机分页 DTO 或借用云端在线回执。已向主代理异步提出问题，当前未收到裁决。

### 建议交给 P0/主代理的具体补冻清单

以下是**提案，不是已实现或已经冻结的接口**：

| 本机路径提案 | 输入 / 输出建议 | 需明确内容 |
| --- | --- | --- |
| GET /api/v2/native-sessions | workspaceId / agentType / cursor / limit；本机分页元素复用 NativeSessionIndex | 本机分页 DTO、缺省 limit、诊断能力缺口如何暴露 |
| GET /api/v2/native-sessions/{nativeSessionId} | NativeSessionIndex | 未配对/离线本机读取是否独立可用 |
| GET /api/v2/native-sessions/{nativeSessionId}/messages | NativeReadInput 对应查询参数；NativeMessagePage | before/sourceRevision 与本机响应 no-store |
| POST /api/v2/native-sessions/{nativeSessionId}/imports | 可复用 RemoteNativeImportInput；本机成功结果使用 LocalConversationView | 同步提交 201，还是有本机命令对账的 202；本机确认签发/幂等/取消语义 |

同时明确是否增加等价 v1 Bearer 路由，以及未配对/尚未完成 2→3 栅栏的桌面导入与“不得创建需同步的 R3 对象”的关系。推荐协议线冻结后与 P3 对齐；若主代理允许 P2 定义本机绑定，也需明确上述公开响应和成功语义，避免电脑前端与 Hub 分别猜测。

此问题不阻止所有内部实施；等待裁决期间已先完成下述根目录基础。其余原生/线路实施仍未完成，不把接口缺口描述成其它内部代码已实现的替代证明。

## 当前已落盘并接线的部分

### 本机授权根目录配置

- `runtime/native/roots.py::AuthorizedRoots` 使用已有 remote_state 保存 `authorized-roots`，默认 `version=1, roots=[]`，严格复用 LocalAuthorizedRootsInput/View；Schema 限制最多 32 根。
- PUT 全量替换和 expectedVersion 在同一 SQLite 事务内比较；新增 rootId 由电脑生成，已有 rootId 必须来自当前配置、不能重复，已删除 ID 不能由调用方重新指定复活。
- 真实目录身份去重，根路径/身份/名称变化递增根版本，全局配置版本递增；原幂等仓储确保同键同内容重放，不能用相同 key 换内容。
- 配置和 `authorized-roots-catalog-pending` 意图原子保存。**这个意图尚没有接入修订 3 可靠 catalog 消费器**，不宣称手机已收到根列表。
- `api/app.py`、`runtime/remote/api.py`、`runtime/remote/worker.py` 作最小接线：同一服务挂载冻结的 v1/v2 GET/PUT authorized-roots，保留本机 Bearer / Cookie / Origin / Idempotency-Key / Cache-Control:no-store。
- 本机响应可以包含本机根路径；`catalog()` 只返回 rootId/displayName/version，不返回绝对路径。它目前仅是内部待接入投影方法。

### 内部目录选择服务（尚未暴露远程查询）

- `runtime/native/paths.py` 先检查绝对路径语法，拒绝 UNC、设备路径、驱动器相对路径、`..`、ADS、NUL、尾部点/空格，随后 resolve 真实路径并做目录包含关系检查。
- Windows 通过 CreateFileW 打开目标及已解析祖先目录，使用 GENERIC_READ、READ/WRITE 共享而不共享 DELETE，读取卷序号和文件 ID；根内目标必须同卷。实际测试证明持有期间重命名被拒。首次仅 FILE_READ_ATTRIBUTES 的实现没有阻止重命名，已由失败测试发现并修正，没有保留错误的安全声明。
- symlink/junction 按真实目标检查，越界返回 REMOTE_PATH_OUTSIDE_ROOT；`.lnk` 文件不执行、不当目录列出。
- 目录选择 token 是内存中的 256-bit 随机引用，绑定 store/rootId/rootVersion/真实目录身份，15 分钟过期；进程重启全部失效，引用上限 4096。根移除/版本改变立即使消费校验失败，不等待 catalog 更新。
- 逐层结果最多 100 个目录，默认 50；不返回普通文件或 `.lnk`；游标绑定目录快照摘要与位置，变更返回 REMOTE_DIRECTORY_CHANGED。扫描目录超过 10000 个子目录时显式限额失败，不静默截断。
- `selected()` 提供消费时再次校验和持有目录句柄的内部上下文；**尚未接入 WorkspaceService 登记事务**，因此“非 Git 登记只读”等登记验收未完成。
- `remote.directory.audited` 是本机内部审计，字段只有 requestId / operation / rootId / resultCode；不含目录 token、名称、路径或正文。没有新增协议事件类型声明或把该内部事件直接当作 Worker 公共帧。
- POSIX 使用目录 fd 和稳定身份复查；本轮在 Windows 执行，没有宣称 POSIX 竞态/真机验收完成。

### 0.9.0 夹具测试兼容

未改生产代码前跑全量，出现：

```text
FAILED tests/test_contracts.py::test_all_frozen_contract_fixtures_validate_and_round_trip
AttributeError: type object 'NativeAgentType' has no attribute 'model_validate'
1 failed, 355 passed, 4 warnings in 187.79s (0:03:07)
```

原因是 manifest 新增了枚举型夹具，测试原来假设所有生成类型都是 Pydantic model。`tests/test_contracts.py` 改为 TypeAdapter.validate_python / dump_python，与协议包自身的测试方式相同；依旧遍历完整 manifest 并逐项断言 JSON 往返完全等于原值，没有跳过枚举、放宽字段或删除断言。除此以外未修改既有测试。

## 未完成范围（必须继续，不能作为交付遗漏隐藏）

1. 修订 3 CODECS、3/2 升级栅栏与能力回退；当前 Worker 仍为之前的修订 1/2 实现。
2. 两家 Runtime 的版本化 history.list/read/adopt 和实际能力探测；未读取任何用户真实会话文件，也未创建原生 reader profile。
3. 可靠原生索引、删除证明、workspace 移除/同步关闭/设备删除清理。
4. 10 秒/1MiB 的临时查询通道、按页读取、断线/取消 buffer 清理；当前内部目录 listing 还不是远程 query 服务。
5. 导入历史的原子发布、精确原生绑定、活动证据/确认审计、跨桌面/手机/重试的原生 ID 写互斥与崩溃恢复。
6. 原生无场景对话的本机 API/显示 Mapper 与原生 resume 接线；待 Q1 统一本机公开边界后继续。
7. WorkspaceService 的授权事务/登记接线及 catalog 可靠同步；没有偷偷 init-git / mkdir / clone。
8. R3 全部新帧、E10/E11、真实 CLI 与目录登记的完整验收。

本轮没有追加迁移，也没有更改既有迁移；只使用现有 remote_state 保存根配置。未动取消后续接、D41 证据、场景执行或 Task 模型。

## 已执行测试与真实输出

新增 `tests/test_r3_roots.py` 共 15 项：根 CAS/幂等/Cookie/Bearer、缺 Origin、移除失效、目录分页与快照变化、10 种非法路径、junction/symlink 越界、目录身份替换/令牌过期、Windows deny-delete 句柄。全部使用 worktree 内 pytest 合成目录，不涉及用户真实原生会话。

所有命令串行，没有 pytest 并行 worker、没有 vitest、没有安装依赖。TEMP/TMP/basetemp 显式位于 worktree 内 `.tmp`，绕过沙箱默认临时目录 WinError 5。

### Hub 全量

cwd：`apps/hub`。

```powershell
$env:TEMP = 'E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP = $env:TEMP
$env:PYTHONIOENCODING = 'utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r3-p2-roots-full 2>&1 | Tee-Object -FilePath ../../.tmp/r3-p2-roots-full.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 19%]
........................................................................ [ 38%]
........................................................................ [ 58%]
........................................................................ [ 77%]
........................................................................ [ 97%]
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
371 passed, 4 warnings in 185.09s (0:03:05)
```

退出码 0。该全量运行期间又补了目标目录与根目录的 Windows 卷序号显式比较；随后对最后落盘代码重跑整个根目录测试模块，不能把之前启动的全量进程说成一定加载了这项末次修改：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider tests/test_r3_roots.py --basetemp ../../.tmp/r3-p2-roots-final --tb=short
```

```text
15 passed, 1 warning in 1.32s
```

退出码 0。4 个 warning 为依赖弃用提示；通用预留清理重试日志是之前 R1.5 回执已记录的未归因日志，本轮没有宣称解决它。

### 协议

cwd：worktree 根目录，TEMP/TMP/PYTHONIOENCODING 同上。

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv/Scripts') + ';' + $env:PATH
pwsh scripts/protocol/validate.ps1 -CheckGenerated 2>&1 | Tee-Object -FilePath .tmp/r3-p2-protocol.log
exit $LASTEXITCODE
```

```text
协议校验通过：426 个类型，288 个 Contract Fixture
```

退出码 0。`git diff --check` 无输出。完整日志在忽略目录 `.tmp/r3-p2-*.log`；未提交临时目录、证据数据、凭据或真实会话内容。本轮没有 0xC0000142 或额度错误。

## 提交与继续入口

- `be82fd58f991e981958b08ffea1a4b95956108f1`：枚举夹具通用校验，保留严格往返断言。
- `8687d159a30ee492b8e9c8ad6a6910c77711f263`：本机授权根配置及目录引用内部基础，含 15 项合成测试。
- 本阶段回执另提交。每次提交后均 `git log -1 --format=%B` 自查，无署名/生成标记；未合回 integration。

请主代理对 Q1 给出冻结补充或明确本机绑定裁决；随后从上述真实磁盘状态继续剩余范围，不回滚已完成基础，也不能以本回执的 tests:pass 认定 R3-P2 完成。
