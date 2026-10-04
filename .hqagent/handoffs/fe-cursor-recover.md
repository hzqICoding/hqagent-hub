# 事件游标过期自动恢复修复回执

工作分支：`feat/r15-web`。开工已执行 `git merge integration/phase1`，合并基线 `ebb01d8`；合并提交信息已用 `git log -1 --format=%B` 自查。本包不合并回 integration。

## 修改与行为

- `apps/desktop/src/stores/chat.store.ts`：`EVENT_CURSOR_EXPIRED` 或 HTTP 410 不再因缺少/非法 `detail.latestSeq` 调用 `stopPolling()`。仅接受非负安全整数；缺失、字符串、负数、小数、NaN、Infinity、越界整数均回退游标0。
- 过期后等待本轮旧快照读取结束，再重新读取会话列表、审批、当前对话消息（从消息序号0开始）及运行快照。保留当前对话、草稿及已有消息展示，不调用清空用户输入的全局reset。未选中对话时仍读取会话和审批，沿用已有自动选择流程。
- 有有效 latestSeq 时仍跳至该序号并补快照，首次重试保持既有忙碌1秒/空闲4秒间隔。无有效序号的连续失败按 **1s、2s、5s、10s、30s，之后30s封顶** 自动重试；有效序号仍反复过期也进入退避，避免快照成功但事件始终失败时清零重试计数。
- 连续第3次过期后，沿用 loadError 显示“事件同步暂未恢复，正在自动重试；对话快照仍会继续刷新”。前两次不显示要求用户重新连接的错误。事件轮询成功后清除恢复计数和提示；离开页面/显式stop/reset仍能终止轮询，旧异步结果不会重新启动已停止的生命周期。
- `apps/desktop/src/shared/api/local-hub-gateway.ts`：4410/4010原本已重连，但被 bootstrap Promise 的完成阻塞，且每次onopen会清零退避。现在重连独立于bootstrap成功/失败/挂起；只有收到可解析事件才清零重连次数。沿用WS既有 **1s × 1.5，15s封顶** 策略。换票报 EVENT_CURSOR_EXPIRED/410 时也重置/跳转游标并请求bootstrap，然后继续换票重连。
- 不修改UI组件、页面布局、协议、Hub、依赖或共享配置；不新增用户操作入口。

## 回归覆盖

新增 `chat.polling.test.ts` 的9个用例：7种非法/缺失游标、自动补四类快照并定时续轮询、连续失败退避封顶与成功后恢复、停止生命周期后迟到快照不重启。原有 `chat.reliability.test.ts` 的 latestSeq=80 用例未改并通过。

新增 `local-hub-gateway.cursor.test.ts` 的4个用例：bootstrap挂起/失败仍重连、连续4410递增退避、收到事件后恢复初始重试间隔、unsubscribe停止重连、换票游标过期缺少/带latestSeq自动补快照与重连。现有4410用例也通过。

定向最终结果：4 files / 34 tests passed。首次定向执行有9项失败，原因是新增测试错误断言未对外暴露的 `store.isPolling`；已删除对私有状态的依赖，改以实际请求次数/定时行为确认恢复，不为测试扩大Store API。下方为最终完整验收真实输出（仅清理ANSI颜色与行尾空格）。

## 验收命令与真实输出

全部串行执行；临时目录为worktree内被忽略的 `.tmp`，未并行运行构建/测试。设置 `TEMP`、`TMP` 指向 `.tmp`，`pnpm_config_verify_deps_before_run=false`，未安装或更新依赖。

### lint

```text
> pnpm --filter @hqagent/desktop lint
$ eslint src
EXIT_CODE=0
```

### typecheck

```text
> pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit
EXIT_CODE=0
```

### vitest

