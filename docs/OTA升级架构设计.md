# HQAgent-Hub OTA 升级架构设计

## 变更记录

| 日期 | 版本 | 变更说明 |
| --- | --- | --- |
| 2026-09-05 | v0.2 | 统一一期 OTA 口径：由 Local Hub 暴露唯一公共接口，采用当前用户级 NSIS 安装、完整进程排空、SQLite 一致性备份和自动健康回滚；新增双方产品共同依赖的版本化 `HQUpdateKit` |
| 2026-09-05 | v0.1 | 审查 HQDroidDeck-Desktop 与 OTA-Platform，确定 HQAgent-Hub 的复用范围、客户端升级架构、跨平台目标、回滚和实施优先级 |

## 1. 设计结论

HQAgent-Hub 不重新建设一套 OTA 后台，也不单独依赖 Tauri 自带更新协议。推荐方案是：

1. 直接复用现有 `E:\OtherPro\OTA-Platform` 作为升级服务和发布管理后台。
2. 在 OTA Platform 中新增产品 `hqagent-hub`，按操作系统、CPU 架构和安装形态建立 Target。
3. 新建独立、版本化的 Go 模块 `E:\OtherPro\HQUpdateKit`，从 `E:\OtherPro\HQDroidDeck-Desktop\internal\update` 与 `cmd\updater` 提取通用更新状态机、下载、验签、Plan 和 Updater Helper；HQDroidDeck-Desktop 与 HQAgent-Hub 都必须改为依赖该模块，才算真正消除代码分叉。
4. HQAgent-Hub 在共享模块之上保留产品级薄封装 `HQAgentUpdateAgent` 和 `HQAgentUpdater`，使桌面壳、Local Hub 和全部 Agent Worker 退出后仍能完成安装。
5. P0 采用 Windows 当前用户级 Tauri NSIS 完整安装包升级，程序目录与数据目录分离，确保桌面壳、Local Hub、协议和内置 Adapter 版本一致，且不要求管理员权限。
6. P0 必须完成新版本健康检查和本机自动回滚；P1 再支持 Adapter/插件独立更新、百分比灰度和多签名密钥轮换。

升级系统必须是独立基础设施。HQAgent Cloud Control Plane 故障时，客户端仍应能从 OTA Platform 检查和下载安全更新；OTA Platform 故障也不能影响本地 Agent 正常工作。

## 2. 现有项目审查结果

### 2.1 HQDroidDeck-Desktop 已有能力

现有客户端升级模块已经实现：

- 完整状态机：`idle → checking → available → downloading → verifying → ready_to_install → installing/restarting`。
- stable/beta 渠道、SemVer、`mandatory` 和 `minimumSupportedVersion`。
- HTTP Range 续传、进度、速度、剩余时间和取消。
- 文件大小、SHA-256 和 Ed25519 签名校验。
- 安装前再次验签，防止“稍后安装”期间升级包被替换。
- 升级状态持久化、已下载包跨重启恢复和过期 Staging 清理。
- 独立 Updater Helper，等待主进程退出后安装或替换文件。
- Portable 更新前备份、ZIP 路径穿越防护和临时文件原子替换。
- 升级结果文件、首次启动结果提示和确认回执。
- 运行任务协调接口，安装前可以检查并停止活动任务。
- 本地 API、事件流、前端全局弹窗和 E2E 测试脚本。

主要参考位置：

```text
E:\OtherPro\HQDroidDeck-Desktop\internal\update\
E:\OtherPro\HQDroidDeck-Desktop\cmd\updater\
E:\OtherPro\HQDroidDeck-Desktop\frontend\src\features\updates\
E:\OtherPro\HQDroidDeck-Desktop\scripts\test-update-e2e.ps1
E:\OtherPro\HQDroidDeck-Desktop\docs\在线升级设计.md
E:\OtherPro\HQDroidDeck-Desktop\docs\在线升级前端交互规范.md
```

### 2.2 OTA-Platform 已有能力

现有 OTA Platform 使用通用模型：

```text
Product/Application
    ↓
Target
    ↓
Release
    ↓
Artifact
    ↓
Channel Assignment
```

已经具备：

