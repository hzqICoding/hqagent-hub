# W1 × W5 契约冒烟（RD-1 前置）

| 项 | 值 |
| --- | --- |
| 日期 | 2026-09-06 |
| 执行 | W0 |
| 方法 | 起真实 W1 进程（`--data-dir` 指向 scratch），按 W5 Rust 代码的实际行为发请求 |
| 结论 | **发现 2 个 RD-1 阻断、2 个待办；契约本身对得上** |

## 为什么要做这个

W5 的安全验收是对着 `acceptance/hub_stub.py`（Python stub）跑的，W1 的 12 个测试是
对着 Starlette `TestClient` 跑的。**两边从来没有互相验证过。**

结果证明这一步是必要的：两个阻断级问题都只在真实进程上暴露，两边各自的测试都是绿的。

## 🔴 R1（阻断）protocol 包在 pytest 之外 import 不到，进程起不来

```
$ python -m runtime.main --data-dir ... --environment production
ModuleNotFoundError: No module named 'protocol'
```

原因：

- `packages/protocol/` 和 `packages/protocol/generated/` **都没有 `__init__.py`**，
  只有 `generated/python/__init__.py`。`protocol.generated.python` 靠 PEP 420
  隐式命名空间包成立，前提是 `packages/` 在 `sys.path` 上。
- `apps/hub/pyproject.toml` 的 `[tool.pytest.ini_options] pythonpath = [".", "../../packages"]`
  只对 pytest 生效。
- `dependencies` 里**没有任何对协议包的依赖**，`[tool.hatch.build.targets.wheel]`
  的 `packages` 只有 `["api", "core", "runtime", "storage"]`。

所以：**测试全绿，但装出来的 wheel 根本 import 不到 protocol，进程也起不来。**
本次冒烟靠临时设 `PYTHONPATH` 绕过。

RD-1 的定义是「Local Hub 鉴权、bootstrap/events、WS Ticket、Update Proxy、
drain/backup 端口**可运行**」——这条不解决，RD-1 过不了，W7 打包也做不了。

**建议解法**（需要 W0 + W1 共同决定，不要各自绕）：给 `packages/protocol` 加独立
`pyproject.toml` 做成可安装包，W1 用 workspace 路径依赖它。不要靠 `PYTHONPATH`
或 `sys.path` 注入——PyInstaller 打包时那些都不成立。

## 🔴 R2（阻断，已修）未声明 websockets，进程无法提供 WebSocket

`pyproject.toml` 依赖里是裸 `uvicorn`，没有 `websockets` 也没有 `wsproto`。
uvicorn 在没有 WS 实现时把 Upgrade 请求当**普通 HTTP** 处理，路由进 HTTP 应用后
被 Bearer 中间件拦成 401。

而 WS Ticket 机制存在的全部理由就是**原生 WebSocket 设不了 Authorization 头**
（D3 / `runtime-descriptor.json` 的 x-contract）。所以整条事件流在真实进程上不可用，
`ws-ticket` 端点、`WsTicketStore`、单次消费、4401 关闭码全是死代码。

**为什么测试发现不了**：Starlette `TestClient` 在进程内自己实现 WebSocket，
不经过 uvicorn 的 WS 层，所以 `test_ticket_is_single_use` 一直是绿的。
这正是 stub 测试和进程测试的差别。

已修：提交 `6ff9be7` 声明 `websockets>=15,<18`。装上后实测（**不带 Authorization 头**）：

```
首次用票 → HTTP/1.1 101 Switching Protocols
同票重放 → HTTP/1.1 403 Forbidden
伪造票   → HTTP/1.1 403 Forbidden
```

WS Ticket 设计本身是对的。

> 更正一处：最初怀疑是 Bearer 中间件对 WebSocket scope 也强制鉴权。实际
> `api/app.py:79` 的 `if scope["type"] != "http": await self.app(...)` 是放行的，
> 中间件没有问题。

## 🟡 R3 畸形 JSON 体返回 500

