---
wp: R16-P0
status: needs-decision
scope_declared: [packages/protocol/**, .hqagent/**]
scope_touched: [.hqagent/handoffs/R16-P0-protocol.md]
build: not-run
tests: not-run
commit: none
open_questions: 1
---

# R1.6-P0 协议核对回执：暂停时的附件上传主体待裁决

本轮没有冻结0.10.0，VERSION仍为0.9.2，线路仍为1/2/3，未改Schema、生成物、OpenAPI、注册表、Fixture或业务代码。开工工作区干净，基线为`9770e4e46a108707c106daed184369dd7234b67b`。本回执只记录核对结果，不是P1/P2/P3开工契约。

已读对话附件方案全文、手机方案§7/§11、现有R1.5/R3契约和api-guide、D40–D51。认可本次明确裁决：方案§8/§11的修订3已被R3占用，应开修订4，支持[1,2,3,4]，包0.10.0、D52；3→4沿双向栅栏和周期探测，结构化unconfirmed只作为控制尝试的栅栏终态，不伪造执行已停止。这部分不需要再次裁决。

## Q1：暂停是否同时禁止Worker的电脑附件同步上传

两条现有要求的交集未明确：

1. `.hqagent/DECISIONS.md` D50：`暂停不关连接/同步/历史；受限业务写拒绝REMOTE_DEVICE_SUSPENDED`。
2. `packages/protocol/remote/R1.5-contract.md` §9.3：`remoteAccess=suspended只暂停手机/开放接口引发的业务写入；绑定、连接、内容同步、busy快照、目录和历史读取全部继续`。
3. 本轮用户规则及`docs/vnext/对话附件方案.md` §5：`暂停远程（D50）时不能上传新附件、不能发消息；已有附件的下载不受影响`，未限定上传方。
4. 同方案§2.2要求电脑本机附件按同步规则上传；本轮同时要求浏览器上传和Worker上传接口。这两条API的调用身份和作用不同。

若“不能上传”包括Worker，则暂停会阻断电脑新附件同步，需明确这是D50的附件例外：文字/忙碌/目录继续，附件变为pending_upload，恢复后重试，不能让PC上正常任务因云端暂停失败。若仅限浏览器上传，则Worker附件同步继续，符合D50，但需在附件规则和Worker HTTP门禁里明确豁免，不能让P1按无条件禁止全部上传实现。

**建议裁决**：暂停只禁止浏览器上传和手机发送；Worker从本机已存在消息发起的附件同步上传继续（仍严格校验设备凭据、owner/store/generation/本机消息绑定、配额、同步开关和删除栅栏），不允许此端点代替浏览器创建或发送消息。已有下载继续。这样不改变D50的电脑独立工作和完整同步语义。

如果主代理选择暂停也禁止Worker上传，也可实现，但请明确附件同步是D50的特定例外及恢复策略。P0不会自行选择并把它写成已确认产品规则。依任务“取舍不明写needs-decision并停在那里”，本轮停止，不自行升版或登记已冻结D52。

## 已完成的只读CLI与代码核实

只执行help，没有传prompt、创建/恢复会话或调用模型：

```text
codex exec --help
  -i, --image <FILE>...  Optional image(s) to attach to the initial prompt
codex exec resume --help
  -i, --image <FILE>     Optional image(s) to attach to the prompt sent after resuming
claude --help
  --input-format <format> ... text, stream-json
  --output-format ... stream-json
```

Codex新建/精确ID续接均有图片输入参数；不能以--last代替绑定ID。P2若沿App Server运行则还需验证该实际transport的图片输入，不可因为exec帮助存在就假定现有Adapter已支持。

Claude help证明stream-json输入选项存在，但未给出图片块格式，不能据此宣称图片已验证可用。`apps/hub/adapters/claude_adapter.py::_launch`当前仅设置output-format stream-json，向stdin写普通message字符串后关闭，没有结构化image输入接线。契约完成时应区分CLI入口支持、Runtime实现和所选模型能力：未验证时catalog必须unknown/unsupported并在发送前拒绝图片，不能凭品牌宣称支持。P2需要实际实现并验证相应输入路径；本轮没有跑模型去验证。

`apps/server/server/service_sync.py::on_hello`和`apps/hub/runtime/remote/delivery.py`已见2→3的结构化unconfirmed终态处理，后续3→4照主代理裁决扩展，不解析错误文本。

## 冻结内容与取舍

当前无冻结内容；未决定Q1，不改变用户限制值、不自行加入PAT附件权限。确认Q1后再定义附件清单、内容寻址/逻辑配额口径、附件状态机、流式HTTP及本机输入、目录图片能力、下载校验/有界失败、可见性/删除证明和修订4完整帧集合。其余用户明确范围继续保留，不另行缩减。

## 下游实施要点（待Q1后正式冻结）

### P1 服务端

暂停的Cookie/Worker上传门禁需按Q1统一；不能先按某种解释发布接口。后续流式读写、内容寻址/引用计数、配额预留及回收、缩略图隔离、24小时未发送清理、真删除及直接查存储验收均按用户方案落实。下载维持Cookie/设备鉴权、attachment/nosniff；不开放PAT。

### P2 Worker/Hub

Q1决定暂停期间是否继续上传本机附件或保留待上传状态；两者都不应阻止本机正常执行。修订4、grant后下载校验、下载期间忙碌/超时/重启兜底、原始文件名不作路径、实际Agent输入及catalog保守能力判断需要在正式契约后实现。

### P3 前端

Q1决定暂停时仅禁手机上传，还是还展示电脑附件待上传；不要用无提示的失效附件ID代替状态。保持上传限额从服务读取、unsupported图片发送前提示、只用服务端缩略图预览、已有原文件下载不受暂停影响。

## 验证与提交边界

仅做只读核对，无协议变更，所以未运行validate/专项测试、不引用旧绿结果冒充0.10.0。未生成真实会话记录/附件、没有模型调用、没有子代理、没有网络请求。未遇到429/0xC0000142/额度错误。只提交本回执，不合回integration；commit字段保留none表示没有协议冻结提交。