- 多产品、多 Target、多 Artifact。
- EXE、APK、IMG、ZIP、BIN 等动态制品类型和扩展名约束。
- 按 `appId + targetKey + channel` 独立维护当前版本指针。
- 草稿、上传、验证、发布、撤回和渠道回滚。
- beta 候选使用同一制品原子晋升 stable。
- 已发布制品不可覆盖。
- 服务端重新计算 SHA-256 并验证 Ed25519 签名。
- RBAC、Session、CSRF、幂等键、revision 并发控制和审计日志。
- 版本化不可变下载地址、ETag、Range 下载和公开 Catalog。
- SQLite 数据库、文件存储、Nginx 部署和生产运维资料。

主要参考位置：

```text
E:\OtherPro\OTA-Platform\backend\
E:\OtherPro\OTA-Platform\frontend\
E:\OtherPro\OTA-Platform\backend\api\openapi.yaml
E:\OtherPro\OTA-Platform\docs\通用固件升级管理系统架构设计.md
E:\OtherPro\OTA-Platform\docs\在线升级管理平台API协议.md
```

### 2.3 本次验证

已执行并通过：

```text
HQDroidDeck-Desktop:
go test ./internal/update ./cmd/updater ./internal/api

OTA-Platform/backend:
go test ./...
```

因此本方案的复用判断基于当前可运行代码，而不是只参考文档。

## 3. 复用矩阵

| 资源 | 复用方式 | 说明 |
| --- | --- | --- |
| OTA Platform 后端 | 直接复用 | 新增 `hqagent-hub` 产品和 Targets，不复制另一套后台 |
| OTA 管理前端 | 直接复用 | 继续管理 Release、Artifact、渠道、晋升、撤回和回滚 |
| 公开升级 API/OpenAPI | 直接复用 | HQAgent Update Agent 使用现有 `/api/v1/updates/check`、`releases` 和包下载协议 |
| `signctl` 与离线签名流程 | 直接复用并扩展 | 使用 HQAgent 独立密钥；后续增加 `keyId` 和轮换 |
| Go 状态机/下载/验签/状态持久化 | 共享模块复用 | 提取到独立版本化模块 `HQUpdateKit`，HQDroidDeck-Desktop 与 HQAgent-Hub 同时依赖 |
| Go 独立 Updater Helper | 共享模块复用 | 在 `HQUpdateKit` 中扩展 Update Plan 和安装策略，由两个产品提供薄封装 |
| 前端升级状态与交互规范 | 设计复用 | React 代码不能直接放进 Vue，但状态机、文案、弹窗规则和测试用例可迁移 |
| PowerShell 发布脚本 | 模板复用 | 替换 Wails/Inno 构建命令、产品名、appId、Target 和路径 |
| OTA E2E 脚本 | 模板复用 | 增加 Tauri、Local Hub、多进程退出、数据库迁移和健康检查验证 |
| Wails 绑定和 ADB 业务代码 | 不复用 | 与 HQAgent-Hub 技术栈和业务无关 |

禁止直接复制 `internal/update` 后分别维护两份，也不能只让 HQAgent-Hub 使用抽取模块而让 HQDroidDeck-Desktop 继续保留原实现。必须先抽象产品元数据、目录、TaskCoordinator、InstallerStrategy 和事件输出到 `HQUpdateKit`，再让两个产品都通过明确版本依赖使用它。

## 4. 目标架构

```text
                     ┌─────────────────────────────┐
                     │ Existing OTA Platform       │
                     │ Product/Target/Release      │
                     │ Artifact/Channel/Audit      │
                     └──────────────┬──────────────┘
                                    │ HTTPS
                                    ▼
┌──────────────────────────────────────────────────────────────┐
│ 用户电脑                                                     │
│                                                              │
│ Tauri Desktop + Vue                                          │
│   └─ Update UI / 用户确认                                    │
│                  │ Local Hub 公共 HTTP Bearer / WS Ticket    │
│                  ▼                                           │
│ HQAgent Local Hub                                             │
│   ├─ Task Drain Controller                                   │
│   ├─ Session Checkpoint                                      │
│   ├─ Update Public API / Event Proxy                         │
│   └─ Update Coordinator                                      │
│                  │ Update Agent 私有本地 API                 │
│                  ▼                                           │
│ HQAgentUpdateAgent（Go）                                      │
│   ├─ Check / Download / Resume                               │
│   ├─ SHA-256 / Ed25519 Verify                                │
│   ├─ State / Result Store                                    │
│   └─ Prepare Update Plan                                     │
│                  │ 启动独立 Helper                           │
│                  ▼                                           │
│ HQAgentUpdater（Go）                                          │
│   ├─ 等待 Desktop/Core/UpdateAgent/Workers 退出              │
│   ├─ 备份和安装                                              │
│   ├─ 启动新版本                                              │
│   ├─ 健康检查                                                │
│   └─ 失败回滚                                                │
└──────────────────────────────────────────────────────────────┘
```

