---
wp: R1-P0
status: needs-decision
scope_declared: [packages/protocol/**, scripts/protocol/**, .hqagent/**]
scope_touched: [.hqagent/INTERFACES.md, .hqagent/handoffs/R1-P0-remote-protocol.md]
build: pass
tests: pass
commit: 302ae4403c911d27e883aaa615738eba93542d27
open_questions: 2
---

# R1-P0 远程协议冻结前核对

## 提交定位

头部commit为首次完整阻断证据提交。随后仅补录该SHA；它不是协议冻结提交，0.6.0仍未生成。

## 结论

**未冻结，协议仍为0.5.0。未新增类型、错误码或Fixture，未生成0.6.0。**

遵守本轮明确指令：“以代码现状为准；文档与现有协议/代码不符时，在回执里指出并停下”。已发现下述两项影响执行身份与结果状态的冲突，所以停止新增契约，没有擅自修改业务代码或选择新的状态映射。P1/P2/P3不能据此宣布远程协议已经冻结。

头部build/tests的pass仅表示**未改动协议/业务代码的0.5.0基线**校验与回归通过，不表示0.6.0已验收。commit字段将登记本回执的证据提交，不是协议冻结SHA。

## 工作区与设计来源

- 工作目录：E:/OtherPro/HQAgent-Hub-worktrees/remote-protocol。
- 分支feat/remote-protocol，代码起点6f38217。
- 已完整阅读docs/vnext/手机远程接入方案.md；文本与`git show 855d871:docs/vnext/手机远程接入方案.md`一致。
- 设计文件Git blob内容SHA-256：e1f3156034001ddb68918e4f8e41ad35849110c1b2964d041bcdc5cb0427241d。
- 已读接口与插件协议§3–4、技术方案§3.1/§5、完整examples/contracts.json。
- 指定的二期讨论共识不在本worktree中，故仅只读访问E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.hqagent/handoffs/二期手机控制-讨论共识.md的§7；未复制、修改或提交该文件。
- 该共识只读文件SHA-256：e53671849bbe94494ecdeeb792a57c6afef96c80edf0083394a8d8d39eb068ca。
- 未在vnext-integration工作区执行安装、生成、测试、提交等操作，未修改那里的三处既有未提交文件。

## open_questions

### Q1：R1的Task/Run/Attempt引用以现有内核为准，还是先迁移执行模型？

文档证据：

- docs/vnext/技术方案.md:134：追加业务要求创建下一Run并复用Task；非终态重试创建新Attempt；终态重试创建带retryOfRunId的新Run。
- 同文件:136：单轮Run成功不自动关闭长期Task。
- docs/vnext/接口与插件协议.md:190和examples/contracts.json也使用上述Attempt语义，上行事件示例包含attemptId。

代码及已有协议证据：

- apps/hub/runtime/local_chat.py:207对尚未绑定执行的每个LocalRun调用`ports.tasks.create_task(spec, f"local-run:{run_id}")`。连续对话恢复的是角色Session，并不是多个LocalRun共用一个长期Task。
- packages/protocol/schema/local-chat.json:321的LocalRunView引用taskId、TaskDetailView，状态直接使用已有TaskStatus。
- apps/hub/runtime/tasks.py:456：终态retry调用_create_child创建另一个Task；非终态retry对原失败Node调用_reset_node，没有创建独立Attempt。
- apps/hub/runtime/tasks.py:1310的_reset_node重置现有Node执行字段；当前schema/存储没有独立Attempt实体，也没有可直接复用的retryOfRunId字段。

影响：不能把现有taskId静默改称长期目标ID，也不能把Node/Session ID改名为attemptId。否则P1结果引用、P2去重恢复与P3多轮/重试历史会产生不同理解。草案的目标模型与当前事实需要明确映射，不能当作已经一致。

**建议但未实施的裁决**：R1继续保持通信工具定位，沿用当前conversationId→LocalRun→execution Task/Node/Session；明确远程taskId的现有内核含义，不要求当前Worker伪造Attempt。缺少的Attempt能力明确不提供；未来执行内核迁移另立工作包及兼容映射。若要求按长期Task/新Attempt原样冻结，须先另行授权内核迁移，超出本轮协议工作。

### Q2：取消结果不明采用现有执行状态的显式映射，还是更换执行状态机？

文档证据：

- docs/vnext/接口与插件协议.md:191：取消进入cancel_requested，超时进入recovery_required。
- docs/vnext/技术方案.md§5.1的Run状态含waiting_input/pause_requested/cancel_requested/recovery_required。
- 接口与插件协议§4.1要求取消结果不明不能视为确认停止，command.completed也不等于Run成功。

代码及冻结契约证据：

- .hqagent/INTERFACES.md:88的FZ-2明确：Adapter refused时Hub标failed，不标cancelled。
- packages/protocol/schema/common.json:56的TaskStatus只有draft/queued/running/waiting_approval/paused/succeeded/failed/cancelled/unknown。
- apps/hub/orchestrator/runtime.py:557–581：取消REFUSED产生TaskStatus.FAILED，提示Agent可能仍运行，不是recovery_required状态。
- apps/hub/runtime/tasks.py:1171–1180：没有当前进程执行句柄时保存Task paused，并在内部task spec存recoveryRequired=true。
- 暂停意图同样是内部pauseRequested标记，不是公开TaskStatus.pause_requested。

影响：直接复用现有TaskStatus不能原样表达草案状态；直接宣布Worker会发送新状态又不符合代码。不能把任意failed/paused猜测成recovery_required，不能把控制命令接收或失败当作执行进程已经停止。

**建议但未实施的裁决**：保留当前执行状态及FZ-2；远程契约单独表达命令接单、取消请求进度和结果待核对的观测信息，基于Worker的结构化证据映射，不解析报错文本猜状态。P2负责桥接实际控制结果，P3分开展示传输状态、控制结果、执行状态。若要求完整替换为草案状态机，需独立内核迁移与兼容性裁决。

## 已确定、无需再裁决的约束

以下是已确认输入，不是本次新增或已冻结DTO：

1. 服务端仅认证、设备配对绑定、消息/状态中转暂存；不调用模型、不保存模型凭据，不参与AI订阅、安装、分发。
2. 多用户以新版方案§5.2为准，旧技术方案§9的单一所有者已明确被覆盖，不计额外open question。
3. owner从认证会话取得；浏览器契约不提供可跨用户引用的owner字段。
4. 设备凭据由Worker生成，服务端只存验证值；原值仅TLS登记/认证使用，不进响应体/普通日志。它独立于本机Hub Token、浏览器Cookie和模型凭据。
5. 心跳15秒、45秒判失联；失联不等于任务失败、不释放本机锁、不跨Worker重派。
6. 仅执行用户消息分配conversationSeq；撤回已分配序号须保留跳过记录，派发结果不明不能宣称撤回成功。
7. Worker连续ack绑定存储世代；浏览器serverCursor独立且不透明。世代变化冻结旧命令自动重投，先对账。
8. 新版方案§5.3明确配对后新建对话remote；不得自动把既有local对话双写或重放历史。其覆盖旧双轨表述的部分不是额外冲突。
9. git_push/deploy/delete/db_migrate及Worker策略声明的高风险动作，R1不可远程批准；Worker不能信任服务端自报低风险。
10. 附件、原生会话发现、飞书/通知、小程序签名审批不在本轮。

未把“账号/WSS/Outbox现在尚未实现”本身当成冲突，这些本来就是P1/P2建设范围。停止原因是与既有执行事实及冻结语义的冲突尚无明确映射裁决。

## 新增类型、错误码及生成物

- 新增类型：无。
- 新增registry错误码：无。
- 新增Contract Fixture：无。
- VERSION保留0.5.0；现有165类型、14个Fixture未变。
- 未进行0.6.0生成，故不执行editable重装；未安装依赖、未联网。

## 真实基线检查输出

所有命令在remote-protocol运行。使用无profile shell，避免本机启动profile阻塞。

### 协议

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv/Scripts') + ';' + $env:PATH
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
```

```text
协议校验通过：165 个类型，14 个 Contract Fixture
```

### Hub

首次按默认临时目录执行：

```text
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
61 passed, 1 warning, 138 errors in 41.18s
```

短回溯确认是fixture setup的环境权限问题，并非断言回归：

```text
PermissionError: [WinError 5] ... C:\Users\ua-hzq\AppData\Local\Temp\pytest-of-ua-hzq
```

只将临时目录放在本worktree新建的.venv子目录，未改业务代码/测试/断言：

```powershell
# cwd: apps/hub
$r1TempRoot = Join-Path (Resolve-Path '../..') ('.venv/r1p0-temp-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $r1TempRoot | Out-Null
$env:PYTEST_DEBUG_TEMPROOT = $r1TempRoot
$env:TEMP = $r1TempRoot
$env:TMP = $r1TempRoot
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --tb=short
```

```text
199 passed, 4 warnings in 26.97s
```

warning为既有Starlette/websockets弃用提示。

### 前端

```text
pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit
退出码 0

pnpm --filter @hqagent/desktop test
Test Files  41 passed (41)
Tests       201 passed (201)
Duration    9.68s
```

## 对下游的提醒

- P1：账号隔离/配对/通信定位已确定，不能据草案假定现有taskId就是长期目标ID或独立Attempt已经存在。
- P2：需先关闭上述两项映射决策；后续建设设备凭据、存储世代、连续ack、Inbox/Outbox、序号跳过、authority及远程审批分级校验。本轮未改这些业务代码。
- P3：accepted不是任务成功，Worker离线不是执行失败；远程高风险审批拒绝不能只禁用网页按钮。
- 本轮不登记“R1远程协议已冻结”或“P1/P2/P3可以开工”的成功结论。

建议主代理确认Q1/Q2都按“保留现有内核、定义显式远程映射”推进，再恢复R1-P0定义0.6.0并重新做完整验收。未收到裁决前不依据该建议编写生产契约。
