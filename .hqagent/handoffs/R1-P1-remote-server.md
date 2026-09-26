---
wp: R1-P1
status: done
scope_declared: [apps/server/**, .hqagent/handoffs/R1-P1-remote-server.md]
scope_touched: ["apps/server/.gitignore", "apps/server/Caddyfile.example", "apps/server/Dockerfile", "apps/server/Dockerfile.dockerignore", "apps/server/README.md", "apps/server/pyproject.toml", "apps/server/requirements.txt", "apps/server/scripts/smoke.py", "apps/server/server/__init__.py", "apps/server/server/__main__.py", "apps/server/server/app.py", "apps/server/server/cli.py", "apps/server/server/common.py", "apps/server/server/config.py", "apps/server/server/events.py", "apps/server/server/repository.py", "apps/server/server/security.py", "apps/server/server/service.py", "apps/server/server/wire.py", "apps/server/server/worker.py", "apps/server/tests/conftest.py", "apps/server/tests/test_boundaries.py", "apps/server/tests/test_commands_events.py", "apps/server/tests/test_controls_storage.py", "apps/server/tests/test_core.py", "apps/server/tests/test_protocol.py", "apps/server/tests/test_security.py", ".hqagent/handoffs/R1-P1-remote-server.md"]
build: pass
tests: pass
commit: a1979b1d8dd2766734ac728b8c8d87e7b4558ed9
open_questions: 0
---

# R1-P1 Hub Server 交付回执

## 结果与裁决

实现位于 apps/server，覆盖 remote-hub.v2 的 26 个 HTTP 操作与 `/ws/v2/worker`。只认证、绑定、排队和转发；没有模型调用、模型凭据、模型配置下发、订阅或安装功能。执行、控制实际结果和审批实际消费仍属于 P2 Worker。

头部 commit 是应用代码、测试和部署文件的实现提交。本回执与三个文件末尾空行整理在后续元数据提交完成，避免自引用哈希。实现提交后 `git log -1 --format=%B` 实际输出：

```text
feat(server): implement authenticated remote relay and durable worker delivery
```

- **Q1 已关闭**：主代理明确允许短码仅在面向发起 Worker 的 RemotePairingChallenge，以及原 Worker 轮询时契约要求的字段中返回。当前 0.6.1 轮询 DTO 不含短码，所以实现仅在创建挑战及合法幂等重放中返回。浏览器、其它 Worker/owner、日志和错误均不返回。数据库只保存短码 HMAC 校验值；重放用请求再次提供的同一 secret 和 challenge ID 重建短码，数据库没有明文短码或可逆设备凭据。
- **D42 已适配**：主代理合入的协议基线是 `1e588b4`（冻结协议 0.6.1）。先读取有界握手中的 wireRevision，再选对应生成 DTO 校验。首次修订支持 `[1]`；hello 的 semver 仅诊断，不比较包版本是否相等。hello_rejected 带 supportedWireRevisions。旧 0.6.0 草稿不会自动当修订 1，不改写已确认事件原内容。
- **D43 范围**：本机 v1 配对/解绑属于 P2，没有在服务端实现；没有添加设备 Bearer 自撤销授权。
- 上轮 `0xC0000142` 是已确认的内存不足环境问题。本轮首条 Get-Location 成功后才继续，保留已有模块和主代理的协议合并；没有安装依赖、联网或部署。

## 模块与表结构

| 模块 | 实际职责 |
| --- | --- |
| server/app.py | 26 个显式 HTTP 绑定，生成 DTO 校验，Cookie/Origin/CSRF，统一脱敏错误，可选静态目录 |
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

schema=1，与包版本和 wireRevision 分离；SQLite 使用 WAL、FULL synchronous、busy timeout。业务只能通过 UnitOfWork 访问，不传 SQL。

| 表 | 分区与内容 |
| --- | --- |
| auth | 独立认证暂存：账号 scrypt 盐/校验值、会话失效信息、认证重放意图 HMAC、credential verifier→owner/worker、挑战/短码校验索引、限速桶。未认领挑战及认证前限速没有 owner，属于契约允许的认证暂存，不是业务设备 |
| records | owner 非空检查，唯一 `(owner, kind, id)`，额外 worker/store/parent 关联列及索引。kind 包含 device/catalog/conversation/message/command/outbox/run/run-ref/approval/event-position/cursor/idempotency/message-intent/approval-intent；读取都传 owner，并在业务层核对 worker/store/conversation |
| inbox | owner/worker/store/event_id、不可变正文、first_seq/last_seq/applied；事件 ID、store 序号与覆盖区间冲突检查 |
| browser_outbox | owner、服务端独立 ordinal 与浏览器事件；owner 索引分页。cursor 为 owner 范围内随机不透明 token，作用域、位置和 TTL 存 records，不向浏览器暴露数字位置 |

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
| §8 事件/cursor | Events.accept/references/project、Service.events/page/snapshot；缺口持久保存但不提前确认；连续事件/投影/浏览器 Outbox 同事务；omitted 不给浏览器；冲突不覆盖；快照和 cursor 同事务；过期 410，跨 owner/错误作用域 cursor 按契约 REMOTE_CURSOR_INVALID |
| §9 权威/审批 | Service.conversation/approval；持久 authority；四类高风险、Worker 禁止、不可远程批准及无法确定安全分类的 shell 拒绝 approve；允许 reject；已终态 Run 不接受批准；Worker 仍须再检 |
| §10 DTO/大小 | HTTP 和 Worker JSON 帧均用生成模型；wire.py 检查总 UTF-8 大小；分页在仓储限量读取，目录有界；不另写边界 DTO |
| §11 D42 | wire.py codec registry 与 test_protocol.py；包版本仅诊断，未知修订先协商拒绝；将来 N/N-1 codec 集中保留 |

## 设计取舍、未运行项与限制

- FastAPI 单进程模块化单体、owner 聚合记录仓储；内部 JSON 聚合不是第二套边界 DTO。SQLite 方言仅在仓储，未来数据库迁移保留仓储接口；多副本还需另做连接路由与栅栏。
- 事务内不等待网络。dispatching/sent 只表示可能发出，不表示接单；断线重传不改变 ID、序号、内容和 expiresAt。
- 密钥使用与账号认证隔离：只有标准库 scrypt/secrets/HMAC，无清单外依赖；设备 secret 只留不可逆验证值。短码重放必须再次提供 Worker secret。
- 浏览器仅 /events 轮询，无另加推送通道。所有 cursor owner/作用域/TTL 绑定；快照有界，更多历史走分页。
- 不提供远程 force-unfreeze。不自动删除关键 Inbox/skip/浏览器业务历史；README 写明磁盘监测与备份保留，不能为清理空间删待核对事实。
- 没有实际 P2/P3 服务参与联调，测试使用按生成 DTO 通信的假 Worker。Dockerfile/Caddyfile 已交付，但没有拉镜像、构建 Docker 镜像、申请证书或部署；这些未运行项没有声称通过。真实 uvicorn 已跑通。
- 根 workspace/CI 未改；Integrator 如需接入，使用 README 的串行 pytest、协议回归命令。没有修改其它应用、协议、docs 或共享根文件。

## 真实命令和输出

最终 pytest 在 `E:/OtherPro/HQAgent-Hub-worktrees/remote-server/apps/server` 执行：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q --basetemp=.tmp/final-verified -p no:cacheprovider
```

退出码 0。以下为真实输出末尾（进度点由工具分两次返回，此处仅列 warning 与统计）：

```text
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-server\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
68 passed, 1 warning in 30.75s
```

没有放宽/删除既有测试断言。warning 原样保留，未为去掉提示安装 httpx2。未开 pytest 并行 worker，验证串行。TEMP/TMP/--basetemp 都在 worktree 内被忽略的 .tmp；本次没有再触发默认临时目录 WinError 5，那是既知环境权限问题，不作为代码失败。

覆盖：双账号设备/对话/命令/事件/审批/Run 隔离、Worker 引用越权、配对过期/重放/撤销断连、Cookie/CSRF/认证泛化和限流、Q1 及落库脱敏、离线排序和 skip/gap、两类幂等、事件区间和连续 ack、store 冻结和旧 epoch、审批分级、D41 完成矩阵、事务故障回滚、游标分页/过期、Backup 恢复、26 路由 DTO 对照、线路协商/超帧/hello timeout、静态挂载、单调时钟和分批投递。测试文件逐项命名可独立复跑。

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
协议校验通过：258 个类型，109 个 Contract Fixture
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

open_questions：0。Q1 和 D42 已落实，未添加同名兼容字段或额外推送通道。