### 4.1 单一事实源

- OTA Platform 是远端版本、渠道和制品事实源。
- HQAgentUpdateAgent 是本机升级状态事实源。
- Local Hub 是桌面 UI 唯一可访问的本地公共 API 和事件入口，负责代理 Update Agent 命令，并为更新事件分配统一 `seq`。
- HQAgentUpdateAgent 只监听私有本地端点，不向 Vue 暴露第二个 Base URL。
- Vue/Tauri 只通过 Local Hub 展示状态和触发命令，不能自行推断升级完成；HTTP 使用 Bearer Token，WebSocket 先换取一次性短效 Ticket。
- HQAgent Cloud 只同步升级提示、审批和结果，不代替 OTA Platform 返回 Manifest。
- Tauri 自带 updater 不单独维护第二套版本状态；如后续使用，只能作为 `InstallerStrategy` 的内部实现。

### 4.2 进程边界

```text
hqagent-desktop.exe       Tauri 桌面壳和托盘
hqagent-core.exe          Local Hub
hqagent-update-agent.exe  更新状态、下载和验签
hqagent-updater.exe       主程序退出后执行替换/安装
agent worker processes    Claude/Codex/Gemini 等进程
```

更新时桌面窗口关闭不代表升级状态丢失。下载和校验由 Update Agent 持有；实际安装由独立 Updater 完成。

## 5. 产品、Target 与制品设计

### 5.1 主产品

```yaml
appId: hqagent-hub
name: HQAgent-Hub
```

建议预建 Targets：

| targetKey | 平台 | 制品建议 | 优先级 |
| --- | --- | --- | --- |
| `windows-amd64-installer` | Windows x64 | Tauri NSIS/安装 EXE | P0 |
| `windows-arm64-installer` | Windows ARM64 | 安装 EXE | 预留 |
| `macos-aarch64-app` | Apple Silicon | 签名并公证的应用归档 | P1 |
| `macos-x86_64-app` | Intel Mac | 签名并公证的应用归档 | P1 |
| `linux-amd64-appimage` | Linux x64 | AppImage | P2 |
| `linux-amd64-deb` | Debian/Ubuntu x64 | DEB | P2 |

同一 HQAgent-Hub Release 可以包含多个系统 Artifact，渠道指针按 Target 独立生效。

### 5.2 整包升级优先

P0 一个 Artifact 应同时包含兼容的一组组件：

```text
Tauri Desktop
Local Hub Core
Update Agent
Updater Helper
内置 Adapter
协议 Schema
数据库迁移
```

桌面壳和 Local Hub 不能在 P0 独立升级，否则容易出现 UI/API、Session Schema 和 Adapter Protocol 不兼容。

### 5.3 独立插件升级预留

社区 Adapter 和大型可选组件后续可以独立发布。建议每个独立生命周期的插件使用单独 OTA Application：

```text
hqagent-adapter-claude
hqagent-adapter-codex
hqagent-adapter-gemini
hqagent-adapter-deepseek
```

插件 Manifest 预留：

```json
{
  "pluginId": "codex",
  "version": "1.2.0",
  "adapterApiVersion": 1,
  "minimumHubVersion": "0.3.0",
  "maximumHubVersion": "0.x",
  "targetKey": "windows-amd64-zip"
}
```

官方内置 Adapter 在早期随主程序整包更新；插件独立更新进入 P1/P2，避免 MVP 同时解决两套依赖管理问题。

## 6. 客户端更新状态机

沿用现有状态并增加维护和回滚状态：

```text
idle
  ↓
checking
  ├─ up_to_date
  ├─ available
  └─ failed

available
  ↓
downloading
  ├─ downloaded
  ├─ cancelled
  └─ failed

downloaded
  ↓
verifying
  ├─ ready_to_install
  └─ failed

ready_to_install
  ↓
draining_tasks
  ├─ waiting_user
  ├─ installing
  └─ cancelled

installing
  ↓
health_checking
  ├─ succeeded
  └─ rolling_back

rolling_back
  ├─ rollback_succeeded
  └─ rollback_failed
```

