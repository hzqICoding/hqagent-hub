# T-W6-updatekit 交接记录

日期：2026-09-06。分支：`work/w6-updatekit`。
工作区：`E:\OtherPro\HQAgent-Hub-worktrees\w6-updatekit`，未切换到主仓库工作。

**交付状态：实现和本地测试已落地，但 W6 完整验收未完成；未合并 main、未提交、未发布模块 Tag。**
原因分别是 Git worktree 元数据写权限、冻结协议/跨包集成缺口及真实 NSIS 测试环境缺失。不能把模拟器测试算成真实 NSIS + 测试证书验收。

## 1. 基线和路径

```text
git rev-parse HEAD main
f892672242868d5dc1b236db6edfa21138760298
61acacbf01997e80b1ce780bcafa0dd7eb3c5e65
```

按指定顺序读取 AGENTS、OTA 文档、分工 §5.7/§6/§7/§8、内部 OpenAPI、State/Result Schema、Runtime Descriptor 和生成 Go DTO。
开工首先尝试用户要求的合并，真实输出：

```text
git merge main
fatal: update_ref failed for ref 'ORIG_HEAD': cannot lock ref 'ORIG_HEAD': Unable to create 'E:/OtherPro/HQAgent-Hub/.git/worktrees/w6-updatekit/ORIG_HEAD.lock': Permission denied
```

当前沙箱可写 worktree 源文件，但不可写其真实 Git 元数据目录，且不允许权限升级。
未绕过权限、未修改 `.git` 指向、未建立替代 Git 仓库。

交付前尝试暂存，同样失败，未继续执行可能误导的空提交：

```text
git add -- packages/updatekit apps/update-agent apps/updater .hqagent/handoffs/T-W6-updatekit.md
fatal: Unable to create 'E:/OtherPro/HQAgent-Hub/.git/worktrees/w6-updatekit/index.lock': Permission denied
```

因此没有新 commit，也没有可供 `git log -1 --format=%B` 做提交后自查的新消息。第 6 节给出准确的待执行提交命令。
工作区协议仍为 0.1.0；为验证最新接口，只读 `git archive main packages/protocol/generated/go` 到 `E:/tmp/hq-w6-protocol-main`，通过临时 `-modfile` 使用 **main 的实际生成协议 0.2.0** 运行全部应用测试。
此验证不等于已完成合并。`packages/protocol/`、Hub、Desktop 和共享根配置没有修改。

实际新增路径仅 `packages/updatekit/**`、`apps/update-agent/**`、`apps/updater/**` 和本交接单。

## 2. 已实现

- 从 HQDroidDeck commit `65d88191d7090af736f6a884b3dfd24ef9941ae9` 抽取公共 Go module，来源映射详见 `packages/updatekit/README.md`。
- 模块标记 `0.1.0`，两个产品薄封装使用固定版本 require + 本地 replace；模块没有 HQAgent 协议或宿主业务依赖。
- 共享状态机、精确 Target 检查、Range 下载/取消/续传、进度、SemVer、mandatory/minimumSupportedVersion、持久化、跨重启重验签。
- 双重验签：大小、SHA-256、Ed25519、产品独立 keyId/trustedKeys，以及 Windows Authenticode 有效性和发布者指纹 pin。没有生产跳过开关。
- 受控 Plan v2：严格 JSON 解码与语义校验；current-user 固定范围；包/备份/数据/程序路径；目录联接防护；完整进程清单与 waitPids 一致性；固定允许的重启程序；禁止任意 args。
- Update Agent 与 Updater 是独立 Windows 可执行文件。Agent 只监听 loopback，检查 Host/Origin/Bearer，描述符每次轮换 Token 并原子写入，只保留当前用户 DACL。
- 消费 W1 的 drain/state 和 SQLite Backup API。缺少排空、备份完成或完整进程清单时拒绝安装；不重新实现 W1 的 checkpoint/SQLite 逻辑。
- Updater 复制到 updates/helper 后运行，等待所有旧进程并重复验签；NSIS `/S`、末尾未额外加引号的 `/D=`；明确非零退出码失败和超时处理。
- 保留上一版安装器、程序、配置和 DB 快照；健康失败自动回滚；移动失败版本目录和 WAL/SHM、恢复快照、重启并验证旧 Core；结果映射为生成 `UpdateResultView`。
- 新 Update Agent 等待 Updater 内核锁释放，避免健康检查期间并发争写状态。
- 实际 `RunAgent` 在独立进程两次起停已验证：鉴权检查、无 Token 401、Token/instance 轮换、重复实例拒绝与描述符清理。
- 已生成 HQAgent 独立测试 Ed25519 密钥。私钥只在 `E:/tmp/hq-w6-test-keys/hqagent-hub-test.pem`，去继承且只留执行账户；未进入仓库。公钥为 `QheoALe2NWTjuOjeih3AsIdEFVrQ58TVpX+kDtvtzTY=`，示例配置仅含公钥。

