# T-W2 Agent 适配层 审核结论

| 项 | 值 |
| --- | --- |
| 审核方 | W0（架构/审核） |
| 被审提交 | `db2a65e`（基线 `5038149`，协议 `0.2.0` / FZ-2 `bfcd91e`） |
| 审核日期 | 2026-09-06 |
| 结论 | **通过。调研阶段是真做了的——这是本轮唯一能被外部证据交叉验证的一份。** |

## 一、独立复现结果

| 项 | 自述 | W0 实测 | 一致 |
| --- | --- | --- | --- |
| 契约测试 | 11 passed in 0.22s | `11 passed in 0.19s` | ✅ |
| `claude --version` | `2.1.263 (Claude Code)` | **我自己跑：`2.1.263 (Claude Code)`** | ✅ |
| `codex --version` | `codex-cli 0.153.4` | **我自己跑：`codex-cli 0.153.4`** | ✅ |
| 无 DTO 重复定义 | 是 | 19 个类全是 Adapter 内部对象，边界 DTO 一律 `from protocol.generated.python` | ✅ |
| Adapter 不认识角色 | — | 全目录只有 `prompt.py:10` 把 `spec.role_id` 拼进提示词，那是任务规格透传，不是厂商绑角色 | ✅ |
| `__pycache__` 不入库 | — | `.gitignore:4` 命中，16 个入库文件里零 `.pyc` | ✅ |
| 路径所有权 | 只碰 adapters + 指定文档 + handoff | 16 文件，`apps/hub/adapters/**`、`docs/Agent适配接入规范.md`（任务书指定）、handoff | ✅ |

3289 行入库。

### 版本号我亲自核了，这一点很重要

上一轮 W1/W5 死在自测之前，这一轮 W3/W6 的证据都只能自证（跑的是它们自己写的测试）。
**W2 是唯一一份能被外部事实交叉验证的**：它声称的两个 CLI 版本号，我在自己的终端
敲同样的命令，逐字符相同。文档里还留了一个真实的被中断 turn ID
`01a076eb-e968-72f1-ad3f-f7164b6e2f4b`。

任务书要求「第一件事是调研，不是写代码」。**它照做了**，而且调研结论直接改变了实现
（见下）。这是本轮质量最高的一个信号。

## 二、抽读核验

### D17 两段式取消：没有伪装成功

`claude_adapter.py:429-435`：

```python
if request.mode is CancelMode.GRACEFUL:
    return self._cancel_result(
        CancelOutcome.REFUSED,
        started,
        "Claude 前台 stream-json 没有已验证的 graceful 中断入口",
        orphan_pids=[state.process.pid],
    )
```

最容易偷懒的写法是 graceful 直接 kill 然后报 `cancelled`——用户看到"已取消"，
实际是被强杀的，孤儿进程还在。这里如实返回 `refused` + 存活 PID，
让 Hub 自己决定要不要升级 force。**调研发现「没有 graceful 入口」，实现就照实写，
没有为了让能力矩阵好看去编一个。**

### 能力降级是往下调的，不是往上吹的

Claude 的 `session_resume`、`tool_approval`、vision、browser **全部 `supported=false`**，
理由是本机沙箱没实测通过。Codex 本机未登录，`health()` 返回 `not_logged_in`
并直接阻断 `start()`。

这是对的方向。适配层最危险的失败模式就是"声称支持、运行时才炸"，而 Role Resolver
（W3）恰恰是拿这些 `capabilities` 做硬匹配的——虚报一个能力，W3 就会把任务派给一个
干不了的 Agent，然后在最贵的地方失败。

## 三、W2 和 W3 独立撞上了同一堵墙

**W2 的 FZ-2.1 候选 #1 和 W3 的 #1 是同一条**：

> `AgentSessionHandle.sessionId` 描述为「Hub 生成后传给 Adapter」，
> 但 `start()` 唯一输入 `AgentTaskSpec` 没有 `sessionId` 字段。

两个包互不通信、分别实现、各自撞墙，结论逐字一致。W2 补了实现层的证据：
当前只能由 Adapter 自己生成 `session_<uuid>`——**会话身份的所有权事实上从 Hub
漏到了 Adapter**，而 D7 要求「同一 Agent 承担实现与审核时必须是两个不同会话」，
这个约束只有 Hub 能保证。

我此前说「等 W2 交出什么再一次性出 FZ-2.1，两份独立证据比一份可信」——现在两份齐了。

## 四、我发现的问题

### W2-R1 🟡 真实闭环没有进测试套件

handoff §4 的 Claude 实测闭环：

```text
HANDLE True True False
EVENTS agent.started,agent.tool_call,...,agent.completed,end:ended
RESULT done CLAUDE_ADAPTER_SMOKE_OK
```

这是一次真跑，很有价值。但它是**一次性手工执行**，不在 `adapters/tests/` 里。
11 条契约测试全是纯离线的（mock 进程、构造事件）。

后果：Claude CLI 一升级改了 JSONL 字段名，整套测试照绿，故障要到用户派任务时才暴露。
建议加一条打了 `@pytest.mark.live` 标记的冒烟测试（默认 skip，CI 或本机手动开），
把这段闭环固化下来。

### W2-R2 🟡 和 W3 同款：环境装不出来，借了 W1 的 venv

`pip install -e packages/protocol` 卡在 build dependency 获取阶段，于是验收改用
`w1-hub/.venv`。测试结果可信（我用同一个 venv 复跑了），但**W2 这两个目录同样没有
可从仓库配置重建的测试环境**。

这已经是第二个包出现同一个问题了（见 `.hqagent/reviews/T-W3-orchestrator.md` W3-R2）。
不是巧合，是缺一份统一的 `apps/hub` 开发环境约定。Integrator 接线时要一次解决，
否则 CI 上这两套测试都跑不起来。

### W2-R3 🔵 11 条测试对 2900 行实现偏薄

契约测试覆盖 D17-D22 是对的优先级（这些是最贵的错误）。但两个 Adapter 的
事件映射、断流分型、审批关联这些实现细节，基本只有正路径被走过。
不阻塞，记在这里供后续补。

## 五、FZ-2.1 裁决更新

W2 提了 7 条，和 W3 的 7 条有交集。合并后的完整裁决另出一份
（见 `.hqagent/DECISIONS.md` 的 FZ-2.1 条目）。这里只记两条 W2 独有的关键项：

| # | 请求 | 裁决 |
| --- | --- | --- |
| W2-2 | `AdapterDescriptor` 的 `installed=false` 描述要求「status 必须是 incompatible 或 unknown」，但该 DTO 根本没有 `status` 字段 | **受理，删描述**。发现状态由 `AdapterManager` 组合 health 后生成 `AgentView.status`，这是对的分层，不该往 Descriptor 里塞 |
| W2-3 | `streamEvents()` 没有冻结单条 Adapter Event 的 DTO | **受理，补冻结**。直接产出 `HubEvent` 不对（全局 `seq`/`eventId` 归 W1），W2 自己定义的内部 `AdapterEvent` 需要提升为冻结形状，否则 W3 消费它时又要各写一套 |
