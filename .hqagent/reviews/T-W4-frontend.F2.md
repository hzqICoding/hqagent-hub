# T-W4 前端 F2 审核结论

| 项 | 值 |
| --- | --- |
| 审核方 | W0（架构/审核） |
| 被审提交 | `0fde99d`（基线 `1810535`） |
| 审核日期 | 2026-09-06 |
| 结论 | **F2 通过。F1 的 R1–R7 七条全部落实，四条验收命令本地重跑全绿** |

## 一、独立复现结果

不采信自述，以下全部由 W0 在 `w4-frontend` worktree 重跑：

| 项 | 自述 | W0 实测 | 一致 |
| --- | --- | --- | --- |
| `pnpm lint` | 0 errors / 0 warnings | `eslint src` 退出 0，无输出 | ✅ |
| `pnpm typecheck` | 退出 0 | `vue-tsc --noEmit` 退出 0 | ✅ |
| `pnpm test` | 15 文件 56 测试 | 15 文件 56 测试全绿 | ✅ |
| `pnpm build` | 构建成功 | `✓ built in 4.71s`，产物清单与自述一致 | ✅ |
| 路径所有权 | 只改 `apps/desktop/**` + handoff | `git diff --stat` 55 文件，禁区零命中 | ✅ |
| 无 AI 署名 | 干净 | `git log main..HEAD` 全文 grep 无命中 | ✅ |
| 无硬编码颜色 | — | 三个新页面裸 hex 零命中；调色板 class 用法与 F1 已过审页面同构 | ✅ |
| 无重复 DTO | — | `TemplateItem` 是本地 UI 类型，protocol 无对应 schema，不算重复 | ✅ |

**自述与实测无出入。** 连续第二轮报告是真跑过的。

## 二、R1–R7 逐条核验

| 项 | 状态 | 核验依据 |
| --- | --- | --- |
| R1 硬编码 Token/端口 | ✅ 真删了 | `tok_dev_fallback_hub_token` / `49210` 全库零命中；`getHubEndpointFromTauri` 拿不到就 `throw`，dev 分支用 `import.meta.env.DEV` 围住且只读 `VITE_HUB_*` |
| R2 WS 竞态双连 | ✅ | `connectPromise` 单飞 + `readyState === CONNECTING\|OPEN` 双重守卫（`local-hub-gateway.ts:302-309`）；`subscribeEvents:378` 也改成 `!this.ws && !this.connectPromise` |
| R3 换票失败永不重连 | ✅ | `catch` 块统一走 `scheduleReconnect`（`:352-362`） |
| R4 协议错误码丢弃 | ⚠️ 半闭环 | 网关侧已修（先解信封后看状态码，抛 `HubApiError` 带 code/status/detail/retryable/requestId）。**但没有消费者**，见 F2-R1 |
| R5 缺 lint | ✅ | ESLint flat config + `"lint": "eslint src"`，退出 0 |
| R6 游标过期恢复 | ⚠️ 名义闭环 | 代码在，但打在了打不到的路径上，见 F2-R2 |
| R7 固定 3s 重连 | ✅ | `Math.min(1000 * 1.5 ** attempts, 15000)`，`onopen` 清零，`unsubscribe` 清定时器 |

`resolveSource` 六值核对：schema `common.json:112` 的枚举是
`task_override / workspace_profile / global_profile / capability_match / fallback / manual`，
`TeamsPage.vue:195-233` 六个 case 一一对应，`fallback` 与 `manual` 另有图标 +
`fallbackReason` 文案，肉眼可辨。**F1 审核里我写的「ask_user」是我记错了，
以 schema 的 `manual` 为准。**

## 三、残留项（不阻塞 F3，F5 接真 Hub 前要处理）

### F2-R1 🟡 协议错误码有生产者、没有消费者

`grep -rn "HubApiError|error\.code|HUB_MAINTENANCE|FEATURE_UNAVAILABLE" src`
排除网关自身后**零命中**。

