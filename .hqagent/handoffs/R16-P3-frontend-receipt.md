# R1.6-P3 对话附件前端回执（0.10.0 / D52）

## 状态、基线与提交

- 工作区：`E:/OtherPro/HQAgent-Hub-worktrees/r15-web`；分支：`feat/r15-web`。
- 起始提交：`d358606`；实现及测试提交：`6ac9e12` — `feat(attachments): add uploads, previews and message attachments on both clients`。
- A、B、C、D 的前端接线及 Mock 已交付；本机 P2 尚未合入，**不把 Mock / 浏览器通过描述为真实 Hub 附件可用**。
- 仅修改 `apps/desktop/**`、`.hqagent/handoffs/**`。没有修改协议、Hub/Server、根配置、依赖清单或根 lockfile；没有合并回 integration、推送或部署。
- 无新依赖。测试和构建串行执行，vitest 固定 minWorkers=1/maxWorkers=2；TEMP/TMP 指向 worktree 已忽略的 `.tmp`。没有触发实际请求 429、0xC0000142 或额度错误。

## A. 手机端

- 输入框左侧增加单个回形针，展开「选图片 / 选文件」系统文件输入；选中附件在输入框上方横向卡片展示名称、大小、校验/上传进度、失败原因、移除/重试。
- 打开选择入口及选择文件时读取 GET attachments/limits。大小、每条数量、图片 MIME、文件后缀、账号配额/已用/预留、未发送 TTL 都取响应，不在 UI 写死业务限额。
- 选择阶段读取极小文件头识别 JPEG/PNG/WebP/GIF/PDF，配合返回白名单与大小做预检查；最终类型仍由服务端内容检测裁定。空文件、数量/类型/大小/配额超限立即提示，拒绝项不上传。
- 每批串行上传，避免突发并发和大块内存；采用 XMLHttpRequest 的真实 upload progress，raw File/Blob 作为 body。设置 application/octet-stream、百分号编码的 X-File-Name、增量 X-Content-Sha256、幂等键及当前内存 CSRF。Content-Length/Origin 由浏览器提供，不手设，不用 FormData/base64/未知长度 ReadableStream。
- 失败保留当前对话的文本与上传结果；手动上传重试复用相同文件意图/key/hash。限流不自动重试并停止当前剩余批次。上传总超时120秒、无进展30秒停止；组件卸载/已知暂停会取消当前读取或上传。
- 发送仅追加 attachmentIds，不带文件、路径、hash清单或下载链接。对话切换后不能把原选择发到新对话；草稿附件只在当前组件内存，移除、成功发送、切换或卸载清理前端选择，未发送服务端暂存遵从接口 TTL。
- 发送前串行查询最新附件元数据并检查归属、数量、大小、可用性与已返回期限；含附件要求设备具备修订4能力，实际协商/栅栏仍由服务端再次判断。
- 图片每次发送前重取当前 catalog，按 sceneId + version 校验全部 roleImageCapabilities；native 按 agentType 查 nativeImageCapabilities。三层入口/实现/verified、support、MIME与大小全部满足才放行；缺项/空数组/unknown/unsupported 均拒绝并提示「当前 Agent 不支持图片」。服务端同码拒绝仍保留文本和附件。
- 请求响应丢失时，附件消息的 clientMessageId/Idempotency-Key 在内存保留，便于对 reserved 附件重放原意图，不默认创建新的消费命令。明确拒绝或成功后清理该意图。
- 暂停禁止手机上传与发送，下载展示不读取暂停门禁。电脑离线仍可暂存到已有对话，发送明确失败，卡片提示已上传附件保留及接口返回的清理小时数。
- 对未发送附件调用 DELETE；删除失败保留卡片与原因，NOT_FOUND 可移除本地已失效的选择。

## B. 电脑端及同步状态

