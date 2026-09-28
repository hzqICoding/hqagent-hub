# R1.5-P3 返修 2 回执（W4 前端）

- 工作区：`E:/OtherPro/HQAgent-Hub-worktrees/r15-web`
- 分支：`feat/r15-web`；起始提交：`a00ee30`。
- 实现与测试提交：`8352ce2` — `fix(remote): repair mobile device, task creation and status interactions`。
- 范围：只改 `apps/desktop/**` 与 `.hqagent/handoffs/**`。未修改协议、Hub、Server、根配置或依赖锁文件。
- A、B、C 已完成；最终 lint、typecheck、vitest、build 均退出 0。截图为 Chromium 无头浏览器 375×812 视口，未冒充实体手机或真实后端联调。

## A. 撤销设备

- 正常列表只展示未撤销电脑；底部「已撤销（N）」默认折叠，N=0 不展示。展开项仅展示名称、平台和撤销状态，无进入或操作入口。
- 当前电脑在设备刷新、轮询或主动撤销后被判定为 revoked，清空目录、对话、消息、运行、审批及创建占位，停止当前轮询并回到设备列表，提示「该电脑已撤销」。迟到的目录、列表、消息、快照和轮询响应不会恢复已清空的当前内容。
- 撤销弹窗保留原有安全提示，补充重新配对会成为新设备、暂时不用可关闭 Hub 的两句说明。

## B. 新建任务

- 对话列表顶部改为「新建任务」，每个项目标题增加可访问名称的「+」入口并预选该项目；目录请求已在进行时也保留预选。
- 项目、场景均来自选中电脑的 `RemoteCatalogView`，显示名称并使用真实 workspaceId、sceneId、version 和 workerStoreId；删除固定项目假值与硬编码场景选项。
- 标题选填，空白自动生成本地时间的「新任务 MM-DD HH:mm」。创建只提交任务元数据，不发送第一条消息。
- 目录加载/失败/空目录均不可创建，显示提示并支持重试；打开弹窗缺少目录时主动请求。切换电脑立即清空旧目录，迟到响应不能覆盖新电脑目录；校验目录 workerId/workerStoreId。
- 离线点击创建立即显示「设备离线，发送失败」，不请求创建接口。
- 保留 202 占位与 30 秒创建超时流程，创建时继续显示占位抽屉；真实同步到达后选中并打开，收起抽屉并聚焦输入框。修正没有活跃对话时首个任务的事件轮询不启动问题。
- Mock 网关同步修正：撤销设备保留 revoked 记录、目录按目标电脑返回、创建使用请求的真实场景版本及 store ID。

### 撤回判断依据

保留撤回入口，但改称「确认撤回待确认指令？」，移除页面所有 `queued_offline` 分支与离线排队文案。

1. `packages/protocol/remote/R1.5-contract.md` §6：在线提交有最多 30 秒传输记录；202 的 queued_online/awaiting_receipt 不代表运行；修订 2 不生产 queued_offline，控制仍需在线、期限及真实执行证据。§8 说明历史 DTO 值保留不能代表旧离线政策继续有效。
2. `packages/protocol/remote/R1-contract.md` §6、§7 的撤回/控制证据规则：已派发但无 Run 投影时，独立 command.withdraw 仍需电脑确认，不能声称从未执行或已经停止。
3. 只读核对 `apps/server/server/service_sync.py` 的 `withdraw`：修订 2 仍接受 type=run.submit、无 resultRef、非终态的原指令，并通过 enqueue_v2 下发 command.withdraw。因此 30 秒送达窗口内存在可达状态，不能整体删除 UI。
4. 按上述真实状态，仅对 queued/accepted、run.submit、无 resultRef、withdrawalState=none 显示按钮。重复撤回、终态、非 submit 或已有运行结果不显示；最终结果由服务端与电脑裁定。文案明确撤回需电脑确认，已有运行结果请用取消运行。

## C. 状态详情

- 三项状态默认不渲染，标题栏显示紧凑的当前运行状态按钮；无 run 不显示该按钮。已暂停沿协议现有状态如实显示。
- 点击展开/收起，状态仅保存在当前组件内存，切换对话重置；不使用 localStorage/sessionStorage。
- unconfirmed、指令失败/REMOTE_DELIVERY_EXPIRED、run 失败自动展开，运行状态标记显示提醒色与感叹号。没有 run 的送达失败仍显示自动展开的错误详情。
- 页面使用动态视口高度，展开详情最大 30dvh 并可内部滚动。截图检查 375 宽收起与展开都无页面横向溢出。