## 3. 没做完，不能认定完成的部分

1. **main 合并、分支提交和版本 Tag：未完成，权限阻塞。** 当前源码是未提交新增文件。
2. **真实 NSIS + HQAgent 测试代码签名证书 E2E：未完成。** 未发现 makensis/signtool；没有修改证书库或下载工具。当前 E2E 是 Go 假 Tauri 安装包，OS 签名验证使用仅测试二进制可用的适配器。
3. **W1/W5 真实联调：未完成。** 需要用户启动/提供真实 Hub 联调环境并由对应包修复第 5 节问题；没有改其源码。
4. **events/defer/acknowledge：协议未冻结完整，未私自加路径/包络。** events 返回 501 FEATURE_UNAVAILABLE；defer/acknowledge 未提供私有路由。11 个事件向 Hub 可靠投递、统一 seq 的集成尚未完成。
5. **NSIS 超时后的子进程收敛：能力缺口。** 无法证明子卸载进程已经退出时，返回 `ErrInstallerNotQuiescent` 并保留备份，禁止盲目覆盖；该超时恢复分支不能认定 P0 全部完成。
6. **新版本健康检查期间的维护模式/Worker Gate：跨包缺口。** 当前 W1 重启默认解除内存中的维护态，需要联调启动期门禁，防止新 Worker 在回滚前开始写入。当前实现只跟踪重启的三个产品进程，不能宣称已控制所有新生后代进程。
7. Helper 被强杀/机器断电后的自动事务续做未实现；程序/DB/安装器备份保留。状态恢复会报告中断，而不伪报成功。
8. SQLite 快照一致性依赖 W1；模拟 E2E 验证快照字节恢复，未以真实 W1 SQLite 数据库验证 Session/Profile/Task 完整性。
9. 未修改 HQDroidDeck，未在 OTA Platform 创建远端产品/Target、未上传/发布。**仍存在双端同步责任，未消除分叉。** 独立模块远端地址和发布流程尚需 Integrator 确认。
10. MSI/portable/macOS/Linux 没有空策略实现，不计入一期验收。未做真实多用户读取拒绝或普通交互用户无 UAC 安装场景；已检查真实 DACL 只含当前用户。

## 4. 验收与真实命令输出

完整原始 stdout 保存于 `apps/update-agent/acceptance/`，均来自实际执行，不是预期示例：

| 验收项 | 实际结果 | 原始记录 |
| --- | --- | --- |
| HQUpdateKit `go test ./... -count=1 -v` | PASS，含下载/验签/Plan/NSIS退出码/成功安装/自动回滚/失败回滚/ACL/签名/联接测试 | `updatekit-tests.txt` |
| Update Agent `go test ./... -count=1 -v` | PASS，含协议 DTO/私有 API/拒绝未排空/进程 E2E | `agent-tests.txt` |
| Updater `go test ./... -count=1 -v` | 编译通过，命令 package 无单独测试；Helper 测试位于共享模块与 Agent 进程 E2E | `updater-tests.txt` |
| main 实际协议 0.2.0 | 两个应用模块测试全部通过 | `protocol-020-tests.txt` |
| `go vet ./...` | 三个模块通过 | `build-vet.txt` |
| 两个 Windows 可执行文件 | 构建成功，均报告产品版本 0.1.0 | `build-vet.txt` |
| go.mod 无 Wails | 匹配数 0 | `dependency-check.txt` |
| 假 Tauri 完整链路 | 进程模拟器 PASS，不能算真实 NSIS/证书通过 | `agent-tests.txt` |
| 真实 Authenticode | 拒绝未签名/错签，接受精确 pin 的 Windows 签名程序；不是 HQAgent 安装器证书 E2E | `updatekit-tests.txt` |
| 最终完整复查（含新增进程起停测试） | 三模块 `go test ./...` 与 0.2.0 应用模块测试通过；受保护路径 diff 为空 | `final-tests.txt` |

