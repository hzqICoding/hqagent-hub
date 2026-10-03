---
wp: PI-P1
status: needs-decision
scope_declared: [apps/server/**, .hqagent/handoffs/PI-P1-server.md]
scope_touched: [apps/server/scripts/smoke.py, apps/server/scripts/smoke_pi.py, apps/server/server/app.py, apps/server/server/attachments.py, apps/server/server/client_features.py, apps/server/server/events.py, apps/server/server/events_sync.py, apps/server/server/http.py, apps/server/server/native.py, apps/server/server/native_events.py, apps/server/server/replica.py, apps/server/server/resources/http-errors.json, apps/server/server/resources/remote-hub.v2.bundle.json, apps/server/server/service.py, apps/server/server/service_sync.py, apps/server/server/wire.py, apps/server/server/worker.py, apps/server/tests/test_devices_tokens.py, apps/server/tests/test_pi_projection.py, apps/server/tests/test_pi_wire.py, apps/server/tests/test_protocol.py, apps/server/tests/test_r15_policy.py, apps/server/tests/test_r3_guards.py, .hqagent/handoffs/PI-P1-server.md]
build: pass
tests: pass
commit: b6ce2897de41e14cc5b6d7bb53722bc62702ba33
open_questions: 2
---

## 当前结论

已提交可独立实施的codec5、HTTP能力投影/游标隔离、PI原生数据/图片绑定检查和测试。**整个工作包尚未完成，不建议按最终交付合入/部署**：WS ticket归属存在任务范围差异；修订5审批事件的浏览器兼容投影缺少明确冻结方案。两项已分别通过异步提问反馈，本轮结束前未收到裁决。测试全绿只证明下述已实现路径，不代表两个缺口已关闭。

基线 `b15f526 merge: sync integration with PI protocol 0.11.0`，工作区起始干净，环境检查输出environment-ok。已读PI-contract全文、PI-P0服务端要点、PI适配方案及相关Schema/OpenAPI；只改允许路径，没有改协议、Hub/前端、根配置，没有合并回integration或部署。

## 待裁决

### Q1：云端没有WS ticket接口，冻结指南明确票据属于本机

任务要求P1实现/测试WS ticket能力绑定，但云端OpenAPI仍为47个HTTP操作，没有ticket签发路径或浏览器WS，唯一WS是设备凭据认证的 `/ws/v2/worker`。`api-guide.md` §15明确写“列表游标、增量游标和**本机WS ticket**绑定能力集”；本机票据实际在local-hub.v1的 `/api/v1/auth/ws-ticket`，属于Hub/P2。

真实读取冻结bundle的输出：

```text
cloud_ticket_routes: []
cloud_websocket: /ws/v2/worker
```

建议主代理确认该验收归P2，本包只负责云端HTTP/轮询及游标能力隔离；若确实需要云端票据，应先由P0定义接口/身份与消费规则。本轮没有自造票据、增加推送端口或把本机接口搬到云端。

### Q2：浏览器worker.event DTO不接受修订5审批，不能仅靠对话通知保证旧流程

当前 `RemoteBrowserEvent` 只含原有 `RemoteBrowserWorkerEvent`（修订1）及 `RemoteBrowserV2WorkerEvent`（payload为固定修订2的RemoteV2ExecutionEvent），没有修订5事件分支。用冻结的 `pi.RemoteV5ApprovalEvent.json` 直接验证：

```text
wire5_approval_valid: True
browser_accepts_wire5_approval: False
```

wire5的Worker DTO校验通过；把同一审批放入合法worker.event信封，生成的RemoteBrowserEvent拒绝。不能通过把wireRevision改成2、隐藏PI新错误或放宽DTO来绕过。

当前代码对wire5命令使用既有command.updated，消息/运行沿已有同步投影；审批事实写入审批投影，可由GET/snapshot取得，临时以conversation.updated通知当前对话。进一步只读检查现有前端 `apps/desktop/src/stores/remote-chat.store.ts`：conversation.updated处理后直接return，不刷新审批，审批列表只在worker.event的approval.state_changed分支更新。因此这个临时通知**不足以满足旧非PI客户端在Worker升级5后的实时审批兼容**；新增测试只覆盖HTTP快照可见和旧端无PI泄露，没有把通知等同完整审批交付。

请P0明确浏览器事件投影方案及旧客户端非PI事件兼容方式：例如冻结适合新客户端的公开事件DTO，并明确旧客户端允许的投影转换规则；或给出其它既有DTO通知/快照刷新方案及相应前端配套。P1不修改协议或前端，也不擅自改标Worker事实的线路版本。Q2关闭前，这部分代码保留为待调整进展，不作为完成态发布。

## 已落盘实现

| 范围 | 文件/行为 |
| --- | --- |
| codec5与握手 | wire.py注册RemoteV5WorkerOutboundFrame/ServerOutboundFrame/CommandEnvelope，支持[1,2,3,4,5]；版本仅诊断，旧错误码域仍严格；Worker与旧内容原revision/epoch/seq/hash不改写 |
| 4→5栅栏 | worker.py持久升级目标，service_sync核对命令、Outbox、未应用事件、双方ACK；unconfirmed控制尝试的最终观测可过栅栏，保留executionMayStillBeRunning/孤儿事实；旧修订连接继续对账，周期探测由Worker/P2负责 |
| HTTP能力声明 | http.py严格读取单个pi-v1头，缺省旧投影，不猜User-Agent/包版本；能力不改变Cookie/PAT/CSRF/owner权限。Worker专用HTTP身份不按浏览器展示能力裁剪 |
| 资源隔离 | client_features.py按显式agentType、catalog.runtimes精确agentId映射和场景角色绑定判断PI；保存私有_pi与无正文pi-resource标记，用于历史关联/删除通知；旧客户端直接访问PI对话、原生索引、命令、运行、审批、附件返回NOT_FOUND |
| 兼容形状 | catalog过滤PI场景/原生能力，省略新runtimes/guard/modelId/transport/角色agentType/新增格式诊断；旧投影可由冻结RemoteV4CatalogView、NativeSessionIndex验证，不把pi伪装为其它Runtime |
| 游标 | c1/p2签名scope绑定pi-v1；列表、消息和事件切换能力后不能复用旧游标，返回REMOTE_CURSOR_INVALID；事件扫描跳过PI项仍推进位置，避免空页卡死；原无能力头的游标域保持兼容 |
| 可靠同步与下行 | PI native枚举只进5；已知PI对话/场景不接收新的旧线事件、不下发旧线命令；旧确认事实仍可按原hash重放。原生索引使用新format及pi profile检查，HTTP读取/导入复用R3，不保存临时正文 |
| 实例/图片/guard | PI场景和native发送要求5；guard缺省不放行、ready需隔离声明与空reasons；图片仍需三层支持，并要求PI能力绑定确切runtime及pi-rpc-images-v1。显式modelId通过生成PiModelSelection校验，不按品牌或名称后缀推断能力 |
| 审批和安全取消 | 高风险approve继续拒绝；reject/cancel保留原D50豁免；Worker结构化PI失败进入命令投影，三新码只在HTTP/5有效；审批事件最终投影仍受Q2阻塞 |
| 公开规范 | 用现有打包脚本刷新0.11.0 bundle及95项错误映射；接口数仍47，不新增云端模型/费用/票据接口 |

Server只信任经设备认证的声明做协议/投影预检，不检查电脑实际扩展源码、模型凭据或运行工具；PI模型可用列表、守卫真实隔离、精确CLI续接、验证probe和周期探测由P2负责。没有调用模型、读取私有模型配置、安装或分发PI。

HTTP列表只显示被授权且可解码的PI资源；capability声明不能让另一owner看到资源。无内容PI标记用于reset之后保留类型隔离，不保存正文/标题；既有设备真删除仍清关联记录。旧客户端非PI原生format也去掉新增诊断字段，防止严格旧DTO拒绝。内部可靠投影不依赖HTTP请求头，完整数据仍存储，响应阶段裁剪不改事实。

## 本轮真实验证

全部串行，TEMP/TMP/basetemp均在worktree内忽略目录apps/server/.tmp；无新依赖、无联网安装，没有429、0xC0000142或额度错误。

PI专项17项：4→5 unconfirmed栅栏两种状态、旧1–4接受原Fixture及拒绝PI枚举/新错误、降级后不得送PI、catalog/直接ID/原生索引/消息/运行/审批/附件/事件差异、owner隔离、格式字段裁剪、列表/消息/事件游标签名域、跳过项推进、原生临时读取/导入、图片实例/transport、guard失败与异步新错误。真实结果 `17 passed, 1 warning in 4.10s`。

全量命令（cwd apps/server）：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q --tb=short -p no:cacheprovider --basetemp=.tmp/pi-full
```

```text
........................................................................ [ 22%]
........................................................................ [ 44%]
........................................................................ [ 67%]
........................................................................ [ 89%]
.................................                                        [100%]
=============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-server\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
321 passed, 1 warning in 93.65s (0:01:33)
```

旧测试只精确更新当前发布版本/错误码数和支持修订列表，未知修订改为6；没有删/skip/xfail旧断言。warning是既有Starlette/httpx弃用提示。当前测试全绿不覆盖未冻结的票据/审批事件兼容语义，不能据此关闭Q1/Q2。

```powershell
../../.venv/Scripts/python.exe -B scripts/smoke.py
```

```text
Account created
uvicorn listening on loopback: PASS
browser login and secure session: PASS
pairing preview and confirmation: PASS
fake Worker revision 2, create/grant/sync, offline refusal and reconnect: PASS
20MB streaming RSS: baseline=101142528 peak=102391808 delta=1249280 bytes; upload/download SHA256: PASS
revision 3 index, ephemeral queries, resource grant and imported history: PASS
revision 5 negotiation, pi-v1 HTTP and cursor isolation: PASS
ephemeral query body and selection absent from database: PASS
packaged public OpenAPI and request IDs: PASS
PAT issuance, device pause/resume/delete and immediate revocation: PASS
Consistent backup created
server output credential redaction: PASS
SMOKE PASS
```

真实本机uvicorn及合成Worker；新smoke_pi覆盖5协商、PI原生索引旧/新HTTP差异、直接ID404和游标能力域，不启动PI或模型。

仓库根设置同一TEMP/TMP并将.venv/Scripts放到PATH：

```powershell
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
```

```text
协议校验通过：606 个类型，485 个 Contract Fixture
```

首次未加-NoProfile运行也校验通过，但PowerShell个人profile提示不存在的oh-my-posh初始化脚本；随后用-NoProfile重跑，以上为无profile警告的真实结果。这不是代码或协议故障。协议/生成物没有改动。

输出保存在 `.tmp/pi-boundaries-output.txt`、`.tmp/pi-full-output.txt`、`.tmp/pi-smoke-output.txt`、`.tmp/pi-protocol-final-output.txt`。git diff --check无空白错误（仅CRLF规范化提示）。

## 提交与下一步

- `1847e03`：codec5、特性投影/游标/同步门禁、公开资源和PI真实进程冒烟；含Q2所述临时通知路径，待裁决后调整。
- `b6ce289`：PI专项及旧版本常量适配测试。
- 本回执另提交；头部commit指实现/测试SHA。各提交后均执行git log -1 --format=%B自查，无署名。

等待主代理确认Q1归属并由P0明确Q2事件投影后继续收尾。没有新增未冻结字段/路由，没有合回integration、推送或部署。当前状态是needs-decision，而非最终done。
