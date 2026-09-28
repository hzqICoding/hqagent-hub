# R1.5+ 协议 0.8.0 审核记录（D50）

- 日期：2026-09-28
- 交付：`feat/remote-protocol`。冻结 SHA 为 `739756f`，回执提交为 `2bdc339`，回执文件 `.hqagent/handoffs/R15-P0-devices.md`。
- 执行：codex `01a0ceda…`（gpt-6-astra）。期间两次被主代理中止后扩大范围：第一次加入 PAT，第二次加入全量接口规范。又因本机内存不足（0xC0000142）中断一次，内存释放后续作完成。
- 结论：**通过，已合入 integration/phase1。**

## 范围

- 设备 REST 资源：GET 列表（remoteAccess / online / includeRevoked 过滤）、GET 详情、PATCH（暂停 / 恢复、服务器别名，expectedVersion CAS）、DELETE（删除并保留最小墓碑）。旧的 revocations 路由保留并标为 deprecated。
- 个人访问令牌：只能用 Cookie 会话签发、列表、吊销；格式 `hqr_pat_`；默认 90 天，最长 365 天；权限范围为 `devices:read`、`devices:manage`、`devices:delete`；只有六条设备路由接受令牌；Cookie 与 Bearer 同时出现时拒绝。
- 全量接口规范：`packages/protocol/remote/api-guide.md` 覆盖 27 条现有和 6 条新增 HTTP 操作，以及 72 个错误码的总表；OpenAPI 事实源加自包含 bundle；`api-contract.py` 校验文档与注册表、示例一致；定义 requestId 与 `X-Client-Request-Id` 的排查规范。
- Worker 线路不变（修订 1 / 2），P2 无需改动。

## 主代理复核

在 `remote-protocol` 中重装 0.8.0 后逐条复跑：

```text
协议校验通过：335 个类型，189 个 Contract Fixture
API contract verified: 27 current + 6 planned HTTP operations; 72 error codes; self-contained bundle; examples/auth/request IDs consistent
43 passed in 5.49s
```

合入 integration 后跑 server 全量测试：161 passed、1 failed。失败的是 `test_http_binding_completeness`，原因是 6 条新路由尚未实现，属于预期，由 R1.5+-P1 实现后消除。

## 审核意见（不阻塞合入）

- 删除设备时，首次返回 200，之后同一幂等键也返回 404。这是对副作用的幂等，不重放响应；回执已写明，前端须先确认服务端支持 0.8 能力，再把 404 当作已删除。
- `api-contract.py` 放在 `packages/protocol/remote/` 下，属于 W0 自有校验脚本，可以接受。以后如果并入 `scripts/protocol/validate.ps1` 统一入口会更好。

## 下一步

R1.5+-P1 服务端已派给 `01a0ddec…`（high）。完成审核后再派 P3 前端，本机内存偏紧，所以串行执行。之后进行本机联调，并部署到 serverD。