```text
> pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2

 RUN  v2.1.9 E:/OtherPro/HQAgent-Hub-worktrees/r15-web/apps/desktop

 ✓ src/pages/remote/RemoteR15Features.test.ts (14 tests) 284ms
 ✓ src/pages/remote/RemoteEvents.test.ts (15 tests) 408ms
stderr | src/shared/attachments/Attachments.test.ts > attachment sending > preserves remote draft and staged attachments after server image rejection
[Vue warn]: injection "Symbol(router)" not found.
  at <RemoteChatPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/native/NativeR3.test.ts > R3 roots and workspace registration > disables the new-task add-project entry when catalog has no authorized roots
[Vue warn]: injection "Symbol(router)" not found.
  at <RemoteChatPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/native/NativeR3.test.ts > R3 roots and workspace registration > selects the registered project in the parent task form after catalog synchronization
[Vue warn]: injection "Symbol(router)" not found.
  at <RemoteChatPage ref="VTU_COMPONENT" >
  at <VTUROOT>

 ✓ src/pages/native/NativeR3.test.ts (26 tests) 702ms
 ✓ src/shared/attachments/Attachments.test.ts (23 tests) 627ms
 ✓ src/shared/api/mock-local-chat-gateway.test.ts (16 tests) 11ms
 ✓ src/shared/maintenance/Maintenance.test.ts (20 tests) 235ms
 ✓ src/shared/runtime/PiRuntime.test.ts (17 tests) 197ms
 ✓ src/pages/remote/RemoteDeviceManagement.test.ts (11 tests) 260ms
 ✓ src/pages/remote-link/RemoteLink.test.ts (9 tests) 284ms
 ✓ src/pages/remote/RemotePhoneRepair.test.ts (10 tests) 486ms
stderr | src/shared/api/local-hub-gateway.test.ts > LocalHubGateway > R3 & R7: handles WS ticket acquisition failure with reconnect backoff
[LocalHubGateway] Failed to establish WS connection HubApiError: Hub is still starting up
    at LocalHubGateway.fetchApi (E:\OtherPro\HQAgent-Hub-worktrees\r15-web\apps\desktop\src\shared\api\local-hub-gateway.ts:133:13)
    at LocalHubGateway.acquireWsTicket (E:\OtherPro\HQAgent-Hub-worktrees\r15-web\apps\desktop\src\shared\api\local-hub-gateway.ts:169:17)
    at E:\OtherPro\HQAgent-Hub-worktrees\r15-web\apps\desktop\src\shared\api\local-hub-gateway.ts:316:24 {
  code: 'HUB_NOT_READY',
  status: 503,
  detail: undefined,
  retryable: true,
  requestId: 'req_init'
}

stderr | src/shared/api/local-hub-gateway.test.ts > LocalHubGateway > R3 & R7: handles WS ticket acquisition failure with reconnect backoff
[LocalHubGateway] Failed to establish WS connection HubApiError: Hub is still starting up
    at LocalHubGateway.fetchApi (E:\OtherPro\HQAgent-Hub-worktrees\r15-web\apps\desktop\src\shared\api\local-hub-gateway.ts:133:13)
    at LocalHubGateway.acquireWsTicket (E:\OtherPro\HQAgent-Hub-worktrees\r15-web\apps\desktop\src\shared\api\local-hub-gateway.ts:169:17)
    at E:\OtherPro\HQAgent-Hub-worktrees\r15-web\apps\desktop\src\shared\api\local-hub-gateway.ts:316:24 {
  code: 'HUB_NOT_READY',
  status: 503,
  detail: undefined,
  retryable: true,
  requestId: 'req_init'
}

 ✓ src/shared/api/local-hub-gateway.test.ts (8 tests) 143ms
 ✓ src/pages/scenes/ScenesPage.test.ts (9 tests) 749ms
 ✓ src/pages/remote/PairingScanner.test.ts (16 tests) 297ms
 ✓ src/pages/native/NativeAvailability.test.ts (16 tests) 228ms
 ✓ src/pages/chat/RemoteConversationReadOnly.test.ts (7 tests) 191ms
 ✓ src/pages/chat/ChatMobile.test.ts (6 tests) 535ms
 ✓ src/stores/chat.polling.test.ts (15 tests) 32ms
 ✓ src/pages/remote/RemoteTokens.test.ts (7 tests) 292ms
 ✓ src/shared/ui/SharedOverlays.test.ts (9 tests) 120ms
 ✓ src/shared/api/desktop-gateway.test.ts (8 tests) 19ms
stderr | src/pages/remote/RemoteChat.test.ts > RemoteChat Workbench and Three-Layer Status > displays "电脑离线" and NEVER "执行中" when computer is offline, and rejects message immediately
[Vue warn]: injection "Symbol(router)" not found.
  at <RemoteChatPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemoteChat.test.ts > RemoteChat Workbench and Three-Layer Status > renders all three distinct layers: Transport State, Control Result, and Execution State
[Vue warn]: injection "Symbol(router)" not found.
  at <RemoteChatPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemoteChat.test.ts > RemoteChat Workbench and Three-Layer Status > displays rejected and unconfirmed control outcomes accurately
[Vue warn]: injection "Symbol(router)" not found.
  at <RemoteChatPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemoteChat.test.ts > RemoteChat Workbench and Three-Layer Status > enforces high-risk approval restrictions: hides approve button and displays warning banner
[Vue warn]: injection "Symbol(router)" not found.
  at <RemoteChatPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemoteChat.test.ts > RemoteChat Workbench and Three-Layer Status > supports opening and closing mobile sidebar drawer
[Vue warn]: injection "Symbol(router)" not found.
  at <RemoteChatPage ref="VTU_COMPONENT" >
  at <VTUROOT>

 ✓ src/pages/remote/RemoteChat.test.ts (7 tests) 234ms
 ✓ src/pages/chat/components/ChatComposer.test.ts (7 tests) 76ms
 ✓ src/stores/chat.store.test.ts (9 tests) 28ms
 ✓ src/shared/api/local-chat-gateway.test.ts (8 tests) 9ms
 ✓ src/shared/attachments/transport.test.ts (8 tests) 14ms
 ✓ src/pages/remote-link/RemoteLinkSyncSwitch.test.ts (3 tests) 143ms
 ✓ src/pages/remote/RemoteMobileLayout.test.ts (8 tests) 337ms
stderr | src/pages/remote/RemotePairing.test.ts > RemotePairingPage > formats input to 8 uppercase alphanumeric characters and fetches preview
[Vue warn]: injection "Symbol(router)" not found.
  at <RemotePairingPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemotePairing.test.ts > RemotePairingPage > handles REMOTE_PAIRING_EXPIRED error correctly
[Vue warn]: injection "Symbol(router)" not found.
  at <RemotePairingPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemotePairing.test.ts > RemotePairingPage > handles REMOTE_PAIRING_CONFLICT error correctly
[Vue warn]: injection "Symbol(router)" not found.
  at <RemotePairingPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemotePairing.test.ts > RemotePairingPage > handles REMOTE_PAIRING_INVALID error correctly
[Vue warn]: injection "Symbol(router)" not found.
  at <RemotePairingPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemotePairing.test.ts > RemotePairingPage > B7: reads shortcode from location.hash, immediately clears hash, auto-fills code and triggers preview without auto-binding
[Vue warn]: injection "Symbol(router)" not found.
  at <RemotePairingPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemotePairing.test.ts > RemotePairingPage > B7: ignores invalid code in location.hash and does not trigger preview
[Vue warn]: injection "Symbol(router)" not found.
  at <RemotePairingPage ref="VTU_COMPONENT" >
  at <VTUROOT>

stderr | src/pages/remote/RemotePairing.test.ts > RemotePairingPage > B7: unauthenticated user preserves code in memory via authStore across login with zero storage leaks
[Vue warn]: injection "Symbol(router)" not found.
  at <RemotePairingPage ref="VTU_COMPONENT" >
  at <VTUROOT>

 ✓ src/pages/remote/RemotePairing.test.ts (7 tests) 80ms
 ✓ src/pages/chat/ChatPage.test.ts (7 tests) 653ms
 ✓ src/stores/chat.context.test.ts (7 tests) 24ms
 ✓ src/stores/task.store.test.ts (7 tests) 544ms
 ✓ src/stores/chat.reliability.test.ts (7 tests) 24ms
 ✓ src/pages/chat/components/ProcessActivityGroup.test.ts (5 tests) 46ms
 ✓ src/pages/remote/RemoteGateway.test.ts (4 tests) 5ms
 ✓ src/stores/scenes.store.test.ts (6 tests) 11ms
 ✓ src/pages/remote/RemoteManagementGateway.test.ts (9 tests) 29ms
 ✓ src/stores/session-resumption.test.ts (13 tests) 32ms
 ✓ src/pages/native/NativeGateway.test.ts (12 tests) 13ms
 ✓ src/shared/api/mock-gateway.test.ts (10 tests) 51ms
 ✓ src/shared/api/local-hub-gateway.cursor.test.ts (4 tests) 9ms
 ✓ src/pages/remote/RemoteModeIsolation.test.ts (4 tests) 49ms
 ✓ src/pages/chat/components/ChatSidebar.test.ts (3 tests) 141ms
 ✓ src/stores/app.store.test.ts (8 tests) 284ms
 ✓ src/pages/remote/RemoteAuth.test.ts (4 tests) 6ms
 ✓ src/pages/tasks/TaskDetailPage.test.ts (5 tests) 121ms
 ✓ src/pages/chat/components/RunSnapshotDrawer.test.ts (1 test) 29ms
 ✓ src/shared/ui/HqMarkdown.test.ts (6 tests) 40ms
 ✓ src/stores/approval.store.test.ts (4 tests) 231ms
 ✓ src/pages/chat/components/ChatMessageItem.test.ts (3 tests) 57ms
 ✓ src/shared/theme/theme.engine.test.ts (5 tests) 5ms
 ✓ src/app/layouts/AppLayout.test.ts (3 tests) 112ms
 ✓ src/app/DesktopConnection.test.ts (1 test) 33ms
 ✓ src/pages/approvals/ApprovalsPage.test.ts (3 tests) 104ms
 ✓ src/stores/team.store.test.ts (5 tests) 1034ms
 ✓ src/stores/chat.action-scope.test.ts (2 tests) 11ms
 ✓ src/pages/tasks/TasksPage.test.ts (3 tests) 63ms
 ✓ src/pages/templates/TemplatesPage.test.ts (3 tests) 83ms
 ✓ src/shared/api/local-chat-timeout.test.ts (3 tests) 6ms
 ✓ src/stores/workspace.store.test.ts (3 tests) 209ms
 ✓ src/pages/agents/AgentsPage.test.ts (3 tests) 146ms
 ✓ src/pages/sessions/SessionsPage.test.ts (3 tests) 70ms
 ✓ src/stores/agent.store.test.ts (3 tests) 351ms
 ✓ src/pages/remote/pairing-qr.test.ts (29 tests) 9ms
 ✓ src/pages/auth/ConnectPage.test.ts (2 tests) 44ms
 ✓ src/pages/onboarding/OnboardingPage.test.ts (2 tests) 180ms
 ✓ src/pages/workspaces/WorkspacesPage.test.ts (3 tests) 69ms
 ✓ src/shared/attachments/sha256.test.ts (10 tests) 4477ms
   ✓ bounded incremental SHA-256 > processes a virtual 20MB file using only bounded slices, without a whole-file read 4470ms
 ✓ src/shared/qr/pairing-qr-code.test.ts (2 tests) 18ms
 ✓ src/pages/teams/TeamsPage.test.ts (3 tests) 88ms
 ✓ src/pages/overview/OverviewPage.test.ts (2 tests) 62ms
 ✓ src/stores/local-auth.store.test.ts (2 tests) 7ms
 ✓ src/shared/ui/HqButton.test.ts (4 tests) 25ms
 ✓ src/stores/session.store.test.ts (2 tests) 291ms
 ✓ src/shared/theme/forms.test.ts (1 test) 2ms
 ✓ src/shared/ui/NoNativeDialogs.test.ts (2 tests) 3ms

 Test Files  75 passed (75)
      Tests  552 passed (552)
   Start at  17:27:26
   Duration  48.02s (transform 3.10s, setup 0ms, collect 23.89s, tests 16.92s, environment 32.76s, prepare 5.12s)
EXIT_CODE=0
```

