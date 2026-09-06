# HQAgent Updater

与 Update Agent 分开的可执行程序。正常入口由 Agent 复制到受控 `updates/helper/` 后启动：

```powershell
go -C apps/updater test ./...
go -C apps/updater build -o E:/tmp/hqagent-updater.exe ./cmd/hqagent-updater
# 安装环境中由 Update Agent 调用，不手工给它任意 Plan：
# .../updates/helper/hqagent-updater.exe --plan .../updates/update-plan.json
```

入口只接受固定数据目录下的 `update-plan.json`，禁止从用户项目读 Plan 或包。
运行位置必须在 `updates/helper/`，不会占用正在替换的安装目录。
读取产品公共验签配置、受控备份及 Core 运行描述用于发现新端口；不读取项目代码或 Agent 凭据。
健康查询仅调用新 Core 的 `/healthz`，不携带 Hub Token。

Helper 二次核验 Plan、完整 waitPids、包大小/SHA-256/Ed25519/Authenticode；超时或进程访问失败不安装。
保留程序、配置、上一版安装器和数据库快照；新版本健康失败自动回滚并验证旧版本。
新 Agent 启动时等待 Updater 的内核锁释放，避免在健康检查期间争写升级状态。

W7 首次安装必须把上一版安装器保留到 `updates/installed/installer.exe`，并使用 `hqagent-desktop.exe`、`hqagent-core.exe`、`hqagent-update-agent.exe`、`hqagent-updater.exe` 的命名。
W1/W5 需完成健康检查期间的维护模式与全进程退出协作；缺口见交接单。尚未通过真实 NSIS 和测试代码签名证书的整包验收。
