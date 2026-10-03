---
wp: R17-P2
status: done
scope_declared: [apps/desktop/**, .hqagent/handoffs/**]
scope_touched: [apps/desktop/src-tauri/**, apps/desktop/src/**, apps/desktop/scripts/build-windows.ps1, .hqagent/handoffs/R17-P2-shell.md, .hqagent/handoffs/r17-p2-validation/**]
build: pass
tests: pass
commit: 1d12e7b1d097125da2035cc8d99a653791f26434
open_questions: 0
---

# R1.7-P2 Windows 桌面壳回执

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/desktop-shell`，分支 `feat/desktop-shell`。
基线 `c99b32cc53b0b0d6cf0d7efb07fdd7a773cea9ff`。实现提交：
`23caf5c`（安装资源/进程守护/托盘）、`1d12e7b`（自动登录/网关/重连）；本回执与构建脚本另作交付提交，避免自引用。
每次提交均执行 `git log -1 --format=%B`，无署名尾注；没有合并、推送或发布。
仅修改桌面壳、桌面网关/UI、打包脚本与回执，没有修改 Hub、协议、共享依赖/lockfile，未合并 integration。
没有启动真实用户 Hub、读取用户 token 或搬迁 `E:/tmp/hqagent-n0-trial`。

## 实现

- 启用当前用户 NSIS；完整 `dist/hqagent-core/` → `core/`，前端 dist → `web/`。
  Tauri resource_dir 解析默认 core 路径，环境变量和 desktop-shell.json 覆盖保留（绝对路径）。
  默认传 `--web-dir` 保留浏览器连接码入口；无 Update Agent 不影响 Hub，status/UI 如实报告 missing。
- 首次启动默认 HKCU Run 自启，--minimized 不弹窗；用户可从顶部关闭且持久保存。
  关窗隐藏；托盘打开/退出/Hub 状态；release 无控制台窗口，子进程 CREATE_NO_WINDOW。
- 单实例判定移到创建 Hub 之前；退出请求先保持事件循环，在后台 join 监控和停止 Hub，
  防止主线程等待正在更新托盘的监控线程。shutdown→EOF→最多15秒→最后强制结束。
  崩溃退避1/2/4/8秒，30秒稳定后重置。
- Tauri 强制真实 v1/v2 网关，每轮请求重新通过 IPC 获取 endpoint；仅并发调用合并，不持久化 token。
  v1/v2 HTTP、附件 XHR/二进制下载均加 Bearer，省略 Cookie；普通浏览器仍是 Cookie。
  桌面没有连接码路由；启动/恢复等待页自动重连，暂时隐藏已挂载页面以保留草稿。
- 保持 CSP 仅本机/IPC，增加 blob 图片预览；capability 未增加远程权限。
  安装目录固定为 LOCALAPPDATA/Programs/HQAgent-Hub，运行数据默认 LOCALAPPDATA/HQAgent-Hub。
  WebView2 用户目录显式使用该数据根的 webview/；卸载 hook 仅清自启注册，不删用户数据。
- 一键脚本：P1 build-core.ps1 → pnpm build → tauri build --offline，串行且 CARGO_BUILD_JOBS=1。
  可选 UpdateAgentPath；校验 exe/_internal，打印安装包和 SHA256。
- README 说明沿用旧根（推荐）与手动复制迁移，包括 DPAPI 同用户、停机备份、runtime 排除、
  绝对路径风险、配对/附件/记录验收和回退；不自动搬迁。

## 集成依赖与明确限制

P1 脚本路径已从 remote-worker 只读确认：`apps/hub/packaging/windows/build-core.ps1`，产物
`dist/hqagent-core/hqagent-core.exe` + `_internal/`。本 worktree 尚无 P1 产物，Rust 编译/测试
使用 `TAURI_CONFIG={"bundle":{"resources":null}}` 仅跳过资源复制；frontendDist 仍使用真实构建产物。
未制造假的 core.exe。最终打包脚本拒绝残留 TAURI_CONFIG。

主聊天界面实际使用 `/api/v2/**`，其 auth/status、普通本机路由已有 Bearer 分支，
与 P1 一起复核 Tauri Origin/CORS。图像验证和对话删除的 v2 路由另有 maintenance_cookie 限制，
本包桌面已切到协议冻结且 Hub 已实现的对应 `/api/v1` Bearer 入口（同一服务/DTO），
浏览器仍用 v2 Cookie。**不需要 P1 放宽 maintenance_cookie**；此前协作询问已由这一接法解决。
P2 没改 Hub。附件、手机配对及所有本机入口仍须跨组件实测。

最终 NSIS 构建、安装/重启/手机真机验收按用户要求交主代理；本回执不把单元测试称作安装通过。
本机缺 rustfmt，未联网安装。Rust 的既有 unused/dead_code 警告保留，不扩展清理范围。

## 验证输出

原始日志在 [r17-p2-validation](r17-p2-validation/)（提交时仅规范换行及去除 Vue 输出的行末空格，命令输出内容保留）。
构建与测试全部串行，Rust
`CARGO_BUILD_JOBS=1`，Vitest 固定 `--minWorkers=1 --maxWorkers=2`，Rust 测试
`--test-threads=1`。TEMP/TMP 指向 worktree 的 `.tmp`。没有实际请求429、0xC0000142或额度错误。

| 命令 | 最终结果 | 原始日志 |
| --- | --- | --- |
| `cargo check --offline --manifest-path apps/desktop/src-tauri/Cargo.toml` | exit 0 | [cargo-check.txt](r17-p2-validation/cargo-check.txt) |
| `cargo test --offline --manifest-path apps/desktop/src-tauri/Cargo.toml -- --test-threads=1` | 24 passed, exit 0 | [cargo-test.txt](r17-p2-validation/cargo-test.txt) |
| `pnpm --dir apps/desktop lint` | exit 0 | [lint.txt](r17-p2-validation/lint.txt) |
| `pnpm --dir apps/desktop typecheck` | exit 0 | [typecheck.txt](r17-p2-validation/typecheck.txt) |
| `pnpm --dir apps/desktop exec vitest run --minWorkers=1 --maxWorkers=2` | 72 files / 518 tests passed | [vitest.txt](r17-p2-validation/vitest.txt) |
| `pnpm --dir apps/desktop build` | exit 0 | [build.txt](r17-p2-validation/build.txt) |
| PowerShell Parser / git diff --check | 0 errors / exit 0 | [build-script.txt](r17-p2-validation/build-script.txt) |

真实输出摘录（未把资源跳过描述为打包通过）：

```text
Finished `dev` profile [unoptimized + debuginfo] target(s) in 6.65s
exit_code=0

Finished `test` profile [unoptimized + debuginfo] target(s) in 17.10s
test result: ok. 24 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 5.01s
exit_code=0

$ eslint src
exit_code=0
$ vue-tsc --noEmit
exit_code=0

Test Files  72 passed (72)
     Tests  518 passed (518)
  Duration  51.24s (transform 3.70s, setup 0ms, collect 25.32s, tests 18.22s, environment 36.21s, prepare 5.73s)
exit_code=0

✓ 1866 modules transformed.
✓ built in 13.23s
exit_code=0
```

过程中的失败也保留：首次 cargo check 缺少 frontendDist（[原始记录](r17-p2-validation/cargo-check-initial.txt)），
生成真实前端 dist 后通过。首次 Rust 测试 22过/2失败（[原始记录](r17-p2-validation/cargo-test-initial.txt)）：
ACL fixture 误用 USERNAME（宿主用户）而实际测试进程属于沙箱用户，现改由 whoami.exe 获取真实进程主体，
**生产 ACL 校验没有放宽**；旧 taskkill 测试被沙箱拒绝，现用真实子进程响应测试标记后异常退出来验证运行中重启。
强制结束路径另有真实 Child.kill 超时测试，真机 taskkill 验收仍保留在下面。
首次 lint this alias 与 typecheck next 重载问题已修正。既有 Vue router 注入警告、Mock WS 503 预期日志、
空 echarts chunk 提示及 Rust unused/dead_code/linker 消息可见于原始日志，未把它们隐藏为零警告。

## 主代理打包步骤

1. 按集成流程合入 P1 与本分支；核对 v1 维护入口与 v2 普通入口的 Tauri CORS/Bearer。
2. 准备仓库 `.venv`（P1 固定 PyInstaller 版本）及已安装 JS/Rust 依赖；不从本包新增依赖。
3. 清除检查用的 TAURI_CONFIG，执行：

   ```powershell
   Remove-Item Env:TAURI_CONFIG -ErrorAction SilentlyContinue
   pwsh -NoProfile -File apps/desktop/scripts/build-windows.ps1
   # 如已有更新组件：追加 -UpdateAgentPath E:/build/hqagent-update-agent.exe
   ```

4. 首次 NSIS/WebView2 工具下载由主代理联网完成；产物见脚本打印和
   `apps/desktop/src-tauri/target/release/bundle/nsis/*.exe`。检查安装包内完整 core/_internal、web，
   缺少 Update Agent 是允许的已知状态。记录产物大小、SHA256、构建提交。

## 主代理真机验收清单

1. **旧数据接续**：停止命令行 Hub；备份 `E:/tmp/hqagent-n0-trial`；按 README 方案①先写
   `coreArgs: ["--data-dir", "E:/tmp/hqagent-n0-trial"]`，用原 Windows 用户安装运行，不重新配对。
2. **安装目录**：确认 exe/core/_internal/web 在 LOCALAPPDATA/Programs/HQAgent-Hub；运行后程序目录
   不新增 DB/log/runtime。用户数据在默认根，或明确配置的旧根；runtime 仍在默认根。
3. **首次自启及开关**：首次打开注册 HKCU Run HQAgent-Hub，路径带引号及 --minimized；顶部关闭后
   注册项移除，退出重开仍关闭；重新开启并注销/登录（再做完整重启），应只见托盘无弹窗。
4. **自动登录**：双击窗口直接进入聊天，没有 /connect 页；DevTools HTTP v1/v2 为当前 loopback
   endpoint，Bearers 不出现在 URL/日志/前端持久存储。普通浏览器 http://127.0.0.1:<port> 仍需连接码。
5. **单实例/托盘**：重复双击只激活原窗口，只有一套 Hub；关窗后 Hub 不退出；托盘左击和菜单恢复。
   验证运行中/启动中/已停止、缺少 Update Agent 提示和 get_shell_status。
6. **崩溃恢复**：在无危险任务的测试状态只结束受管 core PID；首轮约1秒退避，10秒内重新拉起，
   PID/instanceId/token/端口更新，界面自动恢复、事件继续，旧 token 失效。连续故障验证上限8秒退避。
7. **退出**：托盘退出后 Hub 收到 shutdown/EOF 并在15秒内干净退出，壳不假死且无受管残留；
   另用可忽略 shutdown 的测试子进程验强制结束只能在超时后发生。
8. **手机控制**：旧配对设备保持在线，可列出旧对话、继续/新建对话、查看附件和验证记录；
   关电脑窗口后仍可控制；完整重启并登录 Windows 后无需连接码/重新配对即可继续。
9. **安全/维护接口**：无 Bearer v1拒绝、可信 Tauri v2正常、非白名单 Origin拒绝；附件上传/下载/
   缩略图、手机绑定和 v1维护入口均用桌面 Bearer 实测。不要把 token 写入验收截图或日志。
10. **卸载保留**：先正常退出，再卸载；自启项移除，默认/旧用户数据均保留，重装后可接续。

安装、自启是真正用户登录后运行，不是登录前服务；睡眠、关机或断网期间无法手机控制。
