# R3-P3 前端回执（协议 0.9.1 / D51）

## 交付状态与范围

- 工作区：`E:/OtherPro/HQAgent-Hub-worktrees/r15-web`；分支：`feat/r15-web`。
- 基线：`f15a59a`；实现及测试提交：`a69db5a` — `feat(native): add mobile imports, authorized projects and desktop settings`。
- 已实现手机/电脑原生会话入口、读取/导入、授权目录项目登记、本机根目录设置、native 继续会话与内存保护。
- **A5 的“同步关闭时给出精确原因”存在接口缺口，不能宣称完整解决**；已采用明确的待核对提示，依据与建议见下文 Q1。电脑端未提供协商线路及完整同步完成字段，按契约采用保守待同步提示（Q2）。
- lint、typecheck、vitest、build 均退出 0；58 个测试文件、356 项测试通过。新增 38 项 R3 测试。
- 仅修改 `apps/desktop/**` 与 `.hqagent/handoffs/**`。未改协议、Hub、Server、根配置、锁文件或 src-tauri。没有执行部署、合并或推送。
- TEMP/TMP 指向已忽略的 worktree `.tmp`。未发生 0xC0000142 或 API 额度错误。

## A. 手机端原生会话

- 对话列表下独立「原生会话」区，当前电脑内按 workspace 分组，项目名来自 catalog；显示 Claude Code / Codex 以及 unknown / likely_active / closed_confirmed 的三种中文状态。支持索引分页、刷新和可见页面的定时刷新。
- 原生详情只读，在线从电脑实时读取，离线明确显示「电脑离线，无法读取原生会话内容」。格式不可读显示源索引的安全原因；超时、过大、unsupported 显示中文原因与 requestId，可重新读取。
- `NativeMessageAssembler` 将 before 跨页片段保存在当前组件内存，按源版本/快照/会话ID隔离，检查段号、数量、元数据一致性，拼齐后检查 UTF-8 字节数及 SHA-256。未拼齐不渲染正文；最终页仍缺片段明确报错，不截断冒充完整。离线、切换、关闭与卸载清空当前读取状态。
- 「接着对话」先 GET 当前索引，再显示终端退出警告及默认不勾选的复选框；确认才提交 terminalClosedConfirmed=true、expectedIndexVersion、sourceRevision。ACTIVE / CHANGED / WRITER_CONFLICT / SUSPENDED 均显示原因，失败清掉勾选；暂停错误刷新设备状态。勾选不能覆盖电脑的活跃检测与写锁。
- 202 后独立显示「正在电脑上导入…」，不伪造 RemoteConversationView/Run。通过 GET commands 对账；completed + resourceRef.conversationId 后重拉当前电脑对话，真实投影出现才选中并加载。已 accepted/granted 的导入不会因原送达期限经过而被客户端谎报失败。
- native 导入对话显示 Agent 标识，不显示场景；消息固定 continue，即使调用方传 new 也由 store 修正。原忙碌、取消、可见性、状态标记仍走原流程。
- 续接确认失效时显示同样的关闭提醒和显式勾选，可发送 nativeConfirmation（当前 sourceRevision）；unknown 未确认时禁发。CHANGED 会刷新会话状态，不静默新建上下文。
- 修订检查接受 3-only 设备；native 要求 3，普通 R1.5 对话允许 2 或 3。已知不支持 3 的电脑明确显示升级原因。

## B. 授权根目录内添加项目

- 新建任务的项目字段旁增加「添加项目」；没有 authorizedRoots 时置灰并提示「电脑未开放远程添加项目」。离线/暂停同样禁止目录操作。
- 根下拉仅显示 displayName，不显示绝对路径。逐层 POST directory-listings，只发送 rootId/rootVersion/directoryToken/cursor/limit。前端面包屑栈保留目录名和不透明 token，前进/返回不拼接路径。
- 展示文件夹名、Git 仓库标记、分页加载及当前文件夹选择。选择非 Git 目录显示「非 Git 仓库只能运行只读任务」。不执行 mkdir/init-git/clone。
- ROOT_NOT_AUTHORIZED / PATH_OUTSIDE_ROOT / DIRECTORY_CHANGED 显示失败原因，清除旧选择与层级并重读 catalog；回到根后用户可重试。暂停竞态刷新设备状态。
- 登记返回 202 后显示「正在电脑上添加项目…」，GET commands 的真实 resourceRef.workspaceId 出现后拉取 catalog；项目实际进入 catalog 才通知父表单并自动选中。轮询等待不会乐观伪造项目或猜测 ID。

