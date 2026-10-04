---
wp: shell-probe-fix
status: done
scope_declared: [apps/desktop/src-tauri/src/**, apps/desktop/src/**, .hqagent/handoffs/**]
scope_touched: [apps/desktop/src-tauri/src/runtime_descriptor.rs, apps/desktop/src-tauri/src/process_supervisor.rs, apps/desktop/src-tauri/src/state.rs, apps/desktop/src-tauri/src/error.rs, apps/desktop/src/app/DesktopConnection.vue, apps/desktop/src/app/DesktopConnection.test.ts, apps/desktop/src/shared/api/desktop-endpoint.ts, apps/desktop/src/shared/api/desktop-gateway.test.ts, apps/desktop/src/shared/api/local-chat-gateway.ts, apps/desktop/src/stores/local-auth.store.ts, .hqagent/handoffs/shell-probe-fix.md, .hqagent/handoffs/shell-probe-validation/**]
build: pass
tests: pass
commit: 63fe4ad2244f5a27678e10d3eab86e5aad4cbda0
open_questions: 0
---

# 桌面壳启动探测紧急修复

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/desktop-shell`，分支 `feat/desktop-shell`。
开始时工作树干净，已执行 `git merge integration/phase1`，输出 `Already up to date.`，
基线为已有同步提交 `5678e3213ce300ab3897a5922cf94c89790e30fb`。
实现提交：`2342557`（原生探测/守护）、`63fe4ad`（启动提示/错误原因/前端超时）。
回执另作提交，避免自引用。每次提交均执行 `git log -1 --format=%B` 自查。
没有改 `apps/hub`、协议、package.json、lockfile，没有合并回 integration、推送或重打安装包。

## 核对结果

原 `HubEndpointProvider` 确实把 healthz 和 bootstrap 共用 2 秒总超时，会使慢于 2 秒的
Agent 检测阻塞桌面就绪。**原 state.rs 的 get_endpoint 失败分支只记录 warnings，未调用停止或重启**；
原 supervisor 的自动重启发生在进程退出/状态查询异常后。本轮不把“bootstrap 超时导致 core 被杀”
当作已证实事实；主代理观察到的 core 端口消失仍需结合 Hub/父控制退出证据判断。

另发现原 `try_wait()` 返回查询错误时也会进入重新 spawn 的路径，查询失败并不证明旧进程已经退出，
已修正：继续保留受管句柄，由确认退出或独立存活监控作重启决策，避免误拉第二个 core。

## 最终行为

| 项目 | 配置/行为 |
| --- | --- |
| 存活 | 独立客户端只请求 `/healthz`，连接/总超时 2 秒 |
| 就绪 | 独立客户端请求 `/api/v1/bootstrap`，总超时 15 秒 |
| 冷启动 | 每次进程启动后的前 90 秒，bootstrap 单次可等 30 秒；healthz 失败不累积重启阈值 |
| 存活轮询 | 受管进程线程执行，完成一次检查后间隔 2 秒；不受 bootstrap 请求或缓存锁阻塞 |
| 连续失败 | 冷启动宽限后，连续 3 次存活检查失败才停止旧 core；一次成功清零计数 |
| 身份不符 | 仅对已经识别的受管实例检查；宽限后明确 InvalidDescriptor 可请求重启，不向未经验证的地址发请求 |
| 重启方式 | 使用受管 Child 句柄，shutdown→EOF→最多15秒→必要时强制结束，再按既有退避重启 |
| bootstrap 失败 | 只返回就绪错误/显示原因，永不计入健康失败阈值，也不能请求重启 |
| 并发就绪 | UI 与 monitor 单次探测合并；成功/失败结果缓存2秒，按 PID+instanceId 隔离，不缓存 token/endpoint |

返回 endpoint 前再次检查受管身份，避免慢 bootstrap 返回时把已重启实例的连接交给前端。
退出时先通知 supervisor 停止子进程，再等待 readiness monitor，避免先等待30秒冷启动探测才发送 shutdown。
ACL、loopback/导航限制、Bearer、descriptor 校验均保留。

前端在未就绪时始终显示「正在启动本机 Hub，连接就绪后将自动进入。」；
Tauri 序列化的 CommandError 会转换成 ShellConnectionError，中文 ShellError 原因经 auth store
显示在启动提示下方，不再被“请检查桌面 Bearer 接口”或通用失败文本覆盖。
本机请求先等待壳完成发现/就绪，再启动业务 HTTP 的15秒计时；否则30秒冷启动等待仍会被前端15秒截断。
连接码路由隔离、token 不落盘、草稿保留行为不变。

## 测试证据

全部构建/测试串行执行；Rust 单编译任务、单测试线程，Vitest 固定1–2 workers。
原始输出在 [shell-probe-validation](shell-probe-validation/)；提交时仅规范换行及移除日志行末空格。

新增测试使用 Rust 测试二进制作为真实受管子进程，创建当前用户私有 descriptor 和 loopback HTTP 服务：

- **5 秒 bootstrap**：请求真实延迟5秒，两个并发 get_endpoint 成功，共1次 bootstrap；PID未变、没有 shutdown。
  此集成测试将 watchdog 冷启动宽限设为0，避免用宽限期掩盖误重启。
- **就绪失败与存活失败分离**：持续8秒让 bootstrap 返回失败包络但 healthz正常，PID不变；
  然后让 healthz连接失败，达到3次阈值后观察到 shutdown 和新PID。未调用任何真实用户 Hub。
- **配置/计数**：healthz2秒、bootstrap15秒、冷启动30秒/90秒边界；健康成功清零，重启后重新宽限。
- **前端**：壳就绪等待20秒不触发业务15秒超时；中文 ShellError 保留并显示在启动提示下方。

最终原始输出摘录：

```text
Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.87s
exit_code=0

Finished `test` profile [unoptimized + debuginfo] target(s) in 12.37s
test result: ok. 28 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 26.45s
exit_code=0

$ eslint src
exit_code=0
$ vue-tsc --noEmit
exit_code=0

Test Files  74 passed (74)
     Tests  539 passed (539)
  Duration  59.43s (transform 3.40s, setup 0ms, collect 25.50s, tests 16.96s, environment 52.53s, prepare 6.15s)
exit_code=0

✓ 1802 modules transformed.
✓ built in 6.54s
exit_code=0
```

对应完整日志：[cargo check](shell-probe-validation/cargo-check.txt)、[cargo test](shell-probe-validation/cargo-test.txt)、
[lint](shell-probe-validation/lint.txt)、[typecheck](shell-probe-validation/typecheck.txt)、
[Vitest](shell-probe-validation/vitest.txt)、[build](shell-probe-validation/build.txt)。
既有 Rust unused/dead_code/linker 消息、Vue router injection 警告、Mock WS 503 预期日志和空 echarts chunk 提示保留。
未遇真实429/403服务端错误、0xC0000142或额度错误。

## 本机验证环境说明与复现

本 worktree 未生成 `dist/hqagent-core/hqagent-core.exe`，Rust 检查仅用
`TAURI_CONFIG={"bundle":{"resources":null}}` 跳过 bundle 资源复制；使用真实前端 dist，
不制造假exe、不声称验证了安装包。

合入后的前端已依赖 uqr@0.1.3，但 node_modules 仍旧；第一次 pnpm lint 因自动安装无TTY而中止，
[失败输出](shell-probe-validation/lint-initial.txt)保留。只从本机 r15-web 已安装的同版本 uqr 复制到
当前 worktree 的被忽略 node_modules，核对 dist/index.mjs SHA256一致：
`7F0E61C2F13BB3724EDEE7BFB876E13C54AC9EE4FCFA283C9FA93CFB1241C325`。
[缓存恢复记录](shell-probe-validation/dependencies.txt)。没有联网安装、没有更改依赖清单/锁文件，未修改其他worktree。
pnpm 运行时通过当前命令环境关闭自动依赖安装（沿用已有前端回执的验证方式）。

```powershell
# 仓库根目录；现有依赖已准备好时
$env:pnpm_config_verify_deps_before_run = 'false'
$env:TEMP = (Join-Path $PWD '.tmp')
$env:TMP = $env:TEMP
pnpm --dir apps/desktop lint
pnpm --dir apps/desktop typecheck
pnpm --dir apps/desktop exec vitest run --minWorkers=1 --maxWorkers=2
pnpm --dir apps/desktop build
$env:CARGO_BUILD_JOBS = '1'
$env:TAURI_CONFIG = '{"bundle":{"resources":null}}' # 仅缺少P1产物的代码验证
cargo check --offline --manifest-path apps/desktop/src-tauri/Cargo.toml
cargo test --offline --manifest-path apps/desktop/src-tauri/Cargo.toml -- --test-threads=1
Remove-Item Env:TAURI_CONFIG -ErrorAction SilentlyContinue
```

## 主代理验收

1. 按集成流程取本包与并行 Hub 性能修复；清除验证用 TAURI_CONFIG，使用现有 build-windows.ps1 重打安装包。
2. 沿用原数据目录/配对，不做数据搬迁。冷启动显示启动提示，1.7–5秒 bootstrap 能进入主页，core PID保持不变。
3. 让 bootstrap 慢或失败、healthz持续正常：只显示就绪原因，不应出现“存活监控请求重启”。
4. 测试数据环境中令 healthz连续失败：90秒宽限后累计3次才重启，Backoff的 message 含明确存活原因；
   手动结束 core 则仍按原退避重新拉起，新实例再次获得冷启动宽限。
5. 若实际 core仍自行结束，收集进程退出码、Hub日志及父控制/EOF时序继续判断；本包没有把原2秒就绪超时
   伪装成已证明的进程退出原因。测试日志证明的是受管fixture行为，未代替新版安装包真机复验。