网关现在如实抛出 `HubApiError`，但 store 和页面统统按普通 Error 接住转成
一句提示文案。R4 原文列的那张表——`HUB_MAINTENANCE` 要显示维护 Gate、
`FEATURE_UNAVAILABLE` 要按 `features` 禁用入口——**一个都还没做**。

改法：`app.store` 捕获时判 `err instanceof HubApiError`，把 `code` 记进
`ConnectionStatus` 之外的一个 `hubGate` 状态；F3 建任务入口读它做禁用。
属于 F3 范围，这里只记账。

### F2-R2 🟡 `EVENT_CURSOR_EXPIRED` 打在了打不到的路径上

两头都不通：

1. **W1 侧根本不产生它。** `apps/hub/api/app.py` 里 WS 只有 `close(code=4403)`
   （来源不对）和 `close(code=4401)`（票不对）两个关闭码，
   `after=` 游标**没有任何保留窗口校验**。`error-codes.yaml:58` 定义了
   `EVENT_CURSOR_EXPIRED / http 410`，但服务端从未发出过。
2. **W4 侧接在了 HTTP 分支。** `local-hub-gateway.ts:356` 判的是
   `acquireWsTicket()` 抛出的 `HubApiError`——即 `POST /auth/ws-ticket` 的
   响应。可换票接口不校验游标，游标过期只可能从 **WS 握手的关闭码**回来，
   而 `ws.onclose`（`:344-351`）不看 `event.code`，无条件带着同一个
   `after=lastConfirmedSeq` 重连。

后果就是 R6 当初警告的那个死循环：等 W1 真加上事件保留窗口，
游标一过期就是**指数退避封顶 15s 的无限失败重连**，前端永远不知道该重取 Snapshot。

改法（跨包，两边都要动）：
- W1：`/api/v1/events/stream` 校验 `after` 是否落在保留窗口内，
  超窗用一个专用关闭码（建议 `4410`，与 http 410 对齐）关闭。
- W4：`ws.onclose` 读 `event.code`，见到该码时 `lastConfirmedSeq = 0`
  并触发一次 `getBootstrap()` 重取 Snapshot，而不是直接重连。

### F2-R3 🟢 事件流还没接进应用（记录，非缺陷）

`subscribeEvents` 在 `src/` 里**只有测试在调**，没有任何 store 或页面订阅。
R2/R3/R6/R7 修的是一条目前不通电的线路——单测覆盖到了，真实链路没跑过。
F3 接任务页时这条线才第一次上电，届时 R2 的单飞守卫要在真环境再验一次
（`AppLayout` + 页面同 tick 双订阅正是当初 R2 的触发场景）。

### F2-R4 🔵 小瑕疵：403 硬映射成 `ORIGIN_NOT_ALLOWED`

`local-hub-gateway.ts:141`，仅在响应体不是合法 JSON 时兜底。
W1 目前 403 确实只有这一种，但写死映射会在将来加别的 403 时误标。
建议兜底一律用 `INTERNAL` 并把状态码留在 `status` 字段里。

## 四、给 F3 的前置提醒

F3 用 Mock 就能全量开工，**不要等 W3**。任务书 §74 明写「F0–F4 全程用 Mock，
不依赖任何其他包」，协议 DTO 在 FZ-1/FZ-2 已冻结，W3 和前端是照同一份 schema
各写各的。（本文档初稿写的「等 W3 handoff 出来再动」是错的，已改。）

F3 期间顺手把两条残留做掉，都不依赖任何其他包：
- F2-R1：`app.store` 判 `err instanceof HubApiError`，把 `code` 落成一个
  `hubGate` 状态，建任务入口读它做禁用。
- F2-R2 的 W4 半边：`ws.onclose` 读 `event.code`，见到游标过期专用码时
  清零 `lastConfirmedSeq` 并重取 Snapshot，而不是原样重连。

另外 F3 的验收里有一条「WebSocket Mock 的断线、重连和事件补发」——
这正好是 R2 单飞守卫第一次真上电（`AppLayout` + 任务页同 tick 双订阅
就是当初触发 R2 的场景），务必在 Mock 里把这个并发订阅场景造出来测。
