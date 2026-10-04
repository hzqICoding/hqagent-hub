# Local Hub 开发环境

## N0 本地对话版启动（vNext 后端分支）

先在仓库根创建独立环境；固定依赖见 `requirements.local-lock.txt`：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r apps/hub/requirements.local-lock.txt
.venv/Scripts/python.exe -m pip install --no-deps -e packages/protocol -e "apps/hub[test]"
```

在 `apps/hub` 目录启动开发服务：

```powershell
../../.venv/Scripts/python.exe -m runtime.main --environment development --port 8765 --data-dir E:/tmp/hqagent-n0-local
```

控制台显示本地URL和一次性连接码。前端开发服务器把 `/api` 代理到 `http://127.0.0.1:8765`，浏览器通过 `/api/v2/auth/local-session` 换取 HttpOnly Cookie，不读取Hub Token。连接码有效期10分钟，仅用一次；浏览器会话有效期30天，使用时滑动续期（每小时最多落盘一次），Hub重启后仍有效。用户数据目录的 `data/browser-sessions.db` 只保存会话摘要和到期时间，不保存会话密钥；最多保留20个会话，超出淘汰最早建立的会话。系统时钟回拨导致到期时间超出未来30天时，会话失效，需重新输入连接码。

生产同源访问可添加 `--web-dir <前端dist绝对路径>`；只有前端完成构建后才能使用该参数。N0支持HTTP事件补拉，`/ws/v2/local`尚未实现，前端不要依赖它。

CLI从Worker的PATH探测；可用 `HQAGENT_CODEX_PATH` / `HQAGENT_CLAUDE_PATH` 明确指定真实可执行文件。PowerShell函数/交互别名不是可执行文件，不会自动继承。Claude本批适配仅开放只读工具，写任务或宿主审批能力缺失会明确拒绝。

真实模型冒烟会消耗所选Agent的正常额度，且使用独立临时目录，不触碰用户项目：

```powershell
# 在仓库根执行
.venv/Scripts/python.exe -B scripts/e2e/local-chat-smoke.py --runtime codex --model <可用模型ID> --effort <可用等级>
```

当前前端开发与接口对接见[前后端交接手册](../../docs/前后端交接手册.md)，项目范围与交付说明见[项目文档](../../docs/项目文档.md)；`.hqagent/handoffs/N0-backend.md` 保留为历史交付记录。

W2、W3 两轮交付都卡在同一件事上：**测试环境无法从仓库配置重建**。
W3 是把 W1 的 `.venv` 整个拷过去再剔掉 editable `.pth`，W2 是直接借用
`w1-hub/.venv` 跑验收（见 `.hqagent/reviews/T-W3-orchestrator.md` W3-R2、
`.hqagent/reviews/T-W2-adapters.md` W2-R2）。

两次的测试结果都是真的，但 CI 上跑不起来——因为没有任何一份文件记录过
「这个环境怎么装出来」。这份 README 就是那份记录。

## 从零建环境

```powershell
cd <仓库根>
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip

# 协议包必须真装，不能靠 sys.path 碰巧找得到。
# apps/hub/pyproject.toml 的 pythonpath 故意不含 ../../packages，
# 就是为了让「协议包没装好」这种问题在测试里暴露出来（W1 的 R1 藏了整整一轮）。
.venv\Scripts\python.exe -m pip install -e packages/protocol
.venv\Scripts\python.exe -m pip install -e "apps/hub[test]"
```

网络受限时加国内镜像：

```powershell
.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e packages/protocol
```

**镜像装不下 Hatchling 构建依赖时，不要拷别人的 `.venv` 交差。**
如实报告装不上，把命令和真实报错写进 handoff——W2/W6 都是这么做的，这是对的。

## 改了协议之后必须重装

`pip install -e packages/protocol` 的 editable 对这个包**不是软链**——
它用 hatchling 的 force-include 把 `generated/`、`registry/` 等映射进 wheel 里的
`protocol/`，装出来是 site-packages 下的真实文件。所以重新生成协议之后
必须重装，否则代码里 import 到的还是旧的 DTO：

