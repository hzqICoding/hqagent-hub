# R1-P3B 返修 1

审核结论：
- 范围合规，无署名。
- 实测 typecheck 通过，229 passed。
- 登录、配对、设备、三层状态展示、撤回、错误码中文化做得完整。Cookie 与 CSRF 只放内存，这一点正确。

但有三个必须修的问题。第一个会让手机端在真实使用时**看不到任何回复**。

## B1（必须）增量事件拉取后被丢弃

`remote-chat.store.ts` 的 `pollEvents()` 只推进了 `serverCursor`，**完全没有处理 `page.items`**。结果是：初始快照之后，消息、运行状态、命令状态、控制结果、审批都不会更新。Mock 测试没发现，是因为测试只断言游标推进和快照回退。

参考：主代理在真实服务端联调时，浏览器 `/api/v2/events` 实际返回过这些 `type`：
- `conversation.updated`
- `command.updated`：payload 是 RemoteCommandView
- `message.appended`：用户消息
- `worker.event`：payload 是 Worker 上行事件原文，其 `payload.type` 可能为 `command.accepted`、`command.rejected`、`command.completed`、`command.failed`、`command.control_result`、运行状态、消息、审批、进度、目录、`conversation.skip_recorded` 等，见 `packages/protocol/schema/remote.json` 中的 `RemoteBrowserEvent` 与 `RemoteVisibleWorkerEvent`

要求：
1. 按类型把事件应用到当前对话的 messages / runs / commands / approvals，按 id 去重合并；不属于当前对话的事件忽略。
2. `hasMore` 为 true 时连续拉完，再进入下一次等待。
3. 对「能识别对话、但当前不认识具体结构」的事件，退化为刷新该对话的 runs / messages / commands 列表，不要静默丢弃。
4. 控制结果以 `command.control_result` / `command.completed` / `command.failed` 事件或 `RemoteCommandView.controlResult` 为准，不能从执行状态推断。
5. 补测试：
   - 一批事件依次带来命令投递、接单、助手回复消息、运行 succeeded，页面依次显示为已投递、已接单、回复内容、执行成功；
   - 事件里的 `controlResult` 三态分别正确显示；
   - `hasMore` 连续拉取；
   - 其它对话的事件不影响当前对话。

测试数据用契约 Fixture 或按 schema 构造，不要手写与协议不符的结构。

## B2（必须）生产代码里硬编码了 Mock 审批 ID

`rebuildFromSnapshot()` 里有 `gateway.getApproval('approval_demo')`，这是把 Mock 数据写进了真实网关的调用路径，必须删掉。

审批来源改为：
1. 增量事件中的审批事件（见 B1）；
2. 快照中的 `approvals` 字段。协议 0.6.3 正在补这个字段（D45）：快照带出该对话 pending 且未过期的审批，字段可选，缺省按空数组处理。

第 2 点要等 0.6.3 合入后才能写：我会通知你合并 integration/phase1，合并后以 `snapshot.approvals ?? []` 作为初始集合。在那之前先完成 B1 和第 1 点。

补测试：
- 快照带一条待审批，页面能展示；
- 审批事件新增、审批被消费后移除；
- 生产代码路径里不再出现任何 Mock ID（可以用 grep 类测试或代码审查说明）。

## B3（必须）运行模式与路由守卫的前缀冲突

`runtime-mode.ts` 用 `pathname.startsWith('/remote')`，路由守卫用 `to.path.startsWith('/remote')`。电脑端刚合入的「连接手机」页面路径是 `/remote-link`，也会被当成手机远程页：在电脑上刷新这个页面，会被判为 remote 模式并跳到远程登录页。

修法：两处都改为「路径等于 `/remote`，或以 `/remote/` 开头」。

补测试：
- `/remote-link` 判为 local，不触发远程守卫；
- `/remote/chat` 判为 remote。

## 工作方式

- 仍在 `E:\OtherPro\HQAgent-Hub-worktrees\remote-web-gateway`，分支 `feat/remote-web-gateway`。
- **先执行一次** `git merge --no-ff integration/phase1`，拿到 0.6.2 协议、电脑端配对面板（含 `/remote-link` 路由）以及后端改动，冲突按两边功能都保留的原则处理。0.6.3 冻结后我会再通知你合一次。
- 只改 `apps/desktop/**` 和回执，不碰 `packages/protocol`、`apps/hub`、`apps/server`。
- 验收：
  - typecheck 通过；
  - 全部测试通过（合并后的基线数以合并后实测为准），不放宽任何已有断言；
  - 新增测试覆盖 B1–B3。
- 在回执里追加「返修 1」一节，写明改动与测试。
- commit message 不得出现任何 AI 署名，不写 Co-Authored-By，不写「Generated with」之类字样；提交后用 `git log -1 --format=%B` 自查。
