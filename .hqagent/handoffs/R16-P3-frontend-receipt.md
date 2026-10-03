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


## 返修 2：手机端界面整理（2026-10-02）

### 1. 基线与提交

- 工作区 `r15-web`，分支 `feat/r15-web`。开工先执行 `git merge integration/phase1`，从 `8f9f4bd` 快进到 `2446ea8`，无冲突。
- 实现及测试提交：`66ce28f` — `fix(desktop): unify mobile dialogs and simplify chat controls`。
- 实现提交后已运行 `git log -1 --format=%B`，输出即上面的标题，无署名尾注。验收材料另作 handoff 提交，同样逐次检查。
- 自本次合并基线起仅修改 `apps/desktop/**`、`.hqagent/handoffs/**`；无依赖、根配置、协议、Hub 或服务端修改。`RemoteLinkPage.vue` 的 `VITE_DEFAULT_REMOTE_SERVER || 'https://hqremote.hylucky.top'` 保持原样。

### 2. 实现与共用方式

- `shared/ui/confirm.ts` 提供 `confirm(options): Promise<boolean>`，FIFO 排队，每次只显示一个确认。确认返回 `true`，取消、Esc、普通遮罩关闭返回 `false`；危险确认忽略遮罩点击、红色确认按钮。`useConfirm()` 在离开页面时取消未完成请求，避免异步确认后误执行操作。
- `HqDialog` 增加统一 overlay stack：焦点圈定、初始聚焦、关闭后返回触发控件、仅顶层响应 Esc、嵌套滚动锁和层级管理。确认默认焦点在取消按钮。
- `HqSelect`、`HqCombobox`、`HqDropdown` 共用 `HqOptionPanel`：小于 640px 用底部面板，电脑宽度锚定展开。支持 listbox/menu role、aria、方向键、Home/End、Enter、Esc、选择项禁用、焦点返回；可搜索选择器复用同一实现。面板和选项触控目标不小于 44px。
- 设备页和对话页退出均二次确认；设备删除、令牌吊销、团队删除使用统一危险确认。团队删除捕获确认时的目标 ID，避免等待期间切换目标误删。
- 手机可见的原生 select（设备筛选、对话项目/场景、授权根目录）均替换。电脑专用页面保留的原生 select 继续使用 `hq-form-control`。全仓代码搜索未找到 `window.confirm/alert/prompt` 调用，原团队页的裸 `confirm` 调用也已替换。
- 顶部按钮顺序固定为新话题、管理设备、退出；明确使用 **44px**，避免根字号 14px 时 `w-11` 只有 38.5px。顶部连接标签在线为 success 绿色，离线为 warning 橙色，未就绪为 neutral。
- 删除输入区模式单选和连接状态文字。普通发送默认 `continue`；`+` 激活「新话题 ×」，下一条使用 `new`，成功清除、失败保留，可取消；忙碌、离线、暂停和原生会话禁用并有原因。原生会话保持固定 `continue` 及既有终端退出确认。
- 两端输入行统一：回形针 44×44、文本框最小高 44、发送 48×44、间距 8、圆角 12，多行上限 132 并与按钮底部对齐。手机左右 12px，附件草稿卡片与输入行对齐；电脑没有新增顶部 `+`。
- placeholder 全局采用 muted 主题文字、`font-weight: 400`，正文继续原主题色；覆盖原生控件及共用选择器占位文案。

页面接入示例（纯 UI 选项，不新增协议 DTO）：

```ts
import { useConfirm } from '@/shared/ui'
const confirm = useConfirm()
if (await confirm({ title: '确定退出登录？', confirmText: '退出' })) {
  await logout()
}
// 危险操作追加 danger: true；非组件调用可直接导入 confirm，并传 AbortSignal。
```

### 3. 自动化与真实命令输出

新增 19 项测试：确认 Promise/排队/取消/危险遮罩/嵌套焦点和滚动锁、页面卸载取消、下拉键盘/移动面板；默认 continue、一次 new 后恢复、失败重试、取消、忙碌/离线/暂停/native 禁用、退出确认；原生系统弹窗和手机 select 静态检查。

旧测试相应改为查询共享选择器及 teleport 弹窗；旧“没有历史或失败时自动 new”的断言按本包要求改为默认 continue。原生会话续接、附件、设备、令牌等既有用例均通过。

