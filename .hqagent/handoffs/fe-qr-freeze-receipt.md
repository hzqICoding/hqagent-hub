# 桌面「连接手机」冻结原型修复回执

## 基线、范围与提交

- 工作区 `r15-web` / 分支 `feat/r15-web`；开工工作树干净，主代理已合入 integration，基线 `12a08d1`，已含 `uqr@0.1.3`。
- `bd893a6` — `fix(desktop): render pairing QR codes with prototype-safe SVG`
- `9b6a8a0` — `test(desktop): verify production pages with frozen prototypes`
- 每次提交后已执行 `git log -1 --format=%B` 自查，输出即上述标题，无署名/生成标记。回执和真实输出另作交付主题提交并同样自查。
- 仅修改 `apps/desktop/src/**` 与 `.hqagent/handoffs/**`。**未改 tauri.conf.json，freezePrototype 仍为 true；未安装依赖、未改 package.json 或 lockfile。** `qrcode` / `@types/qrcode` 的依赖清理由主代理后续执行，本包已不再引用其运行时或类型。
- 未合并回 integration，未部署或重打桌面安装包。

## 修复

根因与主代理证据一致：旧库向普通 CommonJS exports 对象赋值 toString，在继承的 Object.prototype.toString 已冻结且处于严格模式时触发 override mistake。异常发生在懒加载模块求值阶段，页面尚未挂载，组件内部二维码生成的 try/catch 无法捕获。

- `RemoteLinkPage.vue` 改用纯 ESM `uqr`，通过 `shared/qr/pairing-qr-code.ts` 生成二维码。
- 原编码器源码默认纠错为 M，本次显式 `ecc: 'M'`、`boostEcc: false`；保持 1 模块边距、黑码白底、200×200 固定输出。保留原 img 的响应式尺寸类，另指定 200×200 属性，并用 crispEdges 保持模块边缘清晰。
- 二维码内容仍为 `<serverOrigin>/remote/pair#code=<pairCode>`；默认服务器配置、短码回退、倒计时与取消流程不变。同步生成避免旧异步结果在取消后重新写回二维码。
- SVG 只由编码器产生数值几何路径，颜色、尺寸、属性均是固定受控常量，输入不会拼接进 SVG 标记；经 encodeURIComponent 形成 data URL，使用 **img** 显示，未使用 v-html/innerHTML。
- 已替换应用、测试和旧扫码验收脚本中的库使用。`.hqagent/handoffs/screenshots/r16-p3-fix1/verify.py` 的合成视频源改用 uqr 矩阵绘制，保留其 480px、4 模块边距与 M 纠错；历史截图/回执没有改写。本轮以新的冻结回归覆盖合成流扫码，不把旧布局脚本的历史断言当作本轮验收。
- 保留 `pair-qrcode` 这一测试定位符；搜索剩余 qrcode 字样仅是该定位符或禁止旧库的审计规则，不是运行时引用。

## 冻结原型回归

新增 [生产浏览器回归入口](../../apps/desktop/src/shared/testing/frozen-prototypes.browser.ts) 与 [构建脚本](qr-freeze-regression/build.mjs)、[浏览器断言脚本](qr-freeze-regression/verify.py)。

测试在独立 Chromium 上运行，避免冻结 vitest 测试框架自身：

1. HTML 引导脚本在**任何 ES 模块依赖求值之前**冻结 Object.prototype、Function.prototype、Array.prototype，入口再次检查冻结状态。不是先加载页面后冻结，避免模块缓存掩盖故障。
2. 负向控制在普通对象上赋值 toString 必须抛错，证明测试确实覆盖原 override-mistake 条件。
3. 用真实生产模式 Vite/Rollup 产物、真实 Vue/Pinia/Router/i18n 和组件渲染；只把 API 设置为 mocks。先渲染 ChatPage，再**点击页面内「连接手机」入口**，触发 RemoteLinkPage 的懒加载和导航。
4. 动态加载并渲染 RemoteLinkPage、AgentsPage、ScenesPage、ChatPage、RemotePairingPage；附件草稿、附件项、消息附件、图片验证区块、原生列表和 PairingScanner。
5. 从实际渲染的 SVG 图像提取像素，分别在 **140 / 168 / 200px** 下使用 jsqr 解码，逐字比对预期合成链接；检查固有与声明尺寸为 200×200，取消配对后二维码消失。
6. 冻结环境下给 PairingScanner 注入仅含合成 QR 的 canvas MediaStream，实际运行延迟加载的 jsqr 降级路径；识别成功且所有视频轨道 ended。
7. HTTP 错误会立即使回归停止；成功输出 browserErrors=0、httpErrors=0。临时 HTTP 服务与浏览器运行后关闭。

**其他依赖检查结果：**上述生产模块加载/基本渲染、Vue 栈和实际 jsqr 解码过程中，没有发现其它同类只读原型赋值问题；没有额外替换依赖或关闭安全配置。这不是对全部未执行交互路径的穷尽证明。

