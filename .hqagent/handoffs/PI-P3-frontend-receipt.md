# PI-P3 前端交付回执

## 基线与交付范围

- 工作区 `r15-web` / 分支 `feat/r15-web`，主代理已合入 integration；本轮基线 `32f816d`。按协议 **0.11.0 / D53**、PI-contract、PI-P0 前端要点和 PI 适配方案实施。
- 实现提交：`1636533` — `feat(desktop): support PI runtime with capability and guard checks`。提交后执行 `git log -1 --format=%B`，输出即该标题，无署名尾注或生成标记；验收材料另作 handoff 主题提交并同样检查。
- 仅修改 `apps/desktop/**` 与 `.hqagent/handoffs/**`。未增加依赖，未改根配置/lockfile、协议生成物、Hub 或服务端；未合并回 integration、未部署。
- 本轮全部使用协议生成物和前端 mocks，没有运行真实 PI CLI、读取模型凭据/扩展源码或发起模型调用。

## 实现

### 一致的 pi-v1 投影

`shared/api/client-features.ts` 集中声明 `X-HQ-Client-Features: pi-v1`。本机 v1、v2 与云端 JSON 请求统一使用 clientFetch；附件 XHR 上传和 blob 下载复用同一能力常量。列表、写操作、事件轮询、WS ticket 均携带该头。Bearer、Cookie、CSRF、Origin、Idempotency-Key 的既有处理不变；不会把模型密钥或能力声明放进 URL。

能力集没有运行时切换入口，调用方不能覆盖成另一投影。游标和 WS 确认序号保持内存状态，新客户端实例从新快照/票据开始，沿用既有游标失效后重取快照流程；不复用旧投影的持久游标。WebSocket 本身沿一次性 ticket，能力声明在 ticket 签发请求上携带。

当前 HTTP 原生索引改用 `RuntimeNativeSessionIndex`，远程 catalog 消费 `RemoteV5CatalogView`，名称函数采用 `RuntimeNativeAgentType`。未改协议中冻结的 NativeAgentType 或任何旧线路闭包。

### Agent 管理、模型与保护状态

- PI 使用统一 π 图标，显示实例名、CLI 版本、模型清单和安全状态；模型只在**第一个斜线**处分割为「渠道 · 模型」，保留剩余完整模型 ID 与大小写。
- ready 仅在 status=ready、isolation=hub_extension_only、reasons=[] 时成立。缺少 guard、未验证隔离、blocked 或存在原因均不视为可运行，明确提示 **PI 安全保护未就绪，不能运行任务**。
- 结构化原因全部中文映射，包括未受控扩展、保护未加载/超时、策略不可用、参数变化、路径越界、只读工具、审批拒绝/过期等。
- PI 页面不渲染 diagnosticMessage 原文、executablePath 或扩展源码，也不套用旧诊断弹窗中未经证实的健康/登录默认断言；只展示安全结构化元数据。
- 0.10.1 图片能力区块保留原有费用确认、五项验证和取消流程，PI 行可显示和验证；保护未就绪则禁用验证。PI 模型在此处也按「渠道 · 模型」显示，不根据 vision 名称推断已支持。

### 场景与角色

- 角色可选择实际发现的 PI 实例和已核实的本机模型列表。PI 不回退为任意模型/思考强度文本输入框；模型与思考强度必须匹配本机实际选项，空值表示继承默认，保存时省略空的 PI modelId/reasoningEffort。
- 规划/审核提示 `1aicode/deepseek/deepseek-v4-pro`，执行提示 `1aicode/deepseek/deepseek-v4-flash`。存在于精确本机清单才显示可用；不同 provider 或同名后缀不算命中。
- 建议不自动选择、安装、调用或换渠道。模型缺失显示「本机不可用，不会自动选择或切换渠道」，保留用户明确选择权。
- 场景卡片显示 PI 保护状态、当前模型和建议；只读场景也没有“忽略保护继续运行”入口。

### 运行、原生会话、审批和错误

