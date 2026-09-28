# R1.5-P3 前端接口对照（协议 0.7.0）

配合 `R15-P3-frontend-task.md` 使用。类型一律从 `@hqagent/protocol` 导入。完整规则见 `packages/protocol/remote/R1.5-contract.md`；其中「下游实施要点 · 前端」一节见 `.hqagent/handoffs/R15-P0-remote-protocol.md`。

## 手机端（云端服务器 `/api/v2/*`）

| 功能 | 接口 / 类型 | 要点 |
| --- | --- | --- |
| 我的电脑列表 | `GET /devices` → `RemoteDevicePage`；`RemoteDeviceView` | 新字段 `online`、`busySnapshotFresh`、`supportedWireRevisions`。`online` 为 true **不等于可以发送**：还要看设备是否支持修订 2，以及忙碌状态是否新鲜 |
| 对话列表（按电脑、项目） | `GET /conversations?workerId=&workspaceId=` → `RemoteConversationPage` | `RemoteConversationView` 新字段：`workerId`、`visibility`（`both` / `pc_only` / `mobile_only`）、`busy`、`busyFresh`、`busyObservedAt`、`lastActivityAt`、`archived`、`metadataVersion`。`pc_only` 由服务端过滤，手机收不到 |
| 新建对话 | `POST /conversations` → **202** `RemoteQueuedReceipt` | 只是传输回执。要等电脑同步回来、对话出现在列表里，才算创建成功 |
| 改标题、归档、可见性 | `PATCH /conversations/{id}`，body 为 `RemoteSyncConversationInput`（`expectedVersion` 必填，填 `metadataVersion`） | 同样返回 202 回执，以同步回来的结果为准 |
| 消息分页 | `GET /conversations/{id}/messages?before=` → `RemoteSyncMessagePage`（`items`、`hasMore`、`before`、`snapshotCursor`） | 首次请求不带 `before`，返回最新一页；`hasMore` 为 true 时用返回的 `before` 取更早的一页。按 messageId + revision 合并，按电脑的 messageSequence 排序。**不按 offset 移动** |
| 发消息 | `POST /conversations/{id}/messages`，body 为 `RemoteSendMessageInput` | 处理下方错误码。失败时保留输入，**不自动重试** |
| 删除 / 重置 | 浏览器事件 `RemoteBrowserConversationDeleted`、`RemoteBrowserStoreReset` | 收到后清掉本地缓存，不保留旧内容 |

### 新错误码的中文提示

| 错误码 | 提示 |
| --- | --- |
| `REMOTE_DEVICE_OFFLINE` | 设备离线，发送失败（不再排队） |
| `REMOTE_DELIVERY_EXPIRED` | 设备离线，发送失败（30 秒内未送达，电脑不会执行） |
| `REMOTE_CONVERSATION_BUSY` | 电脑上正在进行，结束后再继续 |
| `REMOTE_STATE_NOT_READY` | 正在同步电脑状态，请稍后再试 |
| `REMOTE_SYNC_DISABLED` | 这台电脑已关闭同步 |
| `REMOTE_REVISION_REQUIRED` | 电脑端版本过旧，请升级 HQAgent |
| `REMOTE_SYNC_RESOURCE_LIMIT` | 内容超出同步上限 |
| `REMOTE_SYNC_CONFLICT` | 同步冲突，请刷新 |

**取消不受忙碌限制**，取消按钮一直可点。

## 电脑端（本机 Hub `/api/v2/*`，Cookie 会话）

| 功能 | 接口 / 类型 | 要点 |
| --- | --- | --- |
| 同步总开关 | `GET` / `PUT /api/v2/remote/sync-settings`：`RemoteSyncSettingsView`（`mirrorEnabled`、`version`、`syncGeneration`）；`RemoteSyncSettingsInput`（`mirrorEnabled`、`expectedVersion`） | 默认开。字段名 `mirrorEnabled` 只是兼容命名，表示「同步总开关」，**没有只读镜像的含义** |
| 对话列表 | `GET /api/v2/conversations?includeHidden=&workspaceId=` | `LocalConversationView` 新字段：`visibility`、`busy`、`busyObservedAt`。默认不返回 `mobile_only`，`includeHidden=true` 时返回 |
| 改可见性 | 沿用现有的对话更新接口，`UpdateLocalConversationInput` 新增 `visibility`，需要 `expectedVersion` | |
| 忙碌 | `busy` 为 true 且这一轮不是本机发起时，发送按钮置灰 | 取消可用 |
| 只读限制 | **撤销**。authority 仅作来源标识，本机写入不再返回 409 | |

## 0.7.0 未提供的

- **同步状态**（补传中 / 已同步 / 异常）没有进入 0.7.0 的视图字段。「连接手机」页这一轮只显示开关，不显示同步进度，列为后续项。回执里注明即可，**不要自造字段**。