```
$ curl -X POST --data-binary '{not json' .../api/v1/auth/ws-ticket
status=500
```

应为 400 + `VALIDATION_FAILED`。这是未处理的异常路径，正常 JSON 体（含空体）都返回 200。

## 🟡 R4 Origin 被拒时的响应码不一致，且冻结注册表里没有对应错误码

| 传输 | 条件 | 实际 |
| --- | --- | --- |
| HTTP | 带正确 token + 非法 Origin | **401** `UNAUTHORIZED` |
| WebSocket | 非法 Origin 或坏票 | **403** |
| W5 的 `hub_stub.py` | 非法 Origin | **403** |

`packages/protocol/registry/error-codes.yaml` 里 `UNAUTHORIZED` 的描述是
「缺少或错误的 Bearer token；token 只能来自 hub.json」，**没有任何一个码是给
「Origin / Host 不在白名单」用的**。W1 只能复用 `UNAUTHORIZED`。

**这是 W0 的 FZ-1 遗漏，不是 W1 的错。** 新增错误码是相容变更（不破坏既有消费方），
建议在 FZ-2 一并补一个 `ORIGIN_NOT_ALLOWED`（403），并统一两种传输的语义。

对 W5 的实际影响为零——`runtime_descriptor.rs` 的 probe 只判 `!is_success()`，
不区分 401/403。但排障时把「没带 token」和「Origin 不对」混成同一个码会误导。

## ✅ 对得上的部分

### hub.json 与 W5 的 `deny_unknown_fields` 结构完全一致

```json
{
  "schemaVersion": 1,
  "instanceId": "hub_d3a7e9abe1724652b2a7c634629bdb9d",
  "port": 60684,
  "token": "TLDKvmkBZuZN0mDDG1bzb9sx0UXhSMlUIcEJiq6JBho",
  "pid": 27988,
  "baseUrl": "http://127.0.0.1:60684",
  "appVersion": "0.1.0",
  "protocolVersion": "0.1.0",
  "startedAt": "2026-09-06T12:29:38.909369Z"
}
```

逐条对 W5 `validate_common` 的校验：`schemaVersion == 1` ✅；
`instanceId` 长度 36 ≥ 8 且无空白 ✅；`port` 在 1024–65535 ✅；
`baseUrl` 精确等于 `http://127.0.0.1:<port>` ✅；`protocolVersion` 三段数字 ✅。

**⚠️ 一个脆弱边界**：W5 的 `valid_secret` 要求 token 长度 ≥ 43，而
W1 的 `secrets.token_urlsafe(32)` 正好产出 **43 字符**，卡在下限上。
现在能过，但 W1 若改成 `token_urlsafe(31)` 就会产出 42 字符，W5 会静默拒绝连接。
两边应该在文档里挑明这个耦合，或者 W1 直接用 `token_urlsafe(48)` 留出余量。

### 其余契约点

| 检查 | 结果 |
| --- | --- |
| `/healthz` 免鉴权 | 200，字段恰好是 `status/appVersion/protocolVersion/pid/startedAt`，无多余 |
| 无 token 打 `/api/v1/bootstrap` | 401 |
| W5 硬编码的 `Origin: http://tauri.localhost` | **被接受**，200 —— 这个常量两边对得上 |
| bootstrap 含 `instanceId` | ✅ W5 的防陈旧 probe 依赖它 |
| bootstrap 含 `maintenance` | ✅ |
| bootstrap **不含** `hubEndpoint` | ✅ token 未泄漏进响应体 |
| `ws-ticket` 的 `ttlSeconds` | 30，与 `WsTicket` schema 的 const 一致 |

## 复现命令

```bash
cd apps/hub
PYTHONPATH="<repo>/packages;<repo>/apps/hub" ../../.venv/Scripts/python.exe \
  -m runtime.main --data-dir <scratch> --environment production
# 另开一个终端，从 <scratch>/runtime/hub.json 读 baseUrl 与 token
```

`PYTHONPATH` 这一段在 R1 修好之后应当不再需要——如果还需要，说明 R1 没真修。
