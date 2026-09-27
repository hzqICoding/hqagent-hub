> 已作废：这是v0.3镜像+接力的历史复核。当前以v0.4回执为准；Q1已采纳建议B。

# R15-P0 独立只读复核记录

复核代理 `/root/r15_protocol_review`，委派 `gpt-6-astra/high`。下述证据由主代理结合实际文件复查；没有实现协议草稿，没有修改apps/docs。合入基线为 integration/phase1@ab889b3。

## 唯一阻断：Q1共享错误码的冻结边界

- remote.json:18：RemoteError.code 引用 common.ErrorCode。
- common.json:30–34：ErrorCode 通过x-registry引用整个error-codes注册表。
- generate.py:253–262、285–289、417–423：按注册表生成TS联合及Python枚举。
- 注册表追加接力专用码会扩大旧RemoteError的可接受值域，而旧Worker拒绝/失败帧引用该类型。只对比rev1 def文本不足以证明严格性未变。
- 任务明确要求新增接力/镜像只读错误码，因此不能仅复用旧码绕过要求；也不能擅自冻结公共ErrorCode，把HTTP/rev2后续注册语义一起改掉。

主代理运行 `.hqagent/reviews/R15-P0-error-code-probe.py`：用既有生成器在内存生成同一个rev1 helloRejected DTO，两次只差注册表列表中一项。旧列表拒绝REMOTE_HANDOVER_BUSY，新增列表接受。Schema、注册表、Fixture、生成文件与VERSION均未落盘修改。完整输出在同名.log。

最小选项：A允许共享错误码注册表追加作为rev1值域例外，承认新包中的rev1可接受集合扩大且禁止在rev1连接发送这些新码；B严格保留rev1接受集合，授权新增独立冻结错误码类型以及必要Schema引用/生成代码调整。主代理建议B，须明确放行“DTO一字不改”的有限例外。尚未实施任何选项。

## 后续设计注意点（不是新增阻断）

1. **升级须处理双向持久数据。** Worker Outbox保留原帧，服务端wire.py:27要求线路修订与连接一致；单纯将旧事件wireRevision改为2违反不可变重放。Worker commands.py:172对完整命令求hash，:174读回旧receipt_json；server wire.py:39发送时覆盖修订。因此切换水位须涵盖服务端旧命令、Worker Inbox回执及待投影事件，不能只观察Worker Outbox为空。
2. **共享DTO需检查闭包。** RemoteMessageView是浏览器视图，rev1消息实际用RemoteWorkerMessagePayload；可给浏览器增加截断标记而不动旧payload。RemoteApprovalView和RemoteVisibleWorkerEvent另有跨边界复用，新增修订不能修改其旧引用闭包。
3. **删除正文要覆盖副本。** server repository.py的Inbox和browser_outbox均保存正文，events.py按旧正文算摘要去重。删除需涵盖投影、Inbox/Outbox正文，保留无正文的哈希/身份/水位tombstone以阻止迟到重放复活；不能只隐藏列表。本轮用户已明确授权镜像删除语义，无需另造产品阻断。
4. **身份与上下文。** 服务端键为(owner,kind,id)，本地对话ID不能假定在设备/store间全局唯一。应定义稳定的worker/store/localConversationId映射；接力保留原本地conversation→run→session链，不新建一套本地对话冒充继续。远程序号只给run.submit，不能等于本地历史消息数量。

镜像、历史补传、删除和接力本身覆盖R1旧产品限制，属于用户已授权增量；不能把这些预期业务改动错误归类为未授权冲突。