## C. 电脑端

- 「连接手机」页新增授权根目录设置：GET/PUT 本机 `/api/v2/remote/authorized-roots`，仅电脑本机会话调用；复用 pickLocalDirectory 选择目录，支持显示名称、添加/移除与最多32根限制。
- PUT 全量替换，带当前 expectedVersion；成功重读；CAS 冲突先重读并要求重新确认，不自动覆盖别人改动。显示默认不开放及移除后既有项目保留的说明。
- 本地侧栏加入独立原生会话组；使用本机 native-sessions 的四个接口，不混用云端公开ID，不依赖配对/网络/远程暂停/同步开关。
- 本机导入是 201 LocalConversationView，同样先显式确认终端退出；成功直接选中本机会话。无远程送达/grant占位，不启动模型。
- native 标识覆盖对话标题、侧栏与运行详情；不展示场景角色卡或伪造 SceneSnapshot。发送固定 continue，禁用上下文重置入口。
- 本机 native 同步提示周期性读取 RemoteLinkView 与 RemoteSyncSettingsView，区分未配对、离线、同步关闭、撤销、冻结/待核对；其余保守显示「已在本机导入，待连接支持修订 3 的服务后同步」。不以连接 online 或协议包版本声称同步成功。

## D. 隐私、错误与网关

- 所有新增 DTO 直接导入 `@hqagent/protocol`。目录、根配置、native 索引/历史/导入分别使用冻结类型；内部 UI 状态没有被当作协议字段。
- 远程 catalog 升为 RemoteV3CatalogView，以读取可选 authorizedRoots；缺字段按空根列表处理。
- 所有 R3 请求使用既有 Cookie 网关，写请求保留 CSRF/Origin/Idempotency-Key 流程，不添加 Authorization。local/remote Base URL 与 ID 分开使用。
- HTTP fetch 设置 cache=no-store；目录 token 放 POST body，目录名与原生正文不放 URL。before/index cursor 是契约指定的 GET 游标参数，不是目录选择 token。
- 新错误码按冻结 guidance 加入 remote-errors.ts。原生交互为 ACTIVE/CHANGED 补充任务书要求的明确提示，超时提示可重试；失败显示 requestId。本机错误也优先取 X-Request-Id，再回退信封。
- 发现旧本地 pendingOperation 会把输入与幂等记录写入 sessionStorage。**native 消息、native 元数据编辑与 native 运行指令使用独立内存记录**；明确拒绝/完成清理，chat reset 清理；不把原生内容写进原有持久化桶。场景任务既有重试行为不变。
- 临时预览内容、目录 token/名称、根目录编辑状态仅在内存；组件关闭/卸载清理。没有新增内容日志、凭据日志或分析上报。
- Mock 只使用 `native-examples.ts` 的合成索引/文本，不读取任何 CLI 文件。导入复制合成历史，native 发送生成无场景快照的单 Agent 运行。

## 接口缺口与需要下游处理的事项

### Q1：手机无法可靠判定“同步关闭”（A5 未完全满足）

只读核对 `apps/server/server/native.py::native_page`：该索引读取路径直接从 native-index 表分页，空表返回 `{items:[],hasMore:false}`，没有查询副本 enabled 状态或返回 REMOTE_SYNC_DISABLED。`apps/server/server/app.py` 的 native_list 分支直接调用上述方法。同步关闭又会清掉索引，所以此空页与“确实没有会话”无法区分。

0.9.1 的 RemoteDeviceView、RemoteNativeSessionPage、RemoteV3CatalogView 均无可用于读取同步开关的字段；store.reset 也没有 reason/开关值。supportedWireRevisions 表示能力集合，不能充当当前协商线路或同步开关。

前端处理：已知低版本显示升级提示；服务端明确返回 REMOTE_SYNC_DISABLED 时显示「这台电脑已关闭同步」；否则空页显示「暂无可用的原生会话索引；请在电脑确认同步已开启、修订 3 连接已就绪。当前接口未提供同步开关状态。」不把空页谎报成同步关闭，也不只显示无会话。