## 测试变化

新增 `RemotePhoneRepair.test.ts` 10 项：撤销分组与提示；当前电脑撤销后的跳转清理；目录选项、项目预选、真实 version、自动标题；目录加载失败与重试；请求进行中的项目预选；缺目录/离线不请求；首个任务同步选中并聚焦；跨电脑目录迟到响应；默认折叠/点击与失败/unconfirmed 自动展开；无 run 送达过期和撤回入口限制。

旧断言逐条调整如下，保留原执行/控制验证，只改变详情的打开步骤：

| 文件 / 用例 | 原断言 | 本轮断言 |
| --- | --- | --- |
| RemoteChat.test.ts / displays computer offline | 直接取常驻 section 验证传输状态 | 点击状态标记后取 remote-status-details；离线提示与立即失败继续验证 |
| RemoteChat.test.ts / renders all three distinct layers | 三层状态始终可见 | 先断言详情不存在，点击后验证三层状态与控制结果 |
| RemoteChat.test.ts / displays rejected and unconfirmed control outcomes | 控制详情直接可见 | 展开后验证拒绝/未确认结果；自动展开另有专项测试 |
| RemoteEvents.test.ts / B1 incrementally processes command delivery ... run succeeded | 直接看到“执行成功” | 标记先显示“已完成”，点击后看到“执行成功” |
| RemoteEvents.test.ts / B1 correctly renders all three outcomes | 直接看到“已确认生效” | 点击展开后依次验证 confirmed/rejected/unconfirmed |
| RemoteEvents.test.ts / B4 activeRun selects the latest run | 常驻 Run ID 与取消按钮 | 展开后验证最新 Run ID 与取消目标 |
| RemoteEvents.test.ts / B4 status bar and control buttons automatically switch | 常驻新 Run ID 与恢复按钮 | 展开后验证事件切换的新 Run 与恢复目标 |

## 最终验收原始输出

以下摘录直接读取最终执行日志；完整 stdout/stderr（仅规范化换行与行尾空白）已保存于 [验收日志目录](r15-p3-fix-2-validation/)。首次完整运行发现 4 项旧状态常驻断言失败，修正为展开后验证后，全套通过；新增预选竞态测试后最终为 291 项。

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
Test Files  53 passed (53)
      Tests  291 passed (291)
   Start at  12:30:26
   Duration  28.54s (transform 1.80s, setup 0ms, collect 12.17s, tests 8.58s, environment 24.37s, prepare 3.71s)