所有构建和测试串行执行，TEMP/TMP 为被忽略的 worktree `.tmp`。完整输出：[lint](r16-p3-fix2-validation/lint.txt)、[typecheck](r16-p3-fix2-validation/typecheck.txt)、[vitest](r16-p3-fix2-validation/vitest.txt)、[build](r16-p3-fix2-validation/build.txt)、[浏览器](r16-p3-fix2-validation/browser.txt)。以下为实际输出，四项退出码均为 0：

```text
> pnpm --filter @hqagent/desktop lint
$ eslint src

> pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit

> pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
Test Files  67 passed (67)
      Tests  462 passed (462)
   Start at  02:03:58
   Duration  39.06s (transform 2.67s, setup 0ms, collect 18.03s, tests 15.39s, environment 27.00s, prepare 4.19s)
```

```text
> pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1854 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-CxiKY7_w.css                                                    60.61 kB │ gzip: 11.23 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-C0Zohg-v.js    0.92 kB │ gzip:  0.60 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-D0I8Oc-F.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-CUwSbvrc.js           1.55 kB │ gzip:  0.75 kB
dist/assets/confirm-YtHa5w4K.js                                                    1.74 kB │ gzip:  0.94 kB
dist/assets/PlaceholderPage-BgPdccfV.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-dhVQGqx6.js             1.88 kB │ gzip:  0.89 kB
dist/assets/native-utils-Dv3iijhn.js                                               2.40 kB │ gzip:  1.57 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-B_V0rn22.js           2.44 kB │ gzip:  1.19 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-CN5R3RPP.js                2.51 kB │ gzip:  1.11 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-DBGSxdbB.js     2.61 kB │ gzip:  1.42 kB
dist/assets/team.store-DeL-xhDK.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-DIsXgYdG.js                                            3.85 kB │ gzip:  1.85 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-YYZ2eT0k.js               4.39 kB │ gzip:  2.02 kB
dist/assets/ConnectPage-CXriYI1o.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-DuUH_exz.js                                          6.23 kB │ gzip:  2.82 kB
dist/assets/PairingScanner-D6Y09DN9.js                                             6.26 kB │ gzip:  3.40 kB
dist/assets/task.store-Di_s8b7O.js                                                 6.99 kB │ gzip:  2.61 kB
dist/assets/RemoteTokensPage-B3Q5spUk.js                                           7.59 kB │ gzip:  3.85 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-B_7duvR2.js               7.62 kB │ gzip:  3.28 kB
dist/assets/RemoteDevicesPage-frZJy_5Z.js                                          8.54 kB │ gzip:  3.75 kB
dist/assets/WorkspacesPage-D2G68V32.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/TemplatesPage-D9u7qrMQ.js                                              9.62 kB │ gzip:  4.27 kB
dist/assets/SessionsPage-Dtp38UrC.js                                              10.58 kB │ gzip:  4.52 kB
dist/assets/AgentsPage-CUJcPuRT.js                                                11.64 kB │ gzip:  4.06 kB
dist/assets/TasksPage-sYQePugW.js                                                 11.80 kB │ gzip:  4.69 kB
dist/assets/OverviewPage-CXESx4Hp.js                                              12.12 kB │ gzip:  3.95 kB
dist/assets/ApprovalsPage-CRkZU9pH.js                                             12.28 kB │ gzip:  4.97 kB
dist/assets/OnboardingPage-DVGHR6Mp.js                                            12.94 kB │ gzip:  4.92 kB
dist/assets/TeamsPage-iPhV2_PM.js                                                 16.12 kB │ gzip:  6.01 kB
dist/assets/remote-chat.store-eqDSuV2P.js                                         21.97 kB │ gzip:  7.06 kB
dist/assets/AttachmentDrafts.vue_vue_type_script_setup_true_lang-C2h_GDlm.js      22.94 kB │ gzip:  9.35 kB
dist/assets/TaskDetailPage-DqqDF7DL.js                                            23.47 kB │ gzip:  8.00 kB
dist/assets/ScenesPage-WD94eZOW.js                                                25.69 kB │ gzip:  8.71 kB
dist/assets/RemoteChatPage-DwbT-XkW.js                                            41.14 kB │ gzip: 12.86 kB
dist/assets/RemoteLinkPage-C57u8YEb.js                                            49.48 kB │ gzip: 18.89 kB
dist/assets/ChatPage-BpIHs9nD.js                                                  78.99 kB │ gzip: 23.95 kB
dist/assets/jsQR-UMIdgYmG.js                                                     130.80 kB │ gzip: 47.46 kB
dist/assets/vendor-BgNhKvOF.js                                                   149.55 kB │ gzip: 50.53 kB
dist/assets/index-NTlLgSM4.js                                                    230.72 kB │ gzip: 75.65 kB
✓ built in 5.57s
```

