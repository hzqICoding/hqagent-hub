# N0 本地试用修复（2026-09-24）

## 问题与处理

- Claude已安装但缺席：旧实现硬编码`cli.js`；本机2.1.281的npm bin已变为`bin/claude.exe`。按已知包的元数据解析原生或JS入口，拒绝包外路径，真实探测通过。
- Codex读取大输出断连：`asyncio`默认64KiB的`readline`上限能稳定复现。改为16MiB有界上限；读流异常先清理归属进程树，诊断仅保留异常类型/通道/清理状态，禁止自动重投。
- 新建对话增加“选择项目目录”：认证后的本地API启动独立目录选择进程，取消不登记；并发打开拒绝，120秒超时清理窗口。手动输入保留。DTO从协议Schema生成。
- 场景页面“刷新配置”重新发现Agent，不再仅读取发现缓存。

## 实测输出

集成目录`apps/hub`：

```text
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider
103 passed, 4 warnings in 14.23s
```

适配器独立工作区定向测试见`../handoffs/N0-adapter-io.md`，22项通过。上述4个warning为既有依赖弃用提示。

使用真实Python子进程向`_CodexConnection`发送150000字符的JSONL事件：

```json
{"receivedFrameLengths": [150000], "disconnect": [{"alive": false, "detail": "exitCode=0"}]}
```

同一脚本在修复前收到`Separator is not found, and chunk exceed the limit`，未收到事件。

```text
pnpm --filter @hqagent/desktop typecheck
exit 0
pnpm --filter @hqagent/desktop test
Test Files 31 passed (31)
Tests 133 passed (133)
pnpm --filter @hqagent/desktop lint
exit 0
pnpm --filter @hqagent/desktop exec vite build --outDir E:/tmp/hqagent-n0-ui-fix
1713 modules transformed.
built in 7.16s
pwsh scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：157 个类型，8 个 Contract Fixture
```

首次构建撞上外部会话正在保存RunSnapshotDrawer的中间状态而失败；保存完成后以上独立输出构建通过。外部会话还修改了LocalChatLayout、ChatPage、ChatComposer、ChatMessageItem、RunSnapshotDrawer和ChatSidebar宽度；保留这些未提交改动，不纳入本轮修复提交。

## 运行结果与边界

重启前：`active_tasks_and_runs 0`，`drain_step ready`，数据库备份成功。只结束确认归属此次Worker的进程树。

新Worker启动日志：`E:/tmp/hqagent-n0-trial/startup-20260924-223009.log`，错误日志为空；前端服务目录`E:/tmp/hqagent-n0-ui-fix`，地址`http://127.0.0.1:8765/connect`。数据保留原试用目录，重启需要新连接码，本文不保存该码。

```json
{"agents": [{"id": "local.claude.default", "version": "2.1.281 (Claude Code)", "status": "ready"}, {"id": "local.codex.default", "version": "codex-cli 0.153.4", "status": "ready"}]}
```

`healthz`正常，前端HTTP 200。未自动重投用户的RTK分析任务；真实目录窗口点击验收待用户操作，自动化覆盖认证、来源、选中/取消、并发、无效路径、超时和子进程异常。此轮未发起新的模型计费任务。

确认弹窗来源未确认：当前任务库网页审批数为0，已请求用户补充弹窗类型；不能据此推断为Windows UAC或其他工具授权。保留既有沙箱与审批策略。
