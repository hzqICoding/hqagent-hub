# vNext 设计交付校验

## 变更记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-09-24 | v0.2 | 按用户最新方向调整为本地角色对话试用优先；复核本地/远程状态归属、认证与阶段依赖。 |
| 2026-09-24 | v0.1 | 记录文档校验、既有审查会话复用及复核修正。 |

## 本轮范围

交付 `docs/vnext/` 四份 Markdown 和一个集中 JSON 样例文件，更新 `.hqagent/PROJECT_CONTEXT.md` 设计入口及会话登记。未修改业务源码、冻结协议、依赖或原有工作区改动；未执行发布、真实 Agent、APK 构建或数据库迁移。

## 文档校验实际输出

在主仓库通过临时 Python 检查器解析所有 JSON fenced blocks，与 contracts.json 对比，并检查相对链接、代码围栏、行尾空白、关联 ID、conversationSeq 和插件 operation：

```text
PASS: 4 Markdown files; 7 JSON blocks match contracts.json; 12 local links resolve; fences/whitespace/IDs/sequence/operation consistent.
PASS: design entry and session continuation records present.
```

`git diff --check` 退出码 0。本轮为文档变更，没有重复运行上一轮的业务测试；前次 71/92 passed 仅为既有代码基线，详见现状评审。

## 复核结论及处理

复用 `/root/audit_adapters` 与 `/root/audit_orchestration` 原线程，均只读，不新增线程、不重复扫全仓库。

| 发现 | 已纳入设计 |
| --- | --- |
| 请求模型与实际运行模型混用 | requested/resolved 字段及 unknown/validationStatus |
| 历史能力缺少调用映射 | execute.mode、sessionBindingId 和可选 history.attachActive |
| inprocess/stdio 清单混淆 | transport 判别联合、架构匹配与 ArtifactAccessRef |
| Command 接单后缺终态定义 | command.completed/failed，区分执行结果与控制动作结果 |
| 备份恢复后旧 ack 可能裁剪新事件 | storeId 绑定确认游标、换世代清空 ack、旧命令先对账 |
| 用户决定与执行器消费审批混淆 | decision_recorded、dispatching、consumed、delivery_unknown 等状态 |
| 未提交修改不能作为可复现基线 | 明确提交 SHA 或 SHA + 归档 patch/hash 的施工前置 |

主代理补充了执行消息顺序、撤回消息跳过记录、终态 Run 的人工重试新建关联 Run、长驻 App Server 以 turn 终态判断等语义。

下一步入口：`docs/vnext/实施与验收.md` 的 N0-A 首个实施任务书。接口仍属设计草案，正式 Schema/DTO 需在唯一协议包内按仓库流程落地。

## v0.2 本地试用优先调整

用户提出先验证本地不同场景、角色职责与聊天任务效果，再接手机。已调整四份设计文档及项目上下文：N0-A修可靠性，N0-B交付本地聊天/场景/角色配置，N1再建Server和远程连接。补充L01–L05验收、本地认证、Conversation authority与历史不重放规则。

此次小范围文档调整由主代理直接完成，未新建或唤醒子代理；业务代码及既有改动不变。完全断网调用云模型不属于本地版承诺。

调整后实际校验输出：

```text
PASS: 4 Markdown files; 7 JSON examples consistent; 12 local links valid.
PASS: local-first N0-A/N0-B -> N1 ordering; L01-L05 acceptance; local-mode contract present.
```