所有状态必须持久化，桌面进程、Local Hub 或 Update Agent 重启后能够恢复或进入明确的失败状态。

## 7. 运行任务排空与维护模式

HQAgent-Hub 与普通桌面工具不同，升级时可能存在持续数小时的 Agent 任务。安装前必须执行：

```text
停止接收新任务
→ 标记设备进入 maintenance_pending
→ 请求所有 Agent 写入 checkpoint/handoff
→ 等待当前文件写入和 Git 操作完成
→ 保存 Session Registry、任务状态和事件偏移量
→ 关闭 Worker 与云端 WSS
→ flush SQLite WAL
→ 备份配置和数据库
→ 启动独立 Updater
```

更新策略：

- 普通更新允许“稍后提醒”“后台下载”“任务完成后安装”。
- 强制安全更新先禁止创建新任务，不应直接杀死正在写代码或迁移数据的 Agent。
- Phase 1 超过等待时间后，由用户在桌面端选择继续等待、取消任务后更新或退出应用；Phase 2 可增加同等语义的手机审批。
- Update Coordinator 必须知道活动任务、危险操作、Git 合并和数据库迁移状态。
- Phase 1 更新安装期间桌面端显示 `maintenance` 并拒绝新任务；Phase 2 接入云端后，再同步维护状态并暂停远程下发但保留离线队列。

## 8. Update Plan v2

现有 `UpdatePlan` 需要扩展为多进程、跨平台和健康检查版本：

```json
{
  "schemaVersion": 2,
  "appId": "hqagent-hub",
  "currentVersion": "0.1.0",
  "targetVersion": "0.2.0",
  "targetKey": "windows-amd64-installer",
  "packagePath": "...\\updates\\staging\\HQAgent-Hub-0.2.0-Setup.exe",
  "installStrategy": "windows-nsis",
  "installScope": "current-user",
  "installDirectory": "%LOCALAPPDATA%\\Programs\\HQAgent-Hub",
  "dataDirectory": "%LOCALAPPDATA%\\HQAgent-Hub\\data",
  "waitPids": [1200, 1201, 1202, 1203],
  "backup": {
    "database": true,
    "config": true,
    "programFiles": true
  },
  "restart": [
    { "component": "core", "command": "hqagent-core.exe" },
    { "component": "desktop", "command": "HQAgent-Hub.exe", "args": ["--updated-from", "0.1.0"] }
  ],
  "healthChecks": [
    { "type": "process", "component": "core", "timeoutSeconds": 30 },
    { "type": "http", "url": "http://127.0.0.1:<port>/healthz", "timeoutSeconds": 30 },
    { "type": "protocol", "expectedVersion": 1 }
  ],
  "rollbackOnFailure": true
}
```

`waitPids` 必须覆盖 Desktop、Local Hub、Update Agent 和本次任务产生的所有 Agent Worker；Plan 文件只允许 Updater 从受控目录读取，并验证 Schema、安装范围、目标路径、包路径和允许的可执行文件，防止路径注入。

## 9. 安装策略

通过接口隔离平台差异：

```text
InstallerStrategy
├── windows-nsis
├── windows-msi
├── windows-portable
├── macos-app-bundle
├── linux-appimage
└── linux-deb
```

现有 HQDroidDeck `runInstaller` 使用 Inno Setup 参数，不能原样用于 Tauri NSIS/MSI。可复用 Updater 主流程，但必须为不同安装器实现独立参数、退出码和回滚策略。

P0 固定采用 `windows-nsis + current-user`：安装目录为 `%LOCALAPPDATA%\Programs\HQAgent-Hub`，数据目录为 `%LOCALAPPDATA%\HQAgent-Hub`，默认无 UAC；Updater 调用经过 Authenticode 与 Ed25519 双重校验的完整安装器，保留上一版本安装器/程序备份和数据库快照，健康检查失败时自动恢复。系统级安装、MSI 与 Portable 仅保留策略接口，不进入一期验收。

macOS 的应用包替换、权限、签名和公证与 Windows 不同，必须在 macOS 构建和真实机器上完成 E2E，不能只靠 Windows 上的 Portable ZIP 测试推断成功。

