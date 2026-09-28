# R1-P3B 返修 2 + 扫码配对（R1.5 / D46）

返修 1 已审核通过：增量事件、快照审批、路由前缀都修好了。之后主代理用真实服务端和真实 Hub 在浏览器里做了联调，通过的项目有：手机登录、发消息后回复自动出现、电脑离线时指令排队、电脑重连后自动投递。联调中又发现下面三个问题，同时用户新增了扫码配对需求（设计见 integration/phase1 上 `docs/vnext/手机远程接入方案.md` §11.1）。

开工前先执行 `git merge --no-ff integration/phase1`，拿到最新的设计文档和集成代码。

## B4（必须）状态栏与控制按钮指向最早的一轮

`remote-chat.store.ts` 的 `activeRun` 用 `runs.value.find(...)`，取到的是该对话**最早**的 run。服务端 runs 按创建先后升序返回，应该取**最新**的一条。现在的后果：
- 顶部三层状态显示的是旧的一轮；
- 暂停、取消、重试会作用在旧的一轮上。

要求：
- 取最新 run。
- 新 run 通过事件到达时，状态栏和控制按钮自动切过去。
- 补测试：一个对话有 3 个 run（succeeded、cancelled、running），状态栏显示 running 那个，取消请求发给它的 runId。

## B5（必须）会话模式默认值

输入框的会话模式默认总是「继续上下文」(`continue`)，由此出现两种失败：
- 新对话里没有上一轮，内核返回「没有可继续的上一轮」；
- 上一轮是 cancelled 或 failed 时，内核返回「上一轮会话已关闭」。

要求：
- 当前对话没有任何 run，或最新 run 为 cancelled / failed 时，默认选「新话题」(`new`)；
- 最新 run 为 succeeded 时，默认「继续上下文」；
- 用户手动切换后，以用户的选择为准。

补测试覆盖这三种情况。

## B6（必须）在线/离线标签不会自动更新

电脑下线或上线后，手机顶部的「电脑在线/离线」要刷新页面才会变。服务端判离线阈值是 45 秒。

要求：
- 远程对话页每 15 秒刷新一次目标设备状态（`GET /api/v2/devices/{workerId}`）；页面不可见时暂停，切回页面时立即刷新一次。
- 收到 `command.updated` 事件时，用其中的 `workerOnline` 同步更新这个标签。

补测试：不刷新页面的情况下，设备由 online 变为 offline 后，标签在下一次轮询时就变成「电脑离线」。

## B7（新需求）扫码配对

**电脑端**（`pages/remote-link/RemoteLinkPage.vue`，pairing 状态）：
- 在短码上方显示二维码，内容为 `<serverOrigin>/remote/pair#code=<pairCode>`。serverOrigin 取自 RemoteLinkView 的 `serverOrigin`，短码放在 `#` 之后。
- 短码文字和倒计时保留，作为无法扫码时的备用。
- 过期或取消后二维码随即消失。
- 二维码只在内存中渲染，不写入任何存储，也不做下载或导出。

**手机端**（`pages/remote/RemotePairingPage.vue` 与路由守卫）：
- 从 `location.hash` 读取 `code`，只接受 8 位、字母表内的值。读取后立即用 `history.replaceState` 把 hash 从地址栏清掉，并自动填入短码、触发预览。
- 未登录时先跳登录页。登录成功后回到 `/remote/pair` 且保留短码。hash 在跳转时可能丢失，所以用一个只存在于内存里的临时变量（store 的一个 ref）带过去，**不要**写入 localStorage、sessionStorage 或 URL 查询参数。
- 预览时展示设备名、平台，用户确认后才绑定。不能扫码后直接自动确认。

**依赖**：允许在 `apps/desktop/package.json` 增加一个二维码生成库（如 `qrcode` 及其类型包），并更新 `pnpm-lock.yaml`。这是本轮对共享锁文件的特许，只能增加这一个库及它的传递依赖，回执里要写明库名和版本。

补测试：
- 二维码内容格式正确，短码在 `#` 之后；
- 手机端读取 hash 后地址栏被清除；
- 未登录经过登录后，仍能带着短码回到配对页；
- 非法 code 被忽略；
- 各类前端存储里都没有短码。

## 要求

- 只改 `apps/desktop/**`、`pnpm-lock.yaml`（仅限 B7 依赖）和回执；不碰 `packages/protocol`、`apps/hub`、`apps/server`。
- 验收：
  - typecheck 通过；
  - 全部测试通过，原有断言不放宽；
  - B4–B7 各有测试；
  - 截图：电脑端二维码、手机端扫码后的预览页，各宽屏一张、375×812 一张。
- 回执 `R1-P3B-remote-web-gateway.md` 追加「返修 2」一节。
- commit message 不得出现任何 AI 署名，不写 Co-Authored-By，不写「Generated with」之类字样；提交后用 `git log -1 --format=%B` 自查。
