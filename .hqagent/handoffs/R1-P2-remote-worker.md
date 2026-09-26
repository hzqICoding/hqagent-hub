---
wp: R1-P2
status: needs-decision
scope_declared: [apps/hub/runtime/remote/**, apps/hub/storage/remote*.py, apps/hub/storage/migrations.py, apps/hub/runtime/local_chat.py, apps/hub/runtime/tasks.py, apps/hub/storage/local_chat.py, apps/hub/api/local_chat.py, apps/hub/api/app.py, apps/hub/runtime/composition.py, apps/hub/tests/**, .hqagent/handoffs/R1-P2-remote-worker.md]
scope_touched: [apps/hub/runtime/remote/__init__.py, apps/hub/runtime/remote/security.py, apps/hub/runtime/remote/wire.py, apps/hub/runtime/remote/api.py, apps/hub/runtime/remote/link.py, apps/hub/runtime/remote/commands.py, apps/hub/runtime/remote/projection.py, apps/hub/runtime/remote/worker.py, apps/hub/storage/remote.py, apps/hub/storage/migrations.py, apps/hub/storage/local_chat.py, apps/hub/runtime/local_chat.py, apps/hub/runtime/tasks.py, apps/hub/runtime/composition.py, apps/hub/api/app.py, .hqagent/handoffs/R1-P2-remote-worker.md]
build: fail
tests: fail (7 failed)
commit: 2bc366d3aac4802fab9c9b3788e98276ac5b08af
open_questions: 1
---

# R1-P2 Worker 草稿与阻断回执

本包未完成，不能合并作为可用的远程 Worker。工作目录仅为 `E:/OtherPro/HQAgent-Hub-worktrees/remote-worker`，分支 `feat/remote-worker`，基线 `8268c5c8be7ed5411f82a9fa6c126facb05e2978`。未与真实服务端联调。

头部 commit 指实现草稿末次提交；本回执另提交，避免自引用。build=fail 表示整体交付门未通过，不表示运行过且通过编译/打包；本轮只验证了 Python 模块导入和 Hub 全量 pytest。

## 必须先裁决的范围冲突

工作包同时要求“storage/migrations.py 只追加新迁移”“原 199 个测试一个不少、全部通过”及“tests/** 只新增测试，不放宽、不删除既有断言”。基线测试 `apps/hub/tests/test_custom_scenes.py:117` 的 `test_migration_v5_preserves_v4_chat_data` 中：

```python
upgraded = Database(path)
upgraded.initialize()
upgraded_repository = LocalChatRepository(upgraded)
assert upgraded.schema_version == 5
```

`Database.initialize()` 默认参数是 `LATEST_SCHEMA_VERSION`。本包追加 migration 6 后，正确的默认初始化版本变为 6，原断言必然失败。保留默认迁移行为、追加迁移且不改既有测试，不能同时满足验收。没有修改既有测试、没有隐藏新迁移、没有为 pytest 添加生产代码分支。

**Q1（唯一待裁决项）**：是否允许仅将该 v5 专项测试的升级调用显式指定 `target_version=5`，保留 `assert upgraded.schema_version == 5` 和所有数据保留断言，并另增“v5 → 最新版本”的迁移测试？这会修改既有测试的设置语句，超出本次“只新增测试”的授权，因此未自行实施。另一种处理是由集成线先修订这个测试并提供新基线。

按任务“契约与现状矛盾就停下写 needs-decision”的要求，发现冲突后停止实现，保留草稿。其余 6 项失败是本包代码回归，不是需要产品裁决的问题，也不是环境问题；恢复工作时必须修复。

## 真实命令与结果

工作目录为 worktree 根：

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TEMP=(Resolve-Path .tmp).Path
$env:TMP=$env:TEMP
.venv/Scripts/python.exe -B -c "import sys; sys.path.insert(0, 'apps/hub'); from runtime.remote.worker import RemoteWorker; from runtime.remote.wire import WIRE_REVISION; print('remote imports OK; wireRevision =', WIRE_REVISION)"
```

```text
remote imports OK; wireRevision = 1
```

工作目录为 `apps/hub`：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/pytest-baseline --tb=short
```

```text
FAILED tests/test_cancel_approval_lifecycle.py::test_cancel_invalidates_pending_and_late_approval_cannot_reach_adapter
FAILED tests/test_cancel_approval_lifecycle.py::test_cancel_wins_race_before_approval_dispatch
FAILED tests/test_cancel_approval_lifecycle.py::test_approve_first_then_cancel_serializes_without_replay_or_running_overwrite
FAILED tests/test_cancel_approval_lifecycle.py::test_late_cancel_preserves_existing_terminal_task[succeeded]
FAILED tests/test_cancel_approval_lifecycle.py::test_late_cancel_preserves_existing_terminal_task[failed]
FAILED tests/test_cancel_approval_lifecycle.py::test_late_cancel_preserves_existing_terminal_task[cancelled]
FAILED tests/test_custom_scenes.py::test_migration_v5_preserves_v4_chat_data
7 failed, 192 passed, 4 warnings in 25.72s
```

关键失败输出：

```text
runtime\tasks.py:1311: in _task_spec
    value = self.state.get(f"task_spec:{task_id}")
E   AttributeError: 'TaskService' object has no attribute 'state'

tests\test_custom_scenes.py:130: in test_migration_v5_preserves_v4_chat_data
    assert upgraded.schema_version == 5
E   assert 6 == 5
```

取消生命周期测试使用 `object.__new__(TaskService)` 构建最小测试实例，没有 `state`。新增证据采集无条件读取了此属性，破坏了原测试能够调用的取消路径。不能修改测试来掩盖这一回归。

原 199 项全部被执行，无 xdist、无跳过、无删减断言。TEMP、TMP、--basetemp 均指向 worktree 内已有 gitignore 规则覆盖的 `.tmp`；未使用默认沙箱临时目录。4 个 warning 为 Starlette/httpx 和 websockets 的弃用提示。本轮没有遇到 0xC0000142，没有安装依赖或访问外网。

`git diff --check` 在草稿提交前退出 0，无输出。前端 typecheck、test 和 `pwsh scripts/protocol/validate.ps1 -CheckGenerated` **未运行**：发现阻断后停工，不引用前序工作包的结果冒充本轮验证。

## 草稿模块与表结构

迁移 1–5 未修改；追加 migration 6：

| 表 | 草稿用途 |
| --- | --- |
| remote_state | identity（store/epoch/ack/高水位/覆盖游标/见证版本）、link 操作世代与安全重试意图、本机策略 |
| remote_inbox | worker+command 唯一键、规范化 hash、原命令、接单回执、run 引用、执行前结构化观测 |
| remote_slots | worker+conversation+sequence 唯一顺序槽，submit/skip/tombstone |
| remote_conversations | 对话绑定的 worker/store、固定目标和已消费序号 |
| remote_outbox | store+seq、不可变 frame、eventId 和 hash |
| remote_operations | 本机配对/取消/解绑的幂等键与操作世代 |
| remote_projections | Run/消息/审批/catalog 投影 hash |

LocalConversation.authority 存在原 payload_json 内，旧数据读 Mapper 缺省为 local，远程新建记录明确写 remote。没有把旧对话批量转换。

## 契约规则的草稿落点（不是验收通过声明）

| 规则 | 文件与当前实现意图 |
| --- | --- |
| D43 本机四个操作、沿用鉴权 | runtime/remote/api.py；api/app.py 沿用 v1 中间件 |
| link 持久化、统一 Mapper、提交后事件 | storage/remote.py 的 set_view/view 与既有 EventStore.after_commit |
| origin 解析、规范化、开发例外 | runtime/remote/security.py；仅本机 HQAGENT_REMOTE_DEVELOPMENT=1 开启例外 |
| 设备 secret | security.py 的 CredentialVault，32 随机字节、Windows DPAPI、解绑删除 |
| 配对世代与迟到隔离 | runtime/remote/link.py |
| 本机解绑、撤销未确认 | link.py，unpaired.lastErrorCode=REMOTE_AUTH_REQUIRED，不调用 owner 撤销接口 |
| hello/心跳/退避/epoch | runtime/remote/worker.py 与 wire.py |
| 生成 DTO 校验 | wire.py、api.py、link.py；wireRevision 从生成模型 Literal[1] 取值，包版本从生成 PROTOCOL_VERSION 导入 |
| Inbox/slot/LocalRun/receipt/Outbox 同事务 | runtime/remote/commands.py、storage/remote.py、storage/local_chat.py 的 transaction 参数 |
| 内核消费入口 | runtime/local_chat.py 的 consume_remote_control / wake_remote_queue |
| authority 检查 | storage/local_chat.py、runtime/local_chat.py、api/app.py 的 Task/Session 写入口 |
| 结构化控制证据 | runtime/tasks.py 的内部读接口与采集点；remote/commands.py 的 control_result |
| 当前审批与策略 | remote/commands.py 的 guard；runtime/tasks.py 在 ApprovalService 锁内调用 current_guard |
| 上行事件/ack/omitted | storage/remote.py、runtime/remote/projection.py、worker.py |
| 有界 Workspace/Scene catalog | runtime/remote/projection.py，只取已登记列表，不上传角色模型配置 |

## 对既有内核的改动与边界

- storage/local_chat.py：增加持久 authority 的读/检查方法；enqueue 接受调用者事务，复用原插入逻辑。未改 Task、Node、Session 模型。
- runtime/local_chat.py：原 control 前加本机 authority 检查；内部消费入口复用原控制方法，仍由原 supervisor/_execute 创建 Task；未迁移执行内核。
- runtime/tasks.py：记录取消结果、节点边界暂停和恢复证据；提供只返回结构化标记的内部接口；给审批响应增加锁内检查回调。这部分已有 6 项回归，尚不能称为符合最小改动验收。
- api/app.py：装配远程服务及生命周期，原中间件补 PATCH/DELETE CORS 方法，Task/Session 写入口核对持久对话归属。
- runtime/composition.py：增加远程服务工厂，复用现有 database/events/local_chat/ports。
- api/local_chat.py 未改；没有改 packages/protocol、apps/desktop、apps/server、docs 或根共享文件。

## 设计取舍与未完成事项

1. secret 默认使用现有 HubPaths.root 下 remote/device.credential，即 Windows 默认 `%LOCALAPPDATA%\HQAgent-Hub\remote\`；数据目录覆盖沿用既有 HubPaths 配置。Windows DPAPI 为当前用户保护；非 Windows 为目录 0700、文件 0600，**未做非 Windows 实机验证**。
2. 握手禁止重定向；HTTP 配对关闭 follow_redirects 和环境代理，WSS 使用专属静默 logger 防止 DEBUG 输出请求头。实际捕获日志脱敏测试尚未编写。
3. 外置 store.witness 在提交前写入，试图检测 hub.db 回滚并冻结；见证文件本身与数据库一起回滚、全目录恢复等情形尚需明确运营恢复入口和故障测试，不能声称解决所有恢复场景。
4. 新远程事件复用本机 events.seq，Outbox 保留原 epoch/hash。当前 cover_private 对未投影的原生事件统一作无内容覆盖，**尚未证明不会覆盖远程关键事件语义**；需在继续工作时审查并修正。
5. 配对取消/解绑的幂等记录与凭据删除失败之间尚有重放窗口；删除失败不能在重试时被误报成功，需补事务/操作状态和故障测试。
6. 控制证据采集尚未覆盖所有暂停/恢复分支；当前 running 分支的 pauseRequested 可能留下旧证据，必须修正后再验收。取消拒绝、残留 PID 和恢复标记也需要真实 TaskService 用例验证。
7. 审批实际消费成功标记在现有 ApprovalCoordinator 中是 `deliveryStatus=consumed`；草稿桥接错误地检查了 `delivered`，尚未修复。审批消费不明时保持 accepted/unconfirmed 的路径也需补齐，不能一概记 failed。
8. 重连后 executing/admitted 控制命令的恢复和不重复放行路径、retry 引用与顺序边界、撤回已接单未启动情形尚未完成故障验证。当前可见 Run 的撤回统一拒绝，不能据此声称全部撤回矩阵已实现。
9. 所有本机写入口的 authority 防绕过仍需系统验证，现有 Task parent/Session/Approval 等引用链不能只靠 UI 隐藏。
10. **尚未新增假服务端测试，也未完成任何用户要求的新验收场景**。所有收发帧/本机响应的生成 DTO 校验只有实现调用点，没有完整集成测试证据。未执行前端及协议验证。

这些都是实现未完成项，不能以 Q1 代替解释；Q1 裁决后仍需继续开发、修复、补测试和全量验收，不能直接将 status 改成 done。

## P1 与电脑端前端接线提示

目前只有草稿，请勿作为联调就绪版本。未与真实服务端联调。

- P1 使用已冻结 pairing-requests 和 /ws/v2/worker；设备 Bearer 没有 owner 撤销权限。本机解绑仅保证本机清理，服务端撤销未确认。
- 四个本机 remote API 位于 v1；v2 浏览器 Cookie 不授予 v1 权限。前端需要复用已有桌面鉴权，不从本机 JSON 获取 Hub Token 或设备 secret。
- lastConnectedAt=null 表示尚未成功握手；frozen+online 不允许提交执行命令。remote 对话解绑后不降级。
- 生成物没有独立导出的 WIRE_REVISION 名称，草稿从生成 RemoteWorkerHello.wire_revision 的 Literal 常量读取 1；未手写兼容字段，未改生成物。

## 草稿提交

```text
7222317 Add draft remote persistence and conversation authority boundaries
2bc366d Add draft worker pairing transport and execution bridge
```

两次提交后均运行 `git log -1 --format=%B`，输出仅上列主题，无署名或 Co-Authored-By。没有合并其它分支、没有推送或部署。