保留既有 router injection 测试警告、模拟 HUB_NOT_READY 的测试日志和 echarts 空 chunk 构建提示。`jsQR-UMIdgYmG.js` 仍为独立异步资源（130.80 kB，gzip 47.46 kB），本包未调整扫码实现或依赖。

### 4. 截图和浏览器检查

[可复现脚本](screenshots/r16-p3-fix2/verify.py)、[结构化结果](screenshots/r16-p3-fix2/verification.json)。Chromium + 本地 mock，16 张亮暗截图，已查看检查；未使用真实账号、设备凭据或附件内容。

| 场景 | 亮色 | 暗色 |
| --- | --- | --- |
| 手机对话页 / 顶栏图标 / 在线 / 单行输入 | [亮色](screenshots/r16-p3-fix2/light-mobile-chat-375x812.png) | [暗色](screenshots/r16-p3-fix2/dark-mobile-chat-375x812.png) |
| 手机新话题标签 | [亮色](screenshots/r16-p3-fix2/light-mobile-new-topic-375x812.png) | [暗色](screenshots/r16-p3-fix2/dark-mobile-new-topic-375x812.png) |
| 手机多行输入底部对齐 | [亮色](screenshots/r16-p3-fix2/light-mobile-multiline-375x812.png) | [暗色](screenshots/r16-p3-fix2/dark-mobile-multiline-375x812.png) |
| 手机退出确认 | [亮色](screenshots/r16-p3-fix2/light-mobile-logout-375x812.png) | [暗色](screenshots/r16-p3-fix2/dark-mobile-logout-375x812.png) |
| 手机离线橙色标签 | [亮色](screenshots/r16-p3-fix2/light-mobile-offline-375x812.png) | [暗色](screenshots/r16-p3-fix2/dark-mobile-offline-375x812.png) |
| 手机底部选择面板 | [亮色](screenshots/r16-p3-fix2/light-mobile-select-375x812.png) | [暗色](screenshots/r16-p3-fix2/dark-mobile-select-375x812.png) |
| 手机配对占位提示 | [亮色](screenshots/r16-p3-fix2/light-mobile-pair-placeholder-375x812.png) | [暗色](screenshots/r16-p3-fix2/dark-mobile-pair-placeholder-375x812.png) |
| 电脑对话输入区 | [亮色](screenshots/r16-p3-fix2/light-desktop-chat-1280x800.png) | [暗色](screenshots/r16-p3-fix2/dark-desktop-chat-1280x800.png) |

浏览器断言结果：

- 手机 375×812：页面无横向溢出；顶部三个操作均 44×44；文本框 243×44、回形针 44×44、发送 48×44；多行文本框为 86px 高时发送仍 44px，底边均在 y=801.5。
- 电脑 1280×800：文本框 438×44、发送 48×44，底部对齐。
- 真实渲染共用表单，normal/focus/强制 autofill 各 89 项检查，正文 ≥4.5:1、placeholder ≥3:1 且常规字重。含 placeholder 的最低对比度：亮色 normal 4.34、autofill 4.15；暗色 normal 5.10、autofill 3.73。配对框常态占位亮色 4.76、暗色 5.10。
- 顶栏文字/图标/状态最低亮色 4.57、暗色 5.10；离线标签亮色 4.51、暗色 7.06。退出取消后返回退出按钮，选择面板 Esc 关闭后返回选择器，滚动锁检查通过。
- `browserErrors: 0`，`screenshots: 16`。

