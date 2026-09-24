# N0 前后端联合集成记录

## 变更记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-09-24 | v1 | 接收前端交付，修复真实联调接缝，验证后推进integration/phase1。 |

## 1. 合并结果

- 前端原交付：`bc224022022c0829375fac60cdbda9f529ccdf80`，路径所有权与无AI署名均已核对。
- 后端代码：`f656f0f5c10634920f93978c4e4021800d903187`，交接文档提交`946408b`。
- 候选合并：`3175a4e47835b618c2df17d8c27cef049c21b514`，无Git冲突。
- 联调修正：`5cb7d5a12c6abc7167a9ff37c4d07ed4b4f83031`。
- 已快进到`integration/phase1`，该分支工作区现为`E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration`。
- 没有合入main、没有推送、没有发布安装包。

旧目录`E:/OtherPro/HQAgent-Hub-worktrees/integration`保留在`preserve/phase1-local-20260924`分支，四个未提交文件内容未动。切换前后逐字节比较git diff及porcelain状态一致，patch SHA-256仍为：

```text
c15653987d72c19410f22a99987f14b893e9baf2e15ed68d7bfc6bab440eb957
```

## 2. 本次实际修正

1. `/chat`、`/scenes`使用独立LocalChatLayout，避免真实模式初始化旧Mock布局、状态栏和Inspector。
2. 审批请求补Idempotency-Key；消息、新建对话、控制和审批操作在未确认结果时保存原请求及key，重试不换新ID。
3. 410游标过期使用后端latestSeq恢复，缺有效游标时明确停止并提示，不循环after=0。
4. 即使事件页为空也刷新最终消息，避免回复晚于最后一个Task事件提交而永久不显示。
5. 消息分页读取、跨对话异步响应隔离、Mock/真实模式状态清理和新一轮后的默认续接。
6. 新建对话时可直接登记已有本机目录，修复空项目列表无法开始使用的缺口；创建错误可见。
7. 开发场景的planner可以启停；思考等级使用Runtime返回的efforts，支持实际列出的xhigh/max等值；换Agent时清空旧型号与等级。
8. 开发代理默认端口统一为8765。后端main的development模式本来已允许5173 Origin，本次没有放宽任意Origin；真实HTTP验收使用同源构建产物。
9. Markdown链接限制可用协议并转义属性，防止脚本链接/引号注入；修复不支持的标题/引用格式导致解析不前进的问题。
10. 中文输入法组合期间Enter不发送，单条输入上限与后端保持一致。

## 3. 自动化实际输出

后端在集成工作区源码上运行（最初借用后端venv作为解释器，不改其依赖）：

```text
python -B -m pytest -q -p no:cacheprovider
90 passed, 4 warnings in 14.34s
```

前端最终回归：

```text
pnpm --filter @hqagent/desktop test
Test Files  31 passed (31)
Tests       132 passed (132)

pnpm --filter @hqagent/desktop typecheck
$ vue-tsc --noEmit
exit_code=0

pnpm --filter @hqagent/desktop lint
$ eslint src
exit_code=0

pnpm --filter @hqagent/desktop build
vite v5.4.21 building for production...
✓ 1713 modules transformed.
✓ built in 5.40s

pwsh scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：155 个类型，8 个 Contract Fixture
```

构建仍提示一个空echarts chunk，非失败。后端warning来自既有FastAPI/httpx与websockets弃用提示。

另外已在集成工作区创建独立`.venv`，按锁文件重建依赖并安装本工作区协议/Hub包。导入验证：

```text
runtime= E:\OtherPro\HQAgent-Hub-worktrees\vnext-integration\apps\hub\runtime\main.py
protocol= 0.3.0
```

## 4. 真实HTTP联调

启动真实Worker进程并同源提供前端dist，使用隔离数据目录`E:/tmp/hqagent-n0-joint-20260924`。已完成：

```text
PASS: SPA deep links; unauthenticated rejected; foreign Origin rejected; cookie login verified
PASS: scene save and stale-version conflict
PASS: workspace registration; conversation idempotency; empty history/run state
PASS: live model catalog verified=True, models=6
PASS: 202 enqueue; duplicate suppressed; unsupported model rejected; final reply persisted (no model turn requested)
PASS: prior run snapshot unchanged after scene restoration
PASS: logout invalidates local session
```

能力拒绝场景指定不存在的模型，由本机Runtime在发起模型turn前拒绝，不消耗真实开发任务额度。测试只登记`E:/tmp/hqagent-n0-ui-fixture`，没有修改ua_android。测试Worker已停止，未遗留自动运行服务。

## 5. 尚未验收的部分

- 浏览器控制工具返回无可用Browser，本轮没有完成可视化布局/点击验收。前端组件测试与HTTP接口验证不冒充真实浏览器体验验收。
- 真实模型正常完成分析、修复和跨重启续接仍未通过验收。前轮遇到Codex上游429、Claude仅能通过Shell函数发现；本轮未重复启动付费模型任务。
- macOS/Linux、原生历史全文导入、手机远程、APK交付、安装与OTA不属于本次通过范围。

可以开始本地试用与界面验收，但不能把此开发分支声明为完整生产交付。启动方法见`docs/vnext/本地试用启动.md`。