- 同一套附件入口/卡片/消息展示通过 LocalChatGateway 调本机 v2 Cookie 路由：限制、上传、查询、删除、content、attachment-capabilities 和 thumbnail代理。没有读取或传递 Hub Token / 设备凭据给浏览器。
- 本机限制接口返回 AttachmentLimits，不伪造云端 usedBytes，也不以云配额不足阻止本机使用。
- 本机消息使用 AttachmentManifestItem；单独 GET LocalAttachmentView 读取 syncStatus / syncError。显示「本机可用 · 尚未同步 / 同步待上传 / 已同步 / 同步失败」，缺省为 not_synced；同步错误显示中文原因且明确不影响本机使用。
- 本机图片只在同步元数据可用时请求本机 thumbnail 代理；代理失败显示图标及原因，不回退 content。not_synced/pending_upload/unavailable 不请求原图预览；提供手动刷新以核对同步进度。真实未配对/离线代理行为待 P2 联调。
- 本机附件消息的幂等意图只走既有内存分支，包含附件ID的请求不进入 sessionStorage 持久化桶；普通旧文字任务行为不变。发送失败保留该对话草稿与附件。
- 兼容修订4的普通/native继续对话及原生索引入口，不把仅支持4的设备误判成旧版本。

## C. 原文件、缩略图及排版

- 共享 AttachmentItem / MessageAttachments；手机图片小网格最多5张，文件行含图标、文件名、大小、下载按钮；pending_upload显示「附件待上传」，unavailable显示原因，两者不显示可用下载按钮。
- 只通过 thumbnail 接口获取服务端PNG产物，校验 Content-Type及PNG签名后建立内存 blob URL。pending/unavailable/非图片使用文件图标；浏览器解码失败也退回图标，不请求原图代替。
- 原文件仅在用户点击下载时取 content，检查响应长度及元数据大小/SHA256；建立 octet-stream blob URL，使用 download 属性交给浏览器。没有把原图、HTML、SVG放进 img/iframe/innerHTML。
- 缩略图URL在替换/卸载时撤销，迟到结果不生成URL；下载URL在交给浏览器后短暂延迟撤销。下载内容、URL、Cookie、令牌和文件正文没有写入 Web Storage/日志/URL查询参数。
- 输入区回形针、选文件/图片、移除、重试、下载、刷新等新增触控目标最小44px；卡片条内部横向滚动，textarea保持min-width:0。375×812浏览器断言没有页面横向溢出。
- 使用现有 content/status/bg/border主题变量；截图审核发现气泡白字继承问题后已修正，浅色/暗色附件状态文字均可见。没有新增配色体系。

## D. Mock 与接口清单

- MockAttachmentLibrary 使用 `r16.AttachmentLimits.json`、`r16.AttachmentTargetCapabilities.json` 生成夹具的类型与数值；元数据引用生成的 LocalAttachmentView/RemoteAttachmentView/MessageAttachmentView。
- Mock文件与记录只在内存；模拟 uploaded/attached、远程pending_upload/available/unavailable、缩略图pending/ready/unavailable、能力unknown/unsupported、同步失败但本机可用。截图全部是合成PNG和文本，不使用真实用户附件。
- 新增网关方法：getAttachmentLimits / uploadAttachment / getAttachment / deleteAttachment / getAttachmentContent / getAttachmentThumbnail，本机额外 getAttachmentCapabilities。远程catalog消费 RemoteV4CatalogView。
- UploadOptions是浏览器进度/取消与raw头参数，不是另造协议DTO。生产错误提示新增11个附件错误码，AGENT_IMAGE_UNSUPPORTED按任务书显示明确中文；二进制失败也保留响应头/信封requestId。

## SHA-256 实现与体积

采用独立原创 TypeScript FIPS 180-4 增量SHA-256，不引入npm依赖。固定64字节block和64-word schedule，File/Blob每次slice读取至多65,536字节；不调用整个File的arrayBuffer，不对整文件使用crypto.subtle.digest。每块后让出事件循环并检查取消。

验证：空输入、abc、55/56/63/64/65字节填充边界、非ASCII、分片更新均与Node crypto结果一致；虚拟20,000,000字节文件禁止整文件读，记录最大slice为65,536并与Node增量hash一致。该测试证明代码分块读取，**不是实测移动浏览器或服务端的整体RSS**。

使用仓库既有Vite依赖的esbuild测量单模块（不安装任何包）；这是独立minify/gzip结果，不把它说成整份UI构建的唯一增量。可复现命令：

```text
node .hqagent/handoffs/r16-p3-validation/measure-hash.cjs
{"implementation":"FIPS 180-4 incremental SHA-256, original TypeScript","newDependencies":0,"sourceBytes":3800,"minifiedBytes":2822,"gzipBytes":1484,"chunkBytes":65536}
```

## 测试与旧断言

新增41项：

