# HQAgent-Hub 现状评估与下一阶段技术方案草案

## 变更记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-09-24 | v0.1 | 核对 main、integration 和独立工作包；完成本地测试及定向复现；提出保留资产、收敛范围和插件化演进建议。 |

## 1. 结论与审查边界

**已有真实、值得复用的本地多 Agent 雏形；不建议推倒重写。当前问题主要是一期交付范围偏重，以及领域能力与实际应用入口没有完全接通。**

旧方案优先交付 Windows 桌面、角色编排和完整整包 OTA，将手机远程放到 Phase 2、跨平台和插件生态放到 Phase 3。当前用户重点已经变为手机远程任务、既有会话续接、模型分工、截图 Bug 修复、APK 交付和插件扩展。应先重排里程碑并补执行可靠性，再扩功能。

本文件是评审与方案草案，不替代已有施工方案、协议冻结或 D38 等决策。未修改业务源码、未合并分支、未发布部署、未启动真实 Claude/Codex 开发任务。

### 检查的代码位置

| 工作区 | 状态 | 本轮用途 |
| --- | --- | --- |
| `E:/OtherPro/HQAgent-Hub` | main，`ef41d515e57c422e6a57b60c41552f5ea34efe42` | 协议、最新文档和本评审记录 |
| `E:/OtherPro/HQAgent-Hub-worktrees/integration` | integration/phase1，`0824cbbbd97b69efaf53ee0312f718d7ab79c86a` | 实际集成代码与测试的主要依据 |
| `E:/OtherPro/HQAgent-Hub-worktrees/w2-adapters` | 既有独立 worktree | 只读接入层复核，对照 integration 提交 |
| `E:/OtherPro/HQAgent-Hub-worktrees/w3-orchestrator` | 既有独立 worktree | 只读编排复核，对照 integration 提交 |

检查前 main 已有 `.gitignore` 未提交修改；integration 已有 `claude_adapter.py`、`path_guard.py`、`test_contract_rules.py`、`runtime/tasks.py` 四个文件的未提交修改。本轮完整保留。以下 integration 行号以检查时工作区内容为准。

main 与 integration 并非同一个完整版本。只看用户给出的 main 目录会低估已完成实现；也不能把分支上的交付说明直接当作最新集成验收。

## 2. 已有资产与真实完成程度

| 模块 | 已有实现 | 尚不能据此宣称的能力 |
| --- | --- | --- |
| Python Local Hub | FastAPI、SQLite、HTTP/WS、事件 seq、鉴权、公共 API 和 Composition Root | 手机远程服务端、多设备配对与可靠任务恢复 |
| Claude/Codex Adapter | 真正的 CLI/App Server 子进程调用、事件转换、结果解析、取消与部分审批路径 | 所有声明能力都已通过真实写任务验证 |
| Role/Team Profile | 角色与厂商解耦、能力匹配、备用链、权限配置 | 按角色指定具体模型及推理等级 |
| 编排领域层 | DAG 数据结构、Session 谱系、权限、Worktree 和恢复状态归约 | 当前产品入口能够动态拆任务、重启后重新接管执行 |
| Vue 前端 | 任务、会话、工作区、团队、审批等页面，Mock/Local 两套 Gateway | 手机端即开即用，或页面中所有动作都已接通 |
| Rust/Tauri 桌面壳 | 本机进程监督、凭据、托盘和启动流程等代码 | 已验证的三平台安装产品 |
| Go 更新模块 | Update Agent、Updater、下载验签与回滚相关实现和测试资产 | 新需求必须等待整包 OTA 和另一产品迁移全部完成 |

接入层的具体实现：Claude 当前使用 CLI stream-json；Codex 使用 App Server 的 thread/turn 协议。不是只有类名和空接口。

## 3. 阻止远程闭环的关键缺口

### 3.1 固定流程代替了任务类型与对话轮次

- `integration/apps/hub/runtime/tasks.py:73` 的 `DEFAULT_WORKFLOW` 固定为 `general_implementer → reviewer`。
- 同文件 `:142` 创建任务时按此流程建节点，`:299` 按常量推进；自然语言规划尚未接入。
- 默认流程包含写角色，因此只读分析也会受到 Git 写任务准入限制。当前产品无法自然表达“先看代码，之后另发一句话要求修改，再另发一句要求打包”。

建议：保留领域编排能力，先新增直接对话、只读分析、代码修改、构建交付几种明确任务类型；按需启用规划者与复核者，不让每条消息必经完整团队。