最终复查按 `packages/updatekit`、`apps/update-agent`、`apps/updater`、使用 0.2.0 临时 modfile 的 `apps/update-agent` 顺序执行，原文：

```text
ok  	hqupdatekit.local/updatekit	10.732s
?   	hqupdatekit.local/updatekit/cmd/keygen	[no test files]
?   	hqagent.local/update-agent/cmd/hqagent-update-agent	[no test files]
ok  	hqagent.local/update-agent/product	2.006s
?   	hqagent.local/updater/cmd/hqagent-updater	[no test files]
?   	hqagent.local/update-agent/cmd/hqagent-update-agent	[no test files]
ok  	hqagent.local/update-agent/product	1.967s
```

```text
# packages/updatekit: go test ./... -count=1 -v
PASS
ok  	hqupdatekit.local/updatekit	10.236s
?   	hqupdatekit.local/updatekit/cmd/keygen	[no test files]

# apps/update-agent: go test ./... -count=1 -v
PASS
ok  	hqagent.local/update-agent/product	1.796s

# apps/updater: go test ./... -count=1 -v
?   	hqagent.local/updater/cmd/hqagent-updater	[no test files]
```

进程 E2E 原文：

```text
check: available; targetKey matched
download: ready_to_install; SHA-256 + Ed25519 verified (test OS-signature adapter)
Plan v2: Desktop/Core/Update Agent + 2 Workers; current-user directories validated
independent Helper: waited for all 5 processes; executed /S and terminal /D
health: new core unhealthy; automatic rollback restored program/config/DB snapshot, removed new WAL, restarted healthy 0.1.0; generated Result DTO persisted
```

安全与构建原文：

```text
descriptor DACL protected; exactly one current-user SID ACE; duplicate lock denied
production Authenticode verifier rejected unsigned/wrong-publisher test executable
production Authenticode verifier accepted an OS-signed binary with its exact configured signer pin
Windows junction rejected before package access
Wails dependency matches: 0
0.1.0
0.1.0
go vet: all 3 modules passed; both Windows binaries built
```

后补实际 Agent 起停测试输出：

```text
go test ./product -run TestActualAgentProcessLifecycleAndTokenRotation -count=1 -v
=== RUN   TestActualAgentProcessLifecycleAndTokenRotation
    lifecycle_test.go:47: real RunAgent in separate processes: two clean starts/stops, authenticated check, 401 without token, instance/token rotation, duplicate-instance rejection, descriptor cleanup
--- PASS: TestActualAgentProcessLifecycleAndTokenRotation (0.26s)
PASS
ok  	hqagent.local/update-agent/product	0.283s
```

额外尝试 race 检测，环境不能执行（CGO 未启用且未找到 C 编译器），不能算通过：

```text
go test -race ./... -count=1
go: -race requires cgo; enable cgo by setting CGO_ENABLED=1
```

0.2.0 验证命令和输出：

```powershell
git archive --format=tar --output=E:/tmp/hq-w6-protocol-main/protocol.tar main packages/protocol/generated/go
& "$env:SystemRoot/System32/tar.exe" -xf E:/tmp/hq-w6-protocol-main/protocol.tar -C E:/tmp/hq-w6-protocol-main
# 临时 modfile 仅把 protocol replace 改为导出目录，其余本地 replace 保持不变。
go -C apps/update-agent test -modfile=E:/tmp/hq-w6-protocol-main/update-agent.mod ./... -count=1 -v
go -C apps/updater test -modfile=E:/tmp/hq-w6-protocol-main/updater.mod ./... -count=1
```

```text
generated protocol package: 0.2.0; HTTP protocolVersion: 1.0
PASS
ok  	hqagent.local/update-agent/product	1.874s
?   	hqagent.local/updater/cmd/hqagent-updater	[no test files]
```

## 5. 协议和跨包变更请求（未修改协议目录）

### W0：冻结私有 API 缺口

