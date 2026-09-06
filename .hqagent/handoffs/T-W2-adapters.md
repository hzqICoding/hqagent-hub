# T-W2 Agent 适配层交付

日期：2026-09-06

分支：`work/w2-adapters`

协议基线：`0.2.0` / FZ-2 `bfcd91e`

## 提交状态

实现与验证均完成，但当前执行会话对共享 Git 元数据目录只有读权限，无法创建 worktree
index lock，因此未能替用户完成 commit：

```text
fatal: Unable to create 'E:/OtherPro/HQAgent-Hub/.git/worktrees/w2-adapters/index.lock': Permission denied
```

已确认 `index.lock` 实际不存在，不是陈旧锁；是目录写权限阻断。需要在有 Git 元数据写权限
的终端执行：

```powershell
git add -- apps/hub/adapters docs/Agent适配接入规范.md .hqagent/handoffs/T-W2-adapters.md
git commit -m "feat(hub): implement Claude and Codex agent adapters"
git log -1 --format=%B
```

## 做了什么

- 用本机真实 Claude Code `2.1.263` 与 Codex CLI `0.153.4` 完成 Phase 1 调研，填满
  `docs/Agent适配接入规范.md` 的 Claude/Codex 矩阵和逐项复现证据。
- 实现 `ClaudeAdapter` 与 `CodexAdapter` 的 8 个 Port 方法：
  `detect / health / start / resume / stream_events / approve / cancel / collect_result`，
  并提供契约原名 `streamEvents / collectResult` 的 Python 别名。
- 所有边界 DTO 从 `protocol.generated.python` 导入；W2 只新增内部进程状态、事件队列、
  审批关联和路径守卫对象。
- 实现 `AdapterManager` 的注册、发现、真实登录态健康检查和 detect TTL 缓存，可作为 W1
  `AgentPort` 注入。
- 实现 Claude JSONL 与 Codex App Server JSON-RPC 事件映射；每个 Adapter 都声明
  `VendorEventMapping[]`，显式 dropped 并计数，未知事件降级为 `agent.progress`。
- Codex 每个 Hub Session 使用隔离 App Server 进程；`turn/interrupt` 做 graceful cancel，
  force 阶段才 kill。Claude 前台 JSONL 没有已验证的 graceful 入口，因此 truthful
  `refused`，force 才 kill。
- Codex approval request 与 Hub approval ID 建立映射；Adapter 不检查 Hub 的过期时间。
  Agent 先放弃请求时返回 `AdapterFailure(kind=agent_error)` 并明确“Agent 侧超时”。
- 在供应商写工具/command approval 可见时做前置路径检查，越界立即拒绝；
  `collect_result()` 仍保留 changedFiles 后置检查。
- 新增 W2 契约测试，覆盖 D17-D22、8 方法存在性、新任务 implement/review 会话隔离、
  禁止 `latest/--last` 恢复。

## 没做什么

- 没有实现、创建或占位 Antigravity / Gemini Adapter；它们属于 Phase 1.1。
- 没有修改 W1 的 `core/api/storage/runtime/tests/pyproject.toml`，也没有修改 W3/W0/W4/W5
  路径。
- 没有实现另一套存储或事件总线。`SessionRegistry` 只保存 Adapter 子进程的运行期状态；
  外部会话 ID 的持久化仍由 Hub/W1-W3 的正式 Session 存储负责。
- 没有把 Claude 的未验证能力报成 true：当前 `session_resume`、`tool_approval`、vision、
  browser 都为 `supported=false`。Claude `resume()` 仍只接受明确 ID 并如实返回供应商失败。
- 当前 Codex CLI 未登录且代理链 TLS 为 `UnknownIssuer`，没有伪造 Codex 模型完成结果；
  真实 `start()` 由 `health()` 阻断为 `not_logged_in`。

## 验收结果

### 1. 真实 CLI 版本和登录态

```text
> claude --version
2.1.263 (Claude Code)

> codex --version
codex-cli 0.153.4

> Adapter detect()/health()
claude detect True 2.1.263 (Claude Code) cli_stream 10
claude health ready True
codex detect True codex-cli 0.153.4 sdk 12
codex health not_logged_in False
```

### 2. D17-D22 与会话隔离契约测试

命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'apps/hub').Path
E:\OtherPro\HQAgent-Hub-worktrees\w1-hub\.venv\Scripts\python.exe `
  -m pytest apps/hub/adapters/tests -q `
  --basetemp E:\tmp\hqagent-w2-pytest-<uuid>
```

真实输出：

```text
...........                                                              [100%]
11 passed in 0.22s
```

覆盖对应关系：

- D17：Claude graceful `refused` + PID、force_killed；Codex interrupt 严格使用 Hub
  `graceSeconds` 总 deadline。
- D18：`transport_lost/resumable=true` 与 `agent_exited/resumable=false` 分流。
- D19：Agent 侧审批超时为 `agent_error`；旧 `decidedAt` 不由 Adapter 重新判过期。
- D20：detect 只跑版本，health 单独跑登录态。
- D21：映射类型来自冻结字典；显式 drop 计数；未知事件带截断 raw 降级。
- D22：Codex file-change approval 写前拒绝越界；collectResult 保留第二道检查。

### 3. W1 临时叠加联调

当前 W2 worktree 未包含 W1 文件，所以从当前仓库对象本地 clone `work/w1-hub` 到
`E:\tmp`，只在临时副本叠加 W2 Adapter；没有 merge/cherry-pick，也没有修改 W1 worktree。

命令和真实输出：

```text
> pytest apps/hub/tests -q --basetemp E:\tmp\hqagent-w2-w1pytest-<uuid>
.............                                                            [100%]
13 passed, 2 warnings in 0.37s

