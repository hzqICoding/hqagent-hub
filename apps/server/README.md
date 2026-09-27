# R1.5 Hub Server

账号认证、设备配对、电脑对话的完整副本、在线命令转发和浏览器轮询。电脑是唯一写入和执行方；服务端不调用模型，不保存模型凭据，不管理 AI 订阅或安装。

协议包：0.7.0；Worker 线路支持修订 1、2。实现 `remote-hub.v2.yaml` 的 27 个 HTTP 操作与 `/ws/v2/worker`。修订 1 保留历史对账，新浏览器写入要求修订 2：离线立即失败，在线命令通过 30 秒收件/grant 门闩送达。D44 本机路由仍属于 P2，D45 待处理审批快照保留。

## 启动与配置

Python 3.11+，单应用进程。依赖见 `requirements.txt`，协议包必须安装同仓库冻结版本。开发工作区已有 `.venv`，本次交付没有联网安装依赖。

Windows 开发环境，在本目录运行：

```powershell
$env:HQREMOTE_ORIGIN = 'https://hub.example.com'
# 默认数据在用户 LOCALAPPDATA 下，不写程序安装目录。
../../.venv/Scripts/python.exe -m server.cli migrate
../../.venv/Scripts/python.exe -m server.cli create-account --login alice --display-name Alice
../../.venv/Scripts/python.exe -m server
```

创建账号时交互输入口令，最少 12 字符，最多 1024 字符。自动化使用 `--password-stdin`，只从标准输入第一行读取。没有 `--password` 参数、公开注册路由或默认账号密码。不要把口令写入 shell 历史、命令参数、CI 日志或项目文件。

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `HQREMOTE_ORIGIN` | `https://localhost` | 浏览器精确 Origin，必须 HTTPS，不含路径、查询或末尾 `/` |
| `HQREMOTE_DATA_DIR` | Windows `%LOCALAPPDATA%/HQAgent-Hub/remote-server`；Linux `${XDG_DATA_HOME:-~/.local/share}/hqagent-hub/remote-server` | `hub.sqlite3` 与首次初始化生成的 `server.key` |
| `HQREMOTE_KEY_FILE` | 数据目录下 `server.key` | 32 字节以上服务端密钥文件；用于不可逆认证验证值及 Cookie/CSRF 认证，与设备 secret 无关 |
| `HQREMOTE_HOST` | `127.0.0.1` | uvicorn 监听地址 |
| `HQREMOTE_PORT` | `8080` | uvicorn 端口 |
| `HQREMOTE_PROXY_IPS` | `127.0.0.1` | 可信反向代理来源；只信任实际代理，不使用 `*` |
| `HQREMOTE_STATIC_DIR` | 未配置 | 可选 H5 构建目录；未配置时不挂静态站点 |
| `HQREMOTE_SESSION_TTL` | `86400` | 浏览器会话有效期（秒） |
| `HQREMOTE_CURSOR_TTL` | `86400` | 浏览器游标有效期（秒），失效后 410，重新取快照 |
| `HQREMOTE_BROWSER_RETENTION_SECONDS` | `604800`（7 天） | browser_outbox 保留期（正整数秒）；低频清理后旧位置返回 410 |
| `HQREMOTE_SYNC_MESSAGE_BYTES` | `16777216`（16 MiB） | 单条完整消息的显式资源配额，超额失败，不截断正文 |
| `HQREMOTE_SYNC_STAGING_BYTES` | `134217728`（128 MiB） | 每 worker/store 未拼齐分段的字节配额 |
| `HQREMOTE_RATE_LIMIT` | `30` | 每个来源地址、操作类别每 60 秒配额；登录、设备认证、配对和浏览器写入受限 |

Linux 数据目录应仅服务账号可读写（目录 0700，密钥 0600）；Windows 自定义数据目录需设置仅运行账号可访问的 ACL。备份数据库和 `server.key` 时同样保护；恢复同一实例需要原服务端密钥，否则原认证验证值和会话无法使用。密钥不可随镜像提交或生成在只读安装目录。

配置 H5 目录后，真实静态文件正常返回；不存在、最后一段无扩展名的 GET 路径（例如 `/remote/chat`）回退到 `index.html`，支持 history 路由刷新。`/api/`、`/ws/` 命名空间不参与回退，未知 API 保持 ApiEnvelope 404；缺失的 `.js`、`.css` 等资源仍返回 404。