### 3.2 真实任务入口未实现幂等，手机重发可能重复执行

- `runtime/tasks.py:142` 接收 `idempotency_key`，但未使用它。
- `api/app.py:281` 将请求键交给 TaskService，没有在此完成任务创建去重。
- `tests/conftest.py:29` 自建 `TransactionalTaskPort` 实现幂等，现有 API 幂等测试测的是该替身，而非 Composition Root 的真实 TaskService。
- 本轮用真实 TaskService、真实临时 SQLite，替换掉外部执行环节，重复提交同一 key，得到两个不同任务。输出见 §6。

建议：在任何 Agent 启动之前先原子保存命令、任务状态及去重记录。外部副作用通过持久化执行记录推进；不承诺依靠消息传输做到任意副作用 exactly-once。

### 3.3 继续、重试、追加指令和重启恢复未接成闭环

- `runtime/tasks.py:189`：resume/retry 仅修改为 queued；append_instruction 仅校验，未保存新指令或推进执行。
- `runtime/tasks.py:653`：会话恢复只转给 SessionManager，没有重新接上输出泵和结果收集。
- `adapters/session_registry.py:68` 是内存字典。重启后仅有数据库中的原生 ID，Adapter 的运行上下文已丢失。
- `adapters/codex_adapter.py:482` 在 registry 缺项时返回 AdapterFailure；`orchestrator/sessions.py:179` 没有检查 resume 返回的失败，仍将会话改为 ACTIVE。
- `TaskRecoveryService` 有代码和单测，但 `runtime/main.py` / `runtime/composition.py` 未启动它，更没有重建进程/事件订阅的监督流程。

建议：持久化运行规格与配置快照；恢复应重建执行上下文、核实进程状态、重新订阅流。不可恢复时进入明确的待处理状态。读取历史、恢复对话、接管正在运行的进程必须区分。

### 3.4 审批和结果状态有生产接线缺口

- `runtime/tasks.py:693` 调用 `coordinator.decide()`，实际 `security/approvals.py:114` 提供的是 `respond()`。
- Adapter 的审批事件被直接转发，但未找到生产链调用 `ApprovalCoordinator.request()` 将其转成可回应的持久化审批记录；审批过期调度也未接入。
- `runtime/tasks.py:592` 调用 collect_result 后，`:598` 只按路径越界决定节点成功与失败，没有按 `AgentResult.status` 判断失败/阻塞。最终又可能把任务写为 succeeded。
- `orchestrator/runtime.py:297` 的 collect_result 默认会结束整个 Task，而应用层实际还要推进 reviewer，存在任务状态/事件的双重写入边界。

建议：只由一个应用层状态机决定 Task/Run 终态；Adapter 与领域执行返回节点结果。审批采用独立 Broker，将请求落库、回传决定、超时和取消接成闭环。

### 3.5 会话、模型、插件和附件不等于已有页面与抽象

- 当前会话列表读取 Hub 自己的记录，没有外部 Claude/Codex 历史枚举、导入和消息浏览接口。
- Claude Adapter `:121` 明确将 session_resume 标为 false。这是旧宿主/接入实测记录，不是对 Claude 当前官方产品能力的结论；需要在目标安装方式下重新验证。
- `packages/protocol/schema/team-profile.json:41` 的角色绑定只有 Agent、约束和权限等；任务规格与启动参数没有贯通 model/reasoningEffort。
- `runtime/composition.py:90` 硬编码两个 Adapter。存在代码扩展接口，但没有插件清单、发现、兼容性和能力安装机制。
- 两个 Adapter 均将 VISION 声明为 false，理由是任务规格没有图片输入。`runtime/tasks.py:133` 固定返回 artifacts=[]；数据库建表不等于产物链已实现。

建议：新增版本化的运行配置、附件/产物引用和插件描述协议，不让模型通过自由文本假装完成这些控制动作。

### 3.6 当前是 Windows 优先，不是已交付的跨平台产品

- `runtime/paths.py:28` 默认依赖 LOCALAPPDATA；可覆盖数据目录，但尚未提供完整的平台默认配置。
- Adapter descriptor 仅声明 Windows。
- 桌面安装与当前验收以 NSIS/Windows 为目标。部分文件锁、文件权限等代码有其他系统分支，属于可复用基础。
- `desktop/src/shared/api/index.ts:11` 缺省使用 mock；真实 Gateway 的 endpoint 主要来自 Tauri invoke，浏览器仅有开发环境例外，不能直接当作生产手机客户端。