- 本机场景按实际角色 Agent ID 检查 PI guard，发送前刷新本机实例状态；远程 PI 按 catalog.runtimes 的候选实例核对，缺失 guard 不放行，发送前刷新 catalog 并核对 worker/store 归属。后端仍是实时授权和隔离核验的最终执行边界。
- 支持修订 5 的现有原生/附件流程；已知 PI 目标缺少修订 5 支持、或 Hub/服务端明确返回 REMOTE_REVISION_REQUIRED 时显示「等待远程线路升级」。不会将 supportedWireRevisions 误当成已完成协商的证明。
- 原生列表/详情、对话侧栏/标题、原生消息与运行详情显示 PI 名称和图标。PI readable 树格式有 profile 时标记「已保存分支」；第一期 reader_not_implemented 样例为 unsupported，继续默认折叠，不假装可读或可续接。
- 本机审批按 requestAgentId 对应的已发现实例显示图标，保留请求 Agent 原名。云端原生会话有明确类型时显示 PI；场景中只知道参与 PI 时标为「含 PI 的场景」，不杜撰实际发起审批的角色身份。
- 新码 `PI_TOOL_CALL_BLOCKED`、`PI_GUARD_UNAVAILABLE`、`PI_UNCONTROLLED_EXTENSIONS` 均中文映射；包含本机/云端 HTTP 错误和云端异步命令失败展示。原来的高风险远程审批限制保持不变。

## 协议对接边界：不自造字段

以下已只读核对生成物，需要主代理在后续联调/协议讨论时明确：

1. **远程原生 PI 图片的精确绑定缺口。** `RemoteConversationView` 有 agentType/nativeSessionId，但没有精确 agentId/modelId；`catalog.nativeImageCapabilities` 可有多个实例/模型条目。不能只按 agentType 取第一条 PI capability，更不能把某模型验证套给另一模型。因此当前远程原生 PI 图片继续以 AGENT_IMAGE_UNSUPPORTED 保守拒绝。场景角色及本机按对话能力端点具有可核对的绑定时，仍按实例/transport/五层能力检查。需后续提供原生绑定元数据或可按对话查询的能力投影，再解除这项拒绝；本轮未擅改协议或路由。
2. **实际协商修订不可直接读取。** `RemoteDeviceView.supportedWireRevisions` 表示支持集合，`RemoteLinkView` 没有 negotiated revision。UI 不能保证已有 5 就代表完成 4→5 栅栏。缺少 5 或服务端明确拒绝时提示等待；本机 PI 原生同步提示需要修订 5 并说明当前接口未给出协商状态，不虚报已升级。
3. **原生运行的精确实例身份。** 原生会话公共元数据仅给 agentType；前端对已知 PI 候选做保守 guard 检查，不猜实例 ID。准确绑定、所有候选/后备链及实际启动前隔离检查必须由 P2/P1 执行。
4. 云端审批没有 requestAgentId/agentType 字段，不能把“场景包含 PI”当作某条审批一定由 PI 发起。前端只展示已有明确身份或场景参与提示。

这些边界不影响本包的 PI 列表/角色配置/请求头/安全提示；第二期原生读取与真实模型、图片、安全隔离验证不在前端 mock 验收范围内。

## 测试与真实输出

新增 `shared/runtime/PiRuntime.test.ts` **17 项**，并扩充既有二进制/桌面网关断言：

- v1 Bearer、v2 Cookie、云端列表/写入/事件轮询和 WS ticket 一致带 pi-v1；二进制上传/下载也携带，认证方式不变。
- 覆盖请求头覆盖冲突与统一入口；无旧投影能力值混入。
- PI 实例与模型展示、三类 guard 状态、未知保护拒绝、诊断路径/源码标记不渲染。
- 三个 PI 错误码的中文提示，PI 图片验证仍需要费用确认。
- readable PI 已保存分支与第一期 unsupported 分组。
- 模型首斜线分割、建议不自动选、不可用建议不跨 provider 替换、角色保存精确 modelId。
- 本机 PI ready 才派发，blocked 不发请求；远程缺失 guard 拒绝，修订未协商的明确拒绝提示等待升级。
- 不按 vision 字样猜能力，不套用无法精确绑定的远程原生图片能力。

原 mock happy-path 的 Agent 数量断言由 3 更新为 6，另断言其中 3 个为本轮合成 PI 状态样例；未删除旧测试。完整原始输出：[lint](pi-p3-validation/lint.txt)、[typecheck](pi-p3-validation/typecheck.txt)、[vitest](pi-p3-validation/vitest.txt)、[build](pi-p3-validation/build.txt)。