`python -m server` 内部启动 uvicorn，并禁用传输层访问日志；应用只记录固定操作名、HTTP 状态或固定错误码，不输出请求体、头、URL 查询或异常输入。不要启用 HTTP/WS 调试日志。反向代理也不要记录认证头、Cookie、请求体或带凭据的查询参数。所有认证和配对响应有 `Cache-Control: no-store`。

## TLS、自部署与 Docker

采用 `Caddyfile.example`，将域名替换为自己的域名。Caddy 负责证书、HTTPS 和 WSS 升级，转发给 `127.0.0.1:8080`。远程 API 的 Origin 必须与 `HQREMOTE_ORIGIN` 一致。设备接口要求 HTTPS；Worker 要求 WSS。uvicorn 仅信任配置的代理转发协议头。

也可用 Nginx 终结 TLS，代理配置需包含：

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 60s;
    access_log off;
}
```

同一份镜像同时用于运营部署与用户自部署。以下是供用户执行的示例；本工作包没有实际构建镜像、部署或连接服务器。

```sh
# 仓库根目录构建；构建环境需要依赖仓库或预先准备的离线镜像。
docker build -f apps/server/Dockerfile -t hqremote:0.1 .
docker volume create hqremote-data
# Linux host networking，保持应用监听 127.0.0.1；宿主机运行 Caddy。
docker run -d --name hqremote --network host \
  -e HQREMOTE_ORIGIN=https://hub.example.com \
  -v hqremote-data:/data hqremote:0.1
docker exec -it hqremote python -m server.cli create-account --login alice --display-name Alice
```

镜像使用非 root UID/GID 10001。自备 bind mount 时先为该账号配置数据目录权限。使用 bridge 网络时需显式配置 `HQREMOTE_HOST=0.0.0.0`，端口仅发布到宿主机 `127.0.0.1:8080:8080`，并把 `HQREMOTE_PROXY_IPS` 精确设为容器实际看到的代理地址。

**宿主机 Caddy + bridge 容器的可信来源配置**：容器看到的是转发/NAT 后的 TCP 来源，通常为 bridge 网关（例如 `172.17.0.1`），不是宿主机的 `127.0.0.1`。先查看选用网络的网关：

```sh
docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}'
```

网关只是候选值，Docker Desktop、rootless 和自定义网络可能不同。可在同一 Docker 网络上用临时端口实测 TCP peer；以下诊断仅打印来源 IP，不发送任何认证信息：

```sh
# 终端 1：bridge 替换为服务实际使用的网络；收到一次连接即退出。
docker run --rm --network bridge -p 127.0.0.1:18080:18080 \
  --entrypoint python hqremote:0.1 -u -c \
  'import socket; s=socket.socket(); s.bind(("0.0.0.0",18080)); s.listen(1); c,a=s.accept(); print(a[0]); c.close()'
