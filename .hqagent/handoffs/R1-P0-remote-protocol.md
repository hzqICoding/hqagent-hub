---
wp: R1-P0
status: done
scope_declared: [packages/protocol/**, scripts/protocol/**, .hqagent/**]
scope_touched: [".hqagent/DECISIONS.md", ".hqagent/INTERFACES.md", ".hqagent/handoffs/R1-P0-remote-protocol.md", ".hqagent/reviews/R1-P0-desktop-tests.log", ".hqagent/reviews/R1-P0-desktop-typecheck.log", ".hqagent/reviews/R1-P0-hub-tests.log", ".hqagent/reviews/R1-P0-offline-package.log", ".hqagent/reviews/R1-P0-protocol-validation.log", ".hqagent/reviews/R1-P0-wire-tests.log", "packages/protocol/README.md", "packages/protocol/VERSION", "packages/protocol/events/event-dictionary.md", "packages/protocol/fixtures/contracts/manifest.json", "packages/protocol/fixtures/contracts/remote.RemoteAccountView.json", "packages/protocol/fixtures/contracts/remote.RemoteAnonymousSession.json", "packages/protocol/fixtures/contracts/remote.RemoteApprovalDecisionCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteApprovalDecisionInput.json", "packages/protocol/fixtures/contracts/remote.RemoteApprovalDecisionPayload.json", "packages/protocol/fixtures/contracts/remote.RemoteApprovalEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteApprovalView.json", "packages/protocol/fixtures/contracts/remote.RemoteAuthenticatedSession.json", "packages/protocol/fixtures/contracts/remote.RemoteBrowserCommandEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteBrowserConversationEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteBrowserEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteBrowserEventPage.json", "packages/protocol/fixtures/contracts/remote.RemoteBrowserMessageEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteBrowserSessionView.json", "packages/protocol/fixtures/contracts/remote.RemoteBrowserWorkerEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteCancelCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteCatalogEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteCatalogView.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandAccepted.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandCompleted.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandEnvelope.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandFailed.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandPage.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandReceipt.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandRejected.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandView.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandWithdrawalCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandWithdrawalInput.json", "packages/protocol/fixtures/contracts/remote.RemoteCommandWithdrawalPayload.json", "packages/protocol/fixtures/contracts/remote.RemoteControlConfirmed.json", "packages/protocol/fixtures/contracts/remote.RemoteControlObserved.json", "packages/protocol/fixtures/contracts/remote.RemoteControlRejected.json", "packages/protocol/fixtures/contracts/remote.RemoteControlResult.json", "packages/protocol/fixtures/contracts/remote.RemoteControlUnconfirmed.json", "packages/protocol/fixtures/contracts/remote.RemoteConversationGap.json", "packages/protocol/fixtures/contracts/remote.RemoteConversationPage.json", "packages/protocol/fixtures/contracts/remote.RemoteConversationSkip.json", "packages/protocol/fixtures/contracts/remote.RemoteConversationSnapshot.json", "packages/protocol/fixtures/contracts/remote.RemoteConversationView.json", "packages/protocol/fixtures/contracts/remote.RemoteCreateConversationInput.json", "packages/protocol/fixtures/contracts/remote.RemoteDevicePage.json", "packages/protocol/fixtures/contracts/remote.RemoteDeviceRevocationView.json", "packages/protocol/fixtures/contracts/remote.RemoteDeviceRevokeInput.json", "packages/protocol/fixtures/contracts/remote.RemoteDeviceView.json", "packages/protocol/fixtures/contracts/remote.RemoteError.json", "packages/protocol/fixtures/contracts/remote.RemoteEventAck.json", "packages/protocol/fixtures/contracts/remote.RemoteEventPosition.json", "packages/protocol/fixtures/contracts/remote.RemoteLoginInput.json", "packages/protocol/fixtures/contracts/remote.RemoteMessageEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteMessagePage.json", "packages/protocol/fixtures/contracts/remote.RemoteMessageView.json", "packages/protocol/fixtures/contracts/remote.RemoteOmittedEvents.json", "packages/protocol/fixtures/contracts/remote.RemotePairingChallenge.json", "packages/protocol/fixtures/contracts/remote.RemotePairingConfirmInput.json", "packages/protocol/fixtures/contracts/remote.RemotePairingPreview.json", "packages/protocol/fixtures/contracts/remote.RemotePairingPreviewInput.json", "packages/protocol/fixtures/contracts/remote.RemotePairingRequestInput.json", "packages/protocol/fixtures/contracts/remote.RemotePairingStatusView.json", "packages/protocol/fixtures/contracts/remote.RemotePauseCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteProgressEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteQueuedReceipt.json", "packages/protocol/fixtures/contracts/remote.RemoteResultRef.json", "packages/protocol/fixtures/contracts/remote.RemoteResumeCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteRetryCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteRunControlInput.json", "packages/protocol/fixtures/contracts/remote.RemoteRunControlPayload.json", "packages/protocol/fixtures/contracts/remote.RemoteRunPage.json", "packages/protocol/fixtures/contracts/remote.RemoteRunStateEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteRunStatePayload.json", "packages/protocol/fixtures/contracts/remote.RemoteRunSubmitCommand.json", "packages/protocol/fixtures/contracts/remote.RemoteRunSubmitPayload.json", "packages/protocol/fixtures/contracts/remote.RemoteRunView.json", "packages/protocol/fixtures/contracts/remote.RemoteSceneSummary.json", "packages/protocol/fixtures/contracts/remote.RemoteSendMessageInput.json", "packages/protocol/fixtures/contracts/remote.RemoteServerHeartbeat.json", "packages/protocol/fixtures/contracts/remote.RemoteServerOutboundFrame.json", "packages/protocol/fixtures/contracts/remote.RemoteSkipRecorded.json", "packages/protocol/fixtures/contracts/remote.RemoteVisibleWorkerEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerEvent.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerHeartbeat.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerHello.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerHelloAck.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerHelloRejected.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerMessagePayload.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkerOutboundFrame.json", "packages/protocol/fixtures/contracts/remote.RemoteWorkspaceSummary.json", "packages/protocol/generated/go/protocol.go", "packages/protocol/generated/python/models.py", "packages/protocol/generated/ts/index.ts", "packages/protocol/openapi/remote-hub.v2.yaml", "packages/protocol/pyproject.toml", "packages/protocol/registry/error-codes.yaml", "packages/protocol/remote/R1-contract.md", "packages/protocol/schema/remote.json", "scripts/protocol/generate.py", "scripts/protocol/tests/test_remote_contract.py", "scripts/protocol/validate.py"]
build: pass
tests: pass
commit: c443e126496c5b5115fe23efed60f9e4a2b4043f
open_questions: 5
---

# R1-P0 远程协议0.6.0交付回执

## 结果与提交定位

R1远程协议已冻结，P1服务端/P2 Worker连接/P3 Web B阶段可以开工。冻结SHA `c443e126496c5b5115fe23efed60f9e4a2b4043f` 包含schema、生成物、错误码、Fixture、HTTP/WS绑定、规范说明及专用测试，前置生成器提交 `068140a`。本回执和裁决登记是后续元数据提交；头部commit指契约冻结SHA，避免自引用提交哈希。未合并integration/phase1。

所有工作基于remote-protocol磁盘现状继续；没有回滚或重做已完成草稿。未修改apps/hub、apps/desktop或docs/vnext，未放宽既有断言，未运行真实Worker/远程服务、未调用模型。D40/D41编号此前空闲，按原编号登记，Q1/Q2已关闭。

服务端严格定位为认证、设备配对、消息/状态中转暂存，不调用模型，不保存模型凭据，不参与AI订阅、安装或分发。附件、R3原生历史、飞书/通知、R5签名审批均未加入。

## 入口与事实源

- `packages/protocol/schema/remote.json`：86个新增命名类型。
- `packages/protocol/openapi/remote-hub.v2.yaml`：26个REST操作和Worker WSS帧绑定，与本机OpenAPI分开。
- `packages/protocol/remote/R1-contract.md`：授权/幂等/顺序/世代/撤回/完成矩阵/P2映射的规范条款，已加入协议包wheel/sdist。
- `packages/protocol/registry/error-codes.yaml`：26个新码，既有码定义逐项保留。
- `scripts/protocol/generate.py`、`validate.py`：oneOf/null与新远程对象的边界约束，旧DTO语义不变。
- `scripts/protocol/tests/test_remote_contract.py`：正反样例、字段边界、不可泄露类型、原状态枚举及生成接口回归。
- TypeScript新增联合；Python新增RootModel以保持model_validate/裸JSON round-trip；Go按原x-go闭包生成版本/错误枚举，不启用远程联合。

## 新增类型清单（86）

每个下列类型对应一个 `packages/protocol/fixtures/contracts/remote.<类型名>.json`，manifest显式登记，旧14个Fixture保留；合计100个。

- `RemoteAccountView`
- `RemoteAnonymousSession`
- `RemoteApprovalDecisionCommand`
- `RemoteApprovalDecisionInput`
- `RemoteApprovalDecisionPayload`
- `RemoteApprovalEvent`
- `RemoteApprovalView`
- `RemoteAuthenticatedSession`
- `RemoteBrowserCommandEvent`
- `RemoteBrowserConversationEvent`
- `RemoteBrowserEvent`
- `RemoteBrowserEventPage`
- `RemoteBrowserMessageEvent`
- `RemoteBrowserSessionView`
- `RemoteBrowserWorkerEvent`
- `RemoteCancelCommand`
- `RemoteCatalogEvent`
- `RemoteCatalogView`
- `RemoteCommandAccepted`
- `RemoteCommandCompleted`
- `RemoteCommandEnvelope`
- `RemoteCommandFailed`
- `RemoteCommandPage`
- `RemoteCommandReceipt`
- `RemoteCommandRejected`
- `RemoteCommandView`
- `RemoteCommandWithdrawalCommand`
- `RemoteCommandWithdrawalInput`
- `RemoteCommandWithdrawalPayload`
- `RemoteControlConfirmed`
- `RemoteControlObserved`
- `RemoteControlRejected`
- `RemoteControlResult`
- `RemoteControlUnconfirmed`
- `RemoteConversationGap`
- `RemoteConversationPage`
- `RemoteConversationSkip`
- `RemoteConversationSnapshot`
- `RemoteConversationView`
- `RemoteCreateConversationInput`
- `RemoteDevicePage`
- `RemoteDeviceRevocationView`
- `RemoteDeviceRevokeInput`
- `RemoteDeviceView`
- `RemoteError`
- `RemoteEventAck`
- `RemoteEventPosition`
- `RemoteLoginInput`
- `RemoteMessageEvent`
- `RemoteMessagePage`
- `RemoteMessageView`
- `RemoteOmittedEvents`
- `RemotePairingChallenge`
- `RemotePairingConfirmInput`
- `RemotePairingPreview`
- `RemotePairingPreviewInput`
- `RemotePairingRequestInput`
- `RemotePairingStatusView`
- `RemotePauseCommand`
- `RemoteProgressEvent`
- `RemoteQueuedReceipt`
- `RemoteResultRef`
- `RemoteResumeCommand`
- `RemoteRetryCommand`
- `RemoteRunControlInput`
- `RemoteRunControlPayload`
- `RemoteRunPage`
- `RemoteRunStateEvent`
- `RemoteRunStatePayload`
- `RemoteRunSubmitCommand`
- `RemoteRunSubmitPayload`
- `RemoteRunView`
- `RemoteSceneSummary`
- `RemoteSendMessageInput`
- `RemoteServerHeartbeat`
- `RemoteServerOutboundFrame`
- `RemoteSkipRecorded`
- `RemoteVisibleWorkerEvent`
- `RemoteWorkerEvent`
- `RemoteWorkerHeartbeat`
- `RemoteWorkerHello`
- `RemoteWorkerHelloAck`
- `RemoteWorkerHelloRejected`
- `RemoteWorkerMessagePayload`
- `RemoteWorkerOutboundFrame`
- `RemoteWorkspaceSummary`

## 新增错误码清单（26）

| code | HTTP | retryable | 含义 |
| --- | --- | --- | --- |
| `REMOTE_AUTH_REQUIRED` | 401 | false | 远程账号会话缺失或失效；与本机Hub Token鉴权分离 |
| `REMOTE_CSRF_REJECTED` | 403 | false | 远程浏览器写请求的Origin或会话CSRF校验失败 |
| `REMOTE_DEVICE_OFFLINE` | 409 | true | 目标设备离线；可排队命令仍返回202和queued_offline，不将离线误报执行失败 |
| `REMOTE_DEVICE_REVOKED` | 403 | false | 设备配对已撤销，禁止新连接与后续命令；不宣称已停止本机执行 |
| `REMOTE_DEVICE_AUTH_FAILED` | 401 | false | 设备凭据验证失败；响应不区分其他所有者设备的存在性 |
| `REMOTE_PAIRING_EXPIRED` | 410 | false | 一次性配对请求或配对码已过期 |
| `REMOTE_PAIRING_CONFLICT` | 409 | false | 配对已消费或设备凭据已绑定；不得重新归属另一用户 |
| `REMOTE_PAIRING_INVALID` | 404 | false | 无效配对码或请求；不泄露已绑定账号信息 |
| `REMOTE_COMMAND_EXPIRED` | 410 | false | 命令接单前已过期，不再执行；已分配执行序号须留跳过记录 |
| `REMOTE_COMMAND_WITHDRAWN` | 409 | false | 命令在未派发时撤回或经Worker核实撤回；拒绝迟到重复执行 |
| `REMOTE_WITHDRAWAL_UNCONFIRMED` | 409 | false | 已可能派发，不能仅删服务端记录宣称撤回；须Worker核实 |
| `REMOTE_STORE_CHANGED` | 409 | false | Worker存储世代变化，冻结旧世代未决命令自动投递等待对账 |
| `REMOTE_EPOCH_STALE` | 409 | false | 非当前已认证连接或旧Worker启动实例的帧被拒绝 |
| `REMOTE_PROTOCOL_UNSUPPORTED` | 409 | false | 协议版本不兼容；不静默降级远程命令语义 |
| `REMOTE_EVENT_CONFLICT` | 409 | false | 同事件ID或存储世代序号/覆盖区间对应不同不可变内容 |
| `REMOTE_ACK_CONFLICT` | 409 | false | 确认位置错误、跨存储世代或服务端确认回退，需要对账而非裁剪Outbox |
| `REMOTE_SEQUENCE_GAP` | 409 | true | 执行对话序号存在缺口，先补命令或跳过记录，控制命令不占执行序号 |
| `REMOTE_APPROVAL_FORBIDDEN` | 403 | false | R1禁止远程批准此高风险或Worker策略禁止的动作；本机可处理 |
| `CONVERSATION_AUTHORITY_MISMATCH` | 409 | false | 本地写接口不能写remote对话，必须走权威服务端；旧local对话不自动转换 |
| `REMOTE_TARGET_MISMATCH` | 409 | false | 命令目标、对话固定Worker或执行引用不匹配；跨owner资源统一NOT_FOUND |
| `REMOTE_SCENE_VERSION_MISMATCH` | 409 | false | Worker场景版本与已排队请求不一致，不静默换用最新角色配置 |
| `REMOTE_CURSOR_EXPIRED` | 410 | false | 浏览器opaque游标已失效，需重新获取owner范围快照 |
| `REMOTE_CURSOR_INVALID` | 400 | false | 游标无效或与当前资源/认证范围不符，不泄露游标归属 |
| `REMOTE_RATE_LIMITED` | 429 | true | 远程登录/配对/提交限流，按Retry-After重试，不能绕过单次码或幂等规则 |
| `REMOTE_FRAME_TOO_LARGE` | 413 | false | 远程帧超过256KiB，拒绝而不是截断关键内容后继续 |
| `REMOTE_WITHDRAWAL_TOO_LATE` | 409 | false | 原提交已形成可见Run或已执行结束，不能声称撤回从未执行；已知Run应按runId控制 |

## 设计取舍及理由

| 取舍 | 理由/约束 |
| --- | --- |
| D40沿用LocalRun和执行Task，远程字段executionTaskId | 不用同名taskId混淆长期目标；不伪造attemptId/retryOfRunId，保留旧LocalRunView |
| D41控制结果三态独立，执行状态原样保留 | failed/paused/cancelled标签不证明停止；recoveryRequired等Worker证据决定是否待核对 |
| oneOf命令分支，只有submit有conversationSeq | 结构上拒绝给pause/cancel/retry/审批分配执行消息槽；控制不被普通消息队列堵住 |
| 撤回携带targetConversationSeq | 只是目标原序号；撤回先到时能保存有序tombstone，不让后续消息永远等缺口 |
| 设备secret只在TLS Authorization头，服务端只存验证值 | 配对码/浏览器Cookie/本机Hub Token各司其职，不在响应、帧、日志泄露设备凭据 |
| owner隐含，跨用户资源统一NOT_FOUND | 所有读写/分页/幂等/连接按认证主体过滤，不能由客户端选owner |
| 待配对为短期认证挑战 | 确认前不知道owner，不创建可路由业务设备；确认事务才建立owner非空绑定 |
| 独立远程OpenAPI，复用既有ApiEnvelope外壳 | 不把本机接口或Token直接暴露公网；响应中不返回模型/设备凭据 |
| acknowledged连续seq和store绑定；浏览器opaque cursor | 多设备不共用Worker序号，网络重启与数据库回滚区别处理 |
| 私有本地事件使用无内容omitted覆盖记录 | 保持既有持久序号连续，但不为补洞上传local历史；不能跳过远程关键结果，浏览器联合排除该帧 |
| 世代/ack异常冻结，R1无远程force-unfreeze | Inbox丢失不能成为重复副作用理由；无证据时保持对账要求 |
| 显式过期时间和离线投递状态 | 202只是持久化入队；离线排队不会伪装运行，accepted任务不因入队TTL过期被杀 |
| command.completed分语义结果 | retry完成只表示新引用入队，pause要实际边界生效，取消未知不能completed |
| 目录/场景只发布有界已登记索引 | 允许手机选择目标但不声明离线路径可用；不加入任意目录、模型配置或历史导入 |
| 高风险批准双重校验，最终取Worker当前策略 | 服务器被攻破也不能自行把高风险动作降级；shell包装无法证明安全时须本机处理 |
| 新远程类型opt-in严格约束；RootModel保留原测试接口 | 不放宽旧断言；必填可空ack即使exclude_none也保留null，避免确认位置语义漂移 |
| 短码5分钟、submit默认24h/最多7d、控制默认5min/最多15min | 给P1/P2一致初值，重发不延长命令寿命；审批不超过真实请求有效期 |

上述结构和跨消息关系共同组成契约。DTO校验不替代owner查验、事务、持久化去重、已分配序号范围和动作实际消费校验；不能因类型通过就宣布副作用已完成。

## P1/P2/P3开工注意

### P1服务端

- owner从认证取得；已绑定业务表/游标/幂等作用域必须含owner；跨owner引用与不存在同样404。
- 先事务保存消息、Command、序号和Outbox再202。写socket前持久化派发意图；接单回执丢失不得视为未派发。
- 服务端仅能拒绝自己确认未派发的入队；不能伪造Worker事件或确认。上行事件、投影、浏览器Outbox一起提交后才连续ack。
- 设备撤销/世代变化不改变真实执行终态；审批server侧预检还必须由Worker重检。
- 账户初始化/认证存储不涉及模型账户；配对/认证响应不进入普通command缓存或日志。

### P2 Worker连接

- 明确保留当前身份链，将LocalRun.taskId映射为executionTaskId；控制按runId，不能直接伪造vNext长期Task或Attempt。
- CancelOutcome/CancelResult与orphanProcessIds来自Adapter/FZ-2；CancellationOutcome来自orchestrator/runtime.py；recoveryRequired/pauseRequested等在runtime/tasks.py使用的`task_spec:<executionTaskId>`内部记录中。必须读结构化值，不能解析错误文字。
- recovery标记和未确认进程证据优先于状态标签；暂停请求写入不等于已暂停，清除recovery标记不证明旧进程已停止。
- Inbox、顺序槽、LocalRun入队、接单回执和Outbox需要同一本机事务，再交TaskEngine；不能先调用本机HTTP执行，再补记远程Inbox。
- 检查expectedWorkerStoreId，恢复旧库换store，重传不改原事件epoch/hash。私有事件用合法范围覆盖记录，不转发原始认证信息。
- 本地API写remote对话要拒绝；原生审批重读真实pending请求和当前Worker策略，不信任服务端风险字段。

### P3 Web B阶段

- 使用独立RemoteGateway和会话Cookie；不访问设备Bearer/本机Hub Token。
- 三层分别展示：在线/排队/已投递，控制confirmed/rejected/unconfirmed，Worker实际TaskStatus。accepted、command.completed都不是普遍的任务成功。
- serverCursor不透明，过期后取快照；不要用Worker seq作浏览器游标。
- 高风险只能提示回本机处理；不把禁用按钮当后端保护，不创建R5签名入口。
- 模板/目录只展示Worker索引及observedAt；离线不能宣称路径仍存在。

## open_questions：5项既有业务适配要求

D40/D41已裁决，以下是按原任务要求记录的P2落地依赖，不是尚待选择的协议方案，不阻塞P1/P2/P3基于本契约开工。本轮未实现这些业务改动：

1. **结构化控制证据出口（P2）**：当前TaskDetailView不公开recoveryRequired/pauseRequested和本次取消回执；需从TaskService.state的task_spec、WorkflowRuntime CancellationOutcome及Adapter CancelResult桥接。否则不能可靠产生ControlResult。
2. **对话authority持久化和本地写拦截（P2）**：现有LocalConversationView/API没有完整remote权威入口；须在配对后创建、发送、追加、resume/retry等入口保证单写入者，并返回CONVERSATION_AUTHORITY_MISMATCH。不能只改UI。
3. **远程Inbox/Outbox与本地入队同事务（P2）**：LocalChatRepository.enqueue现有事务需与新命令接单、序号slot和回执组合；HTTP代理后补记不足以保证不重复执行。
4. **审批来源与当前策略判定（P1/P2）**：现有本机ApprovalCoordinator不是完整远程分级入口；需要明确来源，读取真实动作/策略，阻止禁用动作的远程approve并保留幂等消费/失效行为。
5. **持久世代和事件投影接线（P1/P2）**：现有本地events.seq不等于完整跨端Outbox；需要workerStoreId/epoch/确认高水位、omitted覆盖、域内索引及serverCursor投影。数据库恢复入口必须更换store，不能自动重放旧Inbox缺失命令。

## 真实验证输出

以下日志保存的是执行输出，不是“预计通过”。只使用预装依赖，重装均带--no-index --no-build-isolation。wheel分发元数据仍是0.2.0，实际协议VERSION和generated常量均为0.6.0；没有擅自调整产品/分发版本。

```powershell
# cwd remote-protocol
$env:PATH = (Join-Path (Get-Location) '.venv/Scripts') + ';' + $env:PATH
pwsh -NoProfile -File scripts/protocol/generate.ps1
.venv/Scripts/python.exe -m pip install --no-index --no-build-isolation --force-reinstall --no-deps -e packages/protocol
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
.venv/Scripts/python.exe -B -m pytest scripts/protocol/tests/test_remote_contract.py -q -p no:cacheprovider --tb=short
```

```text
protocol 0.6.0: 生成 251 个类型 -> ts / python / go
协议校验通过：251 个类型，100 个 Contract Fixture
120 passed in 2.63s
```

```powershell
# cwd apps/hub；只调整本轮环境，不改测试文件或断言
$r1TempRoot = Join-Path (Resolve-Path '../..') ('.venv/r1p0-freeze-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $r1TempRoot | Out-Null
$env:PYTEST_DEBUG_TEMPROOT = $r1TempRoot
$env:TEMP = $r1TempRoot
$env:TMP = $r1TempRoot
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --tb=short
```

```text
199 passed, 4 warnings in 24.37s
```

```powershell
pnpm --filter @hqagent/desktop typecheck
pnpm --filter @hqagent/desktop test --maxWorkers=2 --minWorkers=1
```

```text
$ vue-tsc --noEmit
退出码 0
Test Files  41 passed (41)
Tests       201 passed (201)
Duration    23.29s
```

前端限制测试并发以减轻此前Windows进程启动故障压力，没有删测试、跳测试或放宽断言。Hub的4个warning为既有Starlette/websockets弃用提示；前端日志中的模拟HUB_NOT_READY是重连用例的预期诊断。

历史失败如实保留：最初默认pytest临时目录WinError5属于沙箱权限，改worktree临时目录后通过；上一轮0xC0000142导致未能落最终文档/提交，已从磁盘续做；联合类型初版没有model_validate导致旧Fixture测试1失败，已通过生成RootModel修复，原断言未动。本轮新增协议测试初次收集有一个装饰器语法错误，修复后全过。最后一次包重装仅增加规范文档wheel打包，随后120项专用校验通过，生成DTO及业务源码与上述全量验证相同。

## 原始日志

- [R1-P0-desktop-tests.log](../reviews/R1-P0-desktop-tests.log)
- [R1-P0-desktop-typecheck.log](../reviews/R1-P0-desktop-typecheck.log)
- [R1-P0-hub-tests.log](../reviews/R1-P0-hub-tests.log)
- [R1-P0-offline-package.log](../reviews/R1-P0-offline-package.log)
- [R1-P0-protocol-validation.log](../reviews/R1-P0-protocol-validation.log)
- [R1-P0-wire-tests.log](../reviews/R1-P0-wire-tests.log)

## 范围与限制核对

- git diff确认apps/hub、apps/desktop、docs/vnext相对6f38217无改动；旧错误定义、TaskStatus/NodeStatus和LocalRunView.taskId保持不变。
- 所有源码/记录改动均在声明的packages/protocol、scripts/protocol、.hqagent路径内。
- 不在vnext-integration修改其未提交文件；本轮没有部署、配对真实设备、登录远程账号、发送业务命令或调用模型。
- 协议专用测试验证结构、生成及样例，不冒充P1/P2网络断线、数据库崩溃或多租户业务集成验收。远程实现须另行完成故障/越权/幂等验收。
- 不提供schema未声明的附件、原生历史、通知或签名批准占位字段。
