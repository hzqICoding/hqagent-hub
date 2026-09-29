# R1.5+-P3 前端交付回执（协议 0.8.0 / D50）

## 基线与范围

- 工作区：`E:/OtherPro/HQAgent-Hub-worktrees/r15-web`；分支：`feat/r15-web`。
- 起始提交：`17ef0b0`；实现及测试提交：`796fedc`，`feat(remote): add device controls and cookie-based API token management`。
- A、B、C、D 已实现；修改仅在 `apps/desktop/**` 和 `.hqagent/handoffs/**`，没有改协议、后端、根配置或依赖。
- 临时目录为已忽略的 worktree `.tmp`，验收进程设置 TEMP/TMP；未发生 0xC0000142 或额度错误。

## A. 设备管理

- 「我的电脑」显示实际在线/离线与独立的远程可用/已暂停状态，显示名优先 `displayName`，缺省回退 `deviceName`。对话页顶部同样优先显示别名。
- 设备「更多」弹窗支持暂停/恢复、显示名编辑（清空恢复电脑名称）、删除二次确认。管理操作不要求电脑在线，不以撤销代替暂停或删除。
- 打开操作弹窗读取当前设备，PATCH 携带 `expectedVersion`；操作后再次 GET，忽略 PATCH 返回的可能过时快照。CAS CONFLICT 后 GET 刷新并提示「设备状态已变化，请确认后重试」，不自动再次提交；用户下一次确认生成新的 Idempotency-Key。
- 读取请求次序保护防止较早的列表响应覆盖 PATCH 后 GET 的最新设备状态。
- 删除确认完整说明：删除服务器对话副本、电脑本地不受影响；本机任务可能仍在继续；以后只能在电脑端重新扫码。成功后重新读取列表，当前选中设备被删除时清理当前内容并回到设备列表。
- 旧「撤销设备」按钮移除。历史撤销分组仅在展开时请求 `includeRevoked=true`，默认请求显式 `includeRevoked=false`。历史记录可删除，不能进入对话或恢复。
- 设备列表按 nextCursor 完整读取后提供在线状态和远程状态两个独立本地筛选；网关也支持协议约定的 remoteAccess/online/includeRevoked 查询参数，不混用不同过滤条件的游标。

### DELETE 404 的能力判定

`RemoteGateway` 从真实响应信封的 `protocolVersion` 读取能力，不把 Worker 的 supportedWireRevisions 当 HTTP 管理能力。只在确认版本为同一 0.x 系列、minor >= 8 时设置内存能力标识；无版本证据和 0.7 均不视为支持。未知大版本不自动推定兼容。

DELETE 的 404 只有在该标识已确认时才作为「已不存在」继续刷新；未确认时提示「服务端未确认支持设备删除，请升级到 0.8.0 或更新版本后重试」。没有调用旧 revocations 作为替代。依据：api-guide §3、§12 及 P0/P1 回执；HTTP 新能力与线路修订 1/2 分开判断。测试分别覆盖真实网关模拟的 0.7、0.8 响应。

### 撤销数量的协议缺口

0.8.0 的 RemoteDevicePage 只有 items/hasMore/nextCursor，没有撤销总数。为了同时遵守「默认 includeRevoked=false」和「展开才取历史」，首次折叠显示「已撤销（展开查看）」；展开并拉完分页后才显示真实「已撤销（N）」，0 条明确显示没有已撤销设备。未预读隐藏记录、未伪造计数或新增协议字段。

## B. 暂停影响

- 暂停时显示「这台电脑的远程操作已暂停」和「恢复远程」入口；历史、同步和实际在线状态保留，不把暂停映射成离线。
- 页面与 store 同时拦截发送、新建任务、修改对话、批准审批及运行 pause/resume/retry；command.withdraw 也不作为暂停例外。
- 取消运行、拒绝审批继续可用，仍遵守原来的在线、权限和送达规则。
- HTTP 收到 REMOTE_DEVICE_SUSPENDED 后保留草稿、刷新设备状态；浏览器 command.updated 携带该失败码时也刷新，避免只依赖定时轮询。没有增加 Worker 新错误或帧。
- 原 R1.5 的忙碌锁、三项状态折叠、创建占位与输入聚焦继续保留。

## C. API 令牌

