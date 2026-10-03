# 0.10.1-P3 前端交付回执

## 基线、范围与提交

- 工作区 `E:/OtherPro/HQAgent-Hub-worktrees/r15-web`，分支 `feat/r15-web`。
- 开工先执行 `git merge integration/phase1`，输出 `Already up to date.`；基线 `52aa22e`，含 0.10.1 生成物。
- 已按 `R1.6-contract.md` §9 与 `R16-P0-protocol.md` 的 0.10.1 P3 要点实施，只改 `apps/desktop/**` 与本 handoff 目录；未改依赖、根配置、协议、Hub、服务端或手机端页面。
- 按主题提交：
  - `287e8c9` — `feat(desktop): add local maintenance gateway and mocks`
  - `c5626c6` — `feat(desktop): add confirmed image verification workflows`
  - `3d96096` — `feat(desktop): add confirmed conversation deletion and maintenance tests`
- 每次实现提交后已执行 `git log -1 --format=%B` 自查，输出即上述标题，无署名尾注或生成标记。验收材料另作 handoff 提交并同样自查。未合并回 integration，未部署。

## 图片能力验证

电脑端 Agent 管理页新增图片能力矩阵，本地对话顶部导航增加「Agent 管理」入口；手机端无新增入口。所有新操作走 LocalChatGateway 的本机 v2 Cookie 接口：

| 操作 | 请求 | 生成物 |
| --- | --- | --- |
| 读取矩阵 | GET `/api/v2/agents/image-verifications`，limit=50、includeInactiveModels，可翻页 | LocalImageVerificationPage / State |
| 发起验证 | POST `/api/v2/agents/image-verification-jobs` | StartLocalImageVerificationInput / JobView |
| 查询进度 | GET `/api/v2/agents/image-verification-jobs/{jobId}` | LocalImageVerificationJobView |
| 取消 | POST `/api/v2/agents/image-verification-jobs/{jobId}/cancellations`，严格 `{}` | LocalImageVerificationJobView |
| 删除对话 | DELETE `/api/v2/conversations/{id}?expectedVersion=N`，无请求体 | LocalConversationDeletionView |

- 按 Agent 实例和精确模型分别展示；默认选择器显示「默认模型」，发起时省略 modelId，不传 null、空串或伪造 default。展示 Agent 原名和实例 ID、CLI 版本、验证时间、当前是否有效、历史通过但当前无效。六种结构化失效原因均有中文映射；支持显示历史模型。
- 「验证」先弹出共用确认，明确显示本次 Agent/实例 ID/模型，并提示：**这会真实调用模型多次，可能产生费用或消耗订阅额度**。取消、Esc、关闭均不发起。确认只绑定本次捕获的 targetRevision 和精确选择器，确认后才发送 acknowledgeModelUsage=true。
- 一次确认生成一个不可变 input 和幂等键；请求未确认/网络/5xx/408 等不自动重新付费，显示「重试同次请求」，使用同一 input/key。目标变化等明确拒绝后须刷新并重新确认，不静默换实例、模型或修订。
- 约 1 秒轮询在途作业，同一作业不重叠 GET；终态、离页停止自动轮询，查询失败留待手动核对。重新打开页面通过 activeJobId 恢复；同目标 CONFLICT / verification_in_progress 使用返回 activeJobId 打开现有作业。
- 五项 new/resume/mixedFive/cancel/error 直接展示服务端状态，未执行不当作失败；列表顺序不推断实际执行顺序。作业取消与 cancel probe 分开。
- 取消同样二次确认，说明 **已产生的用量无法撤回**。cancel_requested 不声称停止；interrupted/unconfirmed 展示需核对，slotHeld/执行可能仍在运行/清理未确认时禁止重复验证、允许再次请求取消。只有服务端确认释放并已终结后，新的付费验证才允许重新明确确认。取消失败重试沿用取消键。
- 取消响应与旧 GET 并发时，旧轮询响应不能覆盖新的取消结果。安全诊断采用固定阶段/字段白名单，未知 raw/output 等字段不会渲染；不展示模型输出、提示词或内部路径。

## 删除对话

- 电脑端对话列表每行菜单和当前对话顶部菜单均有危险样式「删除对话」，归档对话同样可发起，实际可删由 Hub 检查全部关联执行。
- 删除前重新读取当前列表（含隐藏对话），取当前 version，旧记录缺省为 1；确认文案明确：**将删除本机对话、消息和附件，并清理已同步到云端的副本；原生会话的 CLI 原始记录不会被删除**。
- 只在明确确认后生成删除意图，发送 expectedVersion 和 Idempotency-Key。响应不明可重试同次删除，复用 key/version，不自动改版本或强制删除。
- CONFLICT 根据结构化 reason 显示中文，version_mismatch 显示 currentVersion；active_runs / recovery_required / cancellation_unconfirmed 等显示 blockingRunIds 和列表截断提示。可打开阻塞运行详情；不提供 force，不隐式取消/恢复后再删。
- 成功后移除本机列表、该对话草稿与待发/元数据意图，清理当前视图并选中剩余对话；没有剩余则留空。内存删除标记防止迟到列表响应把已删条目放回。
- remoteCleanup 分别显示：无需远端清理、连接后继续清理云端、已确认清理、云端是否清理未确认。不会把 pending/unconfirmed 说成云端已删除。

