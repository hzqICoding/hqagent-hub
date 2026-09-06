# T-W4 前端 F1 审核结论

| 项 | 值 |
| --- | --- |
| 审核方 | W0（架构/审核） |
| 被审提交 | `1556438`、`19dbbf8`（基线 `15c4878`） |
| 审核日期 | 2026-09-05 |
| 结论 | **F1 通过，可进 F2；但有 4 条必须在 F5 接真 Hub 之前修掉** |

## 一、独立复现结果

不采信自述，以下全部由 W0 重跑：

| 项 | 自述 | W0 实测 | 一致 |
| --- | --- | --- | --- |
| `pnpm typecheck` | 退出 0 | 退出 0，无输出 | ✅ |
| `pnpm test` | 9 文件 33 测试全绿 | 9 文件 33 测试全绿 | ✅ |
| `pnpm build` | 1669 模块，构建成功 | 构建成功，产物大小一致 | ✅ |
| 路径所有权 | 只改 `apps/desktop/**`（不含 `src-tauri/`） | `git diff --name-only` 核对，禁区零命中 | ✅ |
| 无 AI 署名 | 无 | `git log` 全文 grep 无命中 | ✅ |
| 无手写重复 DTO | 无 | 核对通过（见下） | ✅ |
| 无硬编码颜色 | 无 | 只有 `theme.types.ts` 的四套 palette 定义，属合法来源 | ✅ |
| 四态覆盖 | 三页齐全 | 三页均引用 Loading/Empty/Error/Offline 四组件 | ✅ |

**自述与实测无出入。** 这点值得记一笔——上一轮两条 Codex 死在自测之前，
这次的报告是真跑过的。

### 一处我自己的误报

`grep` 曾在 `src/pages/dev/UiKitPage.vue:179` 命中
`export interface HubEvent<T = unknown>`，看着像违反「只 import 不声明」。
实际那是 UI Kit 演示用的 **Markdown 字符串里的代码块**，不是 TS 声明。
约束 1 是干净的：16 处 `from '@hqagent/protocol'`，无重复定义。

### 协议迁移 10 项

逐条核过，全部落实。重点两项：

- `BootstrapView.hubEndpoint` 已删除，且 `mock-gateway.test.ts:20` 有
  `expect((bootstrap as any).hubEndpoint).toBeUndefined()` 把它焊死。**这个测试要留着。**
- 场景数据 `import ... from '@hqagent/fixtures/*.json'`，走的是
  `packages/protocol/fixtures/contracts/`，UI 组合放在 `src/mocks/scenarios/`。分层正确。

---

## 二、必须修（F5 接真 Hub 之前）

### R1 🔴 硬编码回退 Token 与固定端口

`src/shared/api/local-hub-gateway.ts:42-56`

```ts
async function getHubEndpointFromTauri(): Promise<HubEndpoint> {
  if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
    try {
      return await invoke<HubEndpoint>('get_hub_endpoint')
    } catch (err) {
      console.warn('[LocalHubGateway] invoke("get_hub_endpoint") failed, using fallback', err)
    }
  }
  return {
    baseUrl: 'http://127.0.0.1:49210',
    token: 'tok_dev_fallback_hub_token',
  }
}
```

直接违反硬约束 3「Local Hub 地址和令牌不由你决定」。

**当前不在产物里**——`getUiGateway()` 默认走 mock，`VITE_GATEWAY_MODE` 未设时
`if (mode === 'local')` 被静态消除，整个 `localHubGateway` 被 tree-shake。
我 grep 过 `dist/`，`tok_dev_fallback_hub_token` 零命中。

**但只差一个环境变量。** F5 把 `VITE_GATEWAY_MODE=local` 一开，它就上线了。

为什么必须删而不是留着方便调试：

W5 的 `runtime_descriptor.rs` 对 hub.json 做了四重校验——instanceId 要匹配当前
受管进程、pid 要匹配、startedAt 要落在启动窗口内、还要 `process_matches_executable`
确认 pid 没被复用。任何一条不过就返回 `Err`，**故意拒绝连接**。

这个 `catch` 把那四重校验全部废掉了：拒绝 → 落回退 → 照样连。
而且 49210 是猜的固定端口，真实端口由 Descriptor 动态给出——
回退可能连到恰好占着 49210 的**另一个进程**上，还带着一个它不认识的 token。
用户看到的是一串 401，不是「Hub 不可用，因为描述符已过期」。

**改法**：`invoke` 失败就 `throw`，让 `app.store` 落到 `disconnected` 状态并显示
真实原因。开发态回退如果要保留，用 `import.meta.env.DEV` 显式围起来，
baseUrl 和 token 从 `VITE_HUB_BASE_URL` / `VITE_HUB_TOKEN` 读，
**源码里不留任何字面量 token**。

### R2 🔴 WebSocket 竞态双连，导致重复事件与连接泄漏

`local-hub-gateway.ts:225-290`

