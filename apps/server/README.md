# R1 Hub Server

账号认证、设备配对、命令排队、Worker 事件投影和浏览器轮询。服务端不调用模型，不保存模型凭据，不管理 AI 订阅或安装；所有执行发生在用户电脑的 Worker。

协议包：0.6.1；Worker 线路：修订 1。只实现 `remote-hub.v2.yaml` 的 26 个 HTTP 操作与 `/ws/v2/worker`。本机 v1 配对接口由 P2 实现。

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
| `HQREMOTE_RATE_LIMIT` | `30` | 每个来源地址、操作类别每 60 秒配额；登录、设备认证、配对和浏览器写入受限 |

Linux 数据目录应仅服务账号可读写（目录 0700，密钥 0600）；Windows 自定义数据目录需设置仅运行账号可访问的 ACL。备份数据库和 `server.key` 时同样保护；恢复同一实例需要原服务端密钥，否则原认证验证值和会话无法使用。密钥不可随镜像提交或生成在只读安装目录。

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

只运行一个应用进程、一个副本，不使用 uvicorn `--workers`/`--reload`、多副本负载均衡或多个活跃写服务。连接栅栏在单进程内管理；SQLite 仓储串行提交事务。账号创建、迁移检查与 Backup CLI 可通过 SQLite 锁与服务共存；正式升级时先停止服务。未来多实例部署需要数据库和连接路由一同迁移。

## P2 Worker 联调

1. Worker 本地生成至少 32 字节随机 secret（推荐 `secrets.token_urlsafe(32)`），自行安全持久保存。服务端不下发 secret。
2. 使用 `Authorization: Bearer <device-secret>` 和 `Idempotency-Key` 调用 `POST /api/v2/worker/pairing-requests`，JSON 为 `deviceName/workerStoreId/platform/architecture`。201 的 `RemotePairingChallenge` 给出五分钟有效的 8 位 `pairCode`。
3. 用户在已登录浏览器输入短码，先 `POST /api/v2/pairings/preview`，核对设备，再 `POST /api/v2/pairings/{pairRequestId}/confirm`。两个正文均只有 `pairCode`。浏览器响应没有短码和设备 secret。
4. Worker 使用原 secret 轮询 `GET /api/v2/worker/pairing-requests/{pairRequestId}`。0.6.1 的 `RemotePairingStatusView` 没有 `pairCode`。其它 secret 得到 NOT_FOUND。
5. 配对后主动连接 `/ws/v2/worker`，只使用 Authorization 头。不得把 secret 放进 URL、Cookie 或帧。10 秒内 hello：`wireRevision=1`，`protocolVersion` 填生成包常量，仅作诊断。读 `hello_ack` 后才能处理命令。
6. `capability.changed` 发布完整、有界的 workspace/scene 索引。创建远程对话前需至少成功发布一次目录；离线时允许根据最后索引创建对话。
7. 每 15 秒 heartbeat，45 秒无有效流量离线。新连接 fence 旧连接。事件用持久 store 序号，重传保留 eventId、epoch、occurredAt 和原内容；普通重启不得改写旧事件 epoch。不可见本地事件只上传 omitted 范围。
8. 服务端落事件、投影及浏览器 Outbox 后才 ack 连续前缀。缺口先缓冲；不可把最大观察 seq 当确认。Worker 自己必须校验 hello_ack 不高于本机持久分配高水位，不能用裁剪后 MAX(seq) 替代。
9. 断线重发 Command/skip 保持原 ID、正文、序号、期限。对于可能派发过但已过期的命令，服务端重传原命令供 Worker 查 Inbox/对账；P2 必须先查持久 Inbox，已接单返回原事实，未知且过期不得执行。服务端不会为重试延长 TTL。
10. `frozen` 不投递任何命令，包括 approve；观测事件仍可同步。换 store、跨 store ack、确认回退等触发持久冻结。R1 没有远程解除冻结接口：运营者核对本机 Inbox/实际执行记录；无证据时保持冻结，必要时显式撤销旧设备、换新 secret 配对并建新对话，不迁移旧命令。