建议：业务核心跨平台，平台相关目录、凭据、CLI 查找、进程树取消、自启动放入 PlatformServices。支持声明必须与逐平台验收一致。

## 4. 哪些复杂度应该保留，哪些应该后移

### 保留

- 统一 Adapter/Port、Role 与运行时解耦、能力缺口显式呈现。
- 任务/节点/会话 ID、原生 thread ID、序列化事件和历史记录。
- 幂等、断线补传、真实状态检查、取消和失败语义。
- 写任务隔离、路径范围、角色权限、必要操作授权。
- 单一协议事实源、生成 DTO 和契约验证。

这些不是可以为了“简单”删除的冗余，恰恰是手机远程无人值守所需的基础。

### 从新版第一阶段关键路径后移

- 完整商业桌面安装与整包 OTA：保留 Rust/Go 资产，作为可选交付模块，不再阻塞手机任务闭环。
- 强制另一个产品同步迁移到共享 UpdateKit，作为跨产品独立工作项。
- 支付、套餐、榜单、匿名统计、推荐、插件市场。
- 八个角色全部铺进常用流程；先提供少量默认方案，保留自定义角色注册。
- 双传输协议同时建设、任意插件热更新、多个消息中间件和通用工作流平台。

不要把“支持扩展”理解为第一版必须建设完整生态，也不要把四种语言都重写成一种语言作为减复杂度的前提。

## 5. 建议技术路线（供下一轮定稿）

### 5.1 保留底座，调整边界

```text
手机 / Web（复用 Vue + TypeScript 组件，补真实远程 Gateway）
  ↓ HTTPS：命令、历史、附件；WSS：事件
Hub Server（单体应用：配对、会话/命令存储、路由、事件投影、产物入口）
  ↕ Worker 主动建立 WSS，带命令去重与事件确认
Worker（从现有 Python Local Hub 演进）
  ├─ 唯一的本机执行调度与运行监督
  ├─ Agent 执行器：Claude / Codex
  ├─ 模型连接：可选轻量意图识别
  ├─ 能力插件：目录发现、Android 构建、文件上传
  └─ SQLite、凭据引用、会话存储、工作区与产物

可选桌面壳：继续使用 Tauri，不成为 Worker 启动和远程操作的必要前提。
```

第一版由 Worker 持有执行编排权。服务端保存业务会话、待交付命令和执行事件副本，不再运行一套会与 Worker 竞争的执行状态机。Claude/Codex 规划者也只通过 Worker 工具提交子任务，不另起不受管理的执行链。

### 5.2 技术选择

| 部分 | 建议 | 理由/边界 |
| --- | --- | --- |
| Web | 继续 Vue 3 + TypeScript + Vite，补移动布局与附件组件 | 已有组件、Gateway、页面及测试可复用；PWA 能力分步补 |
| Worker | 保留 Python + asyncio + 现有 FastAPI 本地入口 | 已有约万行 Hub/测试资产；先修应用层而不是换语言 |
| 服务端 | 首选 Python/FastAPI 单体，复用协议与验证基础 | 避免第一版另引入一种应用语言；业务与本机执行分开部署 |
| 数据 | Worker SQLite；服务端单实例自用可先 SQLite，多实例/多用户前规划 PostgreSQL | 两端不共享数据库文件；独立 schema 与迁移 |
| 传输 | HTTPS + WSS | 先做一条有确认、补传、去重的链路；MQTT 留作后续可选通道 |
| 插件运行 | 内置适配器注册 + 子进程能力协议 | 先实现安装/禁用/版本校验，升级后重启宿主即可；不追求热更新 |
| 桌面/OTA | 保留 Tauri/Go 代码，后续独立验收 | 不把已有资产删除，也不作为本次核心闭环前置 |

这些是针对现有代码的建议，不是正式冻结的版本或性能承诺。

### 5.3 下轮必须冻结的最小契约