> pytest apps/hub/adapters/tests -q --basetemp E:\tmp\hqagent-w2-adapterpytest-<uuid>
...........                                                              [100%]
11 passed in 0.20s
```

两条 warning 是 FastAPI/Starlette 已有依赖弃用提示，不是 W2 失败。

### 4. 真实 Claude Adapter 闭环

场景：`E:\tmp` 空工作目录；任务要求不改文件，只返回结构化 AgentResult。

```text
HANDLE True True False
EVENTS agent.started,agent.tool_call,agent.tool_call,agent.tool_call,agent.tool_call,agent.completed,end:ended
RESULT done CLAUDE_ADAPTER_SMOKE_OK
```

### 5. 真实 Codex 未登录失败分类

```text
START_FAILURE not_logged_in False Codex 未登录，请先运行 codex login
```

### 6. 当前 worktree 的安装环境阻断

按任务话术创建了当前 `.venv`，但以下命令停在 build dependency 获取阶段且没有后续输出，
当前执行沙箱网络受限，已中止等待：

```text
> .venv\Scripts\python.exe -m pip install \
    -i https://pypi.tuna.tsinghua.edu.cn/simple -e packages/protocol
Looking in indexes: https://pypi.tuna.tsinghua.edu.cn/simple
Obtaining file:///E:/OtherPro/HQAgent-Hub-worktrees/w2-adapters/packages/protocol
  Installing build dependencies: started
```

此外，本 W2 分支基线没有 W1 的 `apps/hub/pyproject.toml` 与 `apps/hub/tests`，所以无法在
当前 worktree 原地执行第二条 install 和 `pytest apps/hub/tests -q`。验收改用 W1 已安装
环境；其 `protocol.__file__` 为：

```text
E:\OtherPro\HQAgent-Hub-worktrees\w1-hub\.venv\Lib\site-packages\protocol\__init__.py
```

即协议来自安装路径，不是把 `../../packages` 加回 pythonpath。

## 需要 W1 / Integrator 接线

1. W1 `apps/hub/pyproject.toml` 的 Hatch packages 当前是
   `["api", "core", "runtime", "storage"]`，需要由 W1/Integrator 加入 `"adapters"`；
   W2 按路径所有权没有修改该共享文件。
2. Composition Root 需要实例化：

   ```python
   AdapterManager([ClaudeAdapter(), CodexAdapter()])
   ```

   并替换 `HubPorts.agents` 的 unavailable 占位；任务编排调用具体 Adapter 仍由 W3 负责。
3. CI 需要在现有 `pytest apps/hub/tests -q` 之外加入
   `pytest apps/hub/adapters/tests -q`，或由 Integrator 调整 testpaths；W2 不能改 W1
   `pyproject.toml`。
4. SessionView 的持久化/list/resume HTTP Port 需要 W1/W3 使用正式存储包装 W2
   `externalSessionId`。W2 没有越权写第二套数据库。

## 调研/实现发现的 FZ-2.1 候选

以下只提变更请求，没有修改 `packages/protocol/`：

1. `AgentSessionHandle.sessionId` 描述为“Hub 生成后传给 Adapter”，但 `start()` 唯一输入
   `AgentTaskSpec` 没有 `sessionId` 字段。当前实现只能由 Adapter 生成
   `session_<uuid>`。建议给 `AgentTaskSpec` 增加 required `sessionId`，或正式修改所有权描述。
2. `AdapterDescriptor` 的 `installed=false` 描述要求“status 必须是 incompatible 或
   unknown”，但该 DTO 没有 `status` 字段。当前由 `AdapterManager` 组合 health 后生成
   `AgentView.status`。建议删除该句或增加发现状态字段。
3. `streamEvents()` 没有冻结单条 Adapter Event 的 DTO，只冻结了终止对象
   `AdapterStreamEnd`；直接产出 `HubEvent` 又不对，因为全局 `seq/eventId` 归 W1。
   当前 W2 定义内部 `AdapterEvent`，建议 FZ-2.1 冻结最小事件项形状。
4. `ApprovalDispatch.externalRequestId` 要求 Adapter 关联供应商请求，但
   `ApprovalRequiredPayload` 没有 `externalRequestId`。当前内部 `AdapterEvent` 额外携带，
   建议协议补可选字段或明确 W3 的旁路关联 Port。
5. D21/adapter-contract 说无法映射可 `dropped=true`；event-dictionary §1.2 又要求未知
   原生事件必须降级为 `agent.progress`、不得丢弃。当前实现：已知噪声显式 drop+计数，真正
   未知事件降级 progress+raw+计数。建议 W0 统一措辞。
6. `AgentProgressPayload.raw` 的生成 Python 类型是 `dict[str, Any]`，而 D21 写“raw 上限
   2048 字符”。当前实现为 `{"vendor": "<截断到 2048 的 JSON 文本>"}`。建议明确上限
   约束的是序列化总长度、字符串字段，还是把 raw 改为 string。
7. `CancelOutcome` 没有“interrupt 已发送但 grace 到点仍运行”的中间结果。当前按契约返回
   `refused`，让 Hub 立即升级 force；若 W0 希望区分“无中断入口”和“已发中断但未及时停”，
   需要新增 outcome 或 detail 规范。

## 能力降级结论

- Claude：`session_resume=false`、`tool_approval=false`；graceful cancel truthful
  `refused`。这些是本机受限宿主真实结果，不是永久否定供应商能力。后续若能在产品宿主完成
  transcript 写入、明确 ID resume、host approval request/response 三项闭环，再由新实测提升。
- Codex：已安装能力形状可用，但本机 `health=not_logged_in`；登录/TLS 修复前不进入任务
  执行。thread resume 与 turn interrupt 已在 App Server 本地协议实测通过。