```

### build（退出码 0）

```text
pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1812 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                   2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                 0.24 kB │ gzip:  0.17 kB
dist/assets/index-raJuea4t.css                                                   55.74 kB │ gzip: 10.36 kB
dist/assets/echarts-l0sNRNKZ.js                                                   0.00 kB │ gzip:  0.02 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-DDIretuf.js          1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-DjSHe-6Z.js          1.55 kB │ gzip:  0.75 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-DmTQBjo2.js            1.69 kB │ gzip:  0.82 kB
dist/assets/PlaceholderPage-BVnB0ILR.js                                           1.74 kB │ gzip:  1.10 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-COPGC65D.js              2.16 kB │ gzip:  1.06 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-CdB3G9DX.js               2.32 kB │ gzip:  1.04 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-DVZdoFZb.js          2.44 kB │ gzip:  1.19 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-_Xbx3Wnh.js    2.61 kB │ gzip:  1.42 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-MsABnwKf.js              2.85 kB │ gzip:  1.34 kB
dist/assets/RemoteLoginPage-BZesHCYr.js                                           3.73 kB │ gzip:  1.79 kB
dist/assets/team.store-BNztw9S0.js                                                3.73 kB │ gzip:  1.88 kB
dist/assets/ConnectPage-Bgsc5O3V.js                                               5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-C8LBJJmL.js                                         5.23 kB │ gzip:  2.44 kB
dist/assets/RemoteDevicesPage-VQVsgl0S.js                                         6.87 kB │ gzip:  3.23 kB
dist/assets/task.store-DC_U9M61.js                                                6.99 kB │ gzip:  2.61 kB
dist/assets/WorkspacesPage-BX94xil-.js                                            8.80 kB │ gzip:  3.50 kB
dist/assets/TemplatesPage-Bcmd0mfR.js                                             9.61 kB │ gzip:  4.26 kB
dist/assets/SessionsPage-qYMcfocy.js                                             10.55 kB │ gzip:  4.50 kB
dist/assets/AgentsPage-CGe3gSFX.js                                               11.61 kB │ gzip:  4.05 kB
dist/assets/TasksPage-CQGvzdTT.js                                                11.73 kB │ gzip:  4.67 kB
dist/assets/OverviewPage-2E-SeeWa.js                                             12.12 kB │ gzip:  3.96 kB
dist/assets/ApprovalsPage-DMO_GFvU.js                                            12.26 kB │ gzip:  4.95 kB
dist/assets/OnboardingPage-fiB5uUP4.js                                           12.93 kB │ gzip:  4.91 kB
dist/assets/TeamsPage-_Z-wRw6p.js                                                15.96 kB │ gzip:  5.93 kB
dist/assets/remote-chat.store-Dgh_UlLr.js                                        18.14 kB │ gzip:  5.73 kB
dist/assets/TaskDetailPage-o4UNq0EE.js                                           23.40 kB │ gzip:  7.98 kB
dist/assets/ScenesPage-DLrTAVqo.js                                               25.53 kB │ gzip:  8.68 kB
dist/assets/RemoteChatPage-BlhRYDzM.js                                           29.97 kB │ gzip:  9.26 kB
dist/assets/RemoteLinkPage-4QFoYV13.js                                           46.37 kB │ gzip: 17.47 kB
dist/assets/ChatPage-COz8R8vg.js                                                 75.61 kB │ gzip: 22.65 kB
dist/assets/vendor-CX0SJbHY.js                                                  146.40 kB │ gzip: 49.57 kB
dist/assets/index-CVHv5JHT.js                                                   211.30 kB │ gzip: 68.19 kB
✓ built in 5.44s
```

测试完整日志中包含既有测试的 router injection 警告与 HUB_NOT_READY 故障模拟日志；构建输出包含 `Generated an empty chunk: "echarts".`，未隐去这些警告，命令退出码均为 0。

## 375×812 截图与复现

| 页面 | 文件 |
| --- | --- |
| 设备列表与折叠的撤销分组 | [devices-375x812.png](screenshots/r15-p3-fix-2/devices-375x812.png) |
| 新建任务弹窗，Web-Ecommerce 预选 | [create-task-375x812.png](screenshots/r15-p3-fix-2/create-task-375x812.png) |
| 状态收起 | [status-collapsed-375x812.png](screenshots/r15-p3-fix-2/status-collapsed-375x812.png) |
| 状态展开 | [status-expanded-375x812.png](screenshots/r15-p3-fix-2/status-expanded-375x812.png) |

已逐张打开检查。复现脚本使用本机 Python Playwright 与 Chromium，仅操作 Mock 数据；TEMP/TMP 指向 worktree 的已忽略 `.tmp`。

```text
pnpm --filter @hqagent/desktop exec vite --mode mock --host 127.0.0.1 --port 5198 --strictPort
python .hqagent/handoffs/screenshots/r15-p3-fix-2/capture.py

collapsed overflow: False
expanded overflow: False
dialog selected workspace: workspace_web
Screenshots: 4 captured at 375x812
```

## 边界与未验证项

- 无新增协议字段；沿用 `@hqagent/protocol` DTO，新增加载、折叠与聚焦标识只属于 UI 内存状态。0.7.0 没有设备删除接口，本轮按产品决定保留只读撤销历史；没有以本地持久化隐藏代替服务端删除。
- 本轮未新增凭据、Cookie、短码的持久化或日志写入。
- 未连接实体手机或真实 Hub/Server；实际移动浏览器软键盘弹出、弱网及真实电脑同步需用部署环境复测。本轮验证了 DOM focus、无头浏览器移动视口和协议形状的 Mock 交互。
- 无协议变更请求，无依赖变更请求。未出现 0xC0000142 或 API 额度错误。
- 每次提交后执行 `git log -1 --format=%B` 自查；提交信息只描述变更，无署名尾注。
