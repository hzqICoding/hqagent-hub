---
wp: R15-P1
status: done
scope_declared: [apps/server/**, .hqagent/handoffs/R15-P1-remote-server.md]
scope_touched: [".hqagent/handoffs/R15-P1-remote-server.md", "apps/server/README.md", "apps/server/scripts/smoke.py", "apps/server/server/app.py", "apps/server/server/common.py", "apps/server/server/config.py", "apps/server/server/events_sync.py", "apps/server/server/replica.py", "apps/server/server/repository.py", "apps/server/server/repository_sync.py", "apps/server/server/service.py", "apps/server/server/service_sync.py", "apps/server/server/wire.py", "apps/server/server/worker.py", "apps/server/tests/conftest.py", "apps/server/tests/legacy_support.py", "apps/server/tests/r15_support.py", "apps/server/tests/test_protocol.py", "apps/server/tests/test_r15_erasure_replay.py", "apps/server/tests/test_r15_flow.py", "apps/server/tests/test_r15_guards.py", "apps/server/tests/test_r15_policy.py", "apps/server/tests/test_r15_replica.py"]
build: pass
tests: pass
commit: fec26fc75c1908ce9cae4e2e67c1076d9554dfa0
open_questions: 0
---

# R1.5-P1 Hub Server 交付回执

## 基线、续作与范围

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/remote-server`，分支 `feat/remote-server`，基线为主代理已合入 0.7.0 的 `fbd4e28cfc7fbe767a6645a29c42cc2948d6463d`。从原来四个修改模块和 repository_sync.py 草稿续作，没有回滚。上一轮未落盘的 replica.py 等模块本轮实际创建并验证。头部 commit 指最终实现/测试提交，本回执单独提交，避免自引用 SHA。

本轮第一条 Get-Location 成功，随后核对 git status/diff 和五个文件全文。已读取方案 v0.4 §11、R1.5-contract 全文、R15-P0 回执、D46–D49、remote-sync.json 与 OpenAPI，并只读查看 P2 回执的 grant 状态机和 7 条接线事项，按契约核对其创建、同步批次和修订协商实现。没有改 remote-worker、协议、前端、docs、根文件或旧 R1-P1 回执；没有安装依赖、联网部署、合回 integration。未出现 0xC0000142 或额度不足错误。

服务端只认证、保存电脑副本、转发命令及持久送达许可。不调用模型，不管理模型凭据/订阅/安装，不创建执行 Task/Session，不持有会话锁。电脑仍是唯一对话写入和执行方。

## 实现与契约落点

| 任务/契约 | 主要文件 | 最终行为 |
| --- | --- | --- |
| §1 双修订与栅栏 | wire.py、worker.py、service_sync.py | CODECS[1]/[2] 分离，按 wireRevision 编解码。已有版本的帧禁止改写修订；rev1 错误域通过生成 RemoteWire1Error 校验。未知新错误不会发到 rev1。升级检查旧未决命令、明确未确认/残留进程证据、未确认 Outbox、旧 Inbox 缺口和双方 ACK；持久保存切换水位后才 ready rev2。保留 rev1 历史对账，新浏览器写入拒绝 rev1，已切换 2 不自动降级 |
| §2 电脑唯一写入及 ID | service_sync.py、repository_sync.py、replica.py | 按 owner/worker/store/kind/localId 建立稳定公开 ID。手机只用公开 ID；下行填正确 localConversationId、真实本机 run/approval ID。POST/PATCH 对话都是 202，仅预留路由/传输记录，等待电脑 upsert 才产生/改变副本。authority 只作来源，不是 R1.5 写门禁 |
| §3 全文/历史同步 | replica.py、events_sync.py、repository_sync.py | 分段落 SQLite，以 generation/message/revision 校验元数据、索引、重复内容、字节总数和全文 SHA256；只有收齐才原子发布。旧完整版本在新版本未齐时仍可见。按电脑 messageSequence 排序。批次索引、水位、计数、实际收帧字节数和 complete 校验，连续应用后才标内部补传完成；完整电脑补传后清掉未获电脑确认的 R1 服务器独有对话影子 |
| §4 真删除/覆盖 | repository_sync.py、replica.py、events_sync.py、service_sync.py | 删除/reset 可在前序缺口尚未确认时先持久删除正文；清投影、分段、浏览器 Outbox、命令副本和 Inbox 正文。保留身份、原 hash、序号、墓碑和最小无正文执行证据。ContentRedaction 绑定已持久删除事件、generation、范围及原摘要；不能覆盖 grant/接单/控制/busy/另一对话或更新代次。重复证明幂等，迟到旧正文只核对 hash 不复活 |
| §5 完整 busy | replica.py、worker.py、service_sync.py | 当前 connection/epoch 新快照未齐即 fresh=false，拼齐且连续应用后整体替换；旧快照/旧连接不覆盖，空集合清旧 busy。新快照淘汰旧暂存；只保留最新完整集合及无正文身份摘要。断线公开 fresh=false，重连及服务重启清持久 fresh/暂存；只有 submit 检查 busy/fresh，取消/其它控制/拒绝审批不受其限制 |
| §6 在线 30 秒许可 | service_sync.py、events_sync.py、worker.py | 离线立即 REMOTE_DEVICE_OFFLINE，不分配序号/不建队列；在线期限缺省/最多 30 秒，expiresAt 不延长 deliverBy。command.received、到期判定和不可逆 grant 共用 SQLite 事务。无 grant 到期 failed/REMOTE_DELIVERY_EXPIRED；迟到 received 消费日志 seq 但不 grant。已有 grant 即使 accepted 丢失、断线或超时也保留，不伪造失败。两类失败均显示“设备离线，发送失败” |
| 创建/修改/撤回 | service_sync.py、events_sync.py | conversation.create/update 不占远程序号、不造 Run。metadata_committed 根据 Worker 结构化结果校验；实际副本由 upsert 更新。修订 2 的撤回是受门闩保护的独立请求，服务端不冒充 Worker 停止成功。未获 grant 的退役槽保存 skip，避免删除/到期后卡住后续序号；不把此规则套到 rev1 的执行不明事实 |
| §7 可见性 | app.py、service_sync.py、replica.py | pc_only 仍完整保存，但所有浏览器列表、直接 ID、消息、Run、审批、快照和事件均过滤。隐藏后直接 ID 返回 NOT_FOUND；从可见改隐藏发无正文 conversation.deleted。可见 upsert 始终发 owner 的 conversation.updated；reset 发 store.reset；完整消息发 message.appended |
| §7 分页/分组 | service_sync.py、repository_sync.py | 对话按 workerId/workspaceId 过滤、按最近活动排序，签名 cursor 固定作用域/截止点。消息 RemoteSyncMessagePage 最新优先，以 before 独占边界向前；绑定 owner/worker/store/对话/同步代次、截止序号与 TTL，snapshotCursor 跨页稳定。新消息不移动旧页偏移；reset/回退导致的旧游标过期，不混代次 |
| HTTP 三处适配 | app.py | 增加 PATCH /conversations/{id}；POST conversations 为 202 RemoteQueuedReceipt；GET messages 为 RemoteSyncMessagePage。原 test_http_binding_completeness 不改断言，已通过 |

其它认证、Cookie/Origin/CSRF、配对短码校验值保存、scrypt、限流、R1.5 保留的审批分级/D41 控制证据、事件驱动唤醒、浏览器保留期、自部署与 Backup API 延续既有实现。

## 存储与边界

schema 3→4 在仓储层追加，不修改协议生成物：

- records 新增 message_sequence 索引列；R1 历史消息的内部展示顺序不冒充电脑 messageSequence。新同步消息填真实序号/revision。
- sync_ids：owner/worker/store/kind/localId 主键，owner 内公开 ID 唯一，记录对话归属及永久删除墓碑。两个电脑相同 localId 不碰撞。
- sync_log：按设备/store 隔离的原 eventId、seq 区间、hash、类型、代次、连接观察、字节数与应用状态。已应用正文不作为重复缓存永久保存；删除时必要执行事实使用独立最小 evidence，而非改写原事件 hash 后重放。
- sync_segments：按 owner/worker/store/generation/message/revision/part 落盘，完整后流式核验并原子替换消息，再清暂存。
- sync-state/sync-stage/deletion-fence/redaction-proof/remote-order/create-reservation 等是 owner 范围内部记录，不是新公共 DTO。busy 状态不是服务器锁。
- Command 及 Outbox 保存原始命令摘要和 grant；删除保留无正文许可/幂等摘要/退休标记。删除后重开同步，不会把同一 clientMessageId 或幂等键当新请求再次执行。

消息默认显式资源配额 16 MiB，可用 HQREMOTE_SYNC_MESSAGE_BYTES 调整；每 store 暂存默认 128 MiB，可用 HQREMOTE_SYNC_STAGING_BYTES 调整。另限每消息 4096 片、每 store 16384 暂存片、busy 快照 1024 片，避免按安全整数上界分配内存。配额不足/SQLite FULL 或 NOMEM 返回 REMOTE_SYNC_RESOURCE_LIMIT，失败事务不推进 ACK。消息/事件页使用约 32 MiB 组装预算（至少一条完整消息），可少于 limit 并正确给出 hasMore，不截断正文。

真正删除指在线逻辑表和可重放副本中无正文；测试直接扫描所有逻辑表。未声称普通 DELETE 物理擦除 SQLite 空闲页、WAL 或历史备份。备份保留/销毁仍由运维生命周期负责，README 已明确。

## 测试范围与旧测试处理

本轮新增 **39 项** R1.5 测试，原 111 项计数保留，合计 **150 项**：

| 文件 | 覆盖 |
| --- | --- |
| test_r15_flow.py（5） | 完整同步/离线直接失败；202 create/update 经 received/grant/metadata_committed/upsert；grant 与 deadline 两种顺序；busy 新鲜度和完整覆盖 |
| test_r15_replica.py（12） | 超 32K Unicode/NUL/CRLF 文本、乱序/重复/缺片/更高 revision、冲突/配额；删除/reset/撤销后扫描全库无正文；缺口前 reset + 原 hash 删除证明；范围越界拒绝；pc_only 各入口/事件过滤；多电脑 ID 隔离、固定截止点分页与新消息 |
| test_r15_guards.py（9） | 正式服务的 rev1 历史回执/升级栅栏/拒绝新 rev1 写入/禁止降级；取消不受 busy/fresh；服务重启；旧 busy 不覆盖与 101 ID 分片；补传计数/高水位/完成/字节预算；旧服务器独有影子待完整补传后才退役 |
| test_r15_policy.py（9） | 高风险 approve 拒绝、reject grant 和本机 ID 映射；grant 断线/期限后原样重放；各类离线写入不建 attempt；幂等；未连续确认的非内容事件展示文字也擦除；SQLite 资源故障回滚；D49 错误域/禁止帧改修订；无定时器先运行的迟到收件；极大 segmentCount 不分配资源 |
| test_r15_erasure_replay.py（4） | 删除后保留 grant/幂等证据但无正文；同意图不重跑；无 grant 的退役序号不堵后续；到期重放报告失败；分页不混 reset 前后代次 |

**历史断言没有冒充新 HTTP 验收**：D48 明确撤销旧离线排队、201 创建及 authority 门禁，原 R1 断言因此在 `tests/legacy_support.py` 的 HistoricalService 与旧响应绑定夹具中验证其历史入队/对账策略。构造仍复用相同认证宿主；原 `env` 在测试构造阶段临时注入旧业务类/响应绑定，不存在生产配置开关。旧 cursor 请求在此历史夹具映射到承载路由的 before 参数；分页隔离/过期断言保留。

正式 `create_app` 始终使用 SyncService/SyncEvents。`r15_env` 和全部 test_r15_* 使用正式服务，明确断言新 rev1 HTTP 写入失败、离线不入队以及无 grant 不接单。另有直接在正式服务加载历史 R1 已受理记录的用例，真实收发修订 1 帧、核对旧 hash 后再升级。没有给线上留下“旧客户端继续新建离线队列”的后门。

已有 `test_protocol.py` 仅将“不支持的修订 2”改为 3，支持列表断言改为 [1,2]，其它拒绝断言保留。`test_http_binding_completeness` 本身未修改，三个差异通过实际路由和业务适配解决。README 解释了测试夹具边界；回执不把历史夹具的旧政策说成 R1.5 正式行为。

## 最终真实命令输出

所有验证串行执行，无 pytest 并行 worker。cwd 为 apps/server，TEMP/TMP/basetemp 在被忽略的 worktree 内 .tmp，避开默认 TEMP 的 WinError 5：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q --tb=short -p no:cacheprovider --basetemp=.tmp/r15-final-verified
```

退出码 0，真实统计与警告：

```text
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-server\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
150 passed, 1 warning in 54.42s
```

已保留既有依赖弃用 warning，没有为消除提示添加 httpx2。源码编译检查使用 compile() 逐文件验证 server/*.py，实际输出 `Python module compilation: PASS`。build=pass 指 Python/启动验证，不表示 Docker 镜像已经构建。

同目录真实 uvicorn 进程冒烟：

```powershell
../../.venv/Scripts/python.exe -B scripts/smoke.py
```

退出码 0：

```text
Account created
uvicorn listening on loopback: PASS
browser login and secure session: PASS
pairing preview and confirmation: PASS
fake Worker revision 2, create/grant/sync, offline refusal and reconnect: PASS
Consistent backup created
server output credential redaction: PASS
SMOKE PASS
```

仓库根目录协议回归：

```powershell
$env:PATH=(Join-Path $PWD '.venv/Scripts')+';'+$env:PATH
$env:TEMP=(Join-Path $PWD 'apps/server/.tmp')
$env:TMP=$env:TEMP
pwsh scripts/protocol/validate.ps1 -CheckGenerated
```

退出码 0：

```text
协议校验通过：321 个类型，173 个 Contract Fixture
```

## 取舍、未运行项与联调入口

- 当前仍是单进程、同步 SQLite 事务，消息分段/分页避免一次加载全部历史；没有做生产大库容量或长时间压力测试。后续数据库线程/PostgreSQL/多实例栅栏方向见 README，不声称这些已经完成。
- 补传高水位、complete 与 recoveryRequired 等必要观测内部持久化；遵循冻结 DTO，不另造公开 syncStatus 或新的 TaskStatus。公开“补传中/已同步/异常”字段仍需后续协议。
- 运行目录、CLI 创建账号（仅交互/stdin 口令）、静态 H5、TLS 代理、自部署与 Backup API 沿用 README。默认 127.0.0.1:8080，先 `python -m server.cli migrate` 升至 schema 4，再单实例启动。
- 本轮已跑正式 Hub Server + 假 Worker 的真实 loopback uvicorn 冒烟，使用可信本机代理头模拟 TLS 终结后的后端链路。**没有跑真实 R1.5 P2、真实浏览器或公网 TLS 的联合验收**，没有部署/拉镜像/连接远端服务器。P2 代码/回执仅只读参考；此前 R1 真机联调不替代这一轮。
- P2：先按升级栅栏完成 rev1 对账；rev2 首先 catalog、完整 busy、分批同步。保留原摘要/epoch，received 不是 accepted，ACK 不是 grant。关闭先发 reset/deleted 再发 ContentRedaction；批次 marker 与实际内容/字节数一致，未拼齐不得 complete。
- 前端：先设备/项目筛选；POST/PATCH 202 只记录传输回执，等 conversation.updated 更新列表。pc_only 的旧可见项由 conversation.deleted 清掉；store.reset 清该设备/store 缓存。消息按 ID/revision 合并、messageSequence 排序；before 固定截止点，410 重取快照。离线、忙碌、送达失败保留输入；取消不受 busy/fresh 禁用。

## 提交与出口

本轮主题提交（每次提交后均用 git log -1 --format=%B 自查）：

```text
6e07e0d  feat(server): add revision two codecs and scoped replica storage
ffd2cf0  feat(server): enforce online grants and computer-owned synchronization
5b28436  test(server): verify replica erasure delivery fencing and browser isolation
fec26fc  fix(server): use consistent offline delivery failure messages
```

所有提交均只描述改动，无署名或生成标记。没有合并回 integration。功能实现及要求的测试已完成；上述联调/部署/压测边界不冒报为已通过。open_questions=0。