- sha256.test.ts：10项，标准向量/填充与分块边界、20MB有界读取、取消。
- Attachments.test.ts：23项，选择限额、进度状态、失败/重试、删除、离线/暂停、全角色与native能力、只传ID、文本附件保留、reserved重放、本机内存意图、不可用下载门禁、缩略图URL生命周期、拒绝SVG/原图回退、下载octet-stream、同步失败本机可用。
- transport.test.ts：8项，raw File、编码文件名、Cookie/CSRF/幂等、没有Content-Length/Authorization/Origin手设、真实进度回调、取消、错误requestId、二进制长度/PNG校验、本机能力与DELETE路径。

既有断言只改一处：`RemoteR15Features.test.ts` 的 Busy Lock on Mobile 原用 `footer button` 选择发送按钮。新增回形针后第一个按钮是附件选择入口，因此改为 `button[aria-label="发送消息"]`；原忙碌文案、textarea禁用、发送按钮禁用断言全部保留。上传不被忙碌状态一刀切禁止。

早期验证暴露并修复：卡片浅响应式更新未触发渲染、Mock库循环导入、旧按钮定位、jsdom Blob夹具缺少arrayBuffer，以及手机气泡继承白字。没有skip/xfail测试；下面为最终结果。

## 最终验收真实输出

全部从worktree根运行，TEMP/TMP均指向 `.tmp`；每个测试/构建命令完成后才运行下一个。完整 stdout/stderr 见 [r16-p3-validation](r16-p3-validation/)，只清理行尾空白与换行，警告保留。

### lint（退出码0）

```text
pnpm --filter @hqagent/desktop lint
$ eslint src
```

### typecheck（退出码0）

```text
pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit
```

### vitest（退出码0）

```text
pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
Test Files  61 passed (61)
      Tests  397 passed (397)
   Start at  18:32:57
   Duration  41.92s (transform 2.73s, setup 0ms, collect 17.67s, tests 16.74s, environment 33.46s, prepare 5.33s)
```

### build（退出码0）

```text
pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1842 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.05 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-Cj2eWR5_.css                                                    55.87 kB │ gzip: 10.41 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-DzNtls84.js    0.92 kB │ gzip:  0.59 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-n1EBZUWi.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-Bd93CNus.js           1.55 kB │ gzip:  0.75 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-BfW-MfWN.js             1.69 kB │ gzip:  0.82 kB
dist/assets/PlaceholderPage-CwJZst25.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-p4BiSDoD.js               2.16 kB │ gzip:  1.06 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-BnUeKF6M.js                2.32 kB │ gzip:  1.04 kB
dist/assets/native-utils-4HZHpe5D.js                                               2.40 kB │ gzip:  1.57 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-DHs_mpPl.js           2.44 kB │ gzip:  1.19 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-YOG6LUGa.js     2.61 kB │ gzip:  1.42 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-C2rgyehP.js               2.85 kB │ gzip:  1.34 kB
dist/assets/team.store-uxnBRqGg.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-DAMrTzwU.js                                            3.82 kB │ gzip:  1.84 kB
dist/assets/ConnectPage-BR3_S9KD.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-Cb_gtc50.js                                          5.33 kB │ gzip:  2.49 kB
dist/assets/task.store-DQq26SDw.js                                                 6.99 kB │ gzip:  2.61 kB
dist/assets/RemoteTokensPage-Budhx6J0.js                                           8.01 kB │ gzip:  3.88 kB
dist/assets/WorkspacesPage-Co5YWf3w.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/RemoteDevicesPage-BHvSlPRr.js                                          9.00 kB │ gzip:  3.77 kB
dist/assets/TemplatesPage-e7AFlitP.js                                              9.61 kB │ gzip:  4.26 kB
dist/assets/SessionsPage-Dgrf6iRC.js                                              10.55 kB │ gzip:  4.50 kB
dist/assets/AgentsPage-CeP9bsou.js                                                11.61 kB │ gzip:  4.05 kB
dist/assets/TasksPage-Cru4ut49.js                                                 11.73 kB │ gzip:  4.67 kB
dist/assets/OverviewPage-9qy1ZMfK.js                                              12.12 kB │ gzip:  3.96 kB
dist/assets/ApprovalsPage-BYgxU0af.js                                             12.26 kB │ gzip:  4.95 kB
dist/assets/OnboardingPage-CCPXxhBk.js                                            12.93 kB │ gzip:  4.91 kB
dist/assets/TeamsPage-B6BV2D3S.js                                                 15.96 kB │ gzip:  5.93 kB
dist/assets/remote-chat.store-BKmXsFrp.js                                         21.97 kB │ gzip:  7.06 kB
dist/assets/AttachmentDrafts.vue_vue_type_script_setup_true_lang-Bt6DEFqB.js      22.92 kB │ gzip:  9.33 kB
dist/assets/TaskDetailPage-CQG9Eqop.js                                            23.41 kB │ gzip:  7.98 kB
dist/assets/ScenesPage-ByCJ1LPb.js                                                25.53 kB │ gzip:  8.68 kB
dist/assets/RemoteChatPage-DFdgceoQ.js                                            41.06 kB │ gzip: 12.64 kB
dist/assets/RemoteLinkPage-Yqsya72w.js                                            49.42 kB │ gzip: 18.85 kB
dist/assets/ChatPage-o6m7BIjL.js                                                  79.34 kB │ gzip: 23.84 kB
dist/assets/vendor-DiKq3s9w.js                                                   147.12 kB │ gzip: 49.67 kB
dist/assets/index-iTjQ3ID3.js                                                    230.63 kB │ gzip: 75.60 kB
✓ built in 15.19s
```