## 10. 安全与密钥

### 10.1 双重信任

正式发布的升级包至少通过：

1. OTA 内部 Ed25519 签名，保护制品在发布和下载链路中的真实性。
2. 操作系统代码签名：Windows Authenticode；macOS Developer ID 签名与公证。

SHA-256 只能证明文件与 Manifest 一致，不能单独证明 Manifest 可信。

### 10.2 产品独立密钥

HQAgent-Hub 不应长期与其他产品共享同一私钥。建议：

- 为 `hqagent-hub` 生成独立 Ed25519 密钥对。
- 私钥只存在于离线发布电脑或后续硬件密钥/HSM，不上传 OTA 服务器。
- 客户端只内置公钥。
- Manifest 预留 `signatureAlgorithm` 和 `keyId`。
- 客户端预留 `trustedKeys[]`，支持新旧公钥并存的轮换窗口。
- 服务端后续将单一全局 `updatePublicKey` 扩展为产品/密钥注册表。

P0 可以使用 HQAgent 独立测试 Ed25519 密钥和测试代码签名证书验证完整流水线；beta/stable 商业发布必须使用受信任的 HQAgent 独立生产证书。多公钥轮换可在 P1 完成，但私钥始终不得进入仓库或 OTA 服务器。

### 10.3 权限与路径

- Updater 不读取项目代码和 Agent 凭据。
- 升级目录、数据目录和备份目录必须分别校验。
- 禁止从普通任务参数传入任意安装命令。
- 只有已经通过签名验证且位于 Staging 的包才能生成 Update Plan。
- 签名失败没有“忽略并继续”入口。

## 11. 数据迁移与回滚

### 11.1 数据库

- 安装前停止新写入，执行 WAL checkpoint，并使用 SQLite Backup API 生成一致性 `hub.db` 快照；同时备份配置和关键 Session Registry。
- SQLite 使用显式 `schema_version`。
- 数据库迁移优先采用向前兼容的新增表/新增列。
- 不可逆迁移必须在 Release 元数据中声明 `rollbackCompatible=false`，并要求额外确认。
- 新版本健康检查通过后才清理旧备份。
- 一期不要求每个 migration 都提供通用 `Down`；回滚依靠程序备份、安装器备份和升级前数据库快照，失败期间设备保持维护状态。

### 11.2 回滚层级

| 层级 | 作用 |
| --- | --- |
| OTA 渠道回滚 | 让尚未升级的客户端停止获取问题版本 |
| 本机自动回滚 | 新版本启动或协议健康检查失败时恢复上一版本 |
| 更高版本修复 | 已完成不可逆迁移或已经大规模安装时发布补丁版本 |

现有 OTA Platform 的渠道回滚不会主动降级已经升级的客户端，因此 HQAgent-Hub 必须增加本机健康检查回滚；同时默认禁止服务器下发低于当前版本的降级包。

## 12. 渠道、灰度与强制更新

### 12.1 P0

- `beta`：自用和内测设备。
- `stable`：正式用户。
- 使用现有“最终版本号候选包 → beta 验收 → 同一 Artifact 晋升 stable”流程。

### 12.2 P1 灰度

现有数据库为灰度预留了通用模型，但当前客户端和服务端尚未实现百分比/设备分组灰度。建议增加：

```text
rollout_percentage
rollout_status
cohort_seed
allowed_device_groups
allowed_subscription_tiers
minimum_os_version
paused_at
```

客户端检查请求增加不可逆向识别用户的安装标识摘要；服务端使用稳定 Hash 分桶，确保同一设备不会在每次检查时随机进入或退出灰度。

灰度顺序建议：

```text
开发设备
→ 内部 beta
→ 5%
→ 20%
→ 50%
→ 100% stable
```

每一阶段观察安装成功率、启动健康检查、回滚率和崩溃率。出现异常时先暂停分发，再切换渠道指针。

### 12.3 强制更新

- `mandatory=true`：该 Release 被明确标记为必须更新。
- `minimumSupportedVersion`：当前版本低于阈值时自动升级为必须更新。
- 强制更新仍必须完成签名验证、任务排空和安装确认策略。
- 高危安全更新可以禁止新任务，但不能静默删除用户未提交的代码或未保存的会话。