- 新增受远程登录路由守卫保护的 `/remote/tokens`，入口为设备页的「API 令牌」。列表显示名称、公开前缀、精确权限、创建/最后使用/到期时间和有效/过期/吊销状态。
- 默认不取已吊销记录；切换过滤从首页重新读取，支持 nextCursor 加载更多。设备与令牌页都有内部滚动区域；浏览器实际验证 60 条令牌的滚动及 50+10 分页。
- 三项 scope 独立勾选，无隐含 read/manage/delete；只有显式选择 delete 才提交该权限，并提示「删除是破坏性操作」。名称修剪且最多 120 字符；有效期默认交给服务端的 90 天，UI 限制整数 1–365 天。
- **签发请求由 RemoteTokenIssueDialog 自身发起。** 完整 secret 仅存于该弹窗的临时 ref；父页面只收到 created 通知，重新读取元数据，不接收秘密或完整签发响应；未新增令牌 Pinia store。
- 弹窗关闭立即清空 secret 和签发意图并销毁组件；卸载/离开页面也清理；关闭之后迟到的响应被丢弃。复制只由用户点击触发；不写任何 Web Storage、URL、诊断记录或日志。
- 网络失败重试保留同一 key 与同一请求体（含冻结后的 expiresAt）；修改表单产生新意图。重放 secretAvailable=false 时显示「令牌已创建但无法再次显示，如未保存请吊销后重建」，提供二次确认的吊销入口，不制造可复制秘密。
- 吊销确认后 DELETE 并刷新列表。所有浏览器管理请求使用 Cookie；写入带 CSRF 和幂等键，从不设置 Authorization。
- 列表中的 tokenPrefix 是协议允许显示的公开定位前缀，不是完整秘密。秘密清理测试区分这两者；localStorage/sessionStorage 连公开 `hqr_pat_` 字符串也不写入。

## D. 错误及排查

- remote-errors.ts 补齐指南缺失的错误提示，包括五个新增 HTTP 码以及 CONFLICT，新增文案来自冻结的 http-error-guidance.yaml；不改 Worker 错误域。
- 网关统一取响应头 X-Request-Id，缺失时回退信封 requestId；非 JSON 错误仍保留响应头 ID，网络失败不伪造 ID。
- lastRemoteFailureRequestId 只记录最近一次失败的关联 ID，保存在模块内存。失败通知仅保留操作路径/方法、中文消息和关联 ID，不保留响应体、请求体、原始 header 或秘密。
- 设备、对话、令牌及既有登录/配对页面显示可长按选择、可点击复制的小字 requestId；弹窗中的错误也能看到。成功响应不会产生成功 requestId 提示，相同操作成功可清理其旧失败通知。

## 测试与旧断言变更

新增 27 项测试：

- RemoteDeviceManagement.test.ts：11 项，覆盖双状态/别名、暂停恢复与版本、CAS 刷新/新 key、0.7/0.8 删除 404、历史删除二次确认、拒绝 PATCH 旧快照、暂停例外、HTTP/事件暂停竞态保留草稿、迟到列表响应。
- RemoteTokens.test.ts：7 项，覆盖独立 scope、秘密仅在弹窗及清理、关闭后迟到响应、元数据重放/吊销确认、列表过滤、90/365 天、网络重试保持同一意图。
- RemoteManagementGateway.test.ts：9 项，覆盖 Cookie/CSRF/幂等/无 Authorization、请求参数与 ID 编码、header/envelope/non-JSON requestId、复制与内存保存、六个关键错误码中文提示。

本轮仅修改了一项既有测试的断言，其他既有用例保持：

| 原文件 / 用例 | 旧断言 | 新断言及原因 |
| --- | --- | --- |
| RemotePhoneRepair.test.ts / hides revoked devices by default, expands a read-only group and keeps the safety guidance | 默认已知道「已撤销（1）」；历史记录纯只读；点击「撤销设备」并验证旧撤销提示 | 改名为 loads revoked history on expansion and offers deletion instead of revocation；默认「已撤销（展开查看）」；展开异步完成后断言真实 N；确认撤销按钮不存在，历史行可点删除，并验证三条删除确认文案。D50 明确替代旧撤销 UI，并要求展开后才读取历史。 |

早期验证发现上述旧 UI 断言冲突、测试夹具对 Vue Proxy 调用 structuredClone、lint 要求保留捕获错误 cause，均已修正。截图脚本曾在开发热更新后等待 Mock 令牌记录超时，停止并重新启动干净 Vite 进程后重跑成功；以下是最终代码及干净开发进程的结果。

## 最终验收真实输出

全部命令在仓库根运行，TEMP/TMP 指向 worktree `.tmp`。完整 stdout/stderr 保存于 [验证目录](r15plus-p3-validation/)；仅规范化换行和行尾空白，没有删去警告。

### lint（退出码 0）

```text
pnpm --filter @hqagent/desktop lint
$ eslint src
```

### typecheck（退出码 0）

```text
pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit
```

### vitest（退出码 0）

```text
pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
Test Files  56 passed (56)
      Tests  318 passed (318)
   Start at  19:37:08
   Duration  28.04s (transform 1.86s, setup 0ms, collect 12.06s, tests 8.70s, environment 23.45s, prepare 3.73s)
```

### build（退出码 0）