## Mocks 与测试

MockVerifications 只生成合成元数据和进度，不调用模型、CLI 或用户会话；当前通过、版本失效、未验证、历史模型、在途进度均可演示。默认目标 ID 绑定现有 mock Agent 实例，历史记录保持自身模型身份。Mock 删除只用于前端协议流程，不代表真实 Hub 的文件/数据库/Outbox 清理已验证。

新增 `shared/maintenance/Maintenance.test.ts` **20 项**，覆盖：

- 费用确认取消不请求、确认后精确 input/默认 modelId 省略。
- 付费幂等键复用、无自动重试、同目标重复发起受阻。
- 1 秒轮询、终态停止、重开 activeJobId、离页停止。
- 同目标 CONFLICT 打开现有 job；target_changed 不静默更新确认。
- 取消二次确认、interrupted/unconfirmed 占槽、cancel_requested 与 cancelled 区分、取消网络失败重用 key。
- 迟到 running 查询不能覆盖已确认取消。
- 当前有效与历史通过分离、includeInactiveModels。
- 诊断白名单排除未声明原文。
- 删除先读当前 CAS 版本，取消确认不 DELETE；成功移除当前选择及本对话草稿，保留其它草稿。
- 四个 remoteCleanup 状态逐项提示；版本冲突、运行冲突、打开阻塞运行、无强制删除。
- 删除不确定响应复用同 key/version。
- 五个真实 gateway 方法的 Cookie/no-store、精确路径、幂等键、取消 `{}`、DELETE 无 body。

## 真实验收输出

TEMP/TMP 均设为 worktree 内被忽略的 `.tmp`，构建、测试始终串行，未启动子代理。四项命令退出码均为 0。完整输出：[lint](fe-0101-validation/lint.txt)、[typecheck](fe-0101-validation/typecheck.txt)、[vitest](fe-0101-validation/vitest.txt)、[build](fe-0101-validation/build.txt)。

```text
> pnpm --filter @hqagent/desktop lint
$ eslint src

> pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit

> pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
Test Files  70 passed (70)
      Tests  511 passed (511)
   Start at  11:22:30
   Duration  45.92s (transform 3.20s, setup 0ms, collect 22.52s, tests 16.75s, environment 32.31s, prepare 5.13s)
```

```text
> pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1863 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-DnrGOxwr.css                                                    60.88 kB │ gzip: 11.29 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-Xazqci39.js    0.92 kB │ gzip:  0.60 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-CwqYZ__S.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-BEAulKVq.js           1.55 kB │ gzip:  0.75 kB
dist/assets/confirm-leMi7wsk.js                                                    1.74 kB │ gzip:  0.94 kB
dist/assets/PlaceholderPage-DAU0Aswm.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-B2Ze07C3.js             1.88 kB │ gzip:  0.89 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-C1FP6hec.js           2.44 kB │ gzip:  1.19 kB
dist/assets/native-utils-lEdcdYbW.js                                               2.45 kB │ gzip:  1.60 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-DdhexR8h.js                2.51 kB │ gzip:  1.11 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-DjrI6-lC.js     2.61 kB │ gzip:  1.42 kB
dist/assets/team.store-CcHZMBuV.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-oDBrlBVL.js                                            3.85 kB │ gzip:  1.85 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-DTFvTsNK.js               4.39 kB │ gzip:  2.02 kB
dist/assets/ConnectPage-eXffIT3C.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-CWoqiu0m.js                                          6.23 kB │ gzip:  2.81 kB
dist/assets/PairingScanner-CpHCa0X1.js                                             6.26 kB │ gzip:  3.40 kB
dist/assets/task.store-AjclxjZb.js                                                 6.99 kB │ gzip:  2.61 kB
dist/assets/RemoteTokensPage-BIa51rcY.js                                           7.59 kB │ gzip:  3.85 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-CWmy47TW.js               7.62 kB │ gzip:  3.28 kB
dist/assets/RemoteDevicesPage-DStaiPD8.js                                          8.54 kB │ gzip:  3.75 kB
dist/assets/WorkspacesPage-BFXdOA0z.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/TemplatesPage-CJFR7A9G.js                                              9.62 kB │ gzip:  4.27 kB
dist/assets/SessionsPage-CzjphNrP.js                                              10.58 kB │ gzip:  4.52 kB
dist/assets/TasksPage-Sx7ocJsn.js                                                 11.80 kB │ gzip:  4.69 kB
dist/assets/OverviewPage-DxmKxEbo.js                                              12.12 kB │ gzip:  3.95 kB
dist/assets/ApprovalsPage-Z50YCjeC.js                                             12.28 kB │ gzip:  4.97 kB
dist/assets/OnboardingPage-D1n3F2OA.js                                            12.94 kB │ gzip:  4.92 kB
dist/assets/TeamsPage-DjkjXLHv.js                                                 16.12 kB │ gzip:  6.01 kB
dist/assets/remote-chat.store-DADO5_Pb.js                                         22.06 kB │ gzip:  7.09 kB
dist/assets/AgentsPage-DQCD2bNE.js                                                22.58 kB │ gzip:  8.34 kB
dist/assets/TaskDetailPage-CxCEarPC.js                                            23.47 kB │ gzip:  7.99 kB
dist/assets/AttachmentDrafts.vue_vue_type_script_setup_true_lang-neUq5Rwr.js      25.54 kB │ gzip: 10.21 kB
dist/assets/ScenesPage-Dq_vpWpG.js                                                25.69 kB │ gzip:  8.71 kB
dist/assets/RemoteChatPage-C6pmwKhi.js                                            41.31 kB │ gzip: 12.92 kB
dist/assets/RemoteLinkPage-C8HDI2df.js                                            49.48 kB │ gzip: 18.90 kB
dist/assets/ChatPage-BgAp9oxA.js                                                  82.27 kB │ gzip: 25.48 kB
dist/assets/jsQR-UMIdgYmG.js                                                     130.80 kB │ gzip: 47.46 kB
dist/assets/vendor-BwG5n6H6.js                                                   149.77 kB │ gzip: 50.59 kB
dist/assets/index-CTdWVDtm.js                                                    239.71 kB │ gzip: 78.72 kB
✓ built in 11.41s
```

