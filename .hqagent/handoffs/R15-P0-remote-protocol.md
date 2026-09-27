---
wp: R15-P0
status: needs-decision
scope_declared: [packages/protocol/**, scripts/protocol/**, .hqagent/**]
scope_touched: [".hqagent/DECISIONS.md", ".hqagent/INTERFACES.md", ".hqagent/codex-sessions.md", ".hqagent/handoffs/R15-P0-remote-protocol.md", ".hqagent/reviews/R15-P0-compatibility-review.md", ".hqagent/reviews/R15-P0-error-code-probe.log", ".hqagent/reviews/R15-P0-error-code-probe.py"]
build: fail
tests: fail (0 failed)
commit: 9bb608dcca8be3cb89110934dd6f9f83ce8f27ea
open_questions: 1
---

# R15-P0：Q1裁决前停止冻结

头部build/tests表示**0.7.0交付门禁未通过**，原因是发现冻结约束冲突后依任务要求停下，未实施或运行全套；不是编译错误或pytest断言失败。实际只读复现通过，0项测试失败，不以此冒充完整验收。头部commit是证据提交，不是0.7.0冻结SHA；冻结记录和本回执另提交。

## 当前现场

- 工作区：`E:/OtherPro/HQAgent-Hub-worktrees/remote-protocol`；分支：`feat/remote-protocol`。
- 先执行指定合并，合入 integration/phase1@`ab889b3a04ebf50ee4246dc8e3f27a10751b096c`；merge为`d495c051f836ddf4ca25a992d1cceef4fbe0a097`。没有冲突，没有回滚或合回集成。
- 完整阅读手机远程接入方案v0.3 §11，重读R1-contract §4–§11，并核对Worker/Server wire.py、Schema和持久化代码。
- VERSION仍0.6.3；没有新增类型、错误码、Fixture或修订2帧，没有修改apps/**、docs/**、packages/protocol/**或scripts/protocol/**。scope_touched对ab889b3计算，不把获授权合并带入的业务文件算成本轮修改。
- D46只登记扫码配对的既有前端裁决。D47登记镜像+接力的已确定产品方向和Q1待决状态，未登记协议已冻结或下游可开工。

## Q1：新错误注册码与修订1严格冻结不能同时按现有机制实现

任务一方面要求接力/镜像只读错误码写入registry；另一方面要求修订1 DTO一字不改、不放宽其严格性。

真实引用链：

1. `packages/protocol/schema/remote.json:18`：rev1 RemoteError.code引用common.ErrorCode；helloRejected、command rejected/failed等rev1帧使用RemoteError。
2. `packages/protocol/schema/common.json:30–34`：ErrorCode使用x-registry:error-codes，是闭合注册表值域。
3. `scripts/protocol/generate.py:253–262`、`:285–289`、`:417–423`：从整个registry生成TS联合和Python枚举，没有按线路修订冻结的错误值域。
4. 因此只往registry加一个REMOTE_HANDOVER_BUSY，即使rev1 def文本完全不变，新生成包里的rev1 DTO也开始接受此码，旧包则拒绝。不能以“没改帧字段”宣称可接受集合完全不变。

只读复现命令：

```powershell
.venv/Scripts/python.exe -X utf8 -B .hqagent/reviews/R15-P0-error-code-probe.py
```

真实输出：

```text
wireRevision=1; code=REMOTE_HANDOVER_BUSY
unchanged rev1 DTO + existing registry accepts: False
unchanged rev1 DTO + in-memory registry addition accepts: True
No schema, registry, fixture, generated file or VERSION was written.
```

复现调用仓库实际生成器，用相同Schema在内存生成三种所需类型；唯一差异是内存注册表增加一个码。退出码0。没有落盘篡改registry后再恢复，也没有执行模型或服务。

### 请主代理裁决的两个选项

| 选项 | 需要明确授权 | 影响 |
| --- | --- | --- |
| A：注册表追加例外 | 将rev1冻结限定为帧字段结构；允许共享错误码闭枚举增量扩展 | 可保留现有公共ErrorCode机制；但必须承认新包rev1接受集合扩大。rev1连接仍只发送旧码，新接力码仅HTTP/rev2，需对应映射与测试 |
| B：严格保留rev1接受集合（建议） | 允许新增独立的rev1冻结错误码类型，并允许必要Schema引用/生成类型引用调整，作为“DTO一字不改”的有限例外 | rev1报文结构、旧Fixture和接受/拒绝行为保持原样；HTTP/rev2使用新增registry码。不能擅自把公共ErrorCode永久锁成旧集合，影响全局注册表语义 |

建议B，保持已部署rev1的严格校验范围。具体类型及生成策略在批准后实施并验证；本轮没有自行选定。也没有用CONFLICT等旧码替代明确要求新增的专用码来绕开任务。

## 后续设计注意点：已有授权内可解决，不另列阻断

1. **线路升级覆盖双向持久记录。** server wire.py:27拒绝与当前连接修订不符的帧；:39编码会覆盖修订。Worker commands.py:172对完整命令求hash，:174读取原receipt_json；只改wireRevision可能触发幂等冲突。不能只检查Worker Outbox为空就宣布可切换，应覆盖服务端旧命令、旧回执、待投影事件和持久切换水位。重传不得重写原事件的epoch/seq/正文摘要。
2. **镜像删除覆盖所有正文副本。** 服务端消息投影、Inbox正文、browser_outbox正文都可能含内容。关闭同步时不仅删除可见列表，还要擦除这些副本，以无正文摘要/身份/水位tombstone保留去重和阻止迟到重放复活。此清理属于用户明确授权的删除语义，不再请用户重复确认。
3. **区分本机身份与云端投影身份。** 服务端主键为(owner,kind,id)，不能假设不同设备/store的本地conversationId绝不相撞。需定义稳定映射；接力保留原本地conversation→run→session链，不能复制新本地对话冒充原上下文。远程conversationSeq只分配执行消息，不能直接取本地历史消息数。
4. **修订2表达候选**：独立rev2帧定义/union可以保持rev1引用闭包清晰；当前生成器支持oneOf和命名引用。具体命名与共享范围待Q1裁决后冻结，本轮不交付假定已就绪的DTO。
5. **区分浏览器与Worker消息DTO。** 浏览器RemoteMessageView不是rev1消息payload；rev1使用RemoteWorkerMessagePayload。镜像浏览器截断字段不应误加到旧Worker payload。其它共享类型也需审查引用闭包，不能只看顶层wireRevision。

## P1 / P2 / P3

- P1/P2不要先各自发明rev2错误码/类型或改变现有CODECS；本回执不是开工冻结契约。
- P1后续负责双修订CODECS、镜像正文删除和HTTP投影，不能调用模型或保存模型凭据。
- P2后续负责同步偏好、历史有界补传、连续确认以及原子接力与原模型Session关联；镜像不能提前改变authority，接力不能反向降级。
- P3可按已经裁决的D46推进扫码交互；R1.5镜像/接力API对接等待0.7.0实际冻结。

## 验证与会话记录

最小环境探测成功，未出现0xC0000142。已完成共享枚举只读复现、源码/Schema引用检查和独立只读复核；未改生成物，未离线重装，未跑validate/协议全套/Hub/server全套，不启动Vitest。既有结果不计作本轮0.7.0结果。

独立复核canonical task为`/root/r15_protocol_review`，委派gpt-6-astra/high；结论同样只将Q1列为阻断。真实thread/session及恢复限制见`.hqagent/codex-sessions.md`，证据汇总见`.hqagent/reviews/R15-P0-compatibility-review.md`。只读代理未写文件或运行重复测试。

每次提交后执行git log -1 --format=%B自查，无署名或生成工具标记。等待主代理Q1裁决后从此worktree继续；没有0.7.0冻结SHA。
