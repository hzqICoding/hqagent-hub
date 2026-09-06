# HQUpdateKit 0.1.0（未发布）

独立 Go module `hqupdatekit.local/updatekit`，公共 package `updatekit`，只使用 Go 标准库。
当前版本文件是 `VERSION`；产品通过 `require ... v0.1.0` 与本地 `replace` 消费。
此轮未发布 Tag，也没有迁移 HQDroidDeck，**仍存在同步责任，尚未消除两端分叉**。
正式发布仓库/module URL 和 Tag 由 Integrator 确认，本地命名空间不是公共 Go proxy 地址。

## 来源与抽取边界

只读来源：`E:\OtherPro\HQDroidDeck-Desktop`，commit
`65d88191d7090af736f6a884b3dfd24ef9941ae9`。

| 来源 | 共享模块中的处理 |
| --- | --- |
| `internal/update/model.go` | 保留 OTA 模型；扩展 Target、签名算法和 keyId |
| `internal/update/semver.go` | 提取比较逻辑，补严格版本格式校验 |
| `internal/update/downloader.go` | 提取 Range/进度/取消，补 Content-Range、长度、链接路径和 HTTPS 降级检查 |
| `internal/update/manifest_client.go` | 提取 OTA Client，增加精确 targetKey 查询、禁用代理与不安全重定向 |
| `internal/update/verifier.go` | 提取 SHA-256 digest 上的 Ed25519 验签；加入产品独立 trustedKeys 和强制 OS 验签 |
| `internal/update/service.go` | 保留 check/download/verify/recovery 流程；将四个宿主依赖替换为 `AppMeta`、`ConfigProvider`、`StateStore`、`EventSink`；重做互斥与持久化错误处理 |
| `internal/update/state_store.go` | 原子写入改为不先删除旧文件；Windows 仅写当前用户受保护 DACL |
| `internal/update/installer.go`、`cmd/updater/main.go` | 提取 Helper 复制与文件备份流程；升级为受控 Plan v2、完整 PID 等待、NSIS 策略、健康回滚 |

没有搬入宿主的 config、apperror、eventhub 或产品业务包。
原 `runInstaller` 的 Inno 参数及 portable ZIP 安装均未启用。
MSI、portable、macOS、Linux 仅可通过 `InstallerStrategy` 后续扩展；当前返回不支持。

## 模块边界

- `Service`：持久状态机、检查、下载、取消、恢复与安装前重复验签。
- `ManifestClient / Downloader / Verifier`：可由测试替换；生产必须同时验证内部签名与 Authenticode。
- `UpdatePlan / PlanPolicy`：模块自己的 v2 磁盘协议。严格 JSON 解码后执行 `ValidatePlan`；信任策略来自产品代码，不能从 Plan 加载。
- `Helper / InstallerStrategy / ProcessLauncher / HealthProbe`：等待、备份、安装、重启、健康检查、失败回滚。
- HQAgent 协议 DTO 和固定目录只存在于 `apps/update-agent/product`；共享模块不依赖 HQAgent 的协议包。

Plan v2 在 OTA 文档示例上增加 `processes`、`release` 和备份材料路径，以便 Helper 独立验证完整进程清单和签名。
目前 W0 未提供 Plan Schema；这是本模块明确版本化的磁盘契约，不能拿它代替未来的冻结协议。
安装范围固定 current-user，重启命令来自产品允许列表，禁止任意参数。
包名使用 SHA-256，不能由下载 URL 或版本字符串决定。

NSIS 使用 `/S`，`/D=<installDirectory>` 位于原始 Windows 命令行末尾且不额外加引号。
仅退出码 0 成功；1/2 和其他非零码失败；不把 MSI 的 3010 当成功。
不传 `/R`，避免安装器自行重启产品。NSIS bundle 必须由 W7 编译为 currentUser；Helper 参数不能改变 bundle 的提权 manifest。

