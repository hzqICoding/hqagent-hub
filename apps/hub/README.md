# Local Hub 开发环境

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
