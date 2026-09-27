---
wp: R1-FZ12
status: done
scope_declared: [packages/protocol/**, scripts/protocol/**, .hqagent/**]
scope_touched: [".hqagent/DECISIONS.md", ".hqagent/INTERFACES.md", ".hqagent/handoffs/R1-FZ12-remote-protocol.md", ".hqagent/reviews/R1-FZ12-generate.log", ".hqagent/reviews/R1-FZ12-hub-tests.log", ".hqagent/reviews/R1-FZ12-offline-package.log", ".hqagent/reviews/R1-FZ12-protocol-tests.log", ".hqagent/reviews/R1-FZ12-protocol-validation.log", "packages/protocol/VERSION", "packages/protocol/fixtures/contracts/manifest.json", "packages/protocol/generated/go/protocol.go", "packages/protocol/generated/python/models.py", "packages/protocol/generated/ts/index.ts", "packages/protocol/openapi/local-chat.v2.yaml", "packages/protocol/remote/R1-contract.md", "scripts/protocol/tests/test_remote_link_browser_contract.py"]
build: pass
tests: pass
commit: 1e00d2c20ca346e4ab37cc690d59a1e2b2fac64f
open_questions: 0
---

# FZ-R1.2 / 0.6.2 交付回执

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/remote-protocol`，分支 `feat/remote-protocol`。头部 commit 为契约、生成物、D44 与测试的冻结 SHA；冻结登记、日志、回执另提交，避免 SHA 自引用。

## 基线与边界

按要求先执行 `git merge --no-ff integration/phase1`，使用只描述改动的提交信息，得到 merge `96b7adfd886b75db91efe7d4423282be810889fa`，合入集成 SHA `b84fe9137bcc35e0bb97f9f149d75476ca358c8d`。无冲突，无回滚。该授权合并带入 P1/P2 既有业务代码；本轮 scope_touched 以 b84fe91 为比较基线，只记录 FZ-R1.2 自身改动。对该基线的 apps/**、docs/** diff 为空。

只实施 D44。未修改云端 remote-hub.v2、本机 local-hub.v1、Schema、错误码 registry、事件字典、生成器、现有测试断言；未新增 DTO、错误码或 Fixture。总量仍是 258 类型 / 109 Fixture，wireRevision 仍为 1。三端重新生成后的 diff 仅包版本常量 0.6.1 → 0.6.2。

## 路由与取舍

真实现状中，本机 Cookie 工作台 API 定义在 `packages/protocol/openapi/local-chat.v2.yaml`，对应 `apps/hub/api/local_chat.py` 的 localSession / require_auth 路由组；不是 local-hub.v1.yaml。因此按裁决允许的分支，在 local-chat.v2.yaml 增量追加四个操作：

| 操作 | operationId | 输入 | 输出 |
| --- | --- | --- | --- |
| GET /api/v2/remote/link | getLocalRemoteLink | 无 | RemoteLinkView |
| POST /api/v2/remote/pairing | startLocalRemotePairing | RemoteLinkPairingInput | RemoteLinkView |
| DELETE /api/v2/remote/pairing | cancelLocalRemotePairing | 无 | RemoteLinkView |
| POST /api/v2/remote/unlink | unlinkLocalRemote | 无 | RemoteLinkView |

- 成功及错误均复用现有 ApiEnvelope；请求/响应引用 D43 的同一 Schema，不复制字段或产生第二份类型。新增的 LocalRemoteLinkError 只是 OpenAPI response component，不是新 DTO 或新错误码。
- 鉴权明确为现有 `localSession`，Cookie 名为 `hqagent_local_session`。浏览器写请求要求可信 Origin 与 Idempotency-Key，沿用本机 v2 边界、幂等及已登记错误码。
- 成功响应、401/403 等边界错误和 default 错误均声明 Cache-Control:no-store。P2 不能只给成功 handler 加头，须覆盖中间件提前拒绝。
- 本机 Local Hub `/api/v2` 与云端 Hub Server `remote-hub.v2` 不是同一个服务，Cookie 不可互换。本机工作台不需要接触 Hub Token；v1 Bearer 路由继续供桌面壳/诊断使用，未放宽其认证。
- 允许工作台轮询 GET link，仅取快照，不触发配对或延长短码期限。remote.link.changed 未变，使用轮询的页面无需接入 v1 WS Ticket。
- 配对、取消、解绑复用同一连接管理器和 D43 生命周期。解绑不保证服务端已撤销、不代表已停止执行；既有 remote 对话仍 remote、本机只读。
- manifest 和相关 OpenAPI 升至 0.6.2；既有 Fixture 作为历史兼容样本完整保留，包括 0.6.1 本机事件与 hello 诊断版本。没有为升包版本修改线路结构或放宽旧断言。

D44 已登记，编号未冲突；它解决 FZ-R1.1 回执接线事项2的协议缺口。原有云端撤销授权不足时 best-effort 的边界继续有效，本次不新增自撤销能力或授权。

## 校验与真实输出

所有以下结果均为本轮实际运行，未复用旧结果。未启动 Vitest，前端测试由主代理负责；本回执 tests=pass 指本轮要求执行的协议和 Hub 测试通过，不代表前端或新 v2 路由联调通过。

1. 根目录将 .venv/Scripts 加到当前进程 PATH，执行 `pwsh -NoProfile -File scripts/protocol/generate.ps1`：

```text
protocol 0.6.2: 生成 258 个类型 -> ts / python / go
```

2. 根目录离线重装：

```powershell
.venv/Scripts/python.exe -m pip install --no-index --no-build-isolation --force-reinstall --no-deps -e packages/protocol
```

```text
Successfully built hqagent-protocol
Successfully installed hqagent-protocol-0.2.0
```

0.2.0 是既有 Python 分发元数据版本，不是协议版本；协议 VERSION 与三端常量已为 0.6.2，未在此任务顺带改分发元数据。全过程未联网安装。

3. 根目录执行 `pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated`（PATH 使用 .venv/Scripts，TEMP/TMP 放 .venv/r1fz12-validation）：

```text
协议校验通过：258 个类型，109 个 Contract Fixture
```

4. 根目录执行 `.venv/Scripts/python.exe -B -m pytest scripts/protocol/tests -q -p no:cacheprovider`：

```text
198 passed in 10.05s
```

原有 validate.py 不扫描 OpenAPI 路由，故本次另加 `test_remote_link_browser_contract.py` 的 11 项检查，未修改生成/校验器职责。覆盖：恰好追加四个操作、现有路由和 Cookie 定义保留、operationId 唯一、D43 输入/输出复用、写请求头、所有成功及边界错误 no-store、引用可解析、Schema/错误码/事件/v1/云端不变、27 帧修订仍为 1、全部旧 Fixture 不变。原协议 187 项保留，无断言放宽。

5. apps/hub 目录全量测试，先建立 worktree 内 `.venv/r1fz12-hub-<随机标识>` 并设置 TEMP/TMP/PYTEST_DEBUG_TEMPROOT，再执行：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --tb=short
```

```text
270 passed, 4 warnings in 90.90s (0:01:30)
```

4 个 warning 来自已有 Starlette/httpx 和 websockets 弃用提示，未屏蔽。测试未调用真实模型。没有遇到 0xC0000142。

完整输出在 `.hqagent/reviews/R1-FZ12-{generate,offline-package,protocol-validation,protocol-tests,hub-tests}.log`，只规范文件末尾换行，不删警告或结果。

## 下游要求

- **P1**：云端 HTTP 和 Worker wireRevision=1 无变化，无需按包版本拒绝 0.6.2 Worker；不能把本机 Cookie 当云端会话。
- **P2**：在既有本机 v2 认证组实现四个等价入口，复用同一连接服务、幂等状态及 DTO。覆盖无会话、非法/缺少 Origin、缺少幂等键、幂等冲突和正常响应的 no-store。保留 v1；禁止为了浏览器访问把 Hub Token 返回给前端。新路由实现由另条线负责，本轮只读业务现状。
- **P3-B**：本机 Cookie 会话下直接调用新增路由；写请求使用既有 v2 网关与幂等键。可轮询 GET link，避免较旧的并发响应覆盖新状态；鉴权失效回到本机连接流程，不能改用云端 Cookie 或要求 Hub Token。
- **主代理**：前端验证和 P2 新路由真实联调由集成线完成。冻结提交和登记提交待审核后合回 integration/phase1，本分支没有主动合回。

## 提交记录

- `96b7adf`：合入已审核集成基线。
- `1e00d2c`：0.6.2 契约、三端版本常量、D44、路由检查冻结。
- 冻结登记、日志及本回执在随后交付记录提交中。

每次提交后执行 git log -1 --format=%B 自查；提交信息没有任何模型署名、Co-Authored-By 或生成工具标记。本轮没有新增待裁决项。