## 13. 本地与远端接口

### 13.1 复用 OTA Platform

```text
GET /api/v1/updates/check
GET /api/v1/updates/releases
GET /packages/{path}
```

检查请求优先使用 `targetKey`：

```text
GET /api/v1/updates/check
  ?appId=hqagent-hub
  &currentVersion=0.1.0
  &channel=beta
  &targetKey=windows-amd64-installer
```

### 13.2 HQAgent 本地 API

以下 9 条更新接口由 Local Hub 的公共 OpenAPI 暴露，Vue/Tauri 只访问这一组接口。Local Hub 再依据 `packages/protocol/openapi/update-agent.internal.v1.yaml` 调用 Update Agent 私有 API；私有端口和凭据不写入前端运行时配置。

```text
GET  /api/v1/updates/state
GET  /api/v1/updates/result
POST /api/v1/updates/result/acknowledge
POST /api/v1/updates/check
POST /api/v1/updates/download
POST /api/v1/updates/cancel
POST /api/v1/updates/install
POST /api/v1/updates/defer
GET  /api/v1/updates/releases
```

统一事件由 Update Agent 产生业务状态、Local Hub 持久化并分配全局单调 `seq` 后再通过公共 WebSocket 推送：

```text
update.state.changed
update.download.progress
update.verification.completed
update.tasks.draining
update.install.ready
update.health_check.started
update.health_check.failed
update.rollback.started
update.rollback.completed
update.completed
update.failed
```

一期由桌面端查看、延后或批准升级；后续手机端接入时也只通过云端命令转发到绑定设备，安装动作最终必须由本地 Update Coordinator 执行。

## 14. 本地目录

```text
%LOCALAPPDATA%\HQAgent-Hub\
├── data\
│   └── hub.db
├── config\
├── runtime\
│   ├── hub.json
│   └── update-agent.json
├── logs\
│   ├── hub.log
│   └── updater.log
├── updates\
│   ├── update-state.json
│   ├── update-plan.json
│   ├── update-result.json
│   ├── staging\
│   └── backup\
└── diagnostics\
```

程序安装目录固定为 `%LOCALAPPDATA%\Programs\HQAgent-Hub`。`runtime\hub.json` 采用原子写入和当前用户 ACL，保存随机端口、进程 ID、协议版本和短期访问材料；`update-agent.json` 仅供 Local Hub 与受信任的 Tauri 进程管理层读取，Tauri 不得把内部 Token 传给 Vue。Updater 只消费受控的 Update Plan。升级包、Plan 和备份不能存入用户项目目录，也不能让 Agent Worker 修改。

## 15. 构建与发布流水线

沿用现有原则：

```text
测试
→ 构建最终版本制品
→ Windows Authenticode 签名并复验
→ 计算大小和 SHA-256
→ 离线 Ed25519 签名并立即复验
→ 生成 release-metadata.json / release-notes.md / SHA256SUMS.txt
→ 上传 OTA Platform 草稿
→ 服务端复验
→ 发布 beta
→ 客户端真实升级验收
→ 同一 Release/Artifact 晋升 stable
```

需要新建 HQAgent 脚本：

```text
scripts/build/build-desktop.ps1
scripts/release/package-release.ps1
scripts/release/package-promotable-release.ps1
scripts/e2e/test-update-e2e.ps1
```

Windows 脚本参考 HQDroidDeck 的发布包目录和元数据格式，但构建命令改为 Tauri、产品 ID 改为 `hqagent-hub`，Target 改为 HQAgent 对应 Target。

## 16. 实施阶段

### OTA-M0：协议与共享模块

- 创建独立版本化 `HQUpdateKit`，固定 OTA Client/Updater 通用模块边界。
- 将 HQDroidDeck-Desktop 与 HQAgent-Hub 都迁移到 `HQUpdateKit`，禁止保留两套产品内核心实现。
- 固定 Manifest、状态机、事件和 Update Plan v2。
- 在 OTA Platform 创建 `hqagent-hub` 和 Windows Target。
- 为 HQAgent 生成独立测试密钥。

### OTA-M1：Windows 整包升级