```text
pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1819 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-raJuea4t.css                                                    55.74 kB │ gzip: 10.36 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-C2ZT2y0f.js    0.92 kB │ gzip:  0.60 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-BQPQKkAD.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-BtfSgnmt.js           1.55 kB │ gzip:  0.75 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-CPaEKRNm.js             1.69 kB │ gzip:  0.82 kB
dist/assets/PlaceholderPage-BuFfJ0y6.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-ZgwSMPl_.js               2.16 kB │ gzip:  1.06 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-BdO3n8cE.js                2.32 kB │ gzip:  1.04 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-Cu7sTo2h.js           2.44 kB │ gzip:  1.19 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-BX496fvm.js     2.61 kB │ gzip:  1.42 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-oOFXapSW.js               2.85 kB │ gzip:  1.34 kB
dist/assets/team.store-BltT5aBc.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-B7eGs2lA.js                                            3.82 kB │ gzip:  1.84 kB
dist/assets/ConnectPage-BI47Ibv8.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-DIPWFHap.js                                          5.33 kB │ gzip:  2.49 kB
dist/assets/task.store-COMxfopB.js                                                 6.99 kB │ gzip:  2.61 kB
dist/assets/RemoteTokensPage-Dnf7rk0S.js                                           8.01 kB │ gzip:  3.88 kB
dist/assets/WorkspacesPage-4dYipYZv.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/RemoteDevicesPage-BO_omgpk.js                                          9.00 kB │ gzip:  3.77 kB
dist/assets/TemplatesPage-BtBqStvx.js                                              9.61 kB │ gzip:  4.26 kB
dist/assets/SessionsPage-CM4-qEqa.js                                              10.55 kB │ gzip:  4.50 kB
dist/assets/AgentsPage-DknlenNY.js                                                11.61 kB │ gzip:  4.05 kB
dist/assets/TasksPage-Cqie0lYt.js                                                 11.73 kB │ gzip:  4.67 kB
dist/assets/OverviewPage-Rt0J-EPP.js                                              12.12 kB │ gzip:  3.96 kB
dist/assets/ApprovalsPage-BnqsgUxI.js                                             12.26 kB │ gzip:  4.95 kB
dist/assets/OnboardingPage-D0ZM2EIC.js                                            12.93 kB │ gzip:  4.91 kB
dist/assets/TeamsPage-B67tddh-.js                                                 15.96 kB │ gzip:  5.93 kB
dist/assets/remote-chat.store-KEInWZIn.js                                         21.04 kB │ gzip:  6.67 kB
dist/assets/TaskDetailPage-C_m07TaE.js                                            23.41 kB │ gzip:  7.98 kB
dist/assets/ScenesPage-Bf70-Wlv.js                                                25.53 kB │ gzip:  8.68 kB
dist/assets/RemoteChatPage-Dd1sUjqJ.js                                            31.62 kB │ gzip:  9.63 kB
dist/assets/RemoteLinkPage-OcQBL0re.js                                            46.37 kB │ gzip: 17.47 kB
dist/assets/ChatPage-yq1Y8JgO.js                                                  75.61 kB │ gzip: 22.65 kB
dist/assets/vendor-CoG1YEnN.js                                                   146.41 kB │ gzip: 49.58 kB
dist/assets/index-nwLq5Sv0.js                                                    214.32 kB │ gzip: 69.81 kB
✓ built in 8.15s
```

测试仍包含既有 router injection 警告及 HUB_NOT_READY 故障模拟日志；构建包含既有 `Generated an empty chunk: "echarts".`，均保留在日志中，退出码为 0。

## 375×812 浏览器验收

使用 Python Playwright + 本机无头 Chromium，Mock 模式，未连接任何真实令牌或生产账号。签发图中的令牌带 EXAMPLE 标记，仅是不能用于认证的合成数据。

| 画面 | 截图 |
| --- | --- |
| 设备管理菜单 | [device-menu-375x812.png](screenshots/r15plus-p3/device-menu-375x812.png) |
| 暂停状态对话页 | [suspended-chat-375x812.png](screenshots/r15plus-p3/suspended-chat-375x812.png) |
| 令牌列表 | [token-list-375x812.png](screenshots/r15plus-p3/token-list-375x812.png) |
| 首次签发弹窗（示例令牌） | [token-issued-example-375x812.png](screenshots/r15plus-p3/token-issued-example-375x812.png) |

复现时先启动一个干净的开发进程，再执行脚本：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
pnpm --filter @hqagent/desktop exec vite --mode mock --host 127.0.0.1 --port 5198 --strictPort
# 另一终端，在同一 worktree 根目录执行：
python .hqagent/handoffs/screenshots/r15plus-p3/capture.py
```

浏览器脚本最终输出（退出码 0）：

```text
suspended chat overflow: False
dialog close and storage cleanup: PASS
token page overflow: False
60-token scrolling and pagination: PASS
page errors: 0
Screenshots: 4 captured at 375x812; token is a non-authenticating example
```

已打开截图检查布局。脚本不打印完整示例秘密，只验证弹窗关闭后的 DOM 和存储清理。

## 交付边界

- 没有真机、真实 Hub/Server 或阿里云联调/部署；本轮是前端单测、模拟 HTTP 契约请求、构建和浏览器视口验收，不将其描述为生产验证。
- 唯一已知协议展示缺口是未展开前的撤销总数，处理方式见上文；没有自造 DTO 字段或提出后端改动。
- 功能实现、测试均已提交；日志/截图/回执另作提交。每次提交后执行 `git log -1 --format=%B` 自查，没有署名尾注或生成标记。