- `/internal/v1/events` 只有路径，缺媒体类型、payload DTO、心跳、重连/重放与游标语义。请冻结事件业务包络，继续由 Hub 分配 seq；补生成 Go DTO 和 Fixture。当前返回 501，不自行选择 SSE/NDJSON。
- 公共 API 有 defer 与 result/acknowledge，内部 API 没有对应路由；请补完整请求/响应以及 `AcknowledgeUpdateResultInput` 的 Go 生成声明。
- install 无 requestBody、返回体，也未冻结 Drain/Backup 请求和包络；请明确排空完成凭据、完整进程登记和快照路径怎样传递。当前消费 W1 已有路由，容器使用 RawMessage，领域值直接导入生成 DrainProgress。
- 没有上次结果时 result 仅声明 200 且 schema 不可空；建议追加 204。当前实现 204，记录为待追认的协议偏差。
- Update Plan v2 只有文档示例，没有 Schema；共享模块已使用严格 v2 磁盘模型，但 `processes/release/backup.databaseSnapshot/backup.previousInstaller` 等字段需 W0/模块发布方共同评审，不能未经讨论成为新的 Hub IPC DTO。
- `rollbackCompatible=false` 的额外确认没有冻结到当前 OTA 返回和私有 install 请求；不能宣传已实现不可逆迁移确认。

### W1/W5：真实联调阻塞

只读检查的是 `E:/OtherPro/HQAgent-Hub-worktrees/w1-hub`：

- `apps/hub/api/app.py` 公共 install 当前调用 `await drain.start()`，未传 Desktop PID；`core/maintenance.py` 仅在收到 desktop_pid 时写入 waitPids。W6 会拒绝缺 Desktop 的计划。需要 W5/W1 从可信进程登记传入，不能靠 Vue 自报任意 PID。
- 公共 install 排空结束后仍直接调用代理，未显式检查 `step=ready`，也未协调 Desktop/Core 退出。W6 会拒绝未排空状态；启动 Helper 后需 W1/W5 停止所有既有产品进程并暂停守护重拉，避免 Helper 等待超时。
- `api/update_proxy.py` 把任何有 `success` 键的对象当包络；裸 `UpdateResultView` 恰有该字段。success=false 的合法失败/回滚回执会被当成 HubError，success=true 则会被解包为缺失的 data。请按路由或完整 envelope 结构识别。
- Update Proxy 默认 5 秒超时，检查上游允许 20 秒；需要统一异步检查或代理超时契约。
- 新 Core 启动后的维护 Gate 与健康成功后的放行需要明确；当前 W1 内存 maintenance 重启丢失，不能保证回滚前没有新 Worker 开始写库/项目。应冻结启动维护语义与完成握手，再调整固定允许的启动参数。
- W1 当前无 Update Agent 事件流订阅实现，与 W0 一起补齐，不能把“路由存在”当事件已投递。

### W7 / OTA Platform

- 首装须缓存上一版安装器到 `updates/installed/installer.exe`；W6 缺恢复材料时拒绝安装。
- 确认 `hqagent-desktop.exe` 为实际 Tauri 文件名；OTA 示例有 `HQAgent-Hub.exe`，本实现采用五进程边界中的命名，不能随意兼容第二套名字。
- 提供真实 currentUser NSIS、HQAgent 测试代码签名证书和签名工具；补安装器超时子进程 Job/收敛保证及无 UAC 验收。
- 当前 OTA `publicPackage` 未输出 targetKey/signatureAlgorithm/keyId；客户端使用精确查询、平台检查、产品专用默认 keyId，显式未知 key/算法会拒绝。请扩展服务器元数据并补回滚兼容标志；目前没有宣称完整密钥注册/轮换发布链路已上线。

## 6. 交付后续命令

解除 worktree 的 Git 元数据权限后，在**本 worktree**执行，不切到主仓库：

```powershell
git merge main
go -C packages/updatekit test ./...
go -C apps/update-agent test ./...
go -C apps/updater test ./...
git add -- packages/updatekit apps/update-agent apps/updater .hqagent/handoffs/T-W6-updatekit.md
git commit -m "Extract HQUpdateKit and add update agent with NSIS rollback helper"
git log -1 --format=%B
```

以上提交命令为待执行步骤，不是已完成证明。不要推 main；按项目约定交 Integrator 合入 integration/phase1。
