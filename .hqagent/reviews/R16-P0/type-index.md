# R1.6新增类型索引

| 类型 | 分类 / 帧tag |
| --- | --- |
| `AttachmentLimits` | metadata / union |
| `RemoteAttachmentLimitsView` | metadata / union |
| `AttachmentManifestItem` | metadata / union |
| `SyncAttachmentItem` | metadata / union |
| `MessageAttachmentView` | metadata / union |
| `RemoteAttachmentView` | metadata / union |
| `AttachmentDeletedView` | metadata / union |
| `LocalAttachmentView` | metadata / union |
| `ImageInputCapability` | metadata / union |
| `RoleImageCapability` | metadata / union |
| `NativeImageCapability` | metadata / union |
| `AttachmentTargetCapabilities` | metadata / union |
| `RemoteV4ApprovalDecisionCommand` | wire4 `approval.decide` |
| `RemoteV4ApprovalEvent` | wire4 `approval.state_changed` |
| `RemoteV4CancelCommand` | wire4 `run.cancel` |
| `RemoteV4CatalogEvent` | wire4 `capability.changed` |
| `RemoteV4CommandAccepted` | wire4 `command.accepted` |
| `RemoteV4CommandCompleted` | wire4 `command.completed` |
| `RemoteV4CommandEnvelope` | metadata / union |
| `RemoteV4CommandFailed` | wire4 `command.failed` |
| `RemoteV4CommandReceipt` | metadata / union |
| `RemoteV4CommandRejected` | wire4 `command.rejected` |
| `RemoteV4CommandWithdrawalCommand` | wire4 `command.withdraw` |
| `RemoteV4ControlObserved` | wire4 `command.control_result` |
| `RemoteV4ConversationGap` | wire4 `conversation.gap` |
| `RemoteV4ConversationSkip` | wire4 `conversation.skip` |
| `RemoteV4EventAck` | wire4 `worker.events_ack` |
| `RemoteV4MessageEvent` | wire4 `message.appended` |
| `RemoteV4OmittedEvents` | wire4 `events.omitted` |
| `RemoteV4PauseCommand` | wire4 `run.pause` |
| `RemoteV4ProgressEvent` | wire4 `run.progress` |
| `RemoteV4ResumeCommand` | wire4 `run.resume` |
| `RemoteV4RetryCommand` | wire4 `run.retry` |
| `RemoteV4RunStateEvent` | wire4 `run.state_changed` |
| `RemoteV4RunSubmitCommand` | wire4 `run.submit` |
| `RemoteV4ServerHeartbeat` | wire4 `server.heartbeat` |
| `RemoteV4ServerOutboundFrame` | metadata / union |
| `RemoteV4SkipRecorded` | wire4 `conversation.skip_recorded` |
| `RemoteV4VisibleWorkerEvent` | metadata / union |
| `RemoteV4WorkerEvent` | metadata / union |
| `RemoteV4WorkerHeartbeat` | wire4 `worker.heartbeat` |
| `RemoteV4WorkerHello` | wire4 `worker.hello` |
| `RemoteV4WorkerHelloAck` | wire4 `worker.hello_ack` |
| `RemoteV4WorkerHelloRejected` | wire4 `worker.hello_rejected` |
| `RemoteV4WorkerOutboundFrame` | metadata / union |
| `RemoteV4ConversationUpserted` | wire4 `sync.conversation.upserted` |
| `RemoteV4MessageSegment` | wire4 `sync.message.segment` |
| `RemoteV4SyncedRunState` | wire4 `sync.run.state` |
| `RemoteV4ConversationDeleted` | wire4 `sync.conversation.deleted` |
| `RemoteV4SyncReset` | wire4 `sync.reset` |
| `RemoteV4BusySnapshot` | wire4 `sync.busy.snapshot` |
| `RemoteV4BackfillProgress` | wire4 `sync.backfill.progress` |
| `RemoteV4CommandReceived` | wire4 `command.received` |
| `RemoteV4DeliveryGrant` | wire4 `command.delivery_granted` |
| `RemoteV4ConversationUpdateCommand` | wire4 `conversation.update` |
| `RemoteV4ExecutionEvent` | metadata / union |
| `RemoteV4ControlConfirmed` | metadata / union |
| `RemoteV4ControlResult` | metadata / union |
| `RemoteV4ConversationCreateCommand` | wire4 `conversation.create` |
| `RemoteV4ContentRedaction` | wire4 `sync.content.redaction` |
| `RemoteV4SyncConversation` | metadata / union |
| `RemoteV4CatalogView` | metadata / union |
| `RemoteWire4Error` | metadata / union |
| `RemoteWire4ErrorCode` | metadata / union |
| `RemoteWire4ApprovalView` | metadata / union |
| `RemoteV4RedactedSlot` | metadata / union |
| `RemoteV4NativeIndexUpserted` | wire4 `native.index.upserted` |
| `RemoteV4NativeIndexDeleted` | wire4 `native.index.deleted` |
| `RemoteV4NativeConfirmationRecorded` | wire4 `native.closure.confirmed` |
| `RemoteV4NativeImportCommand` | wire4 `native.import` |
| `RemoteV4WorkspaceRegisterCommand` | wire4 `workspace.register` |
| `RemoteV4NativeReadQuery` | wire4 `query.native.messages` |
| `RemoteV4DirectoryQuery` | wire4 `query.directory.list` |
| `RemoteV4QueryResultSegment` | wire4 `query.result.segment` |
| `RemoteV4QueryFailed` | wire4 `query.failed` |
| `RemoteV4QueryPayload` | metadata / union |
| `RemoteV4RunSubmitPayload` | metadata / union |
| `RemoteV4SyncMessageSegment` | metadata / union |
| `RemoteV4SceneSummary` | metadata / union |
| `AgentInputAttachment` | adapter-port.json，本机内部路径，不进入HTTP/WSS |