# 终端 2：从运行 Caddy 的宿主机连接此端口。
python -c 'import socket; socket.create_connection(("127.0.0.1",18080)).close()'
```

若实测为 `172.17.0.1`，应用容器设置 `HQREMOTE_PROXY_IPS=172.17.0.1`，同时使用 `HQREMOTE_HOST=0.0.0.0` 与 `-p 127.0.0.1:8080:8080`。不要原样照抄示例 IP，不信任 `*` 或整个共享容器网段。上面的 Linux **host networking** 示例共享宿主机网络命名空间，Caddy 确实经 `127.0.0.1` 连接时才继续使用默认 `127.0.0.1`。

配置过窄/错误会使 uvicorn 忽略 `X-Forwarded-Proto`，后端把代理后的请求视为 HTTP，出现认证拒绝或 WSS 连接失败；配置过宽则允许不可信来源伪造 `X-Forwarded-For` 绕过来源限速，甚至伪造 HTTPS 判断。代理必须根据真实连接重设 `X-Forwarded-Proto`/`X-Forwarded-For`，不能直接透传客户端自报值。上面的 Nginx 例子按单层代理重设这两个头。应用端口不向公网发布。

只运行一个应用进程、一个副本，不使用 uvicorn `--workers`/`--reload`、多副本负载均衡或多个活跃写服务。连接栅栏在单进程内管理；SQLite 仓储串行提交事务。账号创建、迁移检查与 Backup CLI 可通过 SQLite 锁与服务共存；正式升级时先停止服务。未来多实例部署需要数据库和连接路由一同迁移。

## 已知限制

所有 SQLite 操作仍在事件循环线程中同步执行。R1 的单进程、低负载使用可以接受，但慢磁盘、大事务、迁移或首次大量保留期清理会阻塞同进程 HTTP/WSS；事件驱动投递消除了 100ms 空转，并不等于数据库已异步化。

后续迁移方向：在仓储边界把**完整事务单元**交给专用数据库线程/执行器，保持连接线程归属、事务串行性和提交后通知，不能把同一事务的单条 SQL 分散到任意线程。更大负载再替换为 PostgreSQL 仓储及异步连接池，并配套持久投递通知、跨进程连接路由/栅栏。届时用真实负载验证事件循环延迟和锁等待；本版不宣称支持多进程写服务。

每个 Worker 连接由提交后的唤醒信号驱动投递，接收帧与等待唤醒并发进行；每批最多 16 帧，保留固定节奏的 5 秒兜底，即使持续有心跳也不会推迟补投。过期检查只解码该 Worker 的 queued 且到期命令，投递只解码未完成 Outbox。协议的 15 秒心跳、45 秒离线及旧连接隔离语义不变。

## P2 Worker 联调

1. Worker 本地生成至少 32 字节随机 secret（推荐 `secrets.token_urlsafe(32)`），自行安全持久保存。服务端不下发 secret。
2. 使用 `Authorization: Bearer <device-secret>` 和 `Idempotency-Key` 调用 `POST /api/v2/worker/pairing-requests`，JSON 为 `deviceName/workerStoreId/platform/architecture`。201 的 `RemotePairingChallenge` 给出五分钟有效的 8 位 `pairCode`。
3. 用户在已登录浏览器输入短码，先 `POST /api/v2/pairings/preview`，核对设备，再 `POST /api/v2/pairings/{pairRequestId}/confirm`。两个正文均只有 `pairCode`。浏览器响应没有短码和设备 secret。
4. Worker 使用原 secret 轮询 `GET /api/v2/worker/pairing-requests/{pairRequestId}`。当前 `RemotePairingStatusView` 没有 `pairCode`。其它 secret 得到 NOT_FOUND。
5. 配对后主动连接 `/ws/v2/worker`，只使用 Authorization 头。不得把 secret 放进 URL、Cookie 或帧。10 秒内 hello：优先 `wireRevision=2`，`protocolVersion` 填生成包常量，仅作诊断。CODECS[1]/[2] 分开校验；拒绝帧公布 `[1,2]`，不能改写持久帧的修订或 hash。
6. `capability.changed` 发布完整、有界的 workspace/scene 索引。旧 rev1 未决命令、未确认 skip、事件缺口或未核对确认位置阻止升级；先通过 rev1 对账，再持久切换水位。已切换为 2 的设备不自动降级。离线先报 REMOTE_DEVICE_OFFLINE，旧线路在线的新写入报 REMOTE_REVISION_REQUIRED。
7. 每 15 秒 heartbeat，45 秒无有效流量离线。新连接 fence 旧连接。事件用持久 store 序号，重传保留 eventId、epoch、occurredAt 和原内容；普通重启不得改写旧事件 epoch。不可见本地事件只上传 omitted 范围。
8. 服务端落事件、投影及浏览器 Outbox 后才 ack 连续前缀。缺口先缓冲；不可把最大观察 seq 当确认。Worker 自己必须校验 hello_ack 不高于本机持久分配高水位，不能用裁剪后 MAX(seq) 替代。
9. 修订 2 首次命令只有至多 30 秒的 deliverBy。Worker 持久化不可调度的收件/预留，回 command.received；服务端验证摘要、绑定和期限，在同一事务提交不可逆 delivery_granted，Worker 才能正式接单。普通 ACK 不授权。deadline 先到且无 grant 则 failed/REMOTE_DELIVERY_EXPIRED，迟到 received 仍连续确认但不 grant；已有 grant 不因丢 accepted 或计时器而误判失败。重传保持原 ID、摘要和期限；真正执行或拒绝仍由 Worker 回报。
10. `frozen` 不投递任何命令，包括 approve；观测事件仍可同步。换 store、跨 store ack、确认回退等触发持久冻结。R1 没有远程解除冻结接口：运营者核对本机 Inbox/实际执行记录；无证据时保持冻结，必要时显式撤销旧设备、换新 secret 配对并建新对话，不迁移旧命令。

### 修订 2 同步与忙碌

- `sync.conversation.upserted` 保存电脑元数据并向 owner 发布 `conversation.updated`；从可见改为 pc_only 发无正文 `conversation.deleted`，不把隐藏元数据发给浏览器。`sync.run.state` 保存实际运行投影并通知对应可见对话刷新。
- 所有本机 conversation/message/run/approval ID 按 owner、worker、store、localId 映射为公开 ID。浏览器只使用公开 ID；下行 public conversationId 与 localConversationId、payload 内本机 run/approval ID 不能混用。相同 UUID 出现在两台电脑也不会串数据。
- `sync.message.segment` 按 generation/message/revision 拼接，每片 ≤16000 码点、≤64000 UTF-8 字节、整帧 ≤256 KiB；元数据/重复片必须一致。收齐后流式校验字节数和 SHA256，再一次性发布完整消息；旧完整版本可保持可见直到新版本拼齐。每消息最多 4096 片、每 store 暂存最多 16384 片，另受上表字节配额约束；配额故障为 REMOTE_SYNC_RESOURCE_LIMIT，不确认失败位置，不截断。
- `sync.backfill.progress` 校验批次、水位、每批 ≤100 内容事件/1 MiB 和 complete 前无未拼齐消息；只有连续应用后内部状态才标记补齐。当前协议没有公开 syncStatus 字段，服务端不另造字段。完整电脑补传完成后，未被电脑确认的旧 R1 服务器独有对话影子退出副本；历史命令及哈希仍保留对账。
- `sync.busy.snapshot` 是当前 connection/epoch 的完整集合，分片收齐且连续应用后整体覆盖，空集合清空旧 busy。重连/服务端重启、新快照未齐时 busyFresh=false。服务端和手机都不持锁；只有新 run.submit 检查 busy/fresh，取消、其它控制和拒绝审批不依赖它们，但仍需在线和真实权限。
- reset/电脑删除/撤销立即清理对应副本、暂存、可重放正文及旧 Inbox 的正文；删除意图可先于连续 ACK 生效。ContentRedaction 按原 eventId/seq/hash 补齐允许的内容槽，不能覆盖 grant、收件、控制结果、busy 或另一对话，旧正文晚到只比对原 hash，不复活副本。
- 删除不抹去执行许可与去重事实。幂等记录保留摘要/退休标记，重新开启同步也不会重跑旧意图；已 grant 不撤销。没有 grant 的过期/退役序号槽保存 skip，物理写过 socket 不等于获得执行许可；不能把这个修订 2 规则套到 rev1 的不明确执行状态。

Q1 裁决：短码只允许在面向发起 Worker 的挑战响应及合法同请求重放中返回；轮询按 DTO 返回（当前不含短码）。数据库只保存短码 HMAC 校验值；合法重放用请求中再次提供的设备 secret 和 challenge ID 重建短码，服务端数据库没有能独立恢复短码的设备 secret。日志、错误、浏览器响应和其它 Worker 响应均不返回短码。

## P3 浏览器联调

- 登录：`POST /api/v2/auth/login`，正文 `loginName/password`，精确 `Origin` 和 `Idempotency-Key`。成功通过 `Set-Cookie` 写入 `__Host-hqremote`，标记 Secure、HttpOnly、SameSite=Strict、Path=/、无 Domain。JSON 的 `csrfToken` 只用于 CSRF。
- 所有写请求都带 `Idempotency-Key`；登录后另带当前会话 `X-CSRF-Token`。用浏览器 Cookie 认证，不读取 Cookie、不持久化设备凭据；跨域请求不开放 CORS。
- `GET /auth/session` 返回已认证会话或 `authenticated=false`；`POST /auth/logout` 注销当前会话。登录轮换原会话；同登录意图安全重发同一 Cookie。
- `GET /devices` → `GET /devices/{workerId}/catalog` → `GET /conversations?workerId=...&workspaceId=...`。列表按最近活动降序，展示 visibility/busy/busyFresh/项目。authority 只表示历史来源，不再是写入门禁。
- `POST /conversations` 和 `PATCH /conversations/{id}` 都返回 202 RemoteQueuedReceipt；PATCH 带 expectedVersion 和至少一项 title/archived/visibility。下发电脑执行并等待同步 upsert 才出现或更新投影，不能收到 202 就当作创建/修改成功。
- 消息正文只含 `clientMessageId/text/sessionMode` 与可选 `expiresAt`。HTTP 202 是在线送达尝试，不是运行成功。离线不分配序号、不建离线队列；客户端 expiresAt 不能延长 30 秒送达期限。仅 run.submit 占远程传输 conversationSeq，所有消息显示顺序取电脑 messageSequence，两者互不代替。
- visibility 只影响显示，pc_only 仍完整上传存储，但所有浏览器列表、直接 ID、运行、审批、快照和事件都过滤，直接访问返回 NOT_FOUND。只用于清缓存的删除 tombstone 可带旧公开 ID，无标题或正文。
- 首次读取选中对话 `/conversations/{conversationId}/snapshot`，保存同事务返回的 `serverCursor`；之后轮询 `/events?after=<cursor>&limit=100`。无 after 只返回当前尾游标与空 items。游标不透明，不能解析为 Worker seq；hasMore 时继续分页。410 重新取快照。
- 游标为无状态签名值，绑定 owner、scope、position、expiresAt；事件游标另绑定签名中的清理世代。生成/验证不写 cursor 行，不随轮询次数增长。验签失败或 owner/作用域不符返回 REMOTE_CURSOR_INVALID；TTL 到期或其位置已裁剪返回 REMOTE_CURSOR_EXPIRED。升级前的旧随机 cursor 不迁移，客户端应重新取快照。
- 消息 GET 返回 RemoteSyncMessagePage，默认最新完整消息优先；用 before 向前翻页，返回稳定的 snapshotCursor。签名绑定 owner/worker/store/对话/同步代次、截止序号和独占边界；新消息不挪动旧页偏移。客户端按 messageId+messageRevision 合并并按 messageSequence 排序，延迟补齐的旧消息也可从 message.appended 插入正确位置。reset 后旧分页游标失效，重新加载。
- 快照最多各含 100 个 message/run/command，消息为最新页；消息/事件页同时使用约 32 MiB 的响应组装预算（至少返回一条完整消息），可少于请求 limit 并正确给出 hasMore，绝不截断单条正文。其它列表用 cursor/limit，不混用列表、消息和 events 游标。
- D45 快照还带 `approvals`：只含同 owner/对话下仍 pending、未确认消费、且 `expiresAt` 严格晚于快照 `observedAt` 的审批。先筛选再取最多 100 条，超出时合并设置 `hasMore`；本版没有审批分页路由，不能把截断集合显示为全部审批。高风险 pending 仍可见并允许 reject，不能 approve。浏览器应以快照替换待处理集合，再按 `serverCursor` 后的审批事件维护；202/accepted 不代表审批已消费，实际消费/终态或到期后移除。
- 分别展示 `deliveryState`、Worker 的 `controlResult`、Run `status`。断线不改 Run 状态，`command.completed` 不必然表示开发任务成功。
- 撤销设备立即禁止重连、断开连接并清除这台设备的副本；`executionMayStillBeRunning=true`，不声称本机任务已停止。已 grant/accepted 的事实保留，无 grant 的意图退役。
- 高风险或 Worker 禁止动作不允许远程 approve，允许 reject。服务端预检后 Worker 仍须核对真实 pending 请求及当前本机策略。

## 备份与升级

```powershell
# 目标必须不存在；可在服务运行中创建一致性快照。
../../.venv/Scripts/python.exe -m server.cli backup E:/secure-backups/hub-20260926.sqlite3
```

该命令调用 `sqlite3.Connection.backup()`。不能直接复制正在写入的 `hub.sqlite3`，也不能省略 WAL 冒充一致性快照。`server.key` 是单独的稳定密钥文件，需另行安全备份并记录与数据库快照的对应关系。

升级步骤：

1. 先用 Backup CLI 生成一致性数据库快照，保存当前程序/镜像版本与密钥备份。
2. 停止应用进程，保留持久数据卷。更换服务端程序和匹配协议包。
3. 同一服务账号运行 `python -m server.cli migrate`；拒绝打开比当前程序更新的 schema。迁移入口位于 `repository.py`，`PRAGMA user_version` 独立于包版本和 wireRevision。
4. 启动一个进程，经 TLS 代理验证 session、配对状态、Worker hello 和浏览器 snapshot/events。勿把 smoke 测试数据导入正式库。
5. 回滚先停止应用；在离线数据目录恢复一致性备份及匹配密钥，移除旧库的 WAL/SHM 文件后启动匹配旧程序。不能用运行中的数据库文件覆盖。服务端确认位置回退后 Worker 应拒绝裁剪并对账，不得为恢复而绕过冻结。

schema 1→2 为 queued 命令及未完成 Outbox 增加索引；2→3 增加认证过期与浏览器清理水位；3→4 增加电脑消息顺序索引、sync_ids、sync_log、sync_segments。升级本身不改旧命令/事件修订和 hash；删除内容时保留身份/hash/序号及无正文执行证据。

后台每 5 秒清理到期 session、rate、旧 cursor 行，以及超出 `HQREMOTE_BROWSER_RETENTION_SECONDS` 的 browser_outbox；不在 HTTP 请求路径执行清理。每个 owner 仅维护一行清理水位/世代，事件全部删空也不重置 tail，旧边界游标返回 410，清理后新快照的游标仍有效。不同 owner 的清理相互隔离。

周期保留期清理不删除 Inbox 去重证据、命令、消息、Run/审批事实、skip 或幂等摘要。R1.5 的显式电脑删除、sync reset、撤销则会真正删除对应在线逻辑表中的副本正文，而非仅隐藏；无正文去重证据与已持久许可仍保留。普通 DELETE 不保证物理擦除 SQLite 空闲页、WAL 或历史备份；备份销毁/磁盘处理需要单独的运维生命周期，不能把本实现说成已抹除所有历史备份。

## 验证

测试依赖单独声明在 `pyproject.toml` 的 `test` extra，不加入运行时 requirements。准备新的开发/集成环境时，在仓库根目录安装：

```sh
python -m pip install -r apps/server/requirements.txt -e packages/protocol -e "apps/server[test]"
```

离线环境需事先准备完整 wheelhouse 和构建工具；不允许回退到网络下载：

```sh
python -m pip install --no-index --find-links <wheelhouse> --no-build-isolation \
  -r apps/server/requirements.txt -e packages/protocol -e "apps/server[test]"