```powershell
.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps -e packages/protocol
```

症状是 `ImportError: cannot import name 'XxxInput' from 'protocol.generated.python'`，
而 schema 和 generated/ 里明明有。

## 跑测试

```powershell
cd apps/hub
..\..\.venv\Scripts\python.exe -m pytest -q
```

`pyproject.toml` 的 `testpaths` 已经包含四组：

| 路径 | 归属 | 说明 |
| --- | --- | --- |
| `tests/` | W1 | Hub 核心 API / 存储 / 排空 |
| `adapters/tests/` | W2 | Adapter 契约（D17–D22） |
| `orchestrator/tests/` | W3 | Role Resolver / 编排 / Session |
| `security/tests/` | W3 | 权限 / 路径 / Worktree |

分支上还没合进来的目录会被 pytest 自动跳过，所以这份配置在合并前后都能用。

**不要把 W2/W3 的测试搬进 `apps/hub/tests/`**——那是 W1 的独占路径，
搬过去就破坏了路径所有权，也让「谁的测试挂了」变得看不出来。

## 一条真握手的测试要单独说

`tests/test_ws_close_codes_real_handshake.py` 会真起一个 uvicorn 并用真
`websockets` 客户端连上去。它比其他测试慢（约 12 秒），但不能换成
`TestClient`——TestClient 在进程内自实现 WebSocket，不走 HTTP 握手，
这一类问题它结构上就测不出来。已经吃过两次亏：

- 裸 uvicorn 缺 `websockets` 实现时 `/events/stream` 完全不可用，整套 TestClient 测试全绿
  （`.hqagent/reviews/INT-smoke-W1xW5.md`）
- WS 关闭码发在 `accept()` 之前时全部退化成 HTTP 403，浏览器只拿得到 1006
  （`.hqagent/reviews/INT-ws-close-codes.md`）

## 打包注意

`[tool.hatch.build.targets.wheel]` 的 `packages` 必须包含
`adapters`、`orchestrator`、`security`，否则 PyInstaller 打包时这三个包不进产物。
新增顶层包时记得同步这里——W1 的 R1 就是漏了 `protocol` 导致进程起不来。

## 撤销本机浏览器会话

退出登录会撤销当前浏览器会话。需要让所有浏览器重新连接时，在 `apps/hub` 下运行：

```sh
python -m runtime.pair --revoke-sessions
# 自定义数据目录时，与 Hub 启动参数一致：
python -m runtime.pair --data-dir /path/to/hub-data --revoke-sessions
```

使用 Hub 所在虚拟环境的 Python。该命令要求 Hub 正在运行，读取本机 descriptor 后向 loopback 内部接口发送请求，不显示令牌。它仅撤销本机浏览器会话，不解绑远程设备，也不撤销一次性连接码。连接码仍有效10分钟、只能兑换一次、最多尝试10次，并且仅在交互终端显示。

## 修复远程同步冲突冻结

仅当 Hub 本机因 `REMOTE_SYNC_CONFLICT` 冻结、相关生产者问题已修复时，由电脑操作者使用正在运行的 Hub 执行：

```sh
python -m runtime.cli --data-dir /path/to/hub-data remote resync --confirm-reset
python -m runtime.cli --data-dir /path/to/hub-data remote status
```

命令复用本机 descriptor 的 operator Token，不需要重新配对。必须显式确认：服务器确认设备 `ready` 后，会清除该电脑的云端副本和原生索引，再从电脑完整补传；期间手机列表/历史可能暂时不完整。电脑源文件、对话、消息、执行结果及配对凭据不删除。未获 grant 的送达预留按现有 reset 规则释放；不会重新执行历史命令。云端附件随副本删除后按既有上传规则重建，本机缺失的文件无法凭空恢复。

这是异步操作，`requested=true` 只表示恢复请求已持久保存。关闭同步会取消恢复流程。`STORE_CHANGED`、`ACK_CONFLICT`、身份/凭据问题等冻结不接受此命令；重新握手时服务端仍冻结的，也不会执行 reset。不要通过编辑数据库把 link 改回 paired，旧冲突 Outbox 会再次被拒绝。
