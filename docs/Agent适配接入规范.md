# HQAgent-Hub Agent 适配接入规范

> 状态：W2 待完善的占位文档。FZ-2 完成前，本文件不构成已冻结协议；Adapter 的唯一代码级契约以 `packages/protocol/` 和 `.hqagent/INTERFACES.md` 为准。

## 1. 目的

本文件用于记录 Claude、Codex、Antigravity/Gemini 及后续 Agent 的真实接入方式、会话生命周期、事件映射、审批/取消能力和兼容版本，避免实现方依据猜测开发 Adapter。

## 2. W2 必须补齐的调研矩阵

| 项目 | Claude | Codex | Antigravity / Gemini |
| --- | --- | --- | --- |
| 首选接入方式 | 待实测 | 待实测 | Phase 1.1 待实测 |
| 版本与探测命令 | 待补 | 待补 | 待补 |
| 外部会话 ID 获取/恢复 | 待补 | 待补 | 待补 |
| 流式事件格式 | 待补 | 待补 | 待补 |
| 审批与取消语义 | 待补 | 待补 | 待补 |
| 结构化结果能力 | 待补 | 待补 | 待补 |
| 已知限制与降级状态 | 待补 | 待补 | 待补 |

## 3. 固定边界

- Phase 1 必须完成 Claude 与 Codex；Antigravity/Gemini Adapter 属于 Phase 1.1，不阻塞一期。
- Adapter 必须实现 `docs/施工方案.md` §7.2 的统一接口，并声明 §7.3 的能力。
- 新任务默认创建新的本地和外部 Session；只有明确继续或传入 `resume_session_id` 才能恢复指定会话。
- 供应商原始事件必须映射到统一事件字典，未知字段不能直接泄漏到 UI。
- 接入失败或缺少硬能力时返回 `incompatible`/能力缺口，不得伪装成功。
- 正式实现前必须记录实测命令、输入、输出摘要、版本和可复现证据。

## 4. 冻结出口

W2 调研完成后，由 Claude 起草 FZ-2，Codex 做实现可行性复核；最终把 Adapter Port、Session 生命周期、状态/事件映射、审批、取消和错误语义记录到 `.hqagent/INTERFACES.md`，并附对应 Git SHA。