新增 2 项 vitest 检查编码参数和 SVG 注入边界，原配对页测试更新为 SVG/200px 与取消后移除。完整 vitest 74 个文件、537 项通过。

## 真实验收输出

所有构建/测试串行，TEMP/TMP 指向 worktree 内被忽略的 `.tmp`。本机 pnpm 沿用仅命令环境的 `pnpm_config_verify_deps_before_run=false`，防止运行脚本时自动安装依赖；没有执行任何安装操作或改变根配置。

[lint](qr-freeze-validation/lint.txt)、[typecheck](qr-freeze-validation/typecheck.txt)、[vitest](qr-freeze-validation/vitest.txt)、[build](qr-freeze-validation/build.txt) 均退出 0：

```text
> pnpm --filter @hqagent/desktop lint
$ eslint src

> pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit

> pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
Test Files  74 passed (74)
      Tests  537 passed (537)
   Start at  11:26:55
   Duration  47.09s (transform 3.01s, setup 0ms, collect 23.18s, tests 17.04s, environment 32.24s, prepare 4.97s)
```

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
dist/assets/PiGuardStatus.vue_vue_type_script_setup_true_lang-CB1IA4Mn.js          0.79 kB │ gzip:  0.53 kB
dist/assets/RemoteRequestNotice.vue_vue_type_script_setup_true_lang-CbpQgMnA.js    0.92 kB │ gzip:  0.60 kB
dist/assets/HqEmptyState.vue_vue_type_script_setup_true_lang-YiFwxKkw.js           1.17 kB │ gzip:  0.63 kB
dist/assets/LoadingState.vue_vue_type_script_setup_true_lang-CemGJXKT.js           1.55 kB │ gzip:  0.75 kB
dist/assets/confirm-vnul2RD2.js                                                    1.74 kB │ gzip:  0.94 kB
dist/assets/PlaceholderPage-BvLlMhdy.js                                            1.74 kB │ gzip:  1.10 kB
dist/assets/HqTextarea.vue_vue_type_script_setup_true_lang-D2F41ATq.js             1.88 kB │ gzip:  0.89 kB
dist/assets/OfflineState.vue_vue_type_script_setup_true_lang-BgVDdj4n.js           2.44 kB │ gzip:  1.19 kB
dist/assets/HqInput.vue_vue_type_script_setup_true_lang-2fpPiwrl.js                2.51 kB │ gzip:  1.11 kB
dist/assets/native-utils-DWdVhQxM.js                                               2.53 kB │ gzip:  1.70 kB
dist/assets/ResolveSourceBadge.vue_vue_type_script_setup_true_lang-c2Fk6bx0.js     2.61 kB │ gzip:  1.42 kB
dist/assets/team.store-yC71UabK.js                                                 3.73 kB │ gzip:  1.88 kB
dist/assets/RemoteLoginPage-CaLtP9bP.js                                            3.85 kB │ gzip:  1.85 kB
dist/assets/HqDialog.vue_vue_type_script_setup_true_lang-C6Ut7z5Y.js               4.39 kB │ gzip:  2.01 kB
dist/assets/ConnectPage-eN_YwgVX.js                                                5.09 kB │ gzip:  2.46 kB
dist/assets/RemotePairingPage-DplDhgxP.js                                          6.23 kB │ gzip:  2.81 kB
dist/assets/PairingScanner-DlW7YGmB.js                                             6.26 kB │ gzip:  3.40 kB
dist/assets/task.store-BMBmVYHe.js                                                 6.99 kB │ gzip:  2.62 kB
dist/assets/RemoteTokensPage-PQGYlCmy.js                                           7.59 kB │ gzip:  3.85 kB
dist/assets/HqSelect.vue_vue_type_script_setup_true_lang-D90tRIU8.js               7.62 kB │ gzip:  3.28 kB
dist/assets/RemoteDevicesPage-YMCxl8TU.js                                          8.54 kB │ gzip:  3.75 kB
dist/assets/WorkspacesPage-BdIuUmBR.js                                             8.80 kB │ gzip:  3.50 kB
dist/assets/TemplatesPage-IxEore88.js                                              9.62 kB │ gzip:  4.27 kB
dist/assets/SessionsPage-CUEZuKW4.js                                              10.58 kB │ gzip:  4.52 kB
dist/assets/TasksPage-ByVHQoPu.js                                                 11.80 kB │ gzip:  4.69 kB
dist/assets/OverviewPage-BMNEJqNu.js                                              12.12 kB │ gzip:  3.95 kB
dist/assets/ApprovalsPage-DMej-g2D.js                                             12.54 kB │ gzip:  5.07 kB
dist/assets/OnboardingPage-CaL-a9sB.js                                            12.94 kB │ gzip:  4.92 kB
dist/assets/TeamsPage-xBy9-7mL.js                                                 16.12 kB │ gzip:  6.01 kB
dist/assets/remote-chat.store-BNqeKklH.js                                         22.75 kB │ gzip:  7.34 kB
dist/assets/TaskDetailPage-B4mmHA4_.js                                            23.47 kB │ gzip:  7.99 kB
dist/assets/AgentsPage-DtmOVvql.js                                                24.14 kB │ gzip:  8.86 kB
dist/assets/AttachmentDrafts.vue_vue_type_script_setup_true_lang-BQS8ZPRb.js      25.99 kB │ gzip: 10.34 kB
dist/assets/ScenesPage-Sg2WhQTJ.js                                                27.24 kB │ gzip:  9.26 kB
dist/assets/RemoteLinkPage-DW07M6FU.js                                            36.42 kB │ gzip: 13.43 kB
dist/assets/RemoteChatPage-CCXGdgkf.js                                            42.34 kB │ gzip: 13.23 kB
dist/assets/ChatPage-C5OalZnV.js                                                  83.04 kB │ gzip: 25.66 kB
dist/assets/jsQR-UMIdgYmG.js                                                     130.80 kB │ gzip: 47.46 kB
dist/assets/vendor-DAwl41T1.js                                                   150.58 kB │ gzip: 50.79 kB
dist/assets/index-B78Q6qpF.js                                                    253.32 kB │ gzip: 83.78 kB
✓ built in 6.19s
```

保留既有 router injection 测试警告、HUB_NOT_READY 模拟日志和 echarts 空 chunk 提示，没有删减或跳过原测试。

## 生产产物检查

[产物审计脚本](qr-freeze-regression/audit.mjs) 检查正式 dist 的全部 JS chunk：旧 exports.toString 赋值模式及旧 mode 诊断指纹均为 0；应用源码无旧库 import。另读取 tauri.conf.json 断言 freezePrototype=true。生产模式冻结回归构建再使用 Rollup 模块图核对：**旧库模块数 0，uqr 已包含**，不只依靠 minify 后的文本查找。

[正式产物审计输出](qr-freeze-validation/production-audit.txt)，退出 0：

```text
{"freezePrototypeEnabled":true,"jsChunks":42,"legacyModeAssignmentOrDiagnosticMatches":0,"legacyRuntimeSourceImports":0,"remoteLinkChunks":["RemoteLinkPage-DW07M6FU.js"]}
```

[冻结产物构建原始输出](qr-freeze-validation/frozen-build.txt)、[浏览器原始输出](qr-freeze-validation/frozen-browser.txt)、[结构化结果](qr-freeze-validation/frozen-browser.json)，全部退出 0：

```text
{"prototypesFrozen": true, "overrideMistakeBlocked": true, "pages": ["ChatPage", "RemoteLinkPage", "AgentsPage", "ScenesPage", "RemotePairingPage"], "components": ["AttachmentDrafts", "AttachmentItem", "MessageAttachments", "ImageVerificationPanel", "NativeSessionsPanel", "PairingScanner"], "qrDecoded": true, "qrDecodedSizes": [140, 168, 200], "scannerDecoded": true, "cameraReleased": true, "moduleAudit": {"legacyQrModules": 0, "moduleCount": 2299, "uqrIncluded": true}, "browserErrors": 0, "httpErrors": 0, "engine": "Chromium; fresh production ES module graph; mock APIs and synthetic camera"}
```

## 复现与交接

同一 worktree 根目录，使用已安装的 Node、Python Playwright/Chromium，无新增依赖：

```powershell
$env:TEMP=(Join-Path $PWD '.tmp')
$env:TMP=$env:TEMP
$env:pnpm_config_verify_deps_before_run='false'
$env:PYTHONUTF8='1'
pnpm --filter @hqagent/desktop lint
pnpm --filter @hqagent/desktop typecheck
pnpm --filter @hqagent/desktop exec vitest run --minWorkers=1 --maxWorkers=2
pnpm --filter @hqagent/desktop build
node .hqagent/handoffs/qr-freeze-regression/audit.mjs
node .hqagent/handoffs/qr-freeze-regression/build.mjs
python .hqagent/handoffs/qr-freeze-regression/verify.py
```

冻结入口只供额外回归构建使用，未被正常应用入口引用；测试产物位于 `.tmp/qr-freeze-browser`。没有真实摄像头画面、有效配对凭据、模型调用或线上绑定操作；报告不记录二维码内容。

主代理后续可移除 qrcode 及不再需要的类型依赖，再重建安装包进行 WebView2 实机点击/扫码复验。本轮证明的是**生产打包后的 Chromium 冷启动冻结环境**，未冒称已操作重打后的 Tauri 安装包或验证真实 Hub/服务端链路。

未遇真实 429/403 等服务端错误、0xC0000142 或 API 额度错误。所有已授权前端修改和验收材料已落盘；未合并回 integration。