1. **实体**：Project（逻辑项目）、Workspace（某节点的本地路径/checkout）、Conversation（长期交流）、Task（目标）、Run/Attempt（一次执行尝试）、AgentSessionBinding、Artifact。
2. **角色配置**：role + runtime + model + reasoningEffort + tools/permissionProfile；创建 Run 时保存实际可执行配置快照。能力不支持时显式失败/协商，不能静默换模型。
3. **命令**：messageId、idempotencyKey、conversationId、taskId、runId、workerId、schemaVersion；先持久化接单，再执行。
4. **事件**：eventId、runId、workerId、workerEpoch、seq、type、payload；本机 seq 不直接冒充跨所有 Worker 的全局序列。服务端按 eventId 去重，并使用独立投影游标。
5. **插件**：manifest、接口版本、支持平台、能力声明、配置/input/output schema、凭据引用、validate/start/inspect/cancel/recover 能力。recover 可不支持，但必须声明。
6. **附件与产物**：artifactId、mime、size、hash、存储位置、所属任务/Run、代码提交或构建来源。上传结果要与实际文件绑定。
7. **状态权威**：谁写任务终态、谁持有执行租约、谁管理审批与超时、网络断开后如何核对；避免用“最后一句模型回复”代替实际完成状态。

新建项目在空目录中的写入策略与旧 D38 冲突，需要作为明确设计变更处理；本评审没有解除现有 Git/Worktree 边界。

## 6. 本轮验证

### 后端现有测试

工作目录：`E:/OtherPro/HQAgent-Hub-worktrees/integration/apps/hub`

```text
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
71 passed, 5 warnings in 13.01s
```

设置了 PYTHONDONTWRITEBYTECODE=1。现有测试包含本地 WebSocket 真握手，但 Agent 行为和部分应用 Port 仍使用替身。

### 前端现有测试与类型检查

```text
pnpm --filter @hqagent/desktop test
Test Files  22 passed (22)
Tests       92 passed (92)

# 在 apps/desktop 下直接调用已安装工具：
node ./node_modules/vue-tsc/bin/vue-tsc.js --noEmit
exit_code=0
```

首次 pnpm 执行自动修复/补齐 node_modules，导致并发 typecheck 遇到 ENOENT。依赖准备完成后，串行直接运行 vue-tsc 通过。未修改 package.json 或 lockfile，不将这个环境错误归为源码缺陷。

### 真实 TaskService 的定向复现

使用真实 TaskService、TaskRepository、临时 SQLite；仅替换项目/配置查询和外部执行推进，避免任何真实 Agent 或仓库写任务。真实输出：

```text
IDEMPOTENCY {"same_key": true, "same_task_id": false, "task_count": 2}
ACTION {"action": "resume", "advance_calls": 0, "objective": "read-only adapter-free audit", "event_calls": 1}
ACTION {"action": "retry", "advance_calls": 0, "objective": "read-only adapter-free audit", "event_calls": 0}
ACTION {"action": "append_instruction", "advance_calls": 0, "objective": "read-only adapter-free audit", "event_calls": 0}
```

验证范围：证明当前生产应用服务没有兑现命令去重和动作推进；不代表已经运行真实模型或验证过用户项目。

未重新运行真实 Claude/Codex 修改代码、Rust/Go 全量构建、安装/OTA、手机公网、Android 构建、硬件或 macOS/Linux E2E，因此不声明这些已通过。

## 7. 建议里程碑与验收

| 阶段 | 内容 | 必须可复现的出口 |
| --- | --- | --- |
| A：收敛基线与设计 | 记录 integration 未提交改动归属；确认新的优先级、实体、接口和插件协议 | 新文档能明确指出每种命令由谁执行、数据归谁保存 |
| B：补本地执行可靠性 | TaskService 幂等、状态、审批、取消、会话恢复；直达执行与只读分析 | 同 key 只派一次；失败不显示成功；重启后可核对并续接明确会话 |
| C：最小远程垂直链 | Worker 主动连接、手机提交/查看/继续/取消、事件补传 | 手机断网重连不重复执行；主机离线时可明确显示排队/离线 |
| D：首批插件与交付 | 角色模型配置、截图附件、Android Builder、Artifact Uploader | 截图 Bug 任务关联版本；用户后续发打包指令才构建上传，返回经过校验的 APK 链接 |
| E：平台与产品完善 | Windows/macOS/Linux Worker 验证、可选桌面、安装和 OTA | 逐平台报告可用能力；安装升级不损坏任务和会话 |

首个真实场景建议用 Q20/ua_android：手机发“梳理 RTK 基站代码” → 只读执行 → 手机接收结果 → 再发一句明确追加要求 → 续接同一业务会话；随后扩到修复、APK 构建和上传。

下一步交付应是更新后的范围/技术方案与小范围接口草案，再进入实现。保留现有可用资产，避免沿旧 OTA/商业化目标继续扩张。
