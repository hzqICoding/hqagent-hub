# Linux / macOS 用户服务安装

Python 3.13、Git 和已登录的 Agent CLI 必须属于运行 Hub 的同一个普通用户。服务只监听 127.0.0.1；不要把本机端口暴露公网。默认数据根：Linux `$XDG_DATA_HOME/hqagent-hub`（未设置时 `~/.local/share/hqagent-hub`）；macOS `~/Library/Application Support/HQAgent-Hub`。也可用 `HQAGENT_HUB_DATA_DIR`，CLI 必须使用同一值或 `--data-dir`。

示例把仓库检出放在数据根的 `app`、虚拟环境放在 `venv`。安装命令在仓库根执行；CI/Linux 传递依赖锁的交付状态以 R35-P2 回执为准。

```sh
python3.13 -m venv "$HUB_ROOT/venv"
"$HUB_ROOT/venv/bin/python" -m pip install -r apps/hub/requirements.local-lock.txt pyyaml hatchling -e packages/protocol -e apps/hub
```

Linux 设置 `HUB_ROOT="$HOME/.local/share/hqagent-hub"`；macOS 设置 `HUB_ROOT="$HOME/Library/Application Support/HQAgent-Hub"`。调整模板中安装位置和 PATH，使服务能找到用户安装的 CLI；不要把 Agent 凭据写入 unit/plist。非 Git workspace 只读，添加项目不会执行 git init。

## systemd user

将 `hqagent-hub.service` 安装到 `~/.config/systemd/user/`。自定义 XDG 数据根时同时修改模板的安装路径。

```sh
mkdir -p ~/.config/systemd/user
cp apps/hub/packaging/hqagent-hub.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hqagent-hub
journalctl --user -u hqagent-hub -f
```

需要退出登录后仍运行或开机启动时，由管理员按机器策略执行 `loginctl enable-linger <用户名>`。无桌面 Linux 缺少会话 D-Bus / Secret Service 时回退 0600 文件；日志只出现 `Device credential storage mode=file-0600`。不要复制 descriptor 到共享目录，它包含本机令牌。

## launchd LaunchAgent

将 plist 中所有 `/Users/REPLACE_ME` 替换为当前用户真实 HOME，绝对路径不支持 `~` 或环境变量展开。先创建 `$HUB_ROOT/logs`，权限 0700。安装到 `~/Library/LaunchAgents/local.hqagent.hub.plist`。

```sh
plutil -lint ~/Library/LaunchAgents/local.hqagent.hub.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/local.hqagent.hub.plist
launchctl kickstart "gui/$(id -u)/local.hqagent.hub"
```

LaunchAgent 在该用户登录后运行；不是登录前的系统 daemon。使用用户 Keychain，锁定或拒绝访问时日志/状态会如实显示凭据不可用；已有 Keychain 凭据不会悄悄降级或重置。日志在 `logs/service.*.log`；生产运维应配置轮转并限制文件权限。

## 命令行

以下命令在仓库 `apps/hub` 目录或已安装虚拟环境内执行：

```sh
python -m runtime.cli remote status
python -m runtime.cli remote pair --server https://your-server.example --device-name workstation
python -m runtime.cli workspace add /absolute/project
python -m runtime.cli workspace list
python -m runtime.cli agents discover
python -m runtime.cli roots list
python -m runtime.cli roots add /absolute/projects
python -m runtime.cli roots remove <rootId>
python -m runtime.cli remote unlink
```

配对只在交互终端显示 segno 二维码、短码、有效期，等待手机确认；SSH 使用 `ssh -t`。不要重定向配对输出到文件或日志，CLI 会拒绝非终端配对。Ctrl-C 取消本次尚未完成的配对。超时/取消不创建新执行。其它命令通过 descriptor 的本机 Bearer API，不能代替云端账号撤销；unlink 若服务端撤销未确认会保留真实错误状态。根目录添加/删除使用 GET 当前版本后 PUT 的 CAS，冲突时刷新后重试。

服务启动的浏览器连接短码只在 TTY 显示，不进入 journal 或 launchd 重定向日志。如需本机浏览器工作台，交互执行既有 `python -m runtime.pair`；仍不要重定向短码。

## 升级与卸载

升级前先停止服务，备份整个数据根（含 SQLite/WAL、remote 状态及授权配置）；备份须私有。Keychain/Secret Service 中的设备密钥不在目录备份内，迁移到另一用户/机器应重新配对。安装新代码和锁定依赖后启动；不要让两个版本并发使用同一数据库。数据库迁移不可仅靠回退程序降级，回退需要一致的升级前数据备份。

Linux 停止/卸载：`systemctl --user disable --now hqagent-hub`，删除用户 unit 后 `daemon-reload`。macOS：`launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/local.hqagent.hub.plist`，再删除 plist。若还可运行 Hub，先执行 `remote unlink` 以删除钥匙串设备项；然后停止服务。保留数据目录供恢复，用户确认后才手动删除。不要用卸载脚本递归删除任意计算路径。

本地 Windows 测试无法证明 Secret Service、Keychain、systemd、launchd 的真机行为；本轮由主代理推送后以三平台 CI 和回执中的 POSIX 用例验证，交互钥匙串/登录启动仍需后续真机核对。