```

pytest 8.4.2、httpx 0.28.1 与 `apps/hub/requirements.local-lock.txt` 一致。该锁文件当前没有 PyYAML 项，测试 extra 固定使用已验证环境中的 PyYAML 6.0.3；未改 Hub 锁文件。当前 worktree 已预装测试依赖，本轮仅按要求离线重装协议包，未执行上述联网安装。

在本目录，测试串行执行，不启用 pytest 并行 worker：

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.tmp/pytest
../../.venv/Scripts/python.exe -B scripts/smoke.py
```

TEMP/TMP/`--basetemp` 必须指向 worktree 内被忽略的 `.tmp`，避免该 Windows 沙箱默认临时目录的 WinError 5。已有 Starlette 对 httpx TestClient 的弃用 warning 保留，不为消除警告安装清单外依赖。

`scripts/smoke.py` 串行创建临时账号，启动真实 loopback uvicorn，使用可信本机代理协议头模拟 TLS 终结后的后端连接，走登录、配对、修订 2 假 Worker、create/received/grant/upsert、完整回复同步、离线立即失败、重连 busyFresh 重建及在线备份。不访问远端服务器，也不证明真实 Worker/Caddy 证书或公网部署已验收。数据仅在 `.tmp`，退出时检查输出脱敏。

历史测试的 `env` 夹具仅在测试构造期间装入原 R1 Service 和旧响应绑定，保留旧离线排队、201 创建等历史语义断言；它不是可由配置打开的生产模式。`r15_env` 和全部 test_r15_* 使用正式 create_app/SyncService，验证新 HTTP 准入、映射、grant、复制和删除。正式应用不接受新 rev1 浏览器命令。版本协商旧测试中“不支持的修订 2”改为 3，拒绝支持列表更新为 [1,2]，另有真实 rev1 历史对账/升级栅栏用例。

协议回归在仓库根目录运行 `pwsh scripts/protocol/validate.ps1 -CheckGenerated`。根 CI/workspace 未接线，Integrator 可后续将上述串行命令纳入 CI；本工作包不改共享配置。