复现（同一 worktree，需现有 Python Playwright/Chromium）：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
pnpm --filter @hqagent/desktop exec vite --mode mock --host 127.0.0.1 --port 5198 --strictPort
# 另一个终端运行：
$env:PYTHONUTF8='1'
python .hqagent/handoffs/screenshots/r16-p3-fix2/verify.py
```

### 5. 验证边界与交接

- 上述为桌面 Chromium 的手机尺寸模拟；iOS Safari / Android 真机软键盘、安全区、触摸滚动锁、VoiceOver/TalkBack 的完整读屏流程仍需真机复验。
- 发送成功/失败/暂停/离线和原生续接由协议 mock + 组件/Store 测试验证，未触发线上任务、真实注销、设备删除或令牌吊销；没有重新做 P2/服务器真实联调。
- 未改任何凭据或附件持久化路径，没有把秘密、Cookie 或下载地址写入日志、URL 查询参数或存储。
- 未遇真实 429、0xC0000142 或额度错误；没有并行跑构建/测试，未启动子代理。本轮临时开发服务已停止。
- 未合并回 integration，未部署；后续由主代理审核、集成及真机复验。


## 返修 3：原生会话按可用性分组

### 1. 基线与范围

- 工作区 `r15-web` / 分支 `feat/r15-web`，先执行 `git merge integration/phase1`，真实输出 `Already up to date.`；开工基线为 `0c0ff7d`。
- 实现与测试提交：`471a840` — `fix(desktop): group native sessions by format availability`。提交后 `git log -1 --format=%B` 已自查，输出即该标题，无署名或生成标记。
- 仅改 `apps/desktop/src/pages/native/NativeSessionsPanel.vue`、新增同目录 `NativeAvailability.test.ts` 以及本回执/验收材料。不新增依赖，不改协议、Hub、服务端或根配置；未合并回 integration、未部署。

### 2. 行为变化

手机和电脑均复用 `NativeSessionsPanel`，一次修改覆盖两端：

- 每个工作区主列表只显示 `format.status === 'readable'` 的会话，按 `updatedAt` 倒序排列；同时间按会话 ID 稳定排序。
- 其他状态统一收进工作区末尾默认折叠的「暂不支持（N）」。当前协议生成物的枚举只有 readable/unsupported，判断使用“不是 readable”，对未来或异常不可读状态保守处理，不自造协议字段。
- 展开后显示会话标题、Agent 类型、`format.cliVersion`、`format.reason`，采用主题次要文字色；版本/原因缺失时分别显示「CLI 版本未知」/「当前记录格式尚未支持」。
- 某工作区全部不可用时显示「暂无可读取的原生会话」，不可用项继续折叠，不以一整片灰色条目充满主列表。
- 点击不可用项只打开现有 `HqDialog` 说明：「该会话由 Codex 0.111.0 生成，当前版本的记录格式尚未支持，无法读取或续接」，并展示原因；没有重新读取、续接、导入按钮，不读取消息、不查询会话详情、不发起导入、不跳转对话。
- 读取、准备续接、实际导入均只允许 readable。准备续接时若权威详情已变为不可读，直接切换到说明；列表刷新发现所选会话变为不可读时清除旧读取状态。正常原生会话的终端退出确认及既有续接流程保留。
- 计数与折叠状态全部只在内存：刷新列表保留该工作区当前折叠状态，换电脑或重新挂载恢复默认折叠。**不读写 localStorage/sessionStorage**，不存在偏好写入失败中断页面的路径。
- 分页结果按会话 ID 去重后计数；还有未加载页时提示「以下数量仅统计已加载的会话」，不会把已加载数量冒充总数。折叠按钮有 aria-expanded/aria-controls，列表/刷新操作至少 44px，说明弹窗复用 Esc、焦点返回和主题样式。

### 3. 测试与真实输出

新增 16 项组件测试，分别在本机和远程模式覆盖：

1. 按工作区分组计数、主列表更新时间倒序、默认折叠、组末位置、原因和版本展示。
2. 56 条合成会话中仅 5 条 readable 出现在主列表，折叠计数为 51。
3. 点击不可用项展示说明，读取、详情查询、导入请求均为 0，不发出 opened 导航事件。
4. 全部不可用的空状态与缺失版本/原因的中文兜底。
5. 模拟 Storage.getItem 抛 SecurityError、setItem 抛 QuotaExceededError，组件仍可展开、刷新、折叠，且根本不调用这些存储 API；重新挂载恢复折叠。
6. 未知/异常的非 readable 状态同样归入不可用，不扩展生成物枚举。
7. 重叠分页去重、重新计数和排序。
8. 续接前返回 unsupported 时不展示确认导入、不发起续接。

验收命令全部串行，TEMP/TMP 均为 worktree 内被忽略的 `.tmp`。四项退出码均为 0。完整原始输出：[lint](r16-p3-fix3-validation/lint.txt)、[typecheck](r16-p3-fix3-validation/typecheck.txt)、[vitest](r16-p3-fix3-validation/vitest.txt)、[build](r16-p3-fix3-validation/build.txt)。

```text
> pnpm --filter @hqagent/desktop lint
$ eslint src

> pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit

> pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
Test Files  68 passed (68)
      Tests  478 passed (478)
   Start at  09:13:47
   Duration  46.70s (transform 3.09s, setup 0ms, collect 22.89s, tests 16.49s, environment 33.30s, prepare 5.16s)
```

```text
> pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1854 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-CxiKY7_w.css                                                    60.61 kB │ gzip: 11.23 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-UXQOAqi7.js    0.92 kB │ gzip:  0.60 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-UY_eXRkL.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-BuO-Khfs.js           1.55 kB │ gzip:  0.75 kB
dist/assets/confirm--PEU-Baa.js                                                    1.74 kB │ gzip:  0.94 kB
dist/assets/PlaceholderPage-DMYejHCx.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-B0YTw4mB.js             1.88 kB │ gzip:  0.89 kB
dist/assets/native-utils-Ca-hJrEq.js                                               2.40 kB │ gzip:  1.57 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-C0NGwhrZ.js           2.44 kB │ gzip:  1.19 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-pO-dmCg-.js                2.51 kB │ gzip:  1.11 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-BaM_3y0T.js     2.61 kB │ gzip:  1.42 kB
dist/assets/team.store-VboXf8je.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-BJObrrUf.js                                            3.85 kB │ gzip:  1.86 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-DhmT2hJz.js               4.39 kB │ gzip:  2.02 kB
dist/assets/ConnectPage-CT-X52uJ.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-Dv431PcH.js                                          6.23 kB │ gzip:  2.82 kB
dist/assets/PairingScanner-CYeTwBqU.js                                             6.26 kB │ gzip:  3.41 kB
dist/assets/task.store-D0rhA2g1.js                                                 6.99 kB │ gzip:  2.61 kB
dist/assets/RemoteTokensPage-cRbNJJxo.js                                           7.59 kB │ gzip:  3.85 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-BuGN5n_x.js               7.62 kB │ gzip:  3.28 kB
dist/assets/RemoteDevicesPage-BuF_dNXd.js                                          8.54 kB │ gzip:  3.75 kB
dist/assets/WorkspacesPage-hWG-8Fzn.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/TemplatesPage-CSA_x1vl.js                                              9.62 kB │ gzip:  4.27 kB
dist/assets/SessionsPage-C8M_pyOU.js                                              10.58 kB │ gzip:  4.52 kB
dist/assets/AgentsPage-BvOZoOGg.js                                                11.64 kB │ gzip:  4.06 kB
dist/assets/TasksPage-DwgDb83v.js                                                 11.80 kB │ gzip:  4.69 kB
dist/assets/OverviewPage-BZUwkyYb.js                                              12.12 kB │ gzip:  3.96 kB
dist/assets/ApprovalsPage-C1G7dv6t.js                                             12.28 kB │ gzip:  4.97 kB
dist/assets/OnboardingPage-NI2zM0oO.js                                            12.94 kB │ gzip:  4.92 kB
dist/assets/TeamsPage-BQ8fOeXL.js                                                 16.12 kB │ gzip:  6.01 kB
dist/assets/remote-chat.store-BiApmrb-.js                                         21.97 kB │ gzip:  7.05 kB
dist/assets/TaskDetailPage-DJbdIRMa.js                                            23.47 kB │ gzip:  7.99 kB
dist/assets/AttachmentDrafts.vue_vue_type_script_setup_true_lang-DhpObn8q.js      25.54 kB │ gzip: 10.21 kB
dist/assets/ScenesPage-BcRs6Drj.js                                                25.69 kB │ gzip:  8.71 kB
dist/assets/RemoteChatPage-DCW9N_1W.js                                            41.14 kB │ gzip: 12.86 kB
dist/assets/RemoteLinkPage-BUgt_Njy.js                                            49.48 kB │ gzip: 18.89 kB
dist/assets/ChatPage-Bmwsq9-D.js                                                  78.99 kB │ gzip: 23.95 kB
dist/assets/jsQR-UMIdgYmG.js                                                     130.80 kB │ gzip: 47.46 kB
dist/assets/vendor-BKKHNeE9.js                                                   149.77 kB │ gzip: 50.59 kB
dist/assets/index-CtGVniNB.js                                                    230.72 kB │ gzip: 75.64 kB
✓ built in 11.72s
```

保留了既有 router injection 测试警告、模拟 HUB_NOT_READY 日志和 echarts 空 chunk 构建提示；本轮所有测试通过。

### 4. 截图与浏览器复现

手机 375×812、电脑 1280×800，亮/暗各有默认折叠、展开、不可用说明，共 12 张，已查看检查。截图使用合成元数据，不读取用户真实 CLI 历史；示例版本不代表 Hub 的支持范围判定。

| 场景 | 亮色 | 暗色 |
| --- | --- | --- |
| 手机默认列表及全部不可用空状态 | [亮色](screenshots/r16-p3-fix3/light-mobile-collapsed-375x812.png) | [暗色](screenshots/r16-p3-fix3/dark-mobile-collapsed-375x812.png) |
| 手机展开不可用分组 | [亮色](screenshots/r16-p3-fix3/light-mobile-expanded-375x812.png) | [暗色](screenshots/r16-p3-fix3/dark-mobile-expanded-375x812.png) |
| 手机不可用说明 | [亮色](screenshots/r16-p3-fix3/light-mobile-explanation-375x812.png) | [暗色](screenshots/r16-p3-fix3/dark-mobile-explanation-375x812.png) |
| 电脑默认列表及全部不可用空状态 | [亮色](screenshots/r16-p3-fix3/light-desktop-collapsed-1280x800.png) | [暗色](screenshots/r16-p3-fix3/dark-desktop-collapsed-1280x800.png) |
| 电脑展开不可用分组 | [亮色](screenshots/r16-p3-fix3/light-desktop-expanded-1280x800.png) | [暗色](screenshots/r16-p3-fix3/dark-desktop-expanded-1280x800.png) |
| 电脑不可用说明 | [亮色](screenshots/r16-p3-fix3/light-desktop-explanation-1280x800.png) | [暗色](screenshots/r16-p3-fix3/dark-desktop-explanation-1280x800.png) |

[复现脚本](screenshots/r16-p3-fix3/verify.py)、[结构化结果](screenshots/r16-p3-fix3/verification.json)、[原始输出](r16-p3-fix3-validation/browser.txt)。脚本检查两端的默认折叠、空状态、说明文案、零读取/导入请求、Esc 关闭及焦点返回、无横向溢出。

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
pnpm --filter @hqagent/desktop exec vite --mode mock --host 127.0.0.1 --port 5198 --strictPort
# 另一个终端，同一 worktree；使用本机已有 Python Playwright/Chromium：
$env:PYTHONUTF8='1'
python .hqagent/handoffs/screenshots/r16-p3-fix3/verify.py
```

