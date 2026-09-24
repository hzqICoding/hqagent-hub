# N0 Codex AgentResult 契约修复交接

## 根因证据

失败 Task：`task_add2334b6bfa`。只读检查其唯一原生 thread 日志时，仅提取公开 assistant
message 与 turn 终态，未读取 reasoning、凭据或环境内容。

原生日志有三条公开 assistant 消息，phase 都是 `commentary`，每条都是独立 AgentResult
JSON；最后一条包含三个 changedFiles 和一个通过测试。该最后 JSON 用现有
`parse_agent_result()` 单独校验成功。

当前 Adapter 同时把所有 `item/agentMessage/delta` 追加到同一个
`state.last_agent_message`，没有按 message item 边界重置。多条结构化消息被拼成无效 JSON，
`turn/completed` 因而报“Codex 返回值不符合 AgentResult”。

本机 `codex app-server generate-json-schema --experimental` 确认：

- `turn/completed.turn.items` 是当前 turn 的权威 ThreadItem 列表。
- `agentMessage` 必含 `text`，可选 `phase=commentary|final_answer|null`。
- provider 不保证 phase 一定存在，因此不能要求所有模型都发 `final_answer`。

## 修复

- delta 只发进度事件，不再作为最终结果缓存。
- turn 完成时优先从 `turn.items` 提取 agentMessage；存在 `final_answer` 时只解析 final，
  否则按消息顺序从后向前选择第一个严格通过 AgentResult 校验的候选。
- 若 turn 未携带 items，才使用已完成 vendor items；两者都没有时兼容旧
  `last_agent_message`。
- 任意文字不会被包装成 `status=done`。所有候选无效时仍返回 AdapterFailure。
- 失败诊断只保存候选数量、phase、错误类型/字段位置，不保存候选原文。
- `commandExecution` 完成事件将真实整数且非 bool 的 `exitCode` 映射到
  `AgentToolCallPayload.exitCode`。

## 验证

测试使用失败原生线程最后公开 JSON 的脱敏 fixture，覆盖多 commentary 拼接复现、
final_answer 优先、普通文字仍失败且不泄漏、delta 仅进度、command exitCode 类型边界。

协议生成物来自冻结提交 `18a46cbdbad7ed605d67a420036154db22535ad7`，本分支通过
cherry-pick 接入，没有手改协议。

```text
E:\OtherPro\HQAgent-Hub-worktrees\integration\.venv\Scripts\python.exe \
  -m pytest tests\test_codex_result_contract.py adapters\tests -q \
  -p no:cacheprovider --basetemp E:\tmp\pytest-codex-result-contract-final

21 passed, 2 warnings in 0.09s
```

两条 warning 是既有 FastAPI/Starlette TestClient 弃用提示。