建议 P0/P1 明确索引列表在同步关闭时返回现有 REMOTE_SYNC_DISABLED，或冻结一个可读取的就绪/同步视图。当前分工不允许修改后端或协议，因此本轮只上报，不能伪造字段完成精确原因判断。

### Q2：同步完成与当前线路无可观测视图

Local RemoteLinkView 只有连接状态/lastErrorCode 等，没有 negotiatedWireRevision、栅栏完成或按对话补传完成字段。按 R3-contract §11 的裁决，本机采用保守待同步文案并区分已有可证实原因。手机的 command.completed 仅表示导入提交；本轮等待真实对话投影并加载其已发布完整消息页后打开，**不把这个动作标为整段历史已全部同步**。未自造同步成功标志。

## 验证与旧断言调整

新增38项测试：

- NativeR3.test.ts：26项，包括分组/状态/离线、确认勾选、202对账、201本机导入、过送达期仍有grant、四种导入失败、三种读取失败、分段/hash/版本校验、内容清理、native继续及无场景运行、目录token/面包屑、变化回根、202项目同步选择、无根/暂停入口、根CAS/32上限、真实待同步原因和空索引不造开关事实。
- NativeGateway.test.ts：12项，包括本机/远程Cookie路由、no-store、CSRF、幂等、token body、before不附最新sourceRevision、requestId优先级与9个新增码的中文映射。

唯一修改的既有测试文件是 `mock-local-chat-gateway.test.ts`：`persists review mode while keeping existing run snapshots immutable` 的两处 `sceneSnapshot.reviewMode` 改为 `sceneSnapshot!.reviewMode`。0.9.1 为 native 允许省略快照，旧测试对象仍是 develop 场景，仍验证修改前后快照值都为 original_planner；没有改期望、删除或跳过断言。

基线 typecheck 实际报这两行 TS2532。首轮全量另外发现旧HTTP测试夹具没有 headers 对象，requestId读取改为可选链，保留原HubApiError断言；分段读取专项测试使用 waitFor 等待异步SHA完成。以上均修正后重跑，下面只引用最终输出。

## 最终验收命令与真实输出

所有命令在 worktree 根运行：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
```

完整日志位于 [r3-p3-validation](r3-p3-validation/)，仅规范化换行和行尾空白，保留 stdout/stderr 的警告。

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
Test Files  58 passed (58)
      Tests  356 passed (356)
   Start at  02:08:51
   Duration  28.94s (transform 1.95s, setup 0ms, collect 12.57s, tests 9.22s, environment 24.25s, prepare 3.71s)
```

### build（退出码 0）