测试中有既有及组件孤立挂载的 router injection 警告、HUB_NOT_READY故障模拟输出；构建仍有 `Generated an empty chunk: "echarts".`，未隐藏。新依赖数为0，git diff --check通过。

## 浏览器与截图

Python Playwright + 本机无头Chromium，Mock模式；375×812手机、1280×800电脑。已逐张打开检查。

| 场景 | 截图 |
| --- | --- |
| 手机附件草稿卡片 | [mobile-drafts](screenshots/r16-p3/mobile-drafts-375x812.png) |
| 手机缩略图/待上传/不可用/文件 | [mobile-messages](screenshots/r16-p3/mobile-messages-375x812.png) |
| 手机暗色附件状态 | [mobile-messages-dark](screenshots/r16-p3/mobile-messages-dark-375x812.png) |
| 电脑附件草稿 | [desktop-drafts](screenshots/r16-p3/desktop-drafts-1280x800.png) |
| 电脑消息与独立同步失败 | [desktop-messages](screenshots/r16-p3/desktop-messages-1280x800.png) |

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
pnpm --filter @hqagent/desktop exec vite --mode mock --host 127.0.0.1 --port 5198 --strictPort
# 另一个终端，从同一worktree根执行
python .hqagent/handoffs/screenshots/r16-p3/capture.py
```

真实浏览器脚本输出（退出码0）：

```text
mobile selection, statuses, suspended download, 44px target, no horizontal overflow: PASS
desktop input, independent sync failure, local download and storage checks: PASS
browser errors: 0
5 screenshots captured using synthetic attachments only
```

## 必须由真机与P2联调验证的项

1. iOS/Android系统图片/文件选择器、软键盘、窄屏/横屏、页面后台或系统回收后的取消行为；本轮仅无头浏览器视口和自动设置File输入。
2. 真实Cookie/CSRF/Origin、浏览器自动Content-Length、中文/长文件名头、Nginx上传/下载buffer与413错误信封、传输进度、慢网/断网/超时/实际限流；没有上传真实文件至云端。
3. P2本机七个v2接口的raw绑定与本机库身份，未配对/离线时thumbnail代理明确拒绝并显示图标、已同步时只返回服务端PNG；Mock不能证明设备凭据代理链正确。
4. catalog及本机attachment-capabilities的真实全角色/原生模型能力，CLI入口/Runtime实现/实测验证三层；实际Codex/Claude图片理解、新建/精确续接、多图与混合文件不能由合成supported替代。
5. 修订4协商及3→4栅栏、Worker grant后下载/校验与Agent启动门闩、取消和进程强杀恢复；前端沿用执行状态，不把上传/202视为模型启动或任务完成。
6. 本机用户消息pending_upload→available/unavailable的真实revision更新、syncStatus/syncError与同步总开关、断网重连、删除对话/设备后的数据清理和URL卸载。
7. reserved附件响应丢失的真实幂等重放、24小时未发送回收、账号配额竞争、ATTACHMENT_IN_USE、跨owner/pc_only/已删除ID404，以及实际20MB上传下载的浏览器/服务器内存。
8. Safari/移动浏览器的Blob下载和生成缩略图解码；下载URL在触发后延迟释放需在真实下载管理器复验。用户主动下载的文件由浏览器保存，不是应用Web Storage缓存。

当前无新增协议字段或依赖变更请求。本轮没有部署或P2真实联调。每次提交后均执行 `git log -1 --format=%B` 自查；提交信息无署名尾注。

## 返修 1：统一表单暗色适配与页面内扫码配对

### 基线、范围与提交

- 基线 `0a2b1b1`；工作区仍为 `r15-web` / `feat/r15-web`。
- `8615a72`：统一表单主题、原生控件共享类、顶栏颜色和对比度测试。
- `fac5125`：同源扫码配对、摄像头生命周期、懒加载解码及测试。
- 验收证据与本节另行提交。没有合并 integration 或部署。
- 没有修改依赖清单、根 lockfile 或 env.d.ts；使用主代理已安装的 jsqr@1.4.0。RemoteLinkPage 的默认地址仍为 `import.meta.env.VITE_DEFAULT_REMOTE_SERVER || 'https://hqremote.hylucky.top'`，该文件本轮只给两处原生输入加共享主题类。
- 修改范围仅 `apps/desktop/**` 与 `.hqagent/handoffs/**`。测试/构建串行，TEMP/TMP 使用 worktree 的已忽略 `.tmp`。没有出现实际429、0xC0000142或额度错误。

### 1. 统一主题修复

根因包括页面使用了未定义的旧颜色 utility（text-text / bg-bg-app 等），以及共享控件用整块opacity降低禁用态文字对比度。

- 新增 `shared/theme/forms.css`：统一输入背景、正文、占位符、边框、焦点、错误、readonly、disabled；使用既有主题颜色变量，新增的 `--hq-field-*` 只作控件语义映射。
- 页面中的原生 input / textarea / select 全部迁移到共享 hq-form-control；checkbox/radio等使用hq-form-choice。保留页面自己的布局、尺寸和事件，没有逐页补颜色。
- HqInput / HqTextarea 使用共享外框和嵌入式控件；HqSelect / HqCombobox 的触发器、占位、禁用选项及搜索输入一并处理。HqCheckbox / HqRadioGroup / HqSwitch 的禁用文字使用语义色，移除整块半透明。
- 设置根color-scheme并处理native select选项、浏览器默认控件；Chromium/Safari自动填充使用主题text-fill/caret与inset背景，避免UA自动填充文字/背景冲突。
- 在desktop自己的Tailwind配置中将旧utility映射至现有content/bg/status变量，修复手机顶栏设备名、菜单和退出图标，并统一旧页面同类颜色。没有建立第二套配色。
- `forms.test.ts` 静态检查所有Vue原生可编辑控件均接入共享类；浏览器fixture实际渲染共享组件和text/password/email/search/number/url/tel/date/time/datetime-local/month/week、textarea、select及选择控件，覆盖正常、占位、只读、禁用、错误、聚焦及强制autofill伪态。

计算样式验证将透明背景和祖先opacity合成后按WCAG相对亮度计算对比度，断言所有检查项 >=4.5:1。最终共580个文字/占位符检查（页面、顶栏与共享fixture合计）：

| 检查范围 | 亮色最低 | 暗色最低 |
| --- | ---: | ---: |
| 要求截图中的主要表单 | 6.92:1 | 8.21:1 |
| 手机顶栏设备名/菜单/退出 | 4.76:1 | 5.10:1 |
| 共享控件正常/聚焦（含只读、禁用、占位等） | 6.92:1 | 8.21:1 |
| Chromium强制autofill伪态 | 6.61:1 | 6.00:1 |

这里的autofill是通过CDP强制伪态验证CSS，不是读取用户保存的账号密码；Safari/密码管理器的实际填充仍列为真机复验项。

### 2. 页面内扫码

- 配对码输入框旁增加44px「扫码」入口，打开独立全屏对话框，调用getUserMedia的environment后置摄像头偏好。video使用autoplay/muted/playsinline，扫码关闭控件和错误重试均可触控与键盘访问，Esc可关闭，并约束焦点在扫码视图内。
- 查询原生BarcodeDetector支持格式，含qr_code时优先使用；无原生支持或原生解码拒绝画面时，再执行 `import('jsqr')`。扫码组件本身也通过defineAsyncComponent按需加载。
- 画面最长边640px，串行解码结束后至少等待125ms，最多8次/秒，不并发扫描；销毁时清空canvas像素，切后台主动停摄像头。
- 纯函数parsePairingQr只接受合法8位ASCII字母数字短码，或与location.origin严格同源、pathname精确为 `/remote/pair`、fragment中只有一个合法code值的HTTP(S)链接。额外拒绝userinfo、query、外站、错误路径、重复code、非法字符和超长输入；大小写短码规范为大写。
- 扫描结果从不用于跳转。非法内容只显示固定提示「不是本服务的配对二维码」，不回显扫描原文。
- 成功后先停止轨道，再向配对页传递已验证短码；填码后仅调用现有preview流程，仍需用户点击确认绑定。未改现有系统相机打开链接后的hash填码流程。
- 权限拒绝、没有摄像头、设备被占用、安全限制、非安全上下文、缺失浏览器能力均给明确说明，提示系统相机或手动输入；不将所有微信环境一律判定不可用，而是在API缺失/失败时提供系统浏览器替代说明。
- 关闭、成功、离开页面、切后台、权限结果晚到、正在解码时关闭都释放所有轨道、清srcObject、取消定时器并忽略迟到结果。不会把扫码内容写入Web Storage、日志或URL查询。

### 3. 测试与分包证明

新增46项测试：

- pairing-qr.test.ts：29项，同源/默认端口/纯短码、外站、协议/端口/路径、缺code、重复/非法code、query、userinfo、控制字符等。
- PairingScanner.test.ts：16项，后置参数、原生优先、640px降采样、成功填码且不绑定、外站拒绝、四类摄像头错误、不安全/不支持环境、关闭/卸载/后台/迟到清理、8fps、jsqr回退及原生失败回退。
- forms.test.ts：1项，原生可输入控件共享类覆盖。

既有测试断言没有修改、删除或跳过。初轮扫码测试修正了jsdom无srcObject默认值的断言，以及先卸载组件再恢复media mocks的清理顺序；没有用jsdom的媒体实现缺失来放宽摄像头stop断言。

浏览器还使用合成二维码canvas MediaStream触发真实jsqr解码（不访问真实摄像头）：识别后填码/待绑定、没有自动确认、轨道stop、存储与URL不含测试短码均通过。Resource Timing断言打开扫码前没有jsqr请求，打开后才出现。

构建真实产物：`jsQR-UMIdgYmG.js`，130.80 kB，Vite报告gzip 47.46 kB；扫码视图 `PairingScanner-BeDj4J-3.js`，6.26 kB / gzip 3.41 kB。脚本遍历构建产物的静态import闭包，确认jsqr既不在首屏也不在配对页静态依赖中，HTML没有预加载该chunk：

```text
python .hqagent/handoffs/r16-p3-fix1-validation/check_chunks.py
{"jsqrChunks": [{"file": "jsQR-UMIdgYmG.js", "bytes": 130799}], "entryStaticChunkCount": 2, "jsqrInEntryStaticGraph": false, "jsqrInPairingStaticGraph": false, "jsqrPreloadedByHtml": false, "scannerChunks": ["PairingScanner-BeDj4J-3.js"]}
```

### 4. 最终验收真实输出

从worktree根运行，依次执行，完整stdout/stderr见 [r16-p3-fix1-validation](r16-p3-fix1-validation/)；只规范化换行和行尾空白。

**lint，退出码0**

```text
pnpm --filter @hqagent/desktop lint
$ eslint src
```

**typecheck，退出码0**

```text
pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit
```

**vitest，退出码0**

```text
pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
Test Files  64 passed (64)
      Tests  443 passed (443)
   Start at  01:09:11
   Duration  37.36s (transform 2.50s, setup 0ms, collect 17.16s, tests 14.68s, environment 26.95s, prepare 4.08s)
```

**build，退出码0**

```text
pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1848 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-Djx9XYkk.css                                                    60.34 kB │ gzip: 11.08 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-H7flQrSl.js    0.92 kB │ gzip:  0.60 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-C1f1P-UW.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-aQ3AtW7f.js           1.55 kB │ gzip:  0.75 kB
dist/assets/PlaceholderPage-B6C3qwvG.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-BRfqjuBA.js             1.88 kB │ gzip:  0.89 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-BU1-8Fi_.js               2.16 kB │ gzip:  1.06 kB
dist/assets/native-utils-Ch6cwJdY.js                                               2.40 kB │ gzip:  1.57 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-Dx21tGo9.js           2.44 kB │ gzip:  1.19 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-2zmLwAt5.js                2.51 kB │ gzip:  1.11 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-Dmh4FrxW.js     2.61 kB │ gzip:  1.42 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-6zeFG2XP.js               2.99 kB │ gzip:  1.39 kB
dist/assets/team.store-JLeuPyya.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-BtoXGXI3.js                                            3.85 kB │ gzip:  1.85 kB
dist/assets/ConnectPage-CKgDNtlo.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-D3eOPJND.js                                          6.23 kB │ gzip:  2.82 kB
dist/assets/PairingScanner-BeDj4J-3.js                                             6.26 kB │ gzip:  3.41 kB
dist/assets/task.store-piWJcYSV.js                                                 6.99 kB │ gzip:  2.61 kB
dist/assets/RemoteTokensPage-DHFH0dSK.js                                           8.09 kB │ gzip:  3.91 kB
dist/assets/WorkspacesPage-OY3GdsWl.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/RemoteDevicesPage-CPJtv4mW.js                                          9.05 kB │ gzip:  3.79 kB
dist/assets/TemplatesPage-BodhimrB.js                                              9.62 kB │ gzip:  4.27 kB
dist/assets/SessionsPage-BTmZnoTs.js                                              10.58 kB │ gzip:  4.52 kB
dist/assets/AgentsPage-C5c2dlxl.js                                                11.64 kB │ gzip:  4.06 kB
dist/assets/TasksPage-BupbNUGA.js                                                 11.80 kB │ gzip:  4.69 kB
dist/assets/OverviewPage-CMKxOiQx.js                                              12.12 kB │ gzip:  3.96 kB
dist/assets/ApprovalsPage-Dk9lAsn0.js                                             12.28 kB │ gzip:  4.97 kB
dist/assets/OnboardingPage-1gND9sej.js                                            12.94 kB │ gzip:  4.92 kB
dist/assets/TeamsPage-6GT5AvwE.js                                                 16.01 kB │ gzip:  5.94 kB
dist/assets/remote-chat.store-CzMU5Ba4.js                                         21.97 kB │ gzip:  7.06 kB
dist/assets/AttachmentDrafts.vue_vue_type_script_setup_true_lang-DQxHLMJt.js      22.94 kB │ gzip:  9.35 kB
dist/assets/TaskDetailPage-BC8sh8IX.js                                            23.47 kB │ gzip:  7.99 kB
dist/assets/ScenesPage-D9NWnq8G.js                                                25.69 kB │ gzip:  8.71 kB
dist/assets/RemoteChatPage-BjlOJBr_.js                                            41.28 kB │ gzip: 12.69 kB
dist/assets/RemoteLinkPage-o8ca6es7.js                                            49.48 kB │ gzip: 18.89 kB
dist/assets/ChatPage-BxwqkrTK.js                                                  79.47 kB │ gzip: 23.87 kB
dist/assets/jsQR-UMIdgYmG.js                                                     130.80 kB │ gzip: 47.46 kB
dist/assets/vendor-BYHMq7VA.js                                                   149.49 kB │ gzip: 50.50 kB
dist/assets/index-JxkxIpPe.js                                                    230.67 kB │ gzip: 75.62 kB
✓ built in 5.94s
```

保留了既有测试中的router injection警告和HUB_NOT_READY故障模拟日志，构建仍有既有echarts空chunk提示；最终64个测试文件、443项测试全通过。

### 5. 亮暗截图与浏览器对比度复现

每套6张，共12张，均已打开检查。手机375×812，电脑1280×800；设置表单选用工作区目录设置弹窗。

| 场景 | 亮色 | 暗色 |
| --- | --- | --- |
| 手机登录 | [亮色](screenshots/r16-p3-fix1/light-mobile-login-375x812.png) | [暗色](screenshots/r16-p3-fix1/dark-mobile-login-375x812.png) |
| 手机配对 | [亮色](screenshots/r16-p3-fix1/light-mobile-pair-375x812.png) | [暗色](screenshots/r16-p3-fix1/dark-mobile-pair-375x812.png) |
| 手机对话输入区及顶栏 | [亮色](screenshots/r16-p3-fix1/light-mobile-chat-375x812.png) | [暗色](screenshots/r16-p3-fix1/dark-mobile-chat-375x812.png) |
| 电脑对话输入区 | [亮色](screenshots/r16-p3-fix1/light-desktop-chat-1280x800.png) | [暗色](screenshots/r16-p3-fix1/dark-desktop-chat-1280x800.png) |
| 电脑连接手机 | [亮色](screenshots/r16-p3-fix1/light-desktop-remote-link-1280x800.png) | [暗色](screenshots/r16-p3-fix1/dark-desktop-remote-link-1280x800.png) |
| 电脑工作区设置表单 | [亮色](screenshots/r16-p3-fix1/light-desktop-workspace-form-1280x800.png) | [暗色](screenshots/r16-p3-fix1/dark-desktop-workspace-form-1280x800.png) |

复现脚本使用本机Playwright/Chromium和Mock数据，只为对比度临时挂载真实共享组件；fixture未被应用入口引用。截图中没有真实账号、摄像头画面或有效配对码。

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
pnpm --filter @hqagent/desktop exec vite --mode mock --host 127.0.0.1 --port 5198 --strictPort
# 另一终端，在同一worktree根执行：
python .hqagent/handoffs/screenshots/r16-p3-fix1/verify.py
```

真实最终输出（退出码0）：

```text
{"contrastChecks": [{"mode": "light", "view": "mobile-login-375x812", "count": 4, "minContrast": 7.58}, {"mode": "light", "view": "mobile-pair-375x812", "count": 2, "minContrast": 7.58}, {"mode": "light", "view": "mobile-chat-375x812", "count": 2, "minContrast": 6.92}, {"mode": "light", "view": "mobile-header", "count": 3, "minContrast": 4.76}, {"mode": "light", "view": "desktop-chat-1280x800", "count": 4, "minContrast": 7.58}, {"mode": "light", "view": "desktop-remote-link-1280x800", "count": 4, "minContrast": 7.58}, {"mode": "light", "view": "desktop-workspace-form-1280x800", "count": 4, "minContrast": 7.58}, {"mode": "light", "view": "shared-controls-normal", "count": 89, "minContrast": 6.92}, {"mode": "light", "view": "shared-controls-focus", "count": 89, "minContrast": 6.92}, {"mode": "light", "view": "shared-controls-autofill", "count": 89, "minContrast": 6.61}, {"mode": "dark", "view": "mobile-login-375x812", "count": 4, "minContrast": 8.21}, {"mode": "dark", "view": "mobile-pair-375x812", "count": 2, "minContrast": 8.21}, {"mode": "dark", "view": "mobile-chat-375x812", "count": 2, "minContrast": 8.21}, {"mode": "dark", "view": "mobile-header", "count": 3, "minContrast": 5.1}, {"mode": "dark", "view": "desktop-chat-1280x800", "count": 4, "minContrast": 8.21}, {"mode": "dark", "view": "desktop-remote-link-1280x800", "count": 4, "minContrast": 8.21}, {"mode": "dark", "view": "desktop-workspace-form-1280x800", "count": 4, "minContrast": 8.21}, {"mode": "dark", "view": "shared-controls-normal", "count": 89, "minContrast": 8.21}, {"mode": "dark", "view": "shared-controls-focus", "count": 89, "minContrast": 8.21}, {"mode": "dark", "view": "shared-controls-autofill", "count": 89, "minContrast": 6}], "screenshots": 12, "syntheticJsqrStream": "PASS", "cameraReleased": "PASS", "automaticBinding": "not performed", "browserErrors": 0}
```

连接手机截图将Mock设为“尚未保存过服务器地址”的unpaired状态，以验证默认地址；已有服务器偏好仍按原逻辑优先，没有改主代理的默认值或env声明。

### 6. 验证边界

- 未用实体手机摄像头扫描真实配对二维码，未实际绑定设备；真实iOS/Safari、Android及微信内置浏览器权限/后置选择/弱光对焦、切后台指示灯、热量与耗电需真机复验。
- 原生BarcodeDetector分支由组件Mock验证；jsqr分支另有真实解码合成视频的浏览器验证。没有把Mock native检测描述为设备原生API实测。
- Chrome强制autofill样式已验证；系统密码管理器、Safari自动填充及原生select弹出菜单外观需对应浏览器实测。
- 未发出真实API429、未遇内存启动错误或额度错误；构建/测试始终串行，没有启动子代理或改依赖。
- 已检查提交信息，不包含署名尾注或生成标记；未合并回integration，未部署。
