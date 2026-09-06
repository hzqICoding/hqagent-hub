# T-W3 编排与安全 审核结论

| 项 | 值 |
| --- | --- |
| 审核方 | W0（架构/审核） |
| 被审提交 | `625dc32`（基线 `5038149`，协议 `0.2.0` / FZ-2 `bfcd91e`） |
| 审核日期 | 2026-09-06 |
| 结论 | **通过。质量是目前六个包里最高的一档。** 7 条协议变更请求需 W0 裁决，其中 2 条卡 W2 |

## 一、独立复现结果

不采信自述，以下由 W0 在 `w3-orchestrator` 重跑：

| 项 | 自述 | W0 实测 | 一致 |
| --- | --- | --- | --- |
| W3 测试 | 40 passed in 0.28s | `40 passed in 0.29s` | ✅ |
| 运行时代码无厂商名 | 无 | `grep -i "claude\|codex\|gemini\|anthropic\|openai\|cursor"` 运行时 **零命中** | ✅ |
| 测试内无厂商名 | — | 同上，**测试里也零命中**（超出要求） | ✅ |
| 路径所有权 | 只碰两个独占目录 + handoff | 31 个文件，`apps/hub/orchestrator/**`、`apps/hub/security/**`、handoff，**禁区零命中** | ✅ |
| W1 回归 13 passed | 是 | 未复跑：W3 对 `apps/hub/core\|api\|storage\|runtime` 零改动，回归恒真 | — |

代码量 2885 行运行时 + 测试，共 4207 行入库。

### 提交阻断已解除

自述里 `index.lock: Permission denied` 是**瞬时**故障（同机另一个 worktree 操作或杀软占句柄），
锁文件现已不存在。W0 已代为提交为 `625dc32`，提交前 `git diff --cached --check`
报了一处 `domain.py:210 new blank line at EOF`，已修掉再提交。commit message
无 AI 署名，已 `git log -1 --format=%B` 核对。

## 二、抽读核验（挑最容易做错的地方）

### 六级优先级的顺序是对的

`docs/分工与并行开工方案.md:351` 定的顺序是
单次任务覆盖 → 项目 Profile → 全局 Profile → **能力自动匹配** → **备用 Agent** → 提示用户。
`role_resolver.py:48-155` 六段严格照此，`capability_match` 在 `fallback` **之前**——
这一点反直觉（用户配的备用链居然排在自动匹配后面），但确实是冻结规格，没写反。

更关键的是 `:96-106` 那段：自动匹配阶段把**所有配置过的实例**（task override、
两级 profile 的 primary 和 fallback、manual）全部排除在候选之外。
所以一个用户手配的备用 Agent 绝不可能被贴上 `capability_match` 标签——
前端右栏那个「为什么用了这个 Agent」的六色区分才是可信的。这是主动想到的坑，不是碰巧。

### 权限只能收紧，写死了

`permissions.py:49-62`：`allow_shell: true` 想把 shell=false 的角色放宽 → 直接
`raise`；`read_only_fs: false` 想把只读角色放宽 → 直接 `raise`。不是忽略，是报错。

### 路径两层校验的设计是对的

`paths.py:91-111` 的 `intersect_patterns` 是**保守**的：两个 glob 谁也不是谁的子集时
直接丢弃这一对，不做拼接。丢弃会让下发给 Adapter 的白名单**偏窄**——但
`allows()`（`:140-144`）做后置复核时**分别检查两层原始 pattern**，不看交集结果。
所以「交集算窄了」只会误伤（Adapter 少被授权），不会漏放。`:142` 还有
`role_patterns and task_patterns` 的 fail-closed：任一层为空 → 全不允许。

## 三、我发现的问题

### W3-R1 🟡 glob 匹配用了 `re.IGNORECASE`，在大小写敏感文件系统上会放宽白名单

`paths.py:59`：`re.compile("".join(pieces), re.IGNORECASE)`

Windows 上这是对的（`docs/` 和 `DOCS/` 是同一个目录）。但路径白名单是安全边界，
在 macOS/Linux（大小写敏感）上 `docs/**` 会放行 `DOCS/secret.md`——那是**另一个目录**。

现在只出 Windows，不构成实际风险；但 `runtime-descriptor` 和整套 OTA 都在为跨平台
做准备，这条会在跨平台那天变成真漏洞，且不会有任何测试报警。

改法：按平台决定 flag，或干脆分两个 `PathScope` 构造入口（Windows 用 IGNORECASE，
其余不用），并补一条大小写变体的越界测试。

### W3-R2 🟡 `.venv` 是从 W1 拷来的，不是从 pyproject 装出来的