- Tauri 安装包接入发布脚本。
- 使用测试证书跑通 Authenticode 签名、复验和客户端拒绝未签名/错签制品的链路。
- Update Agent 完成检查、续传下载、验签和状态恢复。
- Task Drain Controller 完成任务排空和 Session Checkpoint。
- Updater 完成当前用户级 NSIS 安装、重启、结果回执、健康检查和自动回滚。
- 完成 Windows 本地 E2E。

### OTA-M2：商业发布能力

- 独立生产签名密钥和轮换预留。
- 切换到受信任的生产 Authenticode 证书并固化受控签名环境。
- beta 同制品晋升 stable。
- 强制更新、暂停分发和安装结果匿名统计。

### OTA-M3：跨平台和插件

- macOS Intel/Apple Silicon 安装与回滚策略。
- Developer ID 签名和公证。
- Linux 安装策略。
- Adapter 插件独立 Application、兼容约束和灰度更新。

## 17. 验收标准

1. OTA Platform 可以为 `hqagent-hub` 创建 Windows Release 和签名 Artifact。
2. 客户端能够使用 Target 精确检查 stable/beta 更新。
3. 支持取消和恢复下载，下载完成后大小、SHA-256、Ed25519 全部验证。
4. 篡改包、错误签名、错误平台和错误架构均无法进入安装状态。
5. 有运行任务时不能直接安装；完成 checkpoint 后才能进入维护模式。
6. 更新期间桌面端显示维护状态，停止接收新任务，已有任务 checkpoint、Session 和事件游标不丢失。
7. 主程序退出后独立 Updater 能完成更新并重启新版本。
8. 新版本能够读取旧版本保存的任务、Session 和 Team Profile。
9. 健康检查失败时能够自动恢复上一版本程序和升级前数据库快照，并记录可诊断的回滚结果。
10. 升级结果只展示一次，但诊断记录继续保留。
11. beta 验收后 stable 晋升前后制品大小、SHA-256 和签名不变。
12. 自动升级 E2E 测试不依赖正式 OTA 服务器，不覆盖开发机正式安装目录。
13. Vue/Tauri 只配置 Local Hub 一个 Base URL，更新 HTTP 请求使用 Bearer Token，WebSocket 使用一次性短效 Ticket。
14. HQDroidDeck-Desktop 与 HQAgent-Hub 的更新核心均来自同一版本化 `HQUpdateKit`，不存在复制维护的第二套核心代码。

## 18. 当前缺口与风险

| 缺口/风险 | 当前状态 | HQAgent-Hub 处理 |
| --- | --- | --- |
| 灰度分组 | 数据模型可扩展，尚未实现百分比灰度 | P1 增加稳定分桶、暂停和指标门禁 |
| 自动本机回滚 | 现有 Helper 有备份但未自动健康检查回滚 | P0 在 Update Plan v2 实现健康检查和自动回滚 |
| 多产品密钥隔离 | OTA Platform 当前使用全局公钥 | 增加 `keyId` 和产品密钥注册；商业发布前完成 |
| Tauri 安装策略 | 现有 Helper 使用 Inno 参数 | P0 固定当前用户级 NSIS；MSI/macOS/Linux 后续实现 |
| 多进程排空 | 现有协调器只处理 HQDroidDeck 任务 | 新增 Agent Worker、Git、Session、WSS 排空流程 |
| 数据库不可逆迁移 | 现有桌面应用数据较简单 | 增加 schema 版本、备份和 rollbackCompatible |
| 插件独立升级 | 尚未实现 | P0 整包，P1/P2 使用独立 OTA Application |
| 更新核心再次分叉 | 只复制代码或只有 HQAgent 使用抽取模块仍会产生分叉 | 建立独立 `HQUpdateKit`，两个产品共同依赖并由兼容性测试守门 |

## 19. 下一步

1. 建立独立 `E:\OtherPro\HQUpdateKit` 仓库和版本发布规则，在兼容性测试通过后分步迁移 HQDroidDeck-Desktop 与 HQAgent-Hub。
2. 在测试环境给 OTA Platform 创建 `hqagent-hub/windows-amd64-installer`。
3. 用一个假 Tauri 包完成“检查 → 下载 → 验签 → Update Plan → 当前用户级 NSIS Helper → 健康检查 → 自动回滚”无 UI E2E。
4. 再接入真实 Tauri 安装包、完整 Task Drain Controller 和桌面端审批。
5. Windows 闭环稳定后再实现 macOS，不同时开工所有平台。