```ts
subscribeEvents(...) {
  this.subscribers.add(onEvent)
  if (!this.ws) {                    // ← 同步判空
    this.connectWebSocket(onError)
  }
```
```ts
private connectWebSocket(onError?) {
  Promise.all([this.ensureEndpoint(), this.acquireWsTicket()])
    .then(([{ baseUrl }, ticket]) => {
      this.ws = new WebSocket(wsUrl)   // ← 异步才赋值
```

守卫是同步读的，赋值是异步做的。同一 tick 里两次 `subscribeEvents`
（`AppLayout` 和页面各订阅一次，这是最自然的写法）都会看到 `this.ws === null`，
于是各换一张票、各开一条连接。第二条覆盖 `this.ws`，**第一条变成孤儿**：
它的 `onmessage` 照样触发，每个事件被投递两次；`unsubscribe` 只关得掉第二条，
孤儿连接一直挂到 Hub 那边超时。

注意 `onmessage` 里 `if (event.seq > this.lastConfirmedSeq)` 只更新游标，
**不做投递去重**——`subscribers.forEach` 无条件执行。所以重复会一路穿到 UI。

W1 已经用 `test_websocket_reconnect_replays_without_duplicates` 证明服务端不重复。
这条是纯客户端制造的重复。

**改法**：进 `connectWebSocket` 就先占位（`this.connecting = true` 或把
Promise 本身存起来做单飞），异步失败时再清掉。

### R3 🔴 订阅时 Hub 就不可用 → 永不重连

同一段的 `.catch`：

```ts
.catch((err) => {
  console.error('[LocalHubGateway] Failed to obtain WS ticket for connection', err)
  if (onError) onError(err)
})
```

重连逻辑全挂在 `ws.onclose` 上。但换票失败发生在 `new WebSocket` **之前**，
没有 socket，也就没有 `onclose`，`.catch` 里又没有任何重试。

结果：Hub 启动比前端慢、或者启动瞬间正在维护——用户看到一次错误，
**之后永远不会自动恢复**，只能重启应用。这在「桌面壳拉起 Hub 子进程」
的架构下是常态而不是边缘情况，Hub 一定比 WebView 起得慢。

**改法**：`.catch` 里也走同一条退避重连路径。

### R4 🔴 协议错误码被整体丢弃

`local-hub-gateway.ts:84-92`

```ts
if (!res.ok) {
  throw new Error(`HTTP Error ${res.status}: ${res.statusText}`)
}
const envelope = (await res.json()) as ApiEnvelope<T>
```

**先按状态码抛错，再解析信封**。于是所有非 2xx 响应的结构化错误全部丢掉。

`error-codes.yaml` 里 27 个错误码就是为了让 UI 能分情况反应，而这些恰恰都是非 2xx：

| 错误码 | W1 实际返回 | UI 本该做的 | 现在拿到的 |
| --- | --- | --- | --- |
| `HUB_MAINTENANCE` | 503 | 显示维护/排空界面，禁建新任务 | `HTTP Error 503: Service Unavailable` |
| `FEATURE_UNAVAILABLE` | 503 | 按 `features` 禁用入口并说明原因 | 同上，与维护模式无法区分 |
| `EVENT_CURSOR_EXPIRED` | 4xx + `snapshotUrl` | 重新 bootstrap 取 Snapshot | 一个字符串 |
| `PATH_NOT_ALLOWED` / `CAPABILITY_MISSING` | 4xx | 给出可操作提示 | 一个字符串 |

我在 `src/` 全量 grep 过 `error.code` / `HUB_MAINTENANCE` / `EVENT_CURSOR_EXPIRED` /
`FEATURE_UNAVAILABLE`——**零命中**。没有任何地方消费协议错误码。

**改法**：无论状态码先解析信封，把 `envelope.error.code` 和 `detail` 带进一个
`HubApiError` 抛出；解析失败再退回状态码文本。

---

## 三、应该修（不阻塞 F2）

### R5 🟡 `pnpm lint` 不存在

任务书的验收是 `typecheck` / `lint` / `test` 三条，`apps/desktop/package.json`
和仓库根都没有 `lint` script。三条命令少一条，等于验收标准有一条从来没跑过。
补 ESLint + `lint` script。

### R6 🟡 `EVENT_CURSOR_EXPIRED` 没有恢复路径

`lastConfirmedSeq` 会一直带着 `after=` 重连。游标一旦过期，
每次重连都用同一个过期游标——配合 R3 修好之后会变成无限失败重连。
需要在收到该错误码时清零游标并重新 bootstrap 取 Snapshot（R4 是它的前置）。

### R7 🟡 注释说「退避重连」，实际是固定 3 秒

`setTimeout(..., 3000)`，没有指数退避、没有上限、没有把连续失败反映成
用户可见的 offline 状态。Hub 长时间不在时会 3 秒一次空转到天荒地老。

---

## 四、给 F2 的前置提醒

F2 要做工作区与团队 Profile。`resolveSource` 六值必须在 UI 上如实呈现
（尤其 `fallback` 和 `ask_user` 两种要肉眼可辨），这是「四层解耦」能不能被用户
理解的关键，不要简化成一个「已解析」绿灯。
