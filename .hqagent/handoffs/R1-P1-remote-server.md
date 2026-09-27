---
wp: R1-P1
status: done
scope_declared: [apps/server/**, .hqagent/handoffs/R1-P1-remote-server.md]
scope_touched: [".hqagent/handoffs/R1-P1-remote-server.md", "apps/server/README.md", "apps/server/pyproject.toml", "apps/server/server/app.py", "apps/server/server/repository.py", "apps/server/server/service.py", "apps/server/server/static.py", "apps/server/tests/test_snapshot_approvals.py", "apps/server/tests/test_spa_static.py", "apps/server/tests/test_test_dependencies.py"]
build: pass
tests: pass
commit: f48c636c1f32b6fd1049e926db785da9fbdcc5d0
open_questions: 0
---

# R1-P1 Hub Server 交付回执

## 结果与裁决

实现位于 apps/server，覆盖 remote-hub.v2 的 26 个 HTTP 操作与 `/ws/v2/worker`。只认证、绑定、排队和转发；没有模型调用、模型凭据、模型配置下发、订阅或安装功能。执行、控制实际结果和审批实际消费仍属于 P2 Worker。

头部 commit 是本轮「返修 2」的最终应用/文档提交，本回执另作元数据提交，避免自引用哈希。初始实现为 a1979b1，本次保留原有安全边界及合并基线上的 85 项测试断言。最终主题提交后 `git log -1 --format=%B` 实际输出：

```text
build(server): declare optional test dependencies and setup instructions
```

- **Q1 已关闭**：主代理明确允许短码仅在面向发起 Worker 的 RemotePairingChallenge，以及原 Worker 轮询时契约要求的字段中返回。当前 0.6.3 轮询 DTO 仍不含短码，所以实现仅在创建挑战及合法幂等重放中返回。浏览器、其它 Worker/owner、日志和错误均不返回。数据库只保存短码 HMAC 校验值；重放用请求再次提供的同一 secret 和 challenge ID 重建短码，数据库没有明文短码或可逆设备凭据。
- **D42 已适配**：主代理合入的协议基线是 `1e588b4`（冻结协议 0.6.1）。先读取有界握手中的 wireRevision，再选对应生成 DTO 校验。首次修订支持 `[1]`；hello 的 semver 仅诊断，不比较包版本是否相等。hello_rejected 带 supportedWireRevisions。旧 0.6.0 草稿不会自动当修订 1，不改写已确认事件原内容。
- **D43 范围**：本机 v1 配对/解绑属于 P2，没有在服务端实现；没有添加设备 Bearer 自撤销授权。
- 先前 `0xC0000142` 是已确认的内存不足环境问题。本轮按要求首先合并 integration/phase1，未出现该错误；串行验证，仅离线重装协议包，没有联网安装或部署。

## F1–F4 审核返修（2026-09-26）

以下保留首轮审核返修记录：当时仅在 feat/remote-server 修改所需模块和新增测试，未改既有断言；相对 0975c7f 涉及 10 个应用/测试/README 文件及回执。当前头部 scope_touched 已切换为「返修 2」相对本轮合并基线 b546e47 的实际修改范围。

| 项目 | 实现和对应验证 |
| --- | --- |
| F1 无状态签名游标 | Service.cursor/position 使用 security.mac，签名绑定 owner、scope、position、expiresAt，事件游标另含签名保护的清理世代。owner 不以明文写入 token。签发与校验不再插入 records；scope/owner/验签失败为 REMOTE_CURSOR_INVALID，TTL 到期为 REMOTE_CURSOR_EXPIRED。test_signed_cursors.py 验证反复轮询及分页不累积行、篡改、跨 owner/scope、TTL 和不依赖仓储的签名验证。旧随机游标不迁移，由客户端重新取快照 |
| F2 提交后唤醒与过滤 | UnitOfWork.after_commit 按 (owner, worker) 合并回调，提交且释放仓储锁后才唤醒；回滚丢弃。每个连接持有 asyncio.Event 和常驻接收任务，同时等待接收/唤醒/固定 5 秒兜底，移除 100ms 轮询。固定兜底截止时间不因持续心跳后移。入队、withdraw/skip、撤销、冻结和 gap 补传唤醒对应连接；保留 45 秒离线、单连接隔离、每批最多 16 帧。仓储新增 command_status/due_at/outbox_done 索引列，expire 只解码指定 Worker queued 且到期命令，投递不解码 done 历史。test_delivery_wakeup.py 验证空闲 0.65s/0.4s 期间最多一次初始化事务、入队到收帧 <1s、回滚不唤醒、每事务合并、历史过滤、丢通知兜底和持续心跳不推迟兜底 |
| F3 保留期与恢复 | HQREMOTE_BROWSER_RETENTION_SECONDS 默认 604800（7 天），必须正整数。后台每 5 秒执行 Service.maintain，按索引清理到期 session/rate、旧 cursor 行及超期 browser_outbox；HTTP 路径不执行保留期清理。browser_retention 每 owner 一行 pruned_through/generation，清理和水位同事务；旧边界/被越过位置返回 410，事件全空仍保持 tail，新 snapshot 游标可用。Inbox、命令、消息、skip、投影、幂等记录不删除。test_retention.py 验证全空/部分清理、旧游标 410、新快照续拉、owner 隔离、定时运行、session/rate 清理、业务去重不丢、旧 schema 迁移与配置默认/覆盖；认证重放遇到已清理 session 仍返回泛化 401 |
| F4 运维限制 | README「已知限制」明确 SQLite 在事件循环线程同步执行，R1 单进程低负载可接受，但慢磁盘/大事务/迁移/首轮清理会阻塞。迁移方向是完整仓储事务交专用 DB 线程/执行器，再按需要改 PostgreSQL/异步池和跨实例栅栏。Docker 说明区分 Linux host networking 与 bridge，给出 network inspect、无凭据 TCP peer 实测方法，HQREMOTE_PROXY_IPS 只填实际代理来源，不用 * 或整网段；解释 HTTPS 判定失败和伪造 X-Forwarded-For 风险。Nginx 示例显式重设两个转发头。文档步骤未实际部署执行 |

迁移为 schema 1→2（候选记录过滤列/索引）→3（认证过期、browser_outbox 时间索引、owner 清理水位）。旧命令和 Inbox 正文不重写。清理水位是每 owner 的有界状态，不是每次签发游标新增一行。

F2 首轮回归曾暴露 TestClient 关闭连接时的子任务取消竞态，已通过回收接收/唤醒任务修复，未修改既有断言。另补测试确保持续心跳也不延后兜底投递。当时最终为 85 passed；下文真实命令输出现已更新为「返修 2」的完整复跑。

按主题提交，每次均已执行 git log -1 --format=%B 自查；真实输出依次为：

```text
2df89a1  fix(server): replace stored browser cursors with scoped signatures
9f79052  perf(server): wake worker delivery after committed changes
468df9f  fix(server): preserve fallback cadence during worker traffic
0bca390  feat(server): prune expired authentication and browser event records
aed88bb  docs(server): document retention and trusted proxy deployment limits
```

## 返修 2：S1 / S2 / S3（2026-09-26）

### 基线与范围

先执行 `git merge --no-ff integration/phase1 -m "merge: sync integration baseline for server follow-up fixes"`，将 integration/phase1@`9d729bec348ddf70af908651da343260371710a5` 合入原分支，merge 为 `b546e4769e9c91c8bb2b6fb6705ea6522a3ab7ed`，无冲突。协议、Worker、前端等文件是这次获准合并带入，不属于本轮自行修改；scope_touched 只列相对 b546e47 的 9 个 apps/server 文件和本回执。未合回 integration/phase1。

随后按指定命令离线重装协议：

```powershell
.venv/Scripts/python.exe -m pip install --no-index --no-build-isolation --force-reinstall --no-deps -e packages/protocol
```

退出码 0，实际输出末尾：

```text
Successfully built hqagent-protocol
Successfully installed hqagent-protocol-0.2.0
```

0.2.0 是既有 Python 分发元数据；已另行导入确认生成常量为 `0.6.3`，没有改协议包元数据。Worker 线路仍是 1。D44 本机 Cookie 配对路由未在云端实现。

主代理已确认前一版本通过真实 Worker 的本机 TLS 联调。本轮验收是下面记录的服务端测试与假 Worker uvicorn 冒烟，没有把前一版本的真实联调结果冒充本轮重跑。

### 实现与对应测试

| 项目 | 处理方式与验证 |
| --- | --- |
| S1 / D45 | Service.snapshot 在原事务内填 approvals，沿用其 observedAt、serverCursor 和 View Mapper。仓储按 owner/worker/store/对话及 pending 筛选，用解析后的时间严格比较 expiresAt > observedAt，再取最多 101 个有效项供服务层截断到 100，与其它数组的 hasMore 取或。已收到 Worker command.completed/approval_consumed 的项，即使 terminal approval 投影尚未到达也排除；202/accepted 不视为已消费，不伪造 Worker 事件。SQL 只在 repository.py，schema 仍为 3 |
| S1 测试 | test_snapshot_approvals.py 共 10 项：晚打开看到 pending、高风险不可 approve 项仍可见、跨 owner/对话隔离；approve/reject 的真实消费和 approved/rejected/expired 终态后移除；expiresAt==observedAt 排除；110 条失效/过期历史在前也不遮住后面的有效记录；100/101 边界；hasMore 与消息截断取或；snapshot cursor 后可接上审批增量。所有快照经过生成 RemoteConversationSnapshot 校验 |
| S2 | 新增 SPAStaticFiles，沿用 StaticFiles 的文件查找与文件响应。仅缺失、最后一段无扩展名的 GET 请求回退到 index.html；存在的文件/资源正常返回。api/ws 命名空间始终交父应用的 ApiEnvelope 404，不被静态 404.html 或 SPA 回退吞掉；缺失扩展名资源保持 404 |
| S2 测试 | test_spa_static.py 共 15 项，验证深链接/尾斜杠/查询串、前段含点但最后一段无扩展名、真实资源/无扩展名文件/HEAD、API/ws 404 envelope（包括静态目录恰有同名文件）、缺失 js/css/svg/.env 以及非 GET 不回退。既有静态挂载测试未改 |
| S3 | pyproject.toml 增加 test extra：pytest==8.4.2、httpx==0.28.1、PyYAML==6.0.3；运行时 dependencies 与 requirements.txt 不变。README 验证节给出普通环境与离线 wheelhouse 的安装方式，当前环境不额外联网安装 |
| S3 锁文件差异 | apps/hub/requirements.local-lock.txt 确实列出 pytest 8.4.2、httpx 0.28.1，但没有 PyYAML 条目，因此不存在可直接对齐的 PyYAML 锁值。本轮使用已预装并实际验证的 6.0.3 明确固定，未越界修改 Hub 锁。test_test_dependencies.py 检查 extra、可用 Hub 锁项和运行时依赖保持不变；若集成线要求 Hub 锁也收录 PyYAML，由 Integrator 补录 |

README 同步说明协议 0.6.3、D45 初始化待处理集合/截断边界和 H5 history 回退。S1 未添加审批分页路由或协议字段，S2 未改变认证与事件通道，S3 没有增加运行时依赖。

### 提交

每次提交（包含 merge）均已执行 `git log -1 --format=%B` 自查；主题提交依次为：

```text
b546e47  merge: sync integration baseline for server follow-up fixes
d04bc10  feat(server): include valid pending approvals in conversation snapshots
aee6ffa  fix(server): serve the H5 shell for history deep links
f48c636  build(server): declare optional test dependencies and setup instructions
```

专项输出分别为 `10 passed, 1 warning in 3.92s`（S1）、`16 passed, 1 warning in 1.35s`（S2 连同既有静态测试）、`1 passed, 1 warning in 0.01s`（S3）。最终串行全量、冒烟及协议回归的真实输出见下方「真实命令和输出」。没有修改既有测试断言、开启并行测试或部署服务器；未发生 0xC0000142。

## 模块与表结构

| 模块 | 实际职责 |
| --- | --- |
| server/app.py | 26 个显式 HTTP 绑定，生成 DTO 校验，Cookie/Origin/CSRF，统一脱敏错误，可选静态目录 |
| server/static.py | H5 history 模式回退，保留真实静态资源和 API/ws 404 边界 |
| server/security.py | scrypt 口令、HMAC 设备验证值、认证专用重放、持久限速、300 秒挑战及短码校验 |
| server/repository.py | 全部 sqlite3/SQL/WAL，串行事务、schema 版本、迁移和 Backup API |
| server/service.py | owner 业务、Conversation、原子消息/命令/序号/Outbox、审批预检、撤回/过期/撤销、cursor/快照 |
| server/events.py | 事件去重、连续前缀、引用归属、控制完成矩阵、投影与浏览器 Outbox 原子提交 |
| server/worker.py | WSS 认证、hello timeout、连接栅栏、心跳、冻结、派发意图与有序补传 |
| server/wire.py | 集中的线路识别、codec 选择、生成 DTO 序列化、拒绝支持列表、256 KiB 上限 |
| server/config.py、common.py | 数据目录、密钥和时钟配置，规范化哈希、注册错误码、时间格式 |
| server/cli.py、__main__.py | 安全创建账号、迁移、备份，单进程 loopback uvicorn |
| scripts/smoke.py | 真实进程冒烟、stdin 账号口令、契约假 Worker、输出脱敏检查和进程退出 |
| Dockerfile、Dockerfile.dockerignore、Caddyfile.example、README.md | 自部署、上下文白名单、TLS 代理、配置/初始化/备份/升级/联调说明 |

schema=3，与包版本和 wireRevision 分离；SQLite 使用 WAL、FULL synchronous、busy timeout。业务只能通过 UnitOfWork 访问，不传 SQL。

| 表 | 分区与内容 |
| --- | --- |
| auth | 独立认证暂存：账号 scrypt 盐/校验值、会话失效信息及认证过期索引、认证重放意图 HMAC、credential verifier→owner/worker、挑战/短码校验索引、限速桶。未认领挑战及认证前限速没有 owner，属于契约允许的认证暂存，不是业务设备 |
| records | owner 非空检查，唯一 `(owner, kind, id)`，额外 worker/store/parent 关联列，以及 command_status/due_at/outbox_done 过滤列及索引。kind 包含 device/catalog/conversation/message/command/outbox/run/run-ref/approval/event-position/idempotency/message-intent/approval-intent；读取都传 owner，并在业务层核对 worker/store/conversation |
| inbox | owner/worker/store/event_id、不可变正文、first_seq/last_seq/applied；事件 ID、store 序号与覆盖区间冲突检查 |
| browser_retention | 每 owner 一行 pruned_through/generation，随裁剪事务更新；tail 不回退，旧位置要求快照恢复 |
| browser_outbox | owner、服务端独立 ordinal 与浏览器事件；owner 索引分页。带 recorded_at 保留期索引；cursor 是 owner/scope/位置/TTL/清理世代签名的无状态不透明 token，不存 records |

Command 保存不可变线路帧和原始 202 receipt，派发状态另存；用户消息、Command、conversationSeq、Outbox、幂等记录一起提交。run-ref 只存 Worker 给出的真实引用，不生成执行状态；只有 run.state_changed 创建 Run 投影。已有 Worker 引用即使尚无状态投影，仍可路由取消等控制。

## 每条契约规则的落点

| 契约 | 落点与验证行为 |
| --- | --- |
| §1 定位 | 独立 apps/server；不依赖执行内核、不调用模型、不管理模型凭据 |
| §2 owner/认证/CSRF/重放/限流 | security.py、app.py、repository.py；跨 owner 资源 NOT_FOUND；Cookie 仅 Set-Cookie；精确 Origin 与会话 CSRF；缓存重放前仍查归属；认证独立缓存；HTTP/WSS 认证 429 有 Retry-After |
| §3 配对与撤销 | Security.challenge/pairing_record/device_identity、Service.confirm/revoke、Connection.close；300 秒、验证值存储、事务认领、重放与已消费保护；撤销立即断连拒绝重连，不宣称执行停止 |
| §4 WSS/世代 | worker.py、wire.py；Authorization 唯一认证来源，URL token/Cookie 不能替代；10 秒 hello；单连接与 epoch 栅栏；store/ack 异常持久冻结；15/45 常量，使用单调时钟判离线 |
| §5 入队/期限 | Service.enqueue/send_message/deadline；原子落库再 202；submit 默认 24h/最多 7d，控制 5min/最多 15min；审批不晚于真实请求期限；重放不延长 TTL |
| §6 序号与撤回 | 只有 submit 分配序号；reject_undispatched/withdraw/expire 保存 skip；已可能派发时独立 withdrawal 并保持 requested；WorkerTransport.deliver 写派发意图后才 socket，分批投递、gap 补传不可变记录 |
| §7 控制结果 | Events.finish_matrix/command 按持久命令类型验证结果、引用和结构化证据；取消确认要求停止，pause/resume 可有活跃进程；unconfirmed 保持 accepted；不从 failed/paused/断线推断停止 |
| §8 事件/cursor | Events.accept/references/project、Service.events/page/snapshot；缺口持久保存但不提前确认；连续事件/投影/浏览器 Outbox 同事务；omitted 不给浏览器；冲突不覆盖；快照、有效待处理审批和 cursor 同事务；审批先筛选再有界截取，确认消费后排除；过期 410，跨 owner/错误作用域 cursor 按契约 REMOTE_CURSOR_INVALID |
| §9 权威/审批 | Service.conversation/approval；持久 authority；四类高风险、Worker 禁止、不可远程批准及无法确定安全分类的 shell 拒绝 approve；允许 reject；已终态 Run 不接受批准；Worker 仍须再检 |
| §10 DTO/大小 | HTTP 和 Worker JSON 帧均用生成模型；wire.py 检查总 UTF-8 大小；分页在仓储限量读取，目录有界；不另写边界 DTO |
| §11 D42 | wire.py codec registry 与 test_protocol.py；包版本仅诊断，未知修订先协商拒绝；将来 N/N-1 codec 集中保留 |

## 设计取舍、未运行项与限制

- FastAPI 单进程模块化单体、owner 聚合记录仓储；内部 JSON 聚合不是第二套边界 DTO。SQLite 方言仅在仓储，未来数据库迁移保留仓储接口；多副本还需另做连接路由与栅栏。
- 事务内不等待网络。dispatching/sent 只表示可能发出，不表示接单；断线重传不改变 ID、序号、内容和 expiresAt。
- 密钥使用与账号认证隔离：只有标准库 scrypt/secrets/HMAC，无清单外依赖；设备 secret 只留不可逆验证值。短码重放必须再次提供 Worker secret。
- 浏览器仅 /events 轮询，无另加推送通道。所有 cursor owner/作用域/TTL 绑定；快照有界，更多历史走分页。
- 不提供远程 force-unfreeze。浏览器 Outbox 按可配置保留期清理，通过快照恢复；Inbox、命令、消息、skip、投影与去重事实仍不删除。SQLite 同步调用与后续迁移方向已写入 README「已知限制」。
- 没有实际 P2/P3 服务参与联调，测试使用按生成 DTO 通信的假 Worker。Dockerfile/Caddyfile 已交付，但没有拉镜像、构建 Docker 镜像、申请证书或部署；这些未运行项没有声称通过。真实 uvicorn 已跑通。
- 根 workspace/CI 未改；Integrator 如需接入，使用 README 的串行 pytest、协议回归命令。没有修改其它应用、协议、docs 或共享根文件。

## 真实命令和输出

最终 pytest 在 `E:/OtherPro/HQAgent-Hub-worktrees/remote-server/apps/server` 执行：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.tmp/rework2-final
```

退出码 0。以下为真实输出末尾（进度点由工具分两次返回，此处仅列 warning 与统计）：

```text
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-server\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
111 passed, 1 warning in 41.16s
```

没有放宽/删除既有测试断言。warning 原样保留，未为去掉提示安装 httpx2。未开 pytest 并行 worker，验证串行。TEMP/TMP/--basetemp 都在 worktree 内被忽略的 .tmp；本次没有再触发默认临时目录 WinError 5，那是既知环境权限问题，不作为代码失败。

覆盖：双账号设备/对话/命令/事件/审批/Run 隔离、Worker 引用越权、配对过期/重放/撤销断连、Cookie/CSRF/认证泛化和限流、Q1 及落库脱敏、离线排序和 skip/gap、两类幂等、事件区间和连续 ack、store 冻结和旧 epoch、审批分级、D41 完成矩阵、事务故障回滚、游标分页/过期、Backup 恢复、26 路由 DTO 对照、线路协商/超帧/hello timeout、静态挂载、单调时钟和分批投递。F1–F3 覆盖签名游标不增长、无空转及时唤醒、保留期及迁移；返修 2 新增 D45 审批快照、SPA 回退和 test extra，共 111 项。测试文件逐项命名可独立复跑。

编译检查：将下列 Python 通过标准输入交给 `../../.venv/Scripts/python.exe -B -X utf8 -`，退出码 0：

```python
from pathlib import Path
for path in Path('server').glob('*.py'):
    compile(path.read_text(encoding='utf-8'),str(path),'exec')
print('Python module compilation: PASS')
```

```text
Python module compilation: PASS
```

build=pass 指源码编译与真实 uvicorn 启动成功，不表示 Docker 镜像已构建。

协议回归在仓库根目录执行：

```powershell
$env:PATH=(Join-Path $PWD '.venv/Scripts')+';'+$env:PATH
$env:TEMP=(Join-Path $PWD 'apps/server/.tmp')
$env:TMP=$env:TEMP
pwsh scripts/protocol/validate.ps1 -CheckGenerated
```

退出码 0：

```text
协议校验通过：258 个类型，110 个 Contract Fixture
```

脚本按既有实现重新生成并逐字节比对；`git diff --name-only -- packages/protocol apps/hub apps/desktop docs` 无输出，没有留下协议或其它包变更。

最终冒烟在 apps/server 执行：

```powershell
../../.venv/Scripts/python.exe -B scripts/smoke.py
```

退出码 0：

```text
Account created
uvicorn listening on loopback: PASS
browser login and secure session: PASS
pairing preview and confirmation: PASS
fake Worker revision 1, offline queue, reconnect and durable ack: PASS
Consistent backup created
server output credential redaction: PASS
SMOKE PASS
```

冒烟使用 loopback 临时端口和可信本机代理协议头模拟 TLS 终结后的请求，不是公网证书部署测试。随机账号口令走子进程 stdin，未入 argv/日志；测试数据仅在忽略目录 .tmp，未提交。

## P2/P3 接续

完整启动、配置、自部署、备份、升级与手工 HTTP 配对说明见 `apps/server/README.md`。从 apps/server：

```powershell
$env:HQREMOTE_ORIGIN='https://hub.example.com'
../../.venv/Scripts/python.exe -m server.cli migrate
../../.venv/Scripts/python.exe -m server.cli create-account --login alice --display-name Alice
../../.venv/Scripts/python.exe -m server
```

没有默认测试密码；账号口令交互输入，自动化仅 --password-stdin。默认 127.0.0.1:8080，Caddy/Nginx 终结 TLS。独立实验目录可设 HQREMOTE_DATA_DIR。

- P2：本机生成并保存 secret → POST Worker pairing-requests → 本机展示短码 → 已登录浏览器 preview/confirm → 原 secret 轮询 paired → WSS hello → capability.changed 发布 workspace/scene。不要把短码复制进服务端日志或浏览器响应。
- P2：持久 seq、原 epoch 重传、Inbox/接单/顺序事务、高水位校验、本机审批策略和结构化控制证据都不能省略。已过期但可能派发的原命令用于查 Inbox/对账，不能当新请求执行。服务端不会把旧未决命令迁移到新 store/设备。
- P3：Cookie + Origin + CSRF + Idempotency-Key；设备 catalog 创建 Conversation。202 只表示排队。先 snapshot 的 serverCursor 再轮询 /events；410 重新 snapshot，更多历史分页。传输、控制与执行分开展示，撤销不等于停止。
- 冻结无客户端解除接口。需要重新开始时显式撤销、用新 secret 建新绑定/新对话；不能自动接管旧命令。

open_questions：0。Q1、D42、F1–F4 和本轮 S1–S3 已落实；D45 使用既有冻结字段，未自行增加协议字段或推送通道。PyYAML 锁文件缺项及选用版本已明确记录。