```text
pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1829 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-CBai-Oc3.css                                                    55.80 kB │ gzip: 10.38 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-ByXrFyzR.js    0.92 kB │ gzip:  0.60 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-CqCVyS_D.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-7Uv4u2Q2.js           1.55 kB │ gzip:  0.75 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-DzeCsAdn.js             1.69 kB │ gzip:  0.82 kB
dist/assets/PlaceholderPage-DlC4AO96.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-COnzaYB3.js               2.16 kB │ gzip:  1.06 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-GDnqX88M.js                2.32 kB │ gzip:  1.04 kB
dist/assets/native-utils-DHvfYaPg.js                                               2.40 kB │ gzip:  1.57 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-DkRhlyDX.js           2.44 kB │ gzip:  1.19 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-KN0e8e9E.js     2.61 kB │ gzip:  1.42 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-CbSDk5oy.js               2.85 kB │ gzip:  1.33 kB
dist/assets/team.store-DSUqOJcu.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-O98OFQm2.js                                            3.82 kB │ gzip:  1.84 kB
dist/assets/ConnectPage-B-r97eMO.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-CZziA9dB.js                                          5.33 kB │ gzip:  2.49 kB
dist/assets/task.store-DcW66-ZC.js                                                 6.99 kB │ gzip:  2.61 kB
dist/assets/RemoteTokensPage-OQ5zHzMy.js                                           8.01 kB │ gzip:  3.88 kB
dist/assets/WorkspacesPage-CbO_hgXd.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/RemoteDevicesPage-CXfMi2Lu.js                                          9.00 kB │ gzip:  3.77 kB
dist/assets/NativeSessionsPanel.vue_vue_type_script_setup_true_lang-60CxM3ZB.js    9.11 kB │ gzip:  3.92 kB
dist/assets/TemplatesPage-B8KNUUGI.js                                              9.61 kB │ gzip:  4.26 kB
dist/assets/SessionsPage-BQeLB07Z.js                                              10.55 kB │ gzip:  4.50 kB
dist/assets/AgentsPage-CN_dnXQp.js                                                11.61 kB │ gzip:  4.05 kB
dist/assets/TasksPage-Cxm138cJ.js                                                 11.73 kB │ gzip:  4.67 kB
dist/assets/OverviewPage-BVwyTjX2.js                                              12.12 kB │ gzip:  3.95 kB
dist/assets/ApprovalsPage-CSUqo1Ne.js                                             12.26 kB │ gzip:  4.96 kB
dist/assets/OnboardingPage-BP46pKr8.js                                            12.93 kB │ gzip:  4.91 kB
dist/assets/TeamsPage-3fS-34dW.js                                                 15.96 kB │ gzip:  5.93 kB
dist/assets/remote-chat.store-DBrxm2OZ.js                                         21.30 kB │ gzip:  6.78 kB
dist/assets/TaskDetailPage-k02ZIzDB.js                                            23.41 kB │ gzip:  7.98 kB
dist/assets/ScenesPage-ByuQpOdP.js                                                25.53 kB │ gzip:  8.68 kB
dist/assets/RemoteChatPage-BNJ5zsT8.js                                            40.06 kB │ gzip: 12.37 kB
dist/assets/RemoteLinkPage-BxfQuhtZ.js                                            49.42 kB │ gzip: 18.86 kB
dist/assets/ChatPage-BYMFoSXd.js                                                  78.43 kB │ gzip: 23.54 kB
dist/assets/vendor-Brayy0Hw.js                                                   146.41 kB │ gzip: 49.58 kB
dist/assets/index-B2_YYL6x.js                                                    220.19 kB │ gzip: 71.94 kB
✓ built in 5.59s
```

日志含测试环境 router injection 警告、HUB_NOT_READY 故障模拟输出，以及构建既有 `Generated an empty chunk: "echarts".`；命令退出码均为0，未隐藏警告。

## 截图与浏览器复现

全部使用合成 Mock 数据，没有读取真实会话内容。

| 场景 | 截图 |
| --- | --- |
| 手机原生会话列表 375×812 | [native-list](screenshots/r3-p3/native-list-375x812.png) |
| 手机导入确认 375×812 | [native-import](screenshots/r3-p3/native-import-375x812.png) |
| 手机授权目录浏览 375×812 | [directory](screenshots/r3-p3/directory-375x812.png) |
| 电脑授权根设置 1280×800 | [authorized-roots](screenshots/r3-p3/authorized-roots-1280x800.png) |

已逐张打开检查；列表截图显式等待抽屉动画结束，避免把动画过程当作交付图。浏览器还走了本机导入、导入后历史展示、未配对文案和 Web Storage 不含原生内容的断言。

```powershell
pnpm --filter @hqagent/desktop exec vite --mode mock --host 127.0.0.1 --port 5198 --strictPort
# 另一个终端，从同一 worktree 根目录执行：
python .hqagent/handoffs/screenshots/r3-p3/capture.py
```

最终浏览器输出（退出码0）：

```text
mobile native read / unchecked confirmation / directory browsing: PASS
desktop authorized roots: PASS
desktop local import, history and in-memory-only content: PASS
browser errors: 0
Screenshots: 3 mobile + 1 desktop; synthetic content only
```

## 未验证范围与提交自查

- 未连接真实 Hub/Server、实体手机或 CLI；没有检查真实历史文件、模型执行、双进程写锁、文件系统授权边界或公网部署。这些属于后端/真实环境联调，不用 Mock 通过冒充。
- Q1 需要下游接口补齐才能满足精确提示；Q2 按契约保守显示，不声称同步成功。除此之外上述前端流程已落盘并通过列出的验证。
- 每次提交后执行 `git log -1 --format=%B` 检查，提交信息仅描述改动，没有署名、Co-Authored-By 或生成标记。实现与验收文档分别提交。
