# T-W6 HQUpdateKit / Update Agent / Updater 审核结论

| 项 | 值 |
| --- | --- |
| 审核方 | W0（架构/审核） |
| 被审提交 | `29460e0`（基线 `f892672`；**协议仍是 0.1.0，未合 main**） |
| 审核日期 | 2026-09-06 |
| 结论 | **代码通过。但这是一次「部分交付」，交接单自己就是这么写的，且写对了。** |

## 一、独立复现结果

| 项 | 自述 | W0 实测 | 一致 |
| --- | --- | --- | --- |
| `updatekit go test ./...` | PASS 10.7s | `ok hqupdatekit.local/updatekit 10.461s` | ✅ |
| `update-agent go test ./...` | PASS 2.0s | `ok hqagent.local/update-agent/product 2.148s` | ✅ |
| `updater go test ./...` | 编译过，无测试 | `? .../updater/cmd/hqagent-updater [no test files]` | ✅ |
| `go vet` 三模块 | 通过 | 三模块均无输出 | ✅ |
| go.mod 无 Wails | 0 命中 | `grep -ri wails` 三个 go.mod **零命中** | ✅ |
| Go 代码无厂商名 | — | `claude\|codex\|gemini\|anthropic\|openai` **零命中** | ✅ |
| 路径所有权 | 只碰三个独占目录 + handoff | 42 文件，禁区零命中 | ✅ |
| `acceptance/` 是真实 stdout | 是 | 六份共 12KB，与 handoff 引述逐字对得上 | ✅ |

4559 行入库。提交阻断（`index.lock` / `ORIG_HEAD.lock` 权限拒绝）和 W3 同一个故障，
锁文件现已不存在，W0 代为提交为 `29460e0`，`--check` 干净，无 AI 署名。

## 二、这份交接单值得单独表扬

开头第一句是「**交付状态：实现和本地测试已落地，但 W6 完整验收未完成；未合并 main、
未提交、未发布模块 Tag**」，第 3 节列了 10 条没做完的事，并明确写
「**不能把模拟器测试算成真实 NSIS + 测试证书验收**」。

这是对的。W6 的验收本来就依赖三样本机没有的东西——makensis、HQAgent 测试代码签名
证书、真实运行的 W1/W5。**没有把假 Tauri 安装包的 E2E 说成真实链路通过**，
也没有为了让表格好看去下载工具改证书库。按「部分交付 + 准确列出边界」处理是正解。

## 三、W6 靠读代码找出的 3 个 W1 缺陷——全部复核属实

这是本轮最有价值的产出，比它自己的代码更值钱。

### INT-W6R1 🔴 `update_proxy.py:64` 把裸 DTO 误判成信封，`GET /updates/result` 两个方向都坏

```python
if isinstance(payload, dict) and "success" in payload:
    if not payload.get("success"):
        raise HubError(...)          # ← success=false 走这里
    return payload.get("data")       # ← success=true 走这里
```

而生成的 `UpdateResultView`（`generated/ts/index.ts:1240`）**恰好有一个
`success: boolean` 字段**。于是：

- `success=false`（一次合法的失败/回滚回执，正是用户最需要看到的东西）
  → 被当成错误信封抛 `HubError`，`payload["error"]` 不存在，错误码退化成 `INTERNAL`。
  **用户永远看不到回滚结果。**
- `success=true`（升级成功回执）→ `return payload.get("data")` →
  `UpdateResultView` 没有 `data` 键 → **返回 `None`**。

两条路径都错，方向相反。改法：按路由判断，或要求完整 envelope 结构
（`success` + `requestId` + `protocolVersion` 同时存在才算信封）。

### INT-W6R2 🔴 `app.py:353` 公共 install 排空时不传 Desktop PID

`core/maintenance.py:70-74` 的 `start()` 有 `desktop_pid` / `update_agent_pid` 参数，
`/internal/drain/start`（`:431-435`）也确实传了。但**公共路由
`/api/v1/updates/install`（`:353`）调的是裸 `await drain.start()`**，
两个 PID 都是 None，`waitPids` 因此不完整。

W6 的 Plan v2 校验要求完整进程清单，**缺 Desktop 会直接拒绝安装**——
公共升级入口现在是走不通的。

这条**W0 修不了**：PID 必须来自 W5 的可信进程登记，不能让前端自报
（自报等于让 Vue 决定杀哪个进程）。记为集成项，需 W1+W5 一起接线。

### INT-W6R3 🟡 排空后没检查 `step == ready` 就往下走

`drain.start()` 超时不抛异常，返回的 `DrainProgress` 里 step 可能停在中途，
而 `:353-356` 没人看返回值就直接发起安装。W6 那边会拒，但错误会呈现成
「Update Agent 拒绝」而不是「本机没排空干净」。

## 四、我另外发现的问题

### W6-R1 🟡 `-race` 从未跑过，而这是个并发网络守护进程

```text
go test -race ./... -count=1
go: -race requires cgo; enable cgo by setting CGO_ENABLED=1
```

交接单如实记了「不能算通过」。但严重性要说清楚：Update Agent 是
**长驻的、监听 loopback 的、有并发状态机的守护进程**，还要和 Updater 抢内核锁。
这类程序的数据竞争不会在功能测试里出现，只会在用户机器上偶发。

`-race` 需要 cgo + C 编译器——本机现在有 MSVC（为 Tauri 装的 Build Tools），
`CGO_ENABLED=1` 应该能跑起来。不该长期挂着。

### W6-R2 🟡 本 worktree 协议还是 0.1.0，0.2.0 只用临时 modfile 验过

交接单坦白了：`git archive main packages/protocol/generated/go` 导出到
`E:/tmp/hq-w6-protocol-main`，用 `-modfile` 指过去跑的测试。

「0.2.0 下测试通过」可信（我看了 `protocol-020-tests.txt`），但**分支没合 main，
工作区协议目录仍是 0.1.0**。合并时可能出现临时 modfile 掩盖掉的问题
（replace 路径、go.sum、0.2.0 新增的 adapter-port 生成物）。
必须真合一次再跑一遍，不能拿临时 modfile 的绿当成合并后的绿。

### W6-R3 🔵 测试私钥在 `E:/tmp/hq-w6-test-keys/`

私钥没进仓库（正确），但放在 `E:/tmp` 下——这个目录前几轮一直在清理
（`E:\tmp\hqagent-w5-*`）。公钥 `Qheo...tzTY=` 已进示例配置，私钥一旦误删，
现有签名测试数据就没法再生成。要么写清「可用 `cmd/keygen` 重新生成并更新示例配置」，
要么挪到不会被当垃圾清掉的位置。

### W6-R4 🔵 `acceptance/*.txt` 入库

作为一次性验收证据可以接受，但会随时间失真（版本号、耗时、路径都会变），
且没有机制保证它们和当前代码对得上。建议 README 标一句
「快照，非持续验证」，或将来移到 CI artifact。

## 五、下一步分工

**W0 在 W1 修**：INT-W6R1（信封误判）、INT-W6R3（排空 ready 检查）、
以及独立发现的 WS 关闭码问题（见 `.hqagent/reviews/INT-ws-close-codes.md`）。

**W6 codex（复用会话）**：真合 main 到协议 0.2.0 并重跑三模块测试、
`CGO_ENABLED=1` 跑 `-race`、NSIS 超时子进程收敛（交接单第 3 节第 5 项）。

**留给集成阶段**：INT-W6R2 的 Desktop PID 可信登记（需 W1+W5）、
真实 NSIS/证书 E2E、events 事件投递（依赖 W0 先冻结私有事件包络）。
