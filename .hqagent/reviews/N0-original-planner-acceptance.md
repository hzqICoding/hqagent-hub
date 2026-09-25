# 原规划会话验收与Codex结果修复验收

日期：2026-09-25。范围：实现原会话验收、修复真实Codex返回值解析失败、在E:/tmp计数器项目执行完整真实流程。没有修改业务项目。

## 实现

- 场景增加`reviewMode`，已有独立模式保留；`original_planner`要求三阶段全启用，审核身份沿用planner。模式冻结到Run，改变模式需New。
- 最后节点`roleId=planner, phase=acceptance`，动态绑定本轮规划节点的明确local/native Session ID；保持原cwd、模型配置与只读权限，不把原会话伪装成reviewer，也不默默新建会话。
- Worker从实际实施工作树冻结完整文本源码/哈希、Git差异/基线、真实命令退出记录及原方案，作为证据包内联交回原planner。文件数量上限64、包大小上限256KiB；超限、二进制、路径越界、来源身份不一致明确失败，不静默截断。
- 验收前后核验文件清单/内容、HEAD、分支、包哈希。有效审核报告与执行错误分开：passed/changes_requested/insufficient_evidence；有效否决保留原planner会话以便后续讨论，解析/传输错误不伪造审核结论。
- Codex旧失败thread的最后公开JSON实际符合AgentResult，旧实现把跨item增量拼接成多个JSON导致失败。现在只取本轮最后权威final消息，无final phase时只取最后完整agentMessage；最新无效就失败，绝不回退更早done，也不自动重跑写任务。

设计：[原规划会话验收实施](../../docs/vnext/原规划会话验收实施.md)。适配器与UI回执：`../handoffs/N0-codex-result-contract.md`、`../handoffs/N0-planner-acceptance-ui.md`。

## 自动化输出

```text
# cwd apps/hub
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
146 passed, 4 warnings in 26.01s

# cwd repository
pnpm --filter @hqagent/desktop test
Test Files 37 passed (37)
Tests 163 passed (163)
pnpm --filter @hqagent/desktop typecheck
exit 0
pnpm --filter @hqagent/desktop lint
exit 0
pwsh scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：158 个类型，10 个 Contract Fixture
```

专项测试覆盖精确会话复用、有效否决/证据不足、解析失败不写verdict、证据文件变化与新增文件、超限/越界/二进制材料、原会话不可恢复、暂停后从持久化规格恢复、禁用阶段拒绝、实施Session错配拒绝。Warnings为既有依赖弃用提示。

前端构建：`E:/tmp/hqagent-n0-acceptance-1790295074927`，1717 modules transformed，built in 5.67s。

## 真实完整流程

- 对话：`conversation_9cf598c4aff14d258d5e48fc376bb5ef`，标题“完整验收：Claude原会话规划与复核”。
- Run：`run_0ef1bdb147bc42339c32692a7b498b0f`；Task：`task_4cf48315bc10`。
- 使用原来的独立演示仓库`E:/tmp/HQAgent-Hub-demo-1790269113362`，开发在新worktree`E:/tmp/hqagent-n0-trial/worktrees/task_4cf48315bc10-developer`。

| 阶段 | Agent | Hub Session | 原生会话 | 结果 |
| --- | --- | --- | --- | --- |
| 规划 | Claude | session_fecf59a7dbf541f9be87c178031f8ea3 | 44a8203f-8277-499a-a88e-4a1c73285d0c | succeeded |
| 实施 | Codex | session_453b11212d2a4fbf8d9075cbd183b9ac | 01a0d5e9-ed42-7190-a5d9-457312dff929 | succeeded |
| 原规划者验收 | Claude | 同规划阶段 | 同规划阶段 | succeeded / passed |

验收证据：`evidence_b64965d80046438226f26ca163243f3670238e6dc7139887aa98ed2611337720`。包内文件为index.html、src/counter.js、tests/counter.test.cjs，文件哈希与实际开发产物匹配。

真实Codex工具事件：`node --test tests/counter.test.cjs`，tests 11 / pass 11 / fail 0，exitCode=0。另一个Git差异查看命令exitCode=1，原规划者正确区分正常差异返回值与测试失败。

原规划者最终结论为“通过，没有发现阻断问题”，逐项核对源码、边界、快捷键、提示显隐及测试证据，并明确没有重新运行测试或跨目录读取；提出Ctrl/Meta快捷键处理、非整数输入等非阻断建议，不擅自扩大本轮需求。

主代理补充DOM验证：

```json
{"domInteraction":"passed","range":"0..10","upperHint":true,"reset":true,"keyboard":true,"scriptErrors":0}
{"previewUpdated":"http://127.0.0.1:8766/","sourceTask":"task_4cf48315bc10","assetsMatch":true,"demoMainClean":true}
```

预览仍为`E:/tmp/hqagent-counter-preview-task_238f4929a79e/index.html`，两份静态资产HTTP哈希与已验收的新worktree一致。demo主分支保持初始提交且干净，没有自动提交/合并/推送。旧解析失败的任务保留原失败状态，没有篡改历史记录。

本阶段不含双路对比、自动修复循环或真人浏览器像素验收；真实原生流程、源码/日志证据与DOM交互已验证。

## 用户手工验收

2026-09-25，用户在重新连接后按页面验收清单操作，并明确回复“全部通过”：

- 三阶段记录均成功，原规划者验收结论为通过。
- 规划与验收的原生会话ID相同，实施者使用独立会话。
- 计数器达到10显示“已达上限”，减到9或重置后提示消失。
- 场景配置中的验收方式选择项正常，当前为原规划者验收。

本轮功能验收关闭，作为后续回归基线。人工审批的批准/拒绝/重复提交和取消流程不包含在此次用户验收结论内。