真实输出（退出码 0）：

```text
{"checks": [{"mode": "light", "device": "mobile", "readable": 1, "unavailableByWorkspace": [2, 1], "defaultCollapsed": true, "emptyReadableWorkspaces": 1, "readOrImportRequests": 0, "focusReturned": true, "horizontalOverflow": false}, {"mode": "dark", "device": "mobile", "readable": 1, "unavailableByWorkspace": [2, 1], "defaultCollapsed": true, "emptyReadableWorkspaces": 1, "readOrImportRequests": 0, "focusReturned": true, "horizontalOverflow": false}, {"mode": "light", "device": "desktop", "readable": 1, "unavailableByWorkspace": [2, 1], "defaultCollapsed": true, "emptyReadableWorkspaces": 1, "readOrImportRequests": 0, "focusReturned": true, "horizontalOverflow": false}, {"mode": "dark", "device": "desktop", "readable": 1, "unavailableByWorkspace": [2, 1], "defaultCollapsed": true, "emptyReadableWorkspaces": 1, "readOrImportRequests": 0, "focusReturned": true, "horizontalOverflow": false}], "screenshots": 12, "browserErrors": 0, "source": "Chromium with synthetic mock metadata"}
```

### 5. 验证边界

- 手机截图为 Chromium 375×812 模拟，未完成 iOS/Android 真机触控和读屏实测。
- 未访问用户电脑的 56 个真实会话，未读取真实终端历史、发起真实导入或调用线上会话。Hub 版本范围修正不在本包；前端只依照服务端/Hub 返回的 format 状态展示，真实版本升级后的索引变化由主代理联调复验。
- 未新增持久化存储或日志输出，不记录会话正文、凭据、Cookie、短码或令牌。
- 未遇真实 429、0xC0000142 或 API 额度错误；测试中 Storage 抛错只是有意模拟浏览器偏好不可用。构建和测试串行，本轮开发服务已停止。
- 实现和验收材料按主题提交到 feat/r15-web，逐次检查提交信息，不合并回 integration。


