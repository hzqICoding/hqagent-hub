# R1.5-P3 返修 1

审核对象：`feat/r15-web` @ 50f256a。整体方向正确：网关按 0.7.0 接对了，分页用的是服务端返回的 `before`，降序反转正确，离线立即失败、取消不受忙碌限制、同步总开关和 includeHidden 都到位。下面几处要改，其中 F1–F4 会在真实联调时直接出错。

范围仍然只限 `apps/desktop/**` 和 `.hqagent/handoffs/**`。

## 必改

### F1 新建对话不能伪造对话视图（`remote-chat.store.ts` `createConversation`）

现在 202 回执后，如果列表里还没有这个对话，就手工拼一个 `RemoteConversationView`（`busyFresh: true`、`metadataVersion: 1` 等）插进列表并选中。电脑还没建好这个对话，用户就能对它发消息，状态全是编的。

改为：
- 202 后在列表顶部显示一个**待创建占位**（只是 UI 状态，不是 `RemoteConversationView`，不能选中、不能发送），文案如「正在电脑上创建…」；
- 通过 `conversation.updated` 事件（见 F3）或下一次列表刷新拿到 `conversationId` 与回执相同的真实对话后，移除占位并自动选中；
- 30 秒仍未出现，占位变为「创建失败，请重试」，可关闭；
- 电脑离线时仍然立即失败，不发请求。

### F2 修改对话不能本地先改（`updateConversationSettings`）

现在 PATCH 返回 202 后直接改本地 title / archived / visibility，并把 `metadataVersion` 自行加 1。电脑那边如果冲突或没应用，界面就是错的，下一次 `expectedVersion` 也会是猜出来的，必然触发 `REMOTE_SYNC_CONFLICT`。

改为：
- 202 后不改本地数据，只显示「等待电脑确认」；
- 以 `conversation.updated` 带回的视图为准（含 `metadataVersion`）；
- 收到 `REMOTE_SYNC_CONFLICT` 时重新拉取该对话，并提示「同步冲突，请刷新」。

### F3 `conversation.updated` 要做 upsert，且不依赖当前是否选中了对话（`applyEvent`）

现在：
- `if (!activeId) return` 在它之前，没有选中对话时，所有对话更新都会被丢掉；
- 只更新已存在的对话，不插入新对话。电脑上新建的对话、手机新建后同步回来的对话，都要刷新页面才能看到。

改为：
- 把 `conversation.updated` 的处理移到 `if (!activeId) return` 之前；
- 只处理 `workerId` 等于当前选中电脑的事件；
- 不存在就插入，存在就按 `metadataVersion` 取新值替换，不能用旧值覆盖新值；
- `visibility === 'pc_only'` 的从手机列表移除；如果它是当前对话，就清空当前对话。

### F4 消息合并按 messageId + messageRevision，并按 messageSequence 排序

契约第 100 行规定，客户端按 messageId + messageRevision 去重替换，按 messageSequence 排序，不能直接数组追加。

现在：
- `message.appended` 遇到已存在的 messageId 就忽略。同一条消息的更高 revision（例如 ContentRedaction 后的版本）永远不会生效；
- `loadEarlierMessages` 只做 messageId 去重，把新页直接拼在前面。

改为一个共用的合并函数，`message.appended`、首页和更早页都走它：
- 相同 messageId 时，保留 messageRevision 更大的一条；
- 按 messageSequence 升序排列显示，缺 messageSequence 时退回 createdAt；
- 临时消息（`temp_*`）被真实消息替换的逻辑保留。

## 应改

### F5 版本过旧和状态未就绪要分开提示

`isDeviceSendReady` 把「不支持修订 2」和「busySnapshotFresh 为 false」都提示成「正在同步电脑状态，请稍后再试」。

`supportedWireRevisions` 不含 2 时，应提示 `REMOTE_REVISION_REQUIRED`（「电脑端版本过旧，请升级 HQAgent」）。

### F6 电脑端忙碌提示不要断言来源

`isBusyFromOtherEnd` 依赖内存里的 `locallyInitiatedRunIds`。刷新页面后，本机自己发起的轮次也会显示成「手机上正在进行」。另外，`LocalRunView` 在 0.7.0 里没有来源字段。

改为：
- `conv.busy` 为 true 时一律禁止发送；取消按钮始终可用；
- 提示用中性文案「对话正在进行，结束后再继续」；
- 删除 `locallyInitiatedRunIds` 这套推断，不要自造来源字段。

### F7 小项

- `applyEvent` 里 `conversation.deleted` 和 `store.reset` 两处的 `as any` 去掉，用联合类型自然收窄。
- `RemoteChatPage.vue` 第 127–131 行：`selectDevice` 没有 await，接着又调了一次 `fetchConversations()`，会重复请求并可能竞态。改为 await 之后不再重复拉取。

## 回执必须更正

回执里有几处描述和代码不符，按实际代码改正：

- §1 第 8 项和 §3.2 写「同步状态可视化展示（已同步 / 补传中 / 同步异常）」，§1 第 10 项写 store 新增了 `syncStatus`。代码里都没有，这本来也是这一轮不该做的，**删掉这些描述**。
- §3.1 写「以最旧消息的 messageId 作为 before 游标」。代码实际用的是服务端返回的 `page.before`，这是对的，请把回执改成实际做法。

## 测试

每个 F 至少补一条测试：
- F1：202 后列表里没有可发送的伪对话；事件到达后自动选中；30 秒超时后显示失败。
- F2：202 后标题不变，事件到达后更新；冲突时重新拉取。
- F3：没有选中对话时，新对话事件也能插入列表；其他电脑的事件被忽略；`pc_only` 的对话被移除。
- F4：更高 revision 替换旧版本；乱序到达的消息按 messageSequence 显示；分页合并不重复。
- F5、F6 各一条。

跑 lint、typecheck、test、build，贴真实输出。

## 注意

本机内存偏紧，后端 codex 正在跑 pytest。跑测试时**不要开 watch，不要并行起多个 vitest**。

提交到 `feat/r15-web`，回执追加「返修 1」一节。commit message 不得出现任何 AI 署名。