保留既有 router injection 测试警告、模拟 HUB_NOT_READY 日志和 echarts 空 chunk 提示。最终 **70 个文件、511 项测试通过**，没有删减或跳过原用例。

## 1280×800 亮暗截图

共 8 张，已查看检查；全部使用协议 mocks，没有真实付费验证或用户对话删除。

| 场景 | 亮色 | 暗色 |
| --- | --- | --- |
| 图片能力：已验证 / 失效 / 运行中 | [亮色](screenshots/fe-0101/light-image-capabilities-1280x800.png) | [暗色](screenshots/fe-0101/dark-image-capabilities-1280x800.png) |
| 费用确认 | [亮色](screenshots/fe-0101/light-usage-confirmation-1280x800.png) | [暗色](screenshots/fe-0101/dark-usage-confirmation-1280x800.png) |
| 删除确认 | [亮色](screenshots/fe-0101/light-deletion-confirmation-1280x800.png) | [暗色](screenshots/fe-0101/dark-deletion-confirmation-1280x800.png) |
| 删除冲突与阻塞运行 | [亮色](screenshots/fe-0101/light-deletion-conflict-1280x800.png) | [暗色](screenshots/fe-0101/dark-deletion-conflict-1280x800.png) |

[复现脚本](screenshots/fe-0101/verify.py)、[结构化检查](screenshots/fe-0101/verification.json)、[浏览器真实输出](fe-0101-validation/browser.txt)。脚本从 LocalChatGateway provider 获取当前 mock 实例，避免热更新时不同模块实例使演示作业未进入页面。

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
pnpm --filter @hqagent/desktop exec vite --mode mock --host 127.0.0.1 --port 5198 --strictPort
# 另一个终端，同一 worktree，使用已有 Python Playwright/Chromium：
$env:PYTHONUTF8='1'
python .hqagent/handoffs/screenshots/fe-0101/verify.py
```

浏览器检查退出码 0：

```text
{"checks": [{"theme": "light", "capabilityStates": ["verified", "invalidated", "running"], "paidStarts": 0, "deletion": "synthetic busy conversation rejected", "blockingRunLink": true, "horizontalOverflow": false}, {"theme": "dark", "capabilityStates": ["verified", "invalidated", "running"], "paidStarts": 0, "deletion": "synthetic busy conversation rejected", "blockingRunLink": true, "horizontalOverflow": false}], "screenshots": 8, "browserErrors": 0, "source": "Chromium + local protocol mocks; no real model calls or user deletion"}
```

## Hub 合入后的联调待验项

1. Cookie/Origin/幂等接口与真实分页快照；实际目标/默认模型/Runtime 变化引起的失效与 revision 冲突。
2. **真实模型用量必须由操作者在费用弹窗明确确认**；本包未执行任何真实 probe，不能把 mock 的 passed 当作设备/模型已验证。
3. 真实运行五项阶段 hook、取消与中断的精确句柄清理、Hub 重启恢复 activeJobId、未确认占槽及再次取消。
4. 真实删除的全量运行/recovery 阻塞、文件与数据库清理、原生 CLI 原始记录保护、离线 Outbox 和云端实际 ACK；本包只验证返回状态的界面含义。
5. Hub 旧版本不支持新接口时会显示读取失败/需核对，不假装成功；本轮未做 P2 真正联调或桌面壳端到端验证。

未遇真实 429、0xC0000142 或 API 额度错误；未新增依赖、持久化模型验证意图或敏感日志，开发服务已停止。按用户要求只交付当前分支，后续由主代理审核集成。
