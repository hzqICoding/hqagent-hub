# R15-P0 v0.4 协议复核与验证记录

9bb608d / bf15428那一版镜像+接力草稿已作废。当前0.7.0按电脑唯一写入方案实现，Q1已由D49建议B关闭。

只读复核代理 `/root/r15_v04_delivery_review`（gpt-6-astra/high）未写文件、未运行测试。主代理串行完成修改与验证。复核推动三项补齐：

1. 单阶段accepted后执行无法保证“30秒发送失败后不执行”；新增command.received和持久delivery grant门闩，连续ACK不作执行许可，超时与grant由服务端事务互斥决出。
2. reset之前未ACK内容不能继续上传，又不能普通omitted替换；新增无正文redaction控制，以原事件身份/hash补被删除内容的连续覆盖，执行许可/接单/控制事实禁止覆盖。syncGeneration明确指删除栅栏代次，允许覆盖退休旧代次，不要求旧内容与reset代次相等。
3. 修改两处当前OpenAPI中的“解绑后本机只读”说明，保留authority仅作历史来源；旧R1文档明确是历史基线，接口冻结登记旧needs-decision段标作废。

最终协议321类型/173Fixture，304项协议测试通过。新63类型逐一Fixture，110份旧Fixture内容不变；39个rev2具体帧（含独立redaction控制），原27个rev1帧只有D49批准的错误引用替换。

Hub初次运行 `1 failed, 284 passed`：`tests/test_contracts.py::test_all_frozen_contract_fixtures_validate_and_round_trip` 假定每个边界类型都有model_validate/model_dump，新增冻结错误枚举原先只有TypeAdapter入口。协议生成器为x-wire-strict字符串枚举增加同形入口，不包装或改变字符串线上值；没有修改Hub测试。最终复跑 `285 passed, 4 warnings in 79.41s`。

Server最终 `1 failed, 110 passed, 1 warning in 29.94s`，唯一失败 `tests/test_controls_storage.py::test_http_binding_completeness`：

```text
Missing bindings: [('PATCH', '/api/v2/conversations/{conversationId}')]
Extra bindings: []
Mismatch: ('GET', '/api/v2/conversations/{conversationId}/messages') actual= ('RemoteMessagePage', 200) contract= ('RemoteSyncMessagePage', 200)
Mismatch: ('POST', '/api/v2/conversations') actual= ('RemoteConversationView', 201) contract= ('RemoteQueuedReceipt', 202)
```

前一项触发实际失败，后两项由只读AST提取ROUTES与OpenAPI比较确认，是同一测试继续检查时将遇到的绑定适配。全部归P1：新增PATCH、最新优先消息页、电脑执行创建并返回202。未修改apps/server，未删除或放宽该断言。通过的既有业务测试不证明新规则已实现。

没有启动Vitest，没有出现0xC0000142，没有运行真实模型。生成、离线重装、校验和三套测试日志分别保存；初次测试日志也保留，不伪装为最终结果。