### 本机 pnpm 环境说明

首次运行脚本时当前 pnpm 自动执行依赖状态检查并尝试安装，退出：`ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`。现有工具仍完整可用。仅为本轮 shell 设置 `pnpm_config_verify_deps_before_run=false`，关闭自动安装检查，未修改根配置/lockfile、未增加依赖。所有正式验收使用已安装依赖，TEMP/TMP 指向被忽略的 `.tmp`；测试和构建串行。

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
$env:pnpm_config_verify_deps_before_run='false'
```

最终四项退出码均为 0：

```text
> pnpm --filter @hqagent/desktop lint
$ eslint src

> pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit

> pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
Test Files  73 passed (73)
      Tests  535 passed (535)
   Start at  01:55:09
   Duration  48.59s (transform 3.34s, setup 0ms, collect 23.69s, tests 17.75s, environment 33.66s, prepare 5.37s)
```

```text
> pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1875 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-DnrGOxwr.css                                                    60.88 kB │ gzip: 11.29 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RuntimeIcon.vue_vue_type_script_setup_true_lang-CgzGlMXs.js            0.54 kB │ gzip:  0.35 kB
dist/assets/PiGuardStatus.vue_vue_type_script_setup_true_lang-DT-LR3jn.js          0.79 kB │ gzip:  0.53 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-BVbNCYXX.js    0.92 kB │ gzip:  0.60 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-BnPIhaIF.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-CemGJXKT.js           1.55 kB │ gzip:  0.75 kB
dist/assets/confirm-DcnXR8W2.js                                                    1.74 kB │ gzip:  0.94 kB
dist/assets/PlaceholderPage-rnDbeNrJ.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-D2F41ATq.js             1.88 kB │ gzip:  0.89 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-CeUsbPK0.js           2.44 kB │ gzip:  1.19 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-2fpPiwrl.js                2.51 kB │ gzip:  1.11 kB
dist/assets/native-utils-BxJorGZj.js                                               2.53 kB │ gzip:  1.70 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-QdggqvR6.js     2.61 kB │ gzip:  1.42 kB
dist/assets/team.store-C5QNgZun.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-BMq_HCHq.js                                            3.85 kB │ gzip:  1.86 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-C6Ut7z5Y.js               4.39 kB │ gzip:  2.01 kB
dist/assets/ConnectPage--6IAPXxb.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-CSbN_amR.js                                          6.23 kB │ gzip:  2.82 kB
dist/assets/PairingScanner-zHV0Dh7T.js                                             6.26 kB │ gzip:  3.41 kB
dist/assets/task.store-DWrv_8rW.js                                                 6.99 kB │ gzip:  2.62 kB
dist/assets/RemoteTokensPage-pbQRYYlq.js                                           7.59 kB │ gzip:  3.85 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-D90tRIU8.js               7.62 kB │ gzip:  3.28 kB
dist/assets/RemoteDevicesPage-nJNN2cZd.js                                          8.54 kB │ gzip:  3.75 kB
dist/assets/WorkspacesPage-BcLrdhQJ.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/TemplatesPage-D0dy9fwQ.js                                              9.62 kB │ gzip:  4.27 kB
dist/assets/SessionsPage-9FFWI3bD.js                                              10.58 kB │ gzip:  4.52 kB
dist/assets/TasksPage-D0uUKqxx.js                                                 11.80 kB │ gzip:  4.69 kB
dist/assets/OverviewPage-D-U3vdnb.js                                              12.12 kB │ gzip:  3.95 kB
dist/assets/ApprovalsPage-B5QKxyng.js                                             12.54 kB │ gzip:  5.07 kB
dist/assets/OnboardingPage-DxgqGftA.js                                            12.94 kB │ gzip:  4.92 kB
dist/assets/TeamsPage-DZWli2S8.js                                                 16.12 kB │ gzip:  6.01 kB
dist/assets/remote-chat.store-DRbBjO7C.js                                         22.75 kB │ gzip:  7.34 kB
dist/assets/TaskDetailPage-BKpMyCUg.js                                            23.47 kB │ gzip:  7.99 kB
dist/assets/AgentsPage-CeAlctQV.js                                                24.14 kB │ gzip:  8.86 kB
dist/assets/AttachmentDrafts.vue_vue_type_script_setup_true_lang-QlaOzJxq.js      25.99 kB │ gzip: 10.34 kB
dist/assets/ScenesPage-B-6yNdED.js                                                27.24 kB │ gzip:  9.26 kB
dist/assets/RemoteChatPage-BGT3j8Pt.js                                            42.34 kB │ gzip: 13.23 kB
dist/assets/RemoteLinkPage-Bm7OOGMe.js                                            49.48 kB │ gzip: 18.89 kB
dist/assets/ChatPage-D0epVmj_.js                                                  83.04 kB │ gzip: 25.66 kB
dist/assets/jsQR-UMIdgYmG.js                                                     130.80 kB │ gzip: 47.46 kB
dist/assets/vendor-DAwl41T1.js                                                   150.58 kB │ gzip: 50.79 kB
dist/assets/index-CWw3CY2I.js                                                    253.32 kB │ gzip: 83.79 kB
✓ built in 7.45s
```

保留既有 router injection 警告、HUB_NOT_READY 模拟日志与 echarts 空 chunk 提示；最终 **73 个文件、535 项测试通过**。

## 1280×800 截图

4 张亮暗截图均已查看检查，使用合成协议 mocks，不代表真实 PI CLI/guard/模型已验证。

| 页面 | 亮色 | 暗色 |
| --- | --- | --- |
| Agent 管理：PI 实例、CLI、模型与保护状态 | [亮色](screenshots/pi-p3/light-agents-1280x800.png) | [暗色](screenshots/pi-p3/dark-agents-1280x800.png) |
| 角色配置：PI 与精确 provider/modelId | [亮色](screenshots/pi-p3/light-roles-1280x800.png) | [暗色](screenshots/pi-p3/dark-roles-1280x800.png) |

[复现脚本](screenshots/pi-p3/verify.py)、[检查结果](screenshots/pi-p3/verification.json)、[原始浏览器输出](pi-p3-validation/browser.txt)。运行方式（同一 worktree，已有 Python Playwright/Chromium）：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
$env:pnpm_config_verify_deps_before_run='false'
pnpm --filter @hqagent/desktop exec vite --mode mock --host 127.0.0.1 --port 5198 --strictPort
# 另一个终端：
$env:PYTHONUTF8='1'
python .hqagent/handoffs/screenshots/pi-p3/verify.py
```