### build

```text
> pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1802 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-DnrGOxwr.css                                                    60.88 kB │ gzip: 11.29 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RuntimeIcon.vue_vue_type_script_setup_true_lang-CgzGlMXs.js            0.54 kB │ gzip:  0.35 kB
dist/assets/PiGuardStatus.vue_vue_type_script_setup_true_lang-BFUTiEIW.js          0.79 kB │ gzip:  0.52 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-CUjmychk.js    0.92 kB │ gzip:  0.59 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-CuHKQWzI.js           1.17 kB │ gzip:  0.62 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-CemGJXKT.js           1.55 kB │ gzip:  0.75 kB
dist/assets/confirm-EYJxtNZB.js                                                    1.74 kB │ gzip:  0.94 kB
dist/assets/PlaceholderPage-BtPCzsDm.js                                            1.74 kB │ gzip:  1.09 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-D2F41ATq.js             1.88 kB │ gzip:  0.89 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-BWRXfzfk.js           2.44 kB │ gzip:  1.19 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-2fpPiwrl.js                2.51 kB │ gzip:  1.11 kB
dist/assets/native-utils-n0IYZDfE.js                                               2.53 kB │ gzip:  1.70 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-1EnHHuKG.js     2.61 kB │ gzip:  1.42 kB
dist/assets/team.store-DipK2jiJ.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-C2EENVDT.js                                            3.85 kB │ gzip:  1.85 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-C6Ut7z5Y.js               4.39 kB │ gzip:  2.01 kB
dist/assets/ConnectPage-RlNE7OWz.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-DvKUFQUm.js                                          6.23 kB │ gzip:  2.81 kB
dist/assets/PairingScanner-DT0OEdDR.js                                             6.26 kB │ gzip:  3.40 kB
dist/assets/task.store-Dl6b95It.js                                                 6.99 kB │ gzip:  2.61 kB
dist/assets/RemoteTokensPage-BC9dPXQW.js                                           7.59 kB │ gzip:  3.85 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-D90tRIU8.js               7.62 kB │ gzip:  3.28 kB
dist/assets/RemoteDevicesPage-PFakrIzS.js                                          8.54 kB │ gzip:  3.75 kB
dist/assets/WorkspacesPage-Bpkleye-.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/TemplatesPage-DfSYAJe1.js                                              9.62 kB │ gzip:  4.27 kB
dist/assets/SessionsPage-CzzNpDMp.js                                              10.58 kB │ gzip:  4.52 kB
dist/assets/TasksPage-Cj32ez4J.js                                                 11.80 kB │ gzip:  4.69 kB
dist/assets/OverviewPage-Dzid8P80.js                                              12.12 kB │ gzip:  3.95 kB
dist/assets/ApprovalsPage-Lmr-z19S.js                                             12.54 kB │ gzip:  5.07 kB
dist/assets/OnboardingPage-CE-NRAAh.js                                            12.94 kB │ gzip:  4.92 kB
dist/assets/TeamsPage-CTtbaD1W.js                                                 16.12 kB │ gzip:  6.01 kB
dist/assets/remote-chat.store-7NVYcvT5.js                                         22.75 kB │ gzip:  7.34 kB
dist/assets/TaskDetailPage-SAUPz1Iw.js                                            23.47 kB │ gzip:  7.99 kB
dist/assets/AgentsPage-DnXJvVZu.js                                                24.14 kB │ gzip:  8.86 kB
dist/assets/AttachmentDrafts.vue_vue_type_script_setup_true_lang-BTBv32OI.js      25.99 kB │ gzip: 10.34 kB
dist/assets/ScenesPage-CU3NotW5.js                                                27.24 kB │ gzip:  9.26 kB
dist/assets/RemoteLinkPage-No94b1Yo.js                                            36.42 kB │ gzip: 13.43 kB
dist/assets/RemoteChatPage-CUMvSr2l.js                                            42.34 kB │ gzip: 13.22 kB
dist/assets/ChatPage-Dxdzrdzs.js                                                  83.04 kB │ gzip: 25.66 kB
dist/assets/jsQR-UMIdgYmG.js                                                     130.80 kB │ gzip: 47.46 kB
dist/assets/vendor-DAwl41T1.js                                                   150.58 kB │ gzip: 50.79 kB
dist/assets/index-Du15lia0.js                                                    253.87 kB │ gzip: 84.04 kB
✓ built in 6.42s
EXIT_CODE=0
```

## 边界与联调

- lint、typecheck、vitest、build均退出0；完整vitest为75个文件、552个测试通过。测试日志中的503/断网等为既有mock故障注入，不是真实服务端响应；本轮未请求真实Hub/云端，未遇真实429/403、0xC0000142或额度错误。
- 未运行Tauri安装包/用户真实Hub联调。Hub补齐所有错误detail.latestSeq后，应验证有效序号快速追平；旧Hub无序号时验证快照持续刷新、退避后可恢复。若旧Hub一直拒绝after=0且始终不提供可用序号，前端会持续退避补快照，无法自行推算服务端保留窗口；不会永久停止，也不会要求重启应用。
- 仅有相关4个src文件与本回执为本包新增改动（integration合并带入的既有变更不属于本包）。`git diff --check`通过。按主题提交后自查提交消息，无署名。
