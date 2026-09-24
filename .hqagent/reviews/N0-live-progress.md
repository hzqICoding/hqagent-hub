# 实时进度停滞修复（2026-09-25）

用户截图中的计数器续轮实际已在06:56:33成功完成：`run_8ba15938cb024382bbf26b36a8469368` / `task_15b1e62c166b`。两个节点成功，后端记录732条agent.progress；不是模型任务卡死。

## 修复

- 轮询生命周期与对话响应世代分开：切换对话丢弃旧响应后仍调度下一轮，不会留下isPolling=true但没有定时器的状态。
- 单一轮询请求防重、stop/restart隔离、回到窗口立即刷新；组件卸载后的延迟初始化不启动隐藏轮询。
- 消息/Run快照与事件请求并行；事件接口失败也能显示任务终态和最终回复。当前Run快照中的事件直接显示，不必等全局历史游标追赶。
- 每批最多追赶5页事件，仍有历史则快速续批；历史回包校验视图版本，游标不倒退。
- 普通HTTP请求15秒截止，超时显示可重试错误；目录选择保留125秒窗口。
- 恢复前端交付过程中遗漏的7项既有可靠性回归测试。
- 同时修复Continue节点新建空worktree、实际却仍在原生Session旧cwd执行的不一致：以持久化规格复用真实路径；显式修改allowedPaths、workspace或role拒绝续接。

输入前端交付已按源文件SHA-256固定快照，独立工作区`live-chat-polling`实施；集成输入提交`f811a57`、轮询修复`877028b`；后端`a5ebc99`、`c637a40`。

## 真实验证

```text
pnpm --filter @hqagent/desktop test
Test Files 36 passed (36)
Tests 156 passed (156)

pnpm --filter @hqagent/desktop typecheck
exit 0
pnpm --filter @hqagent/desktop lint
exit 0

# cwd apps/hub
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
125 passed, 4 warnings in 14.89s
```

使用修复后的实际前端Store与Gateway读取正在运行的Hub接口，将本轮局部状态模拟为running后刷新：

```json
{"realHttpState":"succeeded","visibleActivities":744,"finalReplyLoaded":true,"errors":null}
```

临时探针归档`E:/tmp/hqagent-chat-http-probe.test.ts`，只读取HTTP，没有发送模型任务。jsdom与Node的AbortSignal品牌不同，探针传输桥移除该signal；请求超时由独立自动测试覆盖，不把此环境差异当产品问题。可视浏览器验收仍由用户刷新检查。

## 部署与计数器产物

- 前端：`E:/tmp/hqagent-n0-polling-1790291852204`，1717 modules transformed，built in 10.22s。
- 07:21:01重启，日志`E:/tmp/hqagent-n0-trial/startup-20260925-072101.log`；HTTP入口与ChatPage脚本分别与构建产物hash核对一致。
- 停服前active_conversations=0、drain=ready；备份`E:/tmp/hqagent-n0-trial/updates/backup/hub-20260924T232027.966470Z.db`。
- 停服后限定修正已完成计数器Task的Node和task_spec工作树投影，保持事件和代码不变：实际路径为`E:/tmp/hqagent-n0-trial/worktrees/task_238f4929a79e-developer`。审计标记位于hub_state；没有删除错误产生的空工作树。
- 原生Codex本轮测试记录11/11 pass、exit0，未重跑需求。预览两文件已更新到`http://127.0.0.1:8766/`并核对HTTP哈希，上限10生效。
- 复核详情：`E:/tmp/hqagent-n0-trial/counter-followup-review.md`；后台修复回执：[N0-continued-worktree](../handoffs/N0-continued-worktree.md)。所有示例操作在E:/tmp内，未修改业务项目。
