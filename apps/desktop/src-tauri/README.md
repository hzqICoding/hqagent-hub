# HQAgent-Hub Windows 桌面安装版（R1.7-P2）

桌面 Vue 通过 `get_hub_endpoint` 获取 Hub baseUrl/token，以 Bearer 访问 v1/v2。
token 只在内存使用，不存到 localStorage/sessionStorage/IndexedDB；Update Agent endpoint/token 不传给 Vue。
浏览器访问本机 Hub 仍走连接码和 HttpOnly Cookie。

## 默认行为

- 当前用户 NSIS 安装到 `%LOCALAPPDATA%\Programs\HQAgent-Hub`，PREINSTALL hook 固定该路径，
  避免与数据目录混用。运行期不写安装目录。
- 首次运行默认注册 HKCU Run 的 HQAgent-Hub，启动参数为 --minimized；Windows 用户登录后
  在后台启动，不弹窗。顶部「开机自启」可关闭，选择持久保存。这不是登录前 Windows 服务。
- 关窗只隐藏；托盘含「打开 HQAgent-Hub」「退出」和 Hub「运行中 / 启动中 / 已停止」状态。
- 托盘退出发送 shutdown\n，关闭 stdin（EOF），等待最多 15 秒，最后才强制结束。
- Hub 崩溃按 1/2/4/8 秒退避重启，稳定运行 30 秒后重置退避。每轮请求重新读 endpoint，
  避免重启后使用旧端口/token；事件轮询自动恢复，v1 WS 每次重连重新换取 Ticket。
- 桌面启动/恢复显示等待页，不显示连接码；恢复前保留已经打开页面的草稿并阻止交互。
- 未登录、休眠、关机、断网期间手机不能控制；登录后 Hub/远程链路恢复。

## 资源、配置和数据

安装目录：

```text
hqagent-desktop.exe
core/hqagent-core.exe
core/_internal/...          # 必须是完整 PyInstaller onedir
web/index.html + assets/... # 保留普通浏览器入口
hqagent-update-agent.exe   # 本轮可选
```

tauri.conf.json 把仓库 dist/hqagent-core/ 整目录映射为 core/，前端 dist 映射为 web/。
Rust 使用 Tauri resource_dir() 解析，不依赖快捷方式工作目录。存在 web/index.html 时自动加
--web-dir <resource_dir>/web，用户已在 coreArgs 指定该参数则保留用户值。
浏览器可访问 http://127.0.0.1:<当前端口> 并输入连接码。