## 返修 4：续接失败保留具体原因

### 1. 基线和修改

- 工作区 `r15-web` / 分支 `feat/r15-web`，已先执行 `git merge integration/phase1`，输出 `Already up to date.`；基线 `0983b9b`（含 Hub 返修 4）。
- `SESSION_NOT_RESUMABLE` 优先显示 Hub/服务端提供的 message，不再用固定错误字典覆盖。仅缺失、空串或全空白时兜底：
  - 场景对话：**无法接着上一轮继续，请点右上角 + 开启新话题**。
  - 原生对话：**该原生会话暂时无法续接，请稍后重试或在电脑上核对**。
- 共用错误函数的会话类型从生成物 `LocalConversationView['conversationKind']` 引用（scenario/native），未新增 DTO 或协议字段。
- 本机/远程 HTTP 网关保留缺失原因，避免 HTTP `Conflict`、英文默认报错或提前生成的场景兜底掩盖实际缺失。Store 获取会话类型后选择正确文案；本机迟到错误仍保存在原会话名下。
- 手机命令送达失败提示及本机原生错误提示复用同一规则；本机带附件发送若发生续接错误，不被通用附件错误提示覆盖。
- 手机网关缺失续接原因时不创建空白网络诊断横幅，由 Store 显示对应会话兜底；已有原因仍正常显示。错误对象继续携带 code/status/requestId。
- 续接错误区域改为换行，避免具体原因和界面指引被省略号截断。未改变自动新建会话、续接、重置上下文等执行逻辑。
- `chat.reliability.test.ts` 的旧控件指引已更新；两处“不显示旧控件”的文本断言改为检查不存在 radio。前端搜索 `选择.*上下文|新一轮上下文|新上下文` 无匹配。

### 2. 测试与真实验收输出

新增 `stores/session-resumption.test.ts`，共 13 项：有安全原因时保留原文；场景/原生分别兜底；空白原因视为缺失；原生公共错误函数正确处理；其他错误代码映射保持原行为；本机和远程分别通过真实 HTTP 网关 + mocked fetch 验证发送错误进入对应 Store 显示字段，HTTP 状态文本不冒充业务原因。

四项检查串行执行，TEMP/TMP 为 worktree 内被忽略的 `.tmp`，退出码全部为 0。原始完整输出：[lint](r16-p3-fix4-validation/lint.txt)、[typecheck](r16-p3-fix4-validation/typecheck.txt)、[vitest](r16-p3-fix4-validation/vitest.txt)、[build](r16-p3-fix4-validation/build.txt)。

```text
> pnpm --filter @hqagent/desktop lint
$ eslint src

> pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit

> pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
Test Files  69 passed (69)
      Tests  491 passed (491)
   Start at  09:50:22
   Duration  51.04s (transform 3.42s, setup 0ms, collect 24.11s, tests 17.47s, environment 37.32s, prepare 5.85s)
```

