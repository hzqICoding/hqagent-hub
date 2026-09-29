# R1.5+ 联调与部署记录（D50：设备管理 + PAT + 全量接口规范）

- 日期：2026-09-28
- integration/phase1：`68c4fd6`（含协议 0.8.0、P1 服务端、P3 前端）
- 审核记录：`R15plus-P0-protocol-review.md`（协议与服务端）

## P3 前端审核

- 交付：`feat/r15-web`，提交 `796fedc`、`78aa14c`，回执 `.hqagent/handoffs/R15plus-P3-frontend-receipt.md`；执行会话 codex `01a0e638…`（medium）。
- 主代理复跑：typecheck、lint 通过；vitest 56 个文件、**318 passed**。
- 截图核对：设备「更多」弹窗包含暂停、显示名、删除；签发弹窗只显示一次示例令牌，并提示关闭后无法再看。
- 已知的协议展示缺口：0.8.0 的设备分页没有撤销总数。未展开时显示「已撤销（展开查看）」，展开后才显示真实数量。没有自造字段，可以接受。
- 结论：通过，已合入。

## 本机真实联调

环境：本机真实 uvicorn 服务端（自签 TLS，localhost:8443）；两个真实 Hub 进程；真实 Codex。脚本在主代理 scratchpad 的 `joint/r15plus.py`。

| 场景 | 结果 |
| --- | --- |
| 公开规范 | `GET /api/v2/openapi.json` 无需登录，返回 200，version 0.8.0 |
| requestId | 404 响应头的 `X-Request-Id` 与信封一致；服务端日志中能按 requestId 找到恰好一条结构化记录（operation、状态、错误码、耗时）；日志里查不到口令 |
| PAT | 签发 201，令牌以 `hqr_pat_` 开头；服务端数据库和列表里都查不到明文。Bearer 调用结果：读设备 200；修改设备 403 `SCOPE_INSUFFICIENT`；访问对话 403；用 Bearer 签发令牌 403；Cookie 与 Bearer 同时带 400 `REMOTE_AUTH_AMBIGUOUS`；吊销后立即 401 |
| 暂停 / 恢复 | 暂停 200；用过期版本修改 409 CONFLICT；暂停中发送 409 `REMOTE_DEVICE_SUSPENDED`；历史仍可读；暂停中取消运行成功（cancelled）；恢复后在线，发送成功（succeeded） |
| 删除 | 第二台电脑删除 200，`executionMayStillBeRunning=true`；列表（含已撤销的）不再出现；直接访问和第二次删除都返回 404；数据库中该电脑的对话正文与项目名零命中；该电脑本地 link 变为 revoked，`REMOTE_DEVICE_REVOKED` |

## 部署（serverD）

- 按 README 的升级步骤执行：先用 Backup CLI 做一致性快照 `/var/lib/hqremote/backups/hub-20260928-194901.sqlite3`，并备份同期的 `server.key`；停服务 → 更新协议包、服务端代码和手机页面（旧版本保留为 `app.old`、`web.old`）→ migrate（schema 未变）→ 启动。
- 线上验证：`openapi.json` 返回 200 并带 `X-Request-Id`，`journalctl -u hqremote` 中能按这个 requestId 找到记录；手机页面的资源 hash 与本次构建一致。
- 清理：删除了部署时自测用的 `deploy-check` 设备。用户真机测试留下的两台「我的电脑」（一台已撤销、一台离线）没有动。

## 结论

R1.5+ 完成：协议、服务端、前端都已合入，本机联调通过，已上线。下一步开始 R3（原生会话 + §13 授权根目录添加项目）。
