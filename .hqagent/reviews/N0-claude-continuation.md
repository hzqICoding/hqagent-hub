# Claude 连续对话修复验收（2026-09-25）

## 原因与实现

旧适配器基于早期环境的失败实测声明不支持resume，成功任务仍以`supportsResume=false`创建Hub Session，最终`closed/isValid=false`。前端发送成功后默认切到Continue，导致用户的中文追问未到达Claude便被后台拒绝。

- 对Claude 2.1.281重新实测独立CLI进程之间的精确UUID续接，成功回忆首轮随机标识；最低版本同步提升至2.1.281。
- 开启新会话的恢复能力；支持从持久化AgentTaskSpec重建进程与registry，并验证会话ID、工作目录、角色、模型及权限边界。只接受规范UUID，不使用latest或模糊搜索。
- 续轮使用本次目标重新构造统一任务提示词，默认简体中文，明确授权根目录与外部依赖停止点。
- 失败原生进程标记为不可恢复；已知恢复错误时前端阻止重复创建失败轮次，明确选择New后不重新显示上一轮恢复提示。

主集成提交：`6c8a242`、`09220d2`、`bafad5f`。子代理回执：[N0-claude-resume](../handoffs/N0-claude-resume.md)。

## 验证输出

```text
# cwd vnext-integration/apps/hub
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
118 passed, 4 warnings in 13.93s

# cwd vnext-integration
pnpm --filter @hqagent/desktop test
Test Files 32 passed (32)
Tests 142 passed (142)
pnpm --filter @hqagent/desktop typecheck
exit 0
pnpm --filter @hqagent/desktop lint
exit 0
pnpm --filter @hqagent/desktop exec vite build --outDir E:/tmp/hqagent-n0-resume-1790267219756
1717 modules transformed.
built in 5.49s
```

## 旧成功会话的限定数据修复

仅针对`session_f898f0f500894ffc9135c54a855c7547`：确认原Task成功、analyst只读规格、原生UUID文件唯一、记录内UUID一致、cwd均等于`E:/WorkSpace/ua_android`且包含用户/助手历史。保持原会话ID、原生ID与历史内容，仅修正旧能力声明造成的`closed/isValid=false`元数据。

- 排空结果：`active_conversations 0`、`drain_step ready`。
- 正式修复前数据库备份：`E:/tmp/hqagent-n0-trial/updates/backup/hub-20260924T163404.542015Z.db`。
- Worker停止后应用单行修复，事务内复查无运行任务并条件更新，写入`hub_state`修复标记；未修改失败会话，不增加通用CLOSED→IDLE状态迁移。
- 临时修复脚本：`E:/tmp/hqagent-repair-legacy-claude.py`，需`--apply`且端口停止才可修改，默认只验证。

## 原用户对话真实验收

通过实际Hub消息接口，在原对话以Continue提交一次中文转换请求，明确无需重新读项目或修改代码。使用固定Idempotency-Key，未自动重试原分析。

```json
{"runId":"run_bb5177fdb9944e579427a70fec326587","status":"succeeded","error":null,"nodes":[{"status":"succeeded","sameNativeSession":true,"chineseCharacters":877,"error":null}]}
```

原生ID仍为`ced37995-e1ae-43e4-84d6-04ec9c80dda9`，Hub Session最终`idle/isValid=true/turnCount=2`。中文助手消息已写回原对话，开头为“以下是上一轮 RTK 调用链分析结果的简体中文版”。

服务正常HTTP 200，当前前端目录为上述构建目录；启动日志`E:/tmp/hqagent-n0-trial/startup-20260925-003433.log`。连接码不记入本文。外部前端会话的未提交修改继续保留，未纳入本轮提交。