Q1 裁决：短码只允许在面向发起 Worker 的挑战响应及合法同请求重放中返回；轮询按 DTO 返回（当前不含短码）。数据库只保存短码 HMAC 校验值；合法重放用请求中再次提供的设备 secret 和 challenge ID 重建短码，服务端数据库没有能独立恢复短码的设备 secret。日志、错误、浏览器响应和其它 Worker 响应均不返回短码。

## P3 浏览器联调

- 登录：`POST /api/v2/auth/login`，正文 `loginName/password`，精确 `Origin` 和 `Idempotency-Key`。成功通过 `Set-Cookie` 写入 `__Host-hqremote`，标记 Secure、HttpOnly、SameSite=Strict、Path=/、无 Domain。JSON 的 `csrfToken` 只用于 CSRF。
- 所有写请求都带 `Idempotency-Key`；登录后另带当前会话 `X-CSRF-Token`。用浏览器 Cookie 认证，不读取 Cookie、不持久化设备凭据；跨域请求不开放 CORS。
- `GET /auth/session` 返回已认证会话或 `authenticated=false`；`POST /auth/logout` 注销当前会话。登录轮换原会话；同登录意图安全重发同一 Cookie。
- `GET /devices` → `GET /devices/{workerId}/catalog` → `POST /conversations`。Conversation 固定 owner、设备、store、workspace、scene/version，authority=remote。
- 消息正文只含 `clientMessageId/text/sessionMode` 与可选 `expiresAt`。HTTP 202 是持久排队，不是运行成功。只有 run.submit 分配 conversationSeq；控制、审批和撤回不占槽。
- 首次读取选中对话 `/conversations/{conversationId}/snapshot`，保存同事务返回的 `serverCursor`；之后轮询 `/events?after=<cursor>&limit=100`。无 after 只返回当前尾游标与空 items。游标不透明，不能解析为 Worker seq；hasMore 时继续分页。410 重新取快照。
- 快照最多各含 100 个 message/run/command，`hasMore` 提醒继续取对应历史页；列表用 `cursor/limit`，不能混用列表游标和 events 游标。
- 分别展示 `deliveryState`、Worker 的 `controlResult`、Run `status`。断线不改 Run 状态，`command.completed` 不必然表示开发任务成功。
- 撤销设备立即禁止重连、断开连接并停止投递，但 `executionMayStillBeRunning=true`。未派发命令拒绝并留 skip；可能派发的保持对账状态。
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

R1 保留 Inbox、不可变 skip 和关键浏览器事件，暂不自动裁剪业务历史。游标会按 TTL 失效，运维应监测磁盘并按实例需求保留备份。不能为了清理磁盘删除尚未对账的关键结果或只恢复一部分业务表。

## 验证

在本目录，测试串行执行，不启用 pytest 并行 worker：

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TEMP = Join-Path $PWD '.tmp'
$env:TMP = $env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.tmp/pytest
../../.venv/Scripts/python.exe -B scripts/smoke.py
```

TEMP/TMP/`--basetemp` 必须指向 worktree 内被忽略的 `.tmp`，避免该 Windows 沙箱默认临时目录的 WinError 5。已有 Starlette 对 httpx TestClient 的弃用 warning 保留，不为消除警告安装清单外依赖。

`scripts/smoke.py` 串行创建临时账号，启动真实 loopback uvicorn，使用可信本机代理协议头模拟 TLS 终结后的后端连接，然后走登录、配对、假 Worker、离线重连及在线备份。它不访问远端服务器，也不证明 Caddy 证书或公网部署已验收。数据仅在本目录 `.tmp`，进程退出时检查输出不含凭据。

协议回归在仓库根目录运行 `pwsh scripts/protocol/validate.ps1 -CheckGenerated`。根 CI/workspace 未接线，Integrator 可后续将上述串行命令纳入 CI；本工作包不改共享配置。