回滚前必须停止所有已启动的产品进程。停止失败时记录 rollback_failed，不覆盖仍在使用的文件。
失败版本目录移至事务备份，恢复旧程序、配置和 W1 提供的数据库快照，移走新 WAL/SHM，再验证旧 Core 健康。
不会自动清理恢复材料。Helper 被强杀或系统断电后的自动事务续做尚未实现，保留材料供恢复。
安装器以 `CREATE_SUSPENDED` 创建，先加入私有 Windows Job Object 再恢复执行；不设置 `CREATE_BREAKAWAY_FROM_JOB`，Job 不允许普通或静默 breakaway。
必须同时观察到安装器退出和 `JobObjectBasicAccountingInformation.ActiveProcesses == 0`，才按安装器退出码继续处理；只退出父进程不能视为完成。
超过安装超时仍未收敛、或查询失败，返回 `ErrInstallerNotQuiescent`，保留备份并禁止恢复覆盖。退出 Runner 时终止整个 Job，最多再等待 5 秒验证清理；即使清理达到零，也不会把已超时的安装改成成功。
Job 设置 `KILL_ON_JOB_CLOSE` 且句柄不继承，避免 Helper 异常退出留下安装器后代。
第二轮已用真实 Windows 进程模拟器验证等待后代、超时保留备份和拒绝 breakaway；**这些不是实际 NSIS 验收**。真实安装包、证书及新 Core 健康期间的 Worker Gate 仍留待集成。

## 验证

在 HQAgent-Hub worktree 执行：

```powershell
go -C packages/updatekit test ./...
go -C apps/update-agent test ./...
go -C apps/updater test ./...
go -C apps/update-agent test ./product -run TestE2EFakeTauriProcessesNSISAndAutomaticRollback -count=1 -v
```

进程 E2E 使用可执行 Go 假 Tauri 包模拟 NSIS 参数和程序替换，真实运行独立 Helper、5 个待退进程和重启的 Core/Desktop/Update Agent。
内部 Ed25519 和文件校验真实执行；仅该测试二进制使用测试 OS 签名适配器。
测试回滚验证数据库快照字节恢复；SQLite Backup 的一致性由 W1 负责。
这些测试不能替代真实 NSIS、测试证书、非管理员安装和 W1 Hub 联调。

第二轮 race 验证使用仓库外的 LLVM-MinGW（MSVC 不能直接作为 Go cgo 编译器）：

```powershell
$env:CGO_ENABLED='1'
$env:CC='E:/tmp/hq-w6-toolchain/llvm-mingw-20260826-ucrt-x86_64/bin/clang.exe'
$env:PATH=(Split-Path $env:CC)+';'+$env:PATH
go -C packages/updatekit test -race ./... -count=1
go -C apps/update-agent test -race ./... -count=1
```

工具链来自 [LLVM-MinGW 20260826](https://github.com/mstorsjo/llvm-mingw/releases/tag/20260826)，未修改系统 PATH 或 Go 全局配置；临时目录清理后须重新准备该工具链。
`apps/update-agent/acceptance/` 的记录是对应提交的一次性验收快照，不是持续验证结果，应重新运行命令验证当前代码。

## 离线测试密钥

```powershell
go -C packages/updatekit run ./cmd/keygen --private E:/tmp/hqagent-release-keys/hqagent-test.pem
```

命令拒绝把私钥写到 Git checkout 内或覆盖已有密钥，只输出公钥。
每次随机生成独立 Ed25519 密钥，不使用 HQDroidDeck 的密钥。
私钥仅供本地离线发布测试，不能上传 OTA 服务器；生产使用受控离线密钥和生产证书。
临时测试私钥如果被清理，可重新运行 `cmd/keygen` 并更新示例配置的公钥；旧签名需用新密钥重新生成。自动测试自己生成临时密钥，不依赖这份人工测试私钥。

当前 OTA Platform `/updates/check` 的 `package` 不带 `targetKey/keyId/signatureAlgorithm`。
本模块保留字段并校验显式值；兼容现有服务时使用精确 Target 查询、OS/Arch/type 校验、产品专用 `defaultKeyId` 和固定 `ed25519-sha256`。
详见交接单中的服务端能力缺口。
