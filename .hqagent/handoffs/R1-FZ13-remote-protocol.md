---
wp: R1-FZ13
status: done
scope_declared: [packages/protocol/**, scripts/protocol/**, .hqagent/**]
scope_touched: [".hqagent/DECISIONS.md", ".hqagent/INTERFACES.md", ".hqagent/handoffs/R1-FZ13-remote-protocol.md", ".hqagent/reviews/R1-FZ13-generate.log", ".hqagent/reviews/R1-FZ13-hub-tests.log", ".hqagent/reviews/R1-FZ13-offline-package.log", ".hqagent/reviews/R1-FZ13-protocol-tests.log", ".hqagent/reviews/R1-FZ13-protocol-validation.log", ".hqagent/reviews/R1-FZ13-server-tests.log", "packages/protocol/VERSION", "packages/protocol/fixtures/contracts/manifest.json", "packages/protocol/fixtures/contracts/remote.RemoteConversationSnapshot.with-approvals.json", "packages/protocol/generated/go/protocol.go", "packages/protocol/generated/python/models.py", "packages/protocol/generated/ts/index.ts", "packages/protocol/remote/R1-contract.md", "packages/protocol/schema/remote.json", "scripts/protocol/tests/test_remote_link_browser_contract.py", "scripts/protocol/tests/test_remote_link_contract.py", "scripts/protocol/tests/test_remote_snapshot_contract.py"]
build: pass
tests: pass
commit: 500bf1f215fd6d96eb80f9e8677401e57229aa19
open_questions: 0
---

# FZ-R1.3 / 0.6.3 交付回执

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/remote-protocol`，分支 `feat/remote-protocol`。头部 commit 为契约、生成物、D45、Fixture 和协议测试的冻结提交；本回执、日志及冻结登记另提交，避免 SHA 自引用。

## 基线与范围

按要求先合入 integration/phase1@`dd12a2e0dba162078339d7d7c81306926da3af5e`，merge SHA 为 `d442bdc311c4cbd59ee398a730858da880e03b19`，没有冲突。合并带入已审核的 D44 路由与电脑端面板；scope_touched 以 dd12a2e 为基线，只记录本轮自身改动。对该基线的 apps/** 和 docs/** diff 为空，未合回 integration/phase1。

只增加 RemoteConversationSnapshot.approvals 可选字段，类型 RemoteApprovalView[]，maxItems=100；required 列表不变。无新增类型、错误码、路由或事件，Worker 线路修订仍为 1，所有 Worker 帧结构保持原样。版本升为 0.6.3；三端重新生成，TS/Python 增加快照字段，Go 保持既有 x-go 闭包，仅版本常量更新。

## 语义与取舍

- 快照是手机首次打开对话、游标过期后的对账入口，不新增列审批接口。字段缺省按空数组处理，兼容不填此字段的旧服务端；显式 null 不合法，序列化不注入空数组默认值。
- 只含同 owner、同对话、当前仍 pending 且 expiresAt 严格晚于 observedAt 的审批，与投影和 serverCursor 使用同一事务视图。已消费、失效或过期项不再出现在快照。
- 先按归属/状态/期限筛选，再截取 100 条；超出时 hasMore=true，与其它数组截断取或。不能先拿 101 条混合历史再过滤，否则会漏掉后面的有效 pending。hasMore 表明结果可能不完整；本版没有审批分页路由，不声称截断集合就是全部审批。
- 浏览器以快照 approvals 替换初始集合，再从快照 cursor 后应用 approval.state_changed，按 approvalId 更新/移除。重建前旧缓存不能无条件合并回来；审批到期即停止展示为可操作项，不能因没有新事件而延长期限。
- remoteApprovalAllowed=false 不等于隐藏审批。高风险 pending 审批仍需可见，并依既有规则允许远程 reject；approve 限制不变。快照不是授权凭证，提交时仍须重新校验真实状态与期限。
- pending/期限/消费等筛选属于 P1 业务逻辑，JSON Schema 的通用 RemoteApprovalView 仍用于含终态的历史/事件，本次不收窄其 status 枚举。协议 §8 / §9 已明确这些边界。

D45 已按原编号登记，没有编号冲突。执行内核、模型调用、凭据、审批权限不在本次扩展范围。

## Fixture 与协议测试

两种快照样例：

1. `remote.RemoteConversationSnapshot.json`：保留原文件原样，不带 approvals，用于旧服务端兼容。
2. `remote.RemoteConversationSnapshot.with-approvals.json`：新增带审批样例，包含同对话的 waiting_approval Run 和 pending git_push 审批；尚未过期，remoteApprovalAllowed=false，保留 REMOTE_APPROVAL_FORBIDDEN，用来覆盖可拒绝但不可批准的情形。

总计 258 类型 / 110 Fixture，比 0.6.2 只新增一个样例文件。所有既有 Fixture 内容不变。

新增 `test_remote_snapshot_contract.py` 的 13 项测试：两种快照 round-trip；缺字段保持省略并可按空集合读取；空数组/100 条通过；101 条拒绝，即使 hasMore=true；null/错误容器/错误元素拒绝；高风险 pending 样例归属与期限一致；与 dd12a2e 比较仅增加一个非必填浏览器字段，Worker 定义和云端路由/事件/错误码完全不变。新增 Fixture 另被原通用 round-trip 测试自动覆盖，总数 198 → 212。

两份既有协议范围测试做了精确适配：

- FZ-R1.1 的非线路对象相等检查：仅对 RemoteConversationSnapshot 精确校验完整 approvals 属性，再移除此属性与原定义全量比较，未跳过其它字段或任何 Worker 检查。
- FZ-R1.2 的 Schema/版本/Fixture 不变检查：期望只增加同一个精确属性、版本升 0.6.3、manifest 增加唯一新样例；所有旧样例逐个与原基线比较。原本机 OpenAPI 的文档版本 0.6.2 不变，因为这轮没有修改该契约。

没有删除原测试或放宽无关断言；测试变化对应本轮获准的字段和版本增量。

## 本轮验证与真实输出

全部结果均在本 worktree 本轮串行运行，没有复用上轮结果，没有启动 Vitest。tests=pass 指本轮要求的协议/Hub/server 测试通过；前端验证由主代理承担。首次最小命令成功，没有出现 0xC0000142。

根目录将 .venv/Scripts 加到本进程 PATH，执行 `pwsh -NoProfile -File scripts/protocol/generate.ps1`：

```text
protocol 0.6.3: 生成 258 个类型 -> ts / python / go
```

根目录离线重装：

```powershell
.venv/Scripts/python.exe -m pip install --no-index --no-build-isolation --force-reinstall --no-deps -e packages/protocol
```

```text
Successfully built hqagent-protocol
Successfully installed hqagent-protocol-0.2.0
```

0.2.0 是既有 Python 分发元数据版本，不是协议版本；安装后的 DTO 和生成常量来自 0.6.3，未顺手改分发元数据。无联网安装。

根目录 `pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated`，TEMP/TMP 放 worktree 的 .venv/r1fz13-validation：

```text
协议校验通过：258 个类型，110 个 Contract Fixture
```

根目录 `.venv/Scripts/python.exe -B -m pytest scripts/protocol/tests -q -p no:cacheprovider`：

```text
212 passed in 10.32s
```

apps/hub 目录 `../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --tb=short`：

```text
285 passed, 4 warnings in 96.47s (0:01:36)
```

apps/server 目录执行相同相对 Python/pytest 命令：

```text
85 passed, 1 warning in 35.24s
```

Hub/server 分别建立 worktree 内 `.venv/r1fz13-hub-<随机标识>`、`.venv/r1fz13-server-<随机标识>`，设置 TEMP/TMP/PYTEST_DEBUG_TEMPROOT，避开默认临时目录的沙箱权限问题。warning 是已有 Starlette/httpx 和 websockets 弃用提示，原样保留。服务端仍没有填充 approvals，本轮回归验证的是新 DTO 对原来缺字段响应的兼容性。

完整日志：`.hqagent/reviews/R1-FZ13-{generate,offline-package,protocol-validation,protocol-tests,hub-tests,server-tests}.log`。只统一末尾换行，没有删除警告或测试输出。

## P1 / P2 / P3-B 接线与验收

- **P1**：填充入口是 `apps/server/server/service.py` 的 Service.snapshot。现有审批记录可按 owner、kind=approval、parent=conversation 筛选；Service.save 的 parent 来自 conversationId/_conversation。在同一事务中取一致 observedAt/cursor，按有效 pending 过滤后计数截断，并经原 View Mapper 返回。当前函数只填三个旧数组，协议负责人没有修改它。
- **P1 验收**：晚打开可看到已有 pending；游标过期重建可恢复；跨 owner/对话隔离；消费/失效/到期排除（含 expiresAt==observedAt）；高风险不可批准项仍可拒绝；100/101 条边界与 hasMore；失效记录在排序前部时不能遮住后续有效记录；快照与增量交界不漏状态。以上是后续业务验收要求，不是本次已跑测试。
- **P2**：线路帧、RemoteApprovalView、审批事件、策略校验不变，无需因包升级调整 wireRevision，也不能从快照可见性推断批准权限。
- **P3-B**：使用 snapshot.approvals ?? [] 初始化/替换待处理集合，接续 serverCursor 后增量，按 ID 去重更新；收到终态/失效或到期移除/停用。旧服务端缺字段正常处理为空，但不能宣称旧服务端已具备历史 pending 恢复能力。hasMore=true 不得显示“全部审批”。
- **主代理**：前端测试与 P1 填充后的真实恢复联调在集成线继续；本次仅契约冻结，不宣称手机审批缺口已经端到端修复。

## 提交与状态

merge `d442bdc` 合入指定基线；冻结 `500bf1f`；登记、日志与本回执随后单独提交。每次提交后执行 git log -1 --format=%B 自查，不含署名、Co-Authored-By 或生成工具标记。未合回 integration/phase1，没有新增待裁决项。
