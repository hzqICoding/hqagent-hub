# INT 发现：WS 三个关闭码在真实客户端上全部不可见

| 项 | 值 |
| --- | --- |
| 发现方 | W0（架构/审核） |
| 日期 | 2026-09-06 |
| 影响包 | W1（`apps/hub/api/app.py`）、W4（F3 验收） |
| 严重性 | 🔴 阻塞 §22.3 的 `EVENT_CURSOR_EXPIRED` 验收项，并使裁决 D23 在实践中失效 |

## 现象

`api/app.py:380-409` 三处 `websocket.close(code=...)` 全部发生在
`websocket.accept()`（`:396`）**之前**：

```python
if not valid_boundary:
    await websocket.close(code=4403)   # 来源不对
    return
if not ticket_store.consume(ticket):
    await websocket.close(code=4401)   # 票不对
    return
try:
    async with event_store.broker.subscribe() as queue:
        replay = event_store.page(...)  # ← 游标过期在这里抛
        await websocket.accept()        # ← accept 在抛出点之后
        ...
except HubError:
    await websocket.close(code=4410)   # 游标过期
```

按 ASGI 规范，`accept` 之前发 `websocket.close` 会被服务器翻译成 **HTTP 握手拒绝**，
关闭码在握手层就被丢弃。客户端拿到的是一个失败的 HTTP 响应，不是带码的 WS 关闭帧。

## 实测证据

用真 uvicorn + 真 `websockets` 客户端（不是 Starlette TestClient）探测：

```text
BAD_TICKET  -> InvalidStatus: server rejected WebSocket connection: HTTP 403
BAD_ORIGIN  -> InvalidStatus: server rejected WebSocket connection: HTTP 403
GOOD_TICKET -> CONNECTED (ok)
```

坏票和坏 Origin **返回了完全相同的 HTTP 403**，4401 和 4403 的区别彻底消失。
浏览器里对应的是 `ws.onclose` 拿到 code **1006（abnormal closure）**，没有任何可区分信息。

## 后果

1. **裁决 D23 在实践中失效。** D23 的原文是「来源不对与票不对是两回事，关闭码要分开，
   否则前端和排障都分不清是 Origin 配错了还是票过期/被重放了」。代码确实分开写了，
   但两个码都到不了对端。
2. **§22.3 的这条验收项无法实现**：「收到 `EVENT_CURSOR_EXPIRED` 后重新
   bootstrap/Snapshot，界面不继续显示不完整的过期增量状态」。
3. **前端会陷入无限失败重连**：`local-hub-gateway.ts` 的 `ws.onclose` 只能看到 1006，
   于是带着同一个过期 `after=` 退避重连，永远失败。

## 为什么两套测试都是绿的

同上一轮 smoke test 抓到的「缺 `websockets` 依赖」是**同一类盲区**：
Starlette 的 `TestClient` 在进程内自实现 WebSocket，不经过真实握手，
close code 被直接交给调用方。而 `test_ticket_is_single_use`
（`tests/test_api_security.py:35-52`）只断言「抛了异常」，没断言码：

```python
except Exception:
    replay_rejected = True
assert replay_rejected
```

## 更正我自己先前的两处结论

1. `.hqagent/reviews/T-W4-frontend.F2.md` 的 F2-R2 写「W1 侧根本不产生
   `EVENT_CURSOR_EXPIRED`」——**错了**。`storage/events.py:121-135` 实现了保留窗口
   校验，抛 `EVENT_CURSOR_EXPIRED` 并带 `snapshotUrl` / `oldestAvailableSeq` /
   `latestSeq`，`app.py:409` 也确实关 4410。生产者是有的，是**信道把它丢了**。
   我当时的 grep 是 `"EVENT_CURSOR_EXPIRED\|4401\|4403\|cursor"`，漏了 4410。
2. 同文件里建议 W1「新增一个专用关闭码 4410」——已经有了，不用加。真正要改的是
   **发送时机**。

## 改法

`accept()` 提前到所有校验之前，改成「先接受、再发一条错误帧、再带码关闭」：

```python
await websocket.accept()
if not valid_boundary:
    await websocket.close(code=4403, reason="ORIGIN_NOT_ALLOWED")
    return
if not ticket_store.consume(ticket):
    await websocket.close(code=4401, reason="TICKET_INVALID")
    return
```

游标过期同理：`accept()` 之后再调 `event_store.page()`，把 `HubError.detail`
（含 `snapshotUrl` / `oldestAvailableSeq`）先 `send_json` 出去再 `close(4410)`——
前端拿得到 `snapshotUrl` 才知道去哪重取，光有个码还不够。

### 这个改动的代价，明写出来

`accept()` 提前意味着**未通过校验的对端也会被短暂接受**（毫秒级，随即关闭）。
判断这是可接受的：

- 监听面是 `127.0.0.1` 且有 Host/Origin 双重校验，非本机根本连不上；
- Ticket 是一次性 + 30 秒 TTL，接受本身不泄露任何数据（没有 `send` 任何业务内容）；
- 这是 WebSocket 协议下**唯一**能把应用级关闭码送到浏览器的方式。
  握手层改返 401/403/410 也没用——浏览器 WebSocket API 读不到握手响应状态码。

### 配套测试（必须用真握手，不能用 TestClient）

现有 `tests/` 全部基于 TestClient，加多少用例都盖不住这个洞。
需要一条真起 uvicorn 的验收测试，断言坏票 / 坏 Origin / 过期游标三种情况下
客户端**实际收到的关闭码**分别是 4401 / 4403 / 4410。

探针脚本见
`scratchpad/ws_probe.py`（本次实测用的那份），可直接改造成回归测试。