```text
> pnpm --filter @hqagent/desktop build
$ vue-tsc --noEmit && vite build
vite v5.4.21 building for production...
transforming...
✓ 1854 modules transformed.
Generated an empty chunk: "echarts".
rendering chunks...
computing gzip size...
dist/index.html                                                                    2.56 kB │ gzip:  1.04 kB
dist/assets/ChatPage-DQ8nlvA7.css                                                  0.24 kB │ gzip:  0.17 kB
dist/assets/index-CxiKY7_w.css                                                    60.61 kB │ gzip: 11.23 kB
dist/assets/echarts-l0sNRNKZ.js                                                    0.00 kB │ gzip:  0.02 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-D9a1KLyg.js    0.92 kB │ gzip:  0.60 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-CkHf_PnH.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-BuO-Khfs.js           1.55 kB │ gzip:  0.75 kB
dist/assets/confirm-yNWjckwc.js                                                    1.74 kB │ gzip:  0.94 kB
dist/assets/PlaceholderPage-BAOQqUxU.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-B0YTw4mB.js             1.88 kB │ gzip:  0.89 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-CamkzXts.js           2.44 kB │ gzip:  1.19 kB
dist/assets/native-utils-Cad9vs7X.js                                               2.45 kB │ gzip:  1.60 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-pO-dmCg-.js                2.51 kB │ gzip:  1.11 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-BNkDMipx.js     2.61 kB │ gzip:  1.42 kB
dist/assets/team.store-D74A1vKn.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-DAsjrIty.js                                            3.85 kB │ gzip:  1.85 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-DhmT2hJz.js               4.39 kB │ gzip:  2.02 kB
dist/assets/ConnectPage-mGcZ77PU.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-DFiQ9Fs0.js                                          6.23 kB │ gzip:  2.82 kB
dist/assets/PairingScanner-DzeTOmQj.js                                             6.26 kB │ gzip:  3.41 kB
dist/assets/task.store-B_miRHhY.js                                                 6.99 kB │ gzip:  2.61 kB
dist/assets/RemoteTokensPage-BwGmtVPG.js                                           7.59 kB │ gzip:  3.85 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-BuGN5n_x.js               7.62 kB │ gzip:  3.28 kB
dist/assets/RemoteDevicesPage-BRkjg_ll.js                                          8.54 kB │ gzip:  3.75 kB
dist/assets/WorkspacesPage-XEt1D58Y.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/TemplatesPage-CKvwHbzG.js                                              9.62 kB │ gzip:  4.27 kB
dist/assets/SessionsPage-CLi6CgNN.js                                              10.58 kB │ gzip:  4.52 kB
dist/assets/AgentsPage-1KmJi9Ur.js                                                11.64 kB │ gzip:  4.06 kB
dist/assets/TasksPage-CvsijX-q.js                                                 11.80 kB │ gzip:  4.69 kB
dist/assets/OverviewPage-D-II-Egx.js                                              12.12 kB │ gzip:  3.96 kB
dist/assets/ApprovalsPage-KLMdS1VJ.js                                             12.28 kB │ gzip:  4.96 kB
dist/assets/OnboardingPage-brevqME4.js                                            12.94 kB │ gzip:  4.92 kB
dist/assets/TeamsPage-ChHbggUA.js                                                 16.12 kB │ gzip:  6.00 kB
dist/assets/remote-chat.store-BPvzFMkN.js                                         22.06 kB │ gzip:  7.09 kB
dist/assets/TaskDetailPage-Xqd3I9Kg.js                                            23.47 kB │ gzip:  8.00 kB
dist/assets/AttachmentDrafts.vue_vue_type_script_setup_true_lang-DGlScKDy.js      25.54 kB │ gzip: 10.21 kB
dist/assets/ScenesPage-BqBJlX7c.js                                                25.69 kB │ gzip:  8.71 kB
dist/assets/RemoteChatPage-CzLt4hL9.js                                            41.31 kB │ gzip: 12.92 kB
dist/assets/RemoteLinkPage-BTA7W2iZ.js                                            49.48 kB │ gzip: 18.89 kB
dist/assets/ChatPage-Bn-imUOC.js                                                  79.05 kB │ gzip: 23.98 kB
dist/assets/jsQR-UMIdgYmG.js                                                     130.80 kB │ gzip: 47.46 kB
dist/assets/vendor-BKKHNeE9.js                                                   149.77 kB │ gzip: 50.59 kB
dist/assets/index-BRSZaKYd.js                                                    230.97 kB │ gzip: 75.77 kB
✓ built in 7.78s
```

保留既有 router injection 测试警告、模拟 HUB_NOT_READY 日志以及 echarts 空 chunk 构建提示；最终 69 个文件、491 项测试通过。

### 3. 交接

- 仅修改 `apps/desktop/**` 和 `.hqagent/handoffs/**`，无依赖、根配置、协议、Hub 或服务端变更。
- 本轮验证为纯函数及 mocked HTTP 到 Store 的自动化链路，未操作线上真实续接或实体手机；未新增截图。
- 未遇真实 429、0xC0000142 或 API 额度错误；未并行运行构建/测试，未新增持久化存储或敏感日志。
- 提交标题：`fix(desktop): preserve session resumption failure reasons`。提交后运行 `git log -1 --format=%B` 自查，不包含署名或生成标记；只提交到 feat/r15-web，不合并回 integration。