handoff「环境说明」写得很坦诚：清华镜像经沙箱代理 `127.0.0.1:7898` 装不下
Hatchling 构建依赖，于是把 W1 `.venv` 里的 Python 3.13.7 / Pydantic 2.13.5 /
pytest 8.4.2 拷了过来并剔掉 W1 的 editable `.pth`。

「40 passed」是真的（我复跑了）。但**这个环境目前无法从仓库配置重建**——
W3 两个目录没有自己的 `pyproject.toml`，测试也不在 W1 的 `testpaths` 里。
Integrator 接线时必须让这两套测试能在一条可重建的环境里跑起来，否则
CI 上等于没有覆盖。这条和 handoff「Integrator 必做接线」第 3 条是同一件事，
但严重性要提一级：**不是配置便利问题，是「测试证据能否复现」的问题**。

### W3-R3 🔵 `.pytest_cache` 也遇到 WinError 5 拒绝访问

我复跑时同样命中（`could not create cache path ...\.pytest_cache\v\cache`）。
和 `index.lock` 是同一类：这台机器上有东西在锁 worktree 里的文件。
不影响结果，但值得查一下是不是杀软实时扫描——它已经吃掉了 codex 的提交动作一次。

## 四、7 条协议变更请求：W0 裁决

W3 没动 `packages/protocol/`（正确），把歧义写进 handoff 提上来。逐条给结论：

| # | 请求 | 裁决 | 理由 |
| --- | --- | --- | --- |
| 1 | `AgentTaskSpec` 缺 `sessionId` 传入通道 | **受理，改** | Hub 是 sessionId 的唯一权威（D7 要求同 Agent 实现/复核必须两个会话）。现在 Hub 生成不了、只能接受 Adapter 返回的 ID，等于把会话身份权交了出去。加可选 `sessionId` 到 `AgentTaskSpec` |
| 2 | `pause` / 运行中 `append_instruction` 在 Adapter Port 无对应方法 | **受理，收窄** | 不加 `pause()`/`sendInstruction()`。多数 CLI Agent 没有真正的暂停语义，加了会逼每个适配器假装实现。改为收窄 `TaskActionInput`：`pause` 只作用于**节点间**（不打断运行中的 Agent），`append_instruction` 只在节点 idle 时可用 |
| 3 | 成功取消应发 `agent.failed` 但 `ErrorCode` 无取消码 | **受理，改事件规则** | 取消是正常路径不是失败。保持 W3 现在的做法（只发 `task.status_changed(to=cancelled)`），修订事件字典里那条规则。`refused` 继续用 `TASK_NOT_CANCELLABLE` |
| 4 | `SessionView.externalSessionId` 必填 vs Handle 可缺省 | **受理，改** | View 字段改可选。空字符串 + `isValid=false` 是能跑，但让前端无法区分「不支持恢复」和「恢复凭据丢了」 |
| 5 | `continue_lineage` 与 `resume()` 返回 void 冲突 | **受理，明确语义** | 定为**新建子 Session 并记 `parentSessionId`**（否则 lineage 这个词没有意义），`resume()` 返回 `AgentSessionHandle` |
| 6 | `RoleId` 生成成八值 StrEnum，自定义角色进不去 | **受理，改生成器** | schema 明确允许自定义角色，生成成闭枚举是生成器的锅。边界类型回退 `str`，另导出内置角色常量 |
| 7 | `event-dictionary.md` 还写 0.1.0 | **受理，纯修文档** | 无争议 |

**其中 1、2 卡 W2。** W2（Agent 适配层）此刻还在跑，它正照着当前冻结的
`adapter-port.json` 写八个方法。第 1 条要改 `AgentTaskSpec`、第 5 条要改
`resume()` 返回值——两条都落在 W2 的实现面上。等 W2 交付后再改，就是返工。

处理顺序：**先看 W2 交出什么**（它可能已经踩到同样的坑，两份独立证据比一份可信），
再一次性出 FZ-2.1，而不是现在单方面改动一个正在被实现的接口。

## 五、给 Integrator 的接线清单（在 handoff 基础上加两条）

handoff「Integrator 必做接线」5 条我核过，全部成立，照做即可。补两条：

6. W3 两套测试要进 CI。最省事的是在共享 pytest 配置里加
   `orchestrator/tests`、`security/tests` 两个 testpath，**不要**把 W3 测试搬进
   W1 独占的 `apps/hub/tests/**`（handoff 第 3 条已经说了，这里只是强调）。
7. 合入后 `apps/hub/pyproject.toml` 的 wheel packages 要加 `orchestrator`、`security`，
   否则 PyInstaller 打包时这两个包不进产物——这正是 W1 当初 R1 那个坑的同款
   （见 `.hqagent/reviews/INT-smoke-W1xW5.md`）。
