# Windows Hub onedir 产物

在仓库根执行（使用本 worktree 的 `.venv`，需已安装锁定运行依赖与 PyInstaller 6.22.3；脚本不联网、不安装依赖）：

```powershell
pwsh -NoProfile -File apps/hub/packaging/windows/build-core.ps1
.venv/Scripts/python.exe -B apps/hub/packaging/windows/smoke-core.py --exe dist/hqagent-core/hqagent-core.exe --work-dir .tmp/r17-smoke
```

输出 `dist/hqagent-core/hqagent-core.exe` 和同级 `_internal/`。必须分发整个目录，不能只复制 exe。安装器可将该目录的内容放在 `hqagent-desktop.exe` 旁；或保留独立目录，并在桌面配置 `coreExecutable` 指定路径。构建缓存、冒烟数据留在 `.tmp/`，`dist/` 不提交。

资源仅包含 Hub 源码、已安装的协议生成模块、protocol 的 registry YAML 与事件字典、虚拟环境中的运行依赖及其必要资源；Python DLL/标准库/Tcl/Tk 来自创建该虚拟环境的基础 Python。不会收集全局 site-packages、用户 home、真实会话、用户配置或凭据。构建禁用 user site/PYTHONPATH；spec 校验当前解释器属于本 worktree `.venv`。Pillow、segno、keyring、uvicorn WebSocket 实现及目录选择器的 Tk 数据随包提供。

## 桌面壳接线

- stdin 必须为可写管道，并在整个 Hub 生命周期保留父端。设置 `HQAGENT_PARENT_CONTROL=stdio-v1`。
- 每次启动传入不同的 `HQAGENT_INSTANCE_ID`（8–256字符），Hub 原样写入 descriptor；继续按 PID/instanceId/startedAt 排除旧文件。
- `HQAGENT_RUNTIME_DIR` 必须是用户可写的绝对目录，Hub 在其中原子写 `hub.json` 并保持当前用户 ACL。Update Agent 应使用相同 runtime 目录。
- 默认数据根 `%LOCALAPPDATA%/HQAgent-Hub/`，沿用 `--data-dir`/`HQAGENT_HUB_DATA_DIR` 显式覆盖。自定义 descriptor 目录不会改变数据根，也不会绕过每个数据根的单实例锁。
- 桌面不传固定端口（省略 --port 或给0），仅监听 `127.0.0.1` 随机高位端口。传固定非零端口会退出2。
- **本产物是 console=True，以保留 stdin 管道。Windows 壳启动时请加 CREATE_NO_WINDOW（0x08000000）**；当前 process_supervisor.rs 尚未设置，该改动由桌面包完成。本包不改壳代码。不要改用 windowed bootloader 后仍假设 sys.stdin 存在。
- 退出时写入并 flush `shutdown\n`；父管道 EOF 同样退出。其他输入忽略。不要在启动后立即 drop stdin，不要把 `Stdio::null()` 当作控制输入。
- 关闭主窗口只隐藏到托盘，不关闭控制管道。壳整体退出才发送 shutdown；保留现有15秒超时后的强制终止兜底。

Hub 收到退出信号后关闭 HTTP 写入口及本机/远程新任务调度门，关闭远程连接，并走既有 lifespan：停止后台任务、按 TaskService.shutdown 的恢复核对语义持久化未决任务/Session、WAL checkpoint、删除自身 descriptor、释放锁。不会将未确认的执行伪报成功。桌面 HTTP 请求排空窗口为2秒，为其后的既有执行清理预留时间；CLI/服务模式仍为12秒。真实 CLI 在途停止的最坏耗时仍需壳联调，不能用空载冒烟宣称所有 Adapter 都必然在15秒内确认停止。

退出码：0为正常控制退出（含EOF）；2为配置错误/已有同数据根实例；1为普通未处理启动或运行故障（Uvicorn startup failure 可能为3）；OS强杀/崩溃使用系统退出状态。不得将非零退出当作 ready。

## 登录与 Origin

现有 Hub 白名单已经精确支持 `http://tauri.localhost` / `https://tauri.localhost`，未扩大白名单或 Cookie 规则。桌面 `LocalHubGateway` 经 `get_hub_endpoint` 获得 baseUrl/token 并发送 Bearer；Token只留内存，不能放浏览器存储、URL或日志。

当前 `LocalChatGateway` 是独立 Cookie 网关，不会自动附加壳令牌。桌面前端若继续使用它，需由前端包显式接通壳授权路径；不能认为打包 Hub 就自动修好了该网关。浏览器依然使用一次性连接码与30天 Cookie。

`smoke-core.py` 使用隔离数据目录、清空可发现 Agent 的 PATH，只做健康、Bearer/Origin与进程生命周期测试，不读取真实原生会话，也不调用模型。检查 shutdown 与 EOF 两种退出、descriptor与锁清理、Windows子进程残留、安装目录文件清单不变，并打印耗时/字节数，不打印 token。