默认用户数据全部位于 `%LOCALAPPDATA%\HQAgent-Hub\`，包含 data、config、runtime、
logs、updates、diagnostics，WebView2 用户数据也显式放在该根的 webview/。
子进程工作目录固定为用户 runtime 目录，不写安装目录。
缺少 Update Agent 时 get_shell_status.childProcesses 返回 component=update-agent、
state=missing、path/message，界面显示「更新组件未安装」，不阻塞 Hub，不能据此声称 OTA 可用。

配置：`%LOCALAPPDATA%\HQAgent-Hub\config\desktop-shell.json`：

```json
{
  "coreExecutable": "C:\\absolute\\path\\hqagent-core.exe",
  "coreArgs": [],
  "updateAgentExecutable": "C:\\absolute\\path\\hqagent-update-agent.exe",
  "updateAgentArgs": [],
  "autostart": true
}
```

所有字段可省略，通常只设置 coreArgs/autostart。路径覆盖优先级：
HQAGENT_CORE_PATH / HQAGENT_UPDATE_AGENT_PATH 环境变量 > 配置 > 资源默认位置；
覆盖路径必须是绝对路径。改变配置后从托盘退出，再启动。

受管子进程接收 HQAGENT_INSTANCE_ID、HQAGENT_RUNTIME_DIR、HQAGENT_PARENT_CONTROL=stdio-v1。
runtime 始终为默认数据根下 runtime，即使 coreArgs 指向旧数据目录也不变。
P1 必须支持这些环境变量及 stdin shutdown/EOF。壳校验 descriptor 的当前用户私有 ACL、
PID/进程路径/instanceId/启动时间、healthz/v1 bootstrap，不接受陈旧 descriptor。

CSP 仅允许自身、IPC、http/ws://127.0.0.1:*；开发态另加固定 Vite localhost:5173。
capability 仅 main 的 core:default，无远程 URL 的 IPC 权限。HTTP 使用 WebView fetch，
受 CSP/Hub CORS 控制，不需要 HTTP 插件权限。图片允许 blob: 供已鉴权附件预览。

实际聊天页面使用 /api/v2/**，其中 auth/status、聊天、手机绑定、原生会话、附件已支持
Hub Bearer，需与 P1 一起验证 Tauri Origin 的 CORS。图像验证/对话删除在协议中另有
/api/v1 的 Bearer 入口，桌面调用这组已有接口；浏览器继续使用 /api/v2 Cookie-only 维护入口。
不要求放宽 Hub 的 maintenance_cookie。普通浏览器仍须连接码，不能返回 Hub token。

卸载移除安装文件及本应用自启注册项，**不删除用户数据根或用户指定的旧目录**。
重装可继续使用原数据。彻底清理须用户另行备份后手动处理；本轮没有自动搬迁/删除数据。

## 用户迁移：方案 ① 沿用现有目录（推荐）

当前试用数据在 E:/tmp/hqagent-n0-trial，已配对设备凭据、对话、附件、验证记录均在其中。
桌面默认根不同，不指定旧目录会看到另一套空数据，不代表旧数据丢失。

1. 等待任务完成，停止命令行 Hub；退出桌面托盘。不要让两个进程同时访问同一数据库。
2. 备份旧根，继续使用原 Windows 用户（设备凭据由该用户 DPAPI 保护，不要跨账户直接复制）。
3. 桌面首次启动前创建/编辑上述 desktop-shell.json，合并保留其他已有配置：

```json
{
  "coreArgs": ["--data-dir", "E:/tmp/hqagent-n0-trial"],
  "autostart": true
}
```

也可设置用户环境变量 HQAGENT_HUB_DATA_DIR=E:/tmp/hqagent-n0-trial 后重新登录 Windows。
CLI --data-dir 优先于该环境变量；临时终端 $env: 设置不会自动传给下次登录的自启进程。

4. 打开桌面，确认旧对话、附件、验证记录及设备仍在；关闭窗口后从手机继续控制。
   同账户沿用完整旧根无需重新配对。壳配置/runtime 仍在默认 LOCALAPPDATA 根；
   旧数据根属于用户主动选择的兼容例外，安装目录仍只读。
5. 浏览器如需新连接码，使用 P1 本机连接码工具并明确指向同一数据根；不打印/分享 hub.json token。

## 用户迁移：方案 ② 复制到默认数据根

1. 停止旧 Hub 和桌面托盘，确认没有进程写数据库。备份整个旧根，不仅是 hub.db。
   在同机、同 Windows 用户下迁移，复制加密设备文件到其他账户不等于可解密。
2. 备份现有 LOCALAPPDATA/HQAgent-Hub。目标若已有独立数据，先选定完整的一套，
   不直接混合两套数据库。保留旧根，不自动搬走数据。
3. 目标已备份且可接收旧数据时，手动复制整个旧根，排除临时 runtime/锁/token 和桌面壳配置：

```powershell
$oldData = 'E:\tmp\hqagent-n0-trial'
$newData = Join-Path $env:LOCALAPPDATA 'HQAgent-Hub'
robocopy $oldData $newData /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XD (Join-Path $oldData 'runtime') /XF desktop-shell.json window-state.json
if ($LASTEXITCODE -ge 8) { throw '复制失败，请保留源目录并检查输出' }
```

不使用 /MIR；不删除源或目标额外文件。data/config/附件/验证记录目录和设备凭据必须完整保留。
若 SQLite 仍有 WAL/SHM，连同数据库复制，前提是所有写入进程已停止。
数据库或配置中的绝对附件/工作树路径不会因复制改写；保留原项目路径和旧根，
先验收预览/下载/会话恢复。遇绝对路径依赖优先回方案 ①，不直接编辑数据库。

4. 移除新 desktop-shell.json 中旧 --data-dir；清除用户级 HQAGENT_HUB_DATA_DIR 或改为新根。
   重新登录并启动桌面。
5. 核对设备配对、对话、附件预览/下载、验证记录、手机新建/继续对话；重启电脑再验一次。
   验收前保留旧根与备份。回退先退出桌面，再恢复方案 ①，不能同时开两套 Hub。

## 一键打包（集成主代理执行）

前置：合入 P1、本包；.venv 已按 P1 安装固定 PyInstaller 依赖；pnpm install/cargo fetch
已完成，Windows MSVC/WebView2 工具链可用。脚本不安装新依赖。

```powershell
# 仓库根目录，一条命令
pwsh -NoProfile -File apps/desktop/scripts/build-windows.ps1
# 如已有 Update Agent：
pwsh -NoProfile -File apps/desktop/scripts/build-windows.ps1 -UpdateAgentPath E:/build/hqagent-update-agent.exe
```

顺序：P1 apps/hub/packaging/windows/build-core.ps1 → 前端 pnpm build → tauri build --bundles nsis -- --offline。
Rust 单任务构建，脚本检查 exe 和 _internal 后才打包。NSIS/WebView2 打包工具首次可能下载，
由可联网主代理执行。打印安装包路径及 SHA-256；默认在 apps/desktop/src-tauri/target/release/bundle/nsis/。
不提供 Update Agent 则不分发该组件。本轮没有代码签名及真实安装验收。

## 离线验证

先生成前端 dist，Tauri 宏会读取它。未生成 P1 onedir 时可临时用 TAURI_CONFIG 清空 bundle resources，
**仅用于 Rust 检查/测试**；不制造假的 exe，不代表安装资源已验收。打包脚本拒绝残留 TAURI_CONFIG。

```powershell
pnpm --dir apps/desktop lint
pnpm --dir apps/desktop typecheck
pnpm --dir apps/desktop exec vitest run --minWorkers=1 --maxWorkers=2
pnpm --dir apps/desktop build
$env:CARGO_BUILD_JOBS = '1'
$env:TAURI_CONFIG = '{"bundle":{"resources":null}}' # 仅缺少 P1 产物时
cargo check --offline --manifest-path apps/desktop/src-tauri/Cargo.toml
cargo test --offline --manifest-path apps/desktop/src-tauri/Cargo.toml -- --test-threads=1
Remove-Item Env:TAURI_CONFIG -ErrorAction SilentlyContinue
```

Rust 测试用自身测试二进制充当真实子进程，覆盖 shutdown→EOF、15 秒生产超时配置、超时强制结束、
退避重启和缺少 Update Agent；不再依赖固定 Python 路径。
安全 stub 仍可用：pwsh -File apps/desktop/src-tauri/acceptance/run-security-acceptance.ps1。
真实安装/自启/托盘/手机联调按 .hqagent/handoffs/R17-P2-shell.md 由主代理完成。
