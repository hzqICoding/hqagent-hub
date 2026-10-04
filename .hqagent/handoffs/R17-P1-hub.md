---
wp: R17-P1
status: done
scope_declared: [apps/hub/**, .hqagent/handoffs/R17-P1-hub.md]
scope_touched: [apps/hub/runtime/main.py, apps/hub/runtime/parent_process.py, apps/hub/runtime/local_chat.py, apps/hub/runtime/remote/worker.py, apps/hub/api/app.py, apps/hub/tests/test_desktop_process.py, apps/hub/packaging/windows/core_entry.py, apps/hub/packaging/windows/hqagent-core.spec, apps/hub/packaging/windows/build-core.ps1, apps/hub/packaging/windows/smoke-core.py, apps/hub/packaging/windows/README.md, .hqagent/handoffs/R17-P1-hub.md]
build: pass
tests: pass
commit: 4c37ae914ea6cafafedeee5aaa3beab5b983b8af
open_questions: 0
---

# R1.7-P1 Windows 桌面 Hub 与 onedir 打包

基线 `a9d972b`，主代理已合入最新 integration；本轮未再次合并其他分支。使用已安装的协议生成版本0.10.1、Python3.13.7、PyInstaller6.22.3。只改 Hub 和本回执，不改桌面壳/前端、server、协议或共享根文件，不修改真实用户数据。

## 进程约定

- `HQAGENT_INSTANCE_ID`：原样写入 descriptor，并传给应用实例，供壳校验本次启动身份。要求8–256字符；未设置仍生成随机 `hub_...`。
- `HQAGENT_RUNTIME_DIR`：绝对目录，替换 HubPaths.runtime；descriptor及 Update Agent 代理读取位置随之改变，数据根不变。保留原子写入和当前用户 ACL。
- 单实例锁仍按**数据根的 runtime/hub.lock**取得，不因更换 descriptor 目录而另开同一数据库。新增真实双进程测试证明第二实例退出2且不删除第一实例 descriptor。
- `HQAGENT_PARENT_CONTROL=stdio-v1`：专用 daemon 线程有界读取 stdin，以 shutdown 行或 EOF 触发优雅退出。不使用不可取消的默认线程池 readline，避免服务因其他原因退出时被 stdin 阻塞。无此变量不读 stdin；无三个变量时沿用原命令行/服务模式。
- stdin 在启动恢复中关闭时，不再开启新的本机调度或远程接单。未知控制协议、非法 runtime 路径、过短 instanceId 明确拒绝。
- 桌面模式必须 port=0，沿用 OS 随机高位端口，始终只绑定127.0.0.1；CLI/服务模式显式固定端口仍可用。
- 默认数据路径沿 R3.5：Windows `%LOCALAPPDATA%/HQAgent-Hub/`，显式 `--data-dir`/`HQAGENT_HUB_DATA_DIR` 仍保留。运行时不依赖安装目录作为 cwd 或数据目录。

收到关闭信号后立即设置 HTTP 写门禁、维护状态、本机调度门和 Worker 接单门，关闭远程连接；随后使用既有 lifespan 的服务停止顺序：停止验证任务/远程后台/本机调度，TaskService.shutdown 标记未确认在途任务为 paused + recoveryRequired、失效受中断 Session，关闭 SQLite 并执行既有 WAL checkpoint，删除本实例 descriptor、释放锁。没有改变取消 D41 证据、恢复或执行内核语义。

桌面 HTTP 排空等待为2秒，为后续服务停止预留壳15秒等待窗口；非桌面仍12秒。空载真实产物退出已实测，假 Adapter 在途恢复语义已集成测试；**没有使用真实模型验证所有 Adapter 在途停止的最坏耗时**，壳继续保留15秒强制终止兜底。

## Origin 与自动登录边界

读过 tauri.conf.json、壳 process_supervisor.rs、local-hub-gateway.ts / local-chat-gateway.ts。Hub 原有 DEFAULT_ALLOWED_ORIGINS 已精确包含 `http://tauri.localhost`、`https://tauri.localhost`（并保留既有 tauri://localhost/开发来源），因此没有追加任意 Origin 或放宽 Cookie 校验。

新测试验证两种 Tauri Origin 的 v1 Bearer 请求与 OPTIONS 成功、无 Bearer 为401、任意网页/伪后缀域/额外端口拒绝；Cookie 登录仍需可信 Origin、Cookie 写请求缺 Origin 仍拒绝、异源读请求拒绝。token不进入响应正文；原 HttpOnly Cookie 流程和30天持久化未改。

桌面 `LocalHubGateway` 已通过 IPC 取令牌并发送 Bearer，Hub 不需要新增免鉴权登录捷径。`LocalChatGateway` 当前仅使用 Cookie，不会自动带 IPC 令牌，桌面前端接入它时需由前端包处理，不越界修改。

## 打包

新增 `apps/hub/packaging/windows/`：

- core_entry.py：冻结入口调用 runtime.main，含 multiprocessing.freeze_support；原 --pick-directory 私有子进程入口仍先于 Hub 初始化。
- hqagent-core.spec：onedir、console=True、无 UPX；明确加入 protocol 生成模块、registry YAML、事件字典、Pillow 图片插件、segno、keyring 后端/metadata、uvicorn与WebSocket依赖、Tk目录选择资源。
- build-core.ps1：使用本 worktree `.venv`，校验 PyInstaller6.22.3；禁止 user site/PYTHONPATH，构建临时目录在 `.tmp`，不联网/不安装依赖。
- smoke-core.py：真实 Windows 可执行文件两次启动，默认数据目录隔离到临时 LOCALAPPDATA，只有系统 PATH，不发现用户 Agent；只做health、v1 Bearer/Origin及退出检查。通过 Toolhelp32 核对子进程，比较安装目录文件清单，结果不输出 descriptor/token。
- README.md：一条构建命令、目录布局、壳配合与故障含义。

构建来源限 Hub/协议源码及 `.venv` 依赖；基础 Python 的解释器DLL、标准库、Tcl/Tk是该虚拟环境运行时的必要组成。COLLECT清单核对全局 site-packages 项数为0。没有扫描/收集用户 home、会话文件、凭据、hub.json、hub.db。`dist/` 已验证被 Git 忽略，产物未提交。

首次构建暴露 event_mapper 运行时需要 protocol/events/event-dictionary.md，补入该精确资源后重新构建与冒烟通过，没有修改适配器或扩大为收集整个协议目录。

## 真实构建与产物冒烟输出

在 worktree 根执行：

```powershell
pwsh -NoProfile -File apps/hub/packaging/windows/build-core.ps1
.venv/Scripts/python.exe -B apps/hub/packaging/windows/smoke-core.py --exe dist/hqagent-core/hqagent-core.exe --work-dir .tmp/r17-smoke-release
```

```text
28543 INFO: Removing dir E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\dist\hqagent-core
28655 INFO: Building COLLECT COLLECT-00.toc
29327 INFO: Building COLLECT COLLECT-00.toc completed successfully.
29339 INFO: Build complete! The results are available in: E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\dist
Bundle: E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\dist\hqagent-core
Files: 1049; Bytes: 57357167; MiB: 54.7
```

exe SHA-256：`FA37155E246E3CE63A2654B833D8A9AF70EF04ED51E2591D41AEC11652BDDF39`。

产物 `dist/hqagent-core/`：1049个文件，**57,357,167字节 / 54.70 MiB**。冷启动数字为全新进程+全新数据目录至 /healthz 可用，**没有清空 Windows 文件系统缓存，不宣称是重启电脑后的磁盘冷缓存测试**。

```text
{"control": "shutdown", "health": "ok", "protocolVersion": "0.10.1", "coldStartSeconds": 2.676, "exitSeconds": 0.469, "exitCode": 0, "descriptorRemoved": true, "residualChildren": 0}
{"control": "eof", "health": "ok", "protocolVersion": "0.10.1", "coldStartSeconds": 1.438, "exitSeconds": 0.493, "exitCode": 0, "descriptorRemoved": true, "residualChildren": 0}
{"bundleFiles": 1049, "bundleBytes": 57357167, "bundleMiB": 54.7, "installationUnchanged": true}
```

冒烟使用实际 `.exe`，不借用源码或 venv 运行 Hub；protocolVersion=0.10.1，产物PID与descriptor/health一致。分别在shutdown/EOF后15秒内退出0、删除descriptor/锁、无残留子进程，安装目录文件大小与修改时间清单不变。

## 需要桌面壳/前端配合

1. 把整个 onedir 内容安装在桌面程序旁，布局为 `hqagent-desktop.exe`、`hqagent-core.exe`、`_internal/`；不要只放 exe。或通过现有 coreExecutable 配置指向独立 core 目录。
2. 每次启动传不同的 HQAGENT_INSTANCE_ID、用户可写绝对 HQAGENT_RUNTIME_DIR、HQAGENT_PARENT_CONTROL=stdio-v1；stdin必须持续持有管道。Update Agent使用相同runtime位置。
3. **Windows .spawn 前加 CREATE_NO_WINDOW（0x08000000）**。现有 process_supervisor.rs 没有该标志，本包保留 console bootloader 才能可靠读stdin；不加可能出现额外控制台。此项由W5改壳，本包不越界。
4. 常规无需参数；如重用试用数据，主代理先停止旧CLI Hub，再用 coreArgs `--data-dir E:/tmp/hqagent-n0-trial`，或按统一迁移方案复制数据。不能同时运行两个Hub争用同一数据根。本轮没有迁移真实用户数据。
5. 壳整体退出才写 shutdown 并flush/关闭stdin；窗口隐藏至托盘不要关闭管道。descriptor出现后仍以health/现有ready逻辑确认服务，IPC只给前端Hub baseUrl/token，不能给Update Agent凭据。
6. 使用桌面 Bearer 网关；Cookie专用的LocalChatGateway若作为桌面主界面，需前端补壳接入。不得把token放localStorage、URL或日志。
7. 退出码0为正常shutdown/EOF；2为配置无效或同数据根已运行；普通未处理故障通常1，Uvicorn启动失败可能3；OS强杀/崩溃保留系统状态。保留现有退避重启、15秒强杀兜底，勿把非零退出当作ready。

尚未做安装器、签名、Tauri窗口/托盘实机端到端；这些属于后续桌面集成。此包的打包和Hub进程约定已用真实产物验证。

## 测试

新增 tests/test_desktop_process.py：环境变量解析/缺省/非法输入，shutdown/EOF与有界控制输入，精确Origin/Cookie安全回归，假Adapter在途任务的恢复核对持久化，真实源码进程的两种退出及自定义descriptor，跨descriptor目录单实例防绕过，无环境变量时不读stdin，health前EOF退出。

定向命令（cwd apps/hub，TEMP/TMP位于worktree/.tmp）：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -x -p no:cacheprovider --basetemp ../../.tmp/desktop-final-focus tests/test_desktop_process.py --tb=short
```

真实结果：`11 passed, 1 warning in 9.08s`。未改既有断言。

Hub 全量命令（cwd apps/hub）：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -x -p no:cacheprovider --basetemp ../../.tmp/r17-hub --tb=short
```

真实输出：

```text
........................................................................ [  9%]
........................................................................ [ 19%]
........................................................................ [ 29%]
.................................................s................ssssss [ 39%]
ss...................................................................... [ 49%]
........................................................................ [ 58%]
........................................................................ [ 68%]
........................................................................ [ 78%]
........................................................................ [ 88%]
........................................................................ [ 98%]
远程送达预留清理暂未完成，将重试
远程送达预留清理暂未完成，将重试
..............                                                           [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_ws_close_codes_real_handshake.py::test_bad_ticket_closes_with_4401_not_a_handshake_rejection
tests/test_ws_close_codes_real_handshake.py::test_bad_origin_closes_with_4403_and_is_distinguishable_from_bad_ticket
tests/test_ws_close_codes_real_handshake.py::test_expired_cursor_closes_with_4410_and_sends_snapshot_url_first
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\websockets\exceptions.py:137: DeprecationWarning: ConnectionClosed.code is deprecated; use Protocol.close_code or ConnectionClosed.rcvd.code
    warnings.warn(  # deprecated in 13.1 - 2024-09-21

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
SKIPPED [1] tests\test_posix_credentials.py:166: POSIX mode bits
SKIPPED [1] tests\test_posix_path_guard.py:50: POSIX absolute redirect path
SKIPPED [1] tests\test_posix_path_guard.py:68: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:76: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:84: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:101: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:108: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:115: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:122: POSIX executable symlink and directory-fd semantics
725 passed, 9 skipped, 4 warnings in 355.26s (0:05:55)
```

Server 全量命令（cwd apps/server，在Hub全量结束后执行）：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -x -p no:cacheprovider --basetemp ../../.tmp/r17-server --tb=short
```

真实输出：

```text
........................................................................ [ 23%]
........................................................................ [ 47%]
........................................................................ [ 71%]
........................................................................ [ 94%]
................                                                         [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
304 passed, 1 warning in 104.14s (0:01:44)
```

Hub跳过的9项均为既有POSIX专属测试；warning为现有依赖弃用提示。没有发生429、额度错误或0xC0000142。`git diff --check`通过。


构建、冒烟、Hub和server串行，不跑vitest，不调用模型；TEMP/TMP/--basetemp均在worktree内忽略目录，避免默认TEMP权限问题。


## 提交

- `eabf33b9cc1d6835738274538f045732a407ed22`：桌面父进程约定、退出接单门与测试。
- `4c37ae914ea6cafafedeee5aaa3beab5b983b8af`：onedir规格、构建脚本、真实产物冒烟工具及接线README。
- 本回执另作文档提交。每次提交后执行 `git log -1 --format=%B` 自查，无署名/生成标记；未合并回integration，dist产物不提交。