真实浏览器输出，退出码 0：

```text
{"checks": [{"mode": "light", "guardStates": ["ready", "uncontrolled_extensions", "guard_not_loaded"], "providerModel": "1aicode · deepseek/deepseek-v4-pro", "recommendationAutoSelected": false, "horizontalOverflow": false}, {"mode": "dark", "guardStates": ["ready", "uncontrolled_extensions", "guard_not_loaded"], "providerModel": "1aicode · deepseek/deepseek-v4-pro", "recommendationAutoSelected": false, "horizontalOverflow": false}], "screenshots": 4, "browserErrors": 0, "source": "Chromium + synthetic protocol mocks; no model calls"}
```

## 联调待验

- P2/P1 合入后核验真实 pi-v1 旧/新 HTTP 投影、游标与 WS ticket 绑定、4→5 栅栏及延迟补传，不以 Mock 的支持列表证明已协商。
- 核验真实 PI 实例发现、模型清单、默认 provider/model 变化、guard 独立核验及工具安全拦截；UI 不验证扩展源码，也不宣称扩展等于 OS 沙箱。
- 真实收费验证必须由操作者再次明确确认。本轮无模型调用，不能把合成 ready/passed 样例作为安全/图片能力证据。
- 第二期树分支读取、context_edit、导入/续接与单写锁由 P2 实测；PI phase1 未实现读取器仍显示不可用。
- 未做真机、桌面壳与真实 Hub/服务端端到端测试；开发服务已停止。
- 未遇真实 429、0xC0000142 或 API 额度错误；没有并行构建/测试或启动子代理，没有读取凭据/真实 CLI 历史或增加敏感持久化。
