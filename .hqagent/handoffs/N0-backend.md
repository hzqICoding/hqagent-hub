# N0 本地对话后端交接

## 变更记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-09-24 | v1 | 本地场景/聊天/API与执行链实现、验证和前端联调入口。 |

## 分支与基线

- 后端：`E:/OtherPro/HQAgent-Hub-worktrees/vnext-backend`，`work/vnext-backend`。
- 前端：`E:/OtherPro/HQAgent-Hub-worktrees/vnext-frontend`，`work/vnext-frontend`，由用户指定的另一个Agent开发。
- 共同协议基线：`3dc070443b06d8d5d4c4e2d9458d2d3502e1d652`。
- 后端代码提交：`f656f0f5c10634920f93978c4e4021800d903187`。
- 执行链子提交：`706c80798b02ecc7c11ee45f42d9a424cb110122`，在后端分支cherry-pick为`a88d6c1`，后端代码提交另有接线修正。
- 原integration修改已在`f602c6b`基线保存；原始patch和SHA-256在`.hqagent/baselines/`。原integration与main的用户修改未改动。
- 尚未合并到`integration/phase1`或main；没有推送。前端完成后再统一联调合并。

## 已实现

1. 本地连接码换HttpOnly Cookie，独立于原Hub Token；跨Origin和未登录请求被拒绝。
2. 三个场景：代码分析、需求规划、开发修复。配置角色Agent/职责/model/effort和可选角色，按版本保存。
3. 对话/消息/运行轮次的SQLite持久化；双标识去重（HTTP key和clientMessageId）；按消息序号排队。
4. 每轮冻结场景配置，最多三个本地执行轮次并行；同一对话串行。
5. 真TaskService去重、失败结果、任务/节点状态、审批回应、过期检查、取消和重启待核实状态。
6. 连续对话通过明确session ID恢复；检查idle和isValid，配置改变或不支持恢复时明确报错。
7. 原生规格落库及Codex恢复重建；多轮复用的session可以按实际使用它的Task查询。
8. 规划/分析等前序节点结果传给后续节点；只读目录不强制Git，写节点仍受worktree与审批约束。
9. CLI模型/effort参数真实传递；Codex使用model/list检查明确配置，提供模型目录API。
10. 内置Runtime注册表；公开本地API、HTTP事件补拉、可选同源静态Web及开发启动参数。

N0沿用旧Task作为每轮执行的内部对象，由LocalConversation/LocalRun做业务映射；未把未来所有vNext实体和远端复制机制一次实现。v1默认工作流保持原行为，v2场景明确指定workflowRoles。

## 前端对接

必读`docs/vnext/前端独立开工说明.md`。协议类型从`@hqagent/protocol`导入；正式本地接口在`packages/protocol/openapi/local-chat.v2.yaml`。

- 所有v2响应使用ApiEnvelope；新消息HTTP202表示入队，不是完成。
- `credentials: include`；写请求带可信Origin，创建/发送/控制/审批带Idempotency-Key。
- 模型为空时表示继承CLI配置；不要把请求型号或目录默认项冒充实际观测型号。
- `GET /api/v2/bootstrap`是后端新增的兼容入口，data沿用已有BootstrapView，无新DTO要求。旧Layout若依赖v1/Bearer，使用该入口或单独LocalLayout。
- 新Run尚未派发时taskId为空、task字段缺省。只有task就绪才展示旧TaskDetailView。
- scene保存时传完整roles数组，包含disabled角色；版本冲突返回409和刷新提示。
- `/api/v2/events`已实现；`/ws/v2/local`未实现，首版使用有退避的HTTP补拉。
- 外部CLI历史导入、图片附件、APK打包/上传、手机控制均不属于本批后端。

前端工作区仍停在共同基线；本文件所列新增bootstrap入口只复用已有类型，不要求前端自行修改协议。集成时由主代理合入后端完整协议。

## 启动方式

后端独立`.venv`已经可用。在后端`apps/hub`目录：

```powershell
../../.venv/Scripts/python.exe -m runtime.main --environment development --port 8765 --data-dir E:/tmp/hqagent-n0-local
```

使用控制台的一次性连接码。前端Vite仅代理`/api`到`http://127.0.0.1:8765`，不设置VITE_HUB_TOKEN。前端构建后，可通过`--web-dir <dist目录>`使用同源页面。依赖重建方式见`apps/hub/README.md`与`requirements.local-lock.txt`。

CLI需要是真实可执行文件，不是仅存在于交互PowerShell里的函数。可以用`HQAGENT_CODEX_PATH`或`HQAGENT_CLAUDE_PATH`指定路径。

## 实际验证

### 后端全集

在`apps/hub`执行：

```text
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
90 passed, 4 warnings in 13.57s
```

随后对最终消息顺序/CLI路径等调整执行定向回归：

```text
pytest tests/test_local_chat.py adapters/tests/test_contract_rules.py -q -p no:cacheprovider
24 passed, 1 warning in 1.22s
```

其中包含只替换供应商Adapter的完整Composition/API/SQLite测试，三轮对话真实复用一个Session；不是只测FakeTaskPort。还验证派发中取消、消息与终态同事务、过期幂等记录不重复启动、上游结果交接。

### 协议与前端兼容

```text
pwsh scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：155 个类型，8 个 Contract Fixture

pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit
exit_code=0
```

前端兼容检查运行在后端工作区的既有前端基线上，不代表用户另一个Agent的新页面已验收。

### 真实CLI（未通过业务成功验收）

```text
Codex model/list:
verified=True model_count=6 reason=None

默认Codex只读任务：
90秒未结束，发出取消，实际任务最终为cancelled。

明确 gpt-5.6-luna / low 的只读任务：
上游返回 exceeded retry limit, last status: 429 Too Many Requests。
本地任务最终failed，duplicateSuppressed=true，readOnlyPreserved=true。

Claude：
claude is not ready；本机仅发现PowerShell函数，未发现Worker可直接启动的CLI。
```

因此只能确认模型目录、会话/事件链和失败/取消处理可达，不能宣称真实AI完成分析或修改通过。后续需在模型额度/服务可用、CLI路径正确的环境重跑：

```powershell
# 仓库根，会调用真实模型并使用正常额度
.venv/Scripts/python.exe -B scripts/e2e/local-chat-smoke.py --runtime codex --model gpt-5.6-luna --effort low
```

真实测试仅使用临时目录中的README标记，未改ua_android或其他用户项目；测试目录保留用于排查，未自动递归删除。

## 已知边界

- Claude当前接入只开放Read/Glob/Grep，不开放shell/写入/宿主审批；声明缺口，不降级伪装完成。
- 真实写任务、多角色真实模型协作和模型重启续接仍需外部运行环境恢复后验收。
- 取消无法确认或重启后原生状态不明时，以paused和failureReason提示人工核实，不假装已经停止或可无损恢复。
- 插件是内置注册机制；没有第三方动态加载、市场或热升级。
- Windows完成本轮测试，macOS/Linux只有路径/进程适配代码，尚未实机验收。
- 完整前端和前后端联合体验等待前端提交；这一交接不标记N0产品整体完成。

## 合并步骤

1. 获取前端SHA与`.hqagent/handoffs/N0-frontend.md`；检查路径所有权和协议差异。
2. 从已保存基线整合两个分支，保留原integration用户改动；不直接覆盖工作目录。
3. 在合并候选工作区运行协议、后端、前端typecheck/test/build。
4. 实测本地连接、场景保存、三轮对话、等待/取消/错误、关闭页面后恢复。
5. 真实Agent成功验收及双方交付完成后，再按用户要求合入integration/phase1。
