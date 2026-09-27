# R1 手机远程接入：本机真实联调与合并记录

日期：2026-09-27
审核与联调：主代理

## 合并内容

| 分支 | 内容 | 审核 |
| --- | --- | --- |
| `feat/remote-protocol` | 协议 0.6.0（`c443e12`）→ 0.6.1（`7bfbe95`，D42 线路修订号、D43 本机配对契约） | 通过 |
| `feat/remote-worker` | P2 Worker 远程连接（HEAD `9558da9`，含 G1 坏命令持久化拒绝、G2 接单与执行分离） | 通过 |
| `feat/remote-server` | P1 Hub Server（HEAD `ab05245`，含 F1 签名游标、F2 事件唤醒、F3 保留期、F4 文档） | 通过 |

合并提交：`49a714a`（worker + protocol）、`dff7bda`（server）。均为 `--no-ff`。

## 合并后验证（integration/phase1 工作区）

```text
协议校验通过：258 个类型，109 个 Contract Fixture
协议测试：187 passed
Hub：270 passed, 4 warnings
Server：85 passed, 1 warning
前端：vue-tsc 通过；Tests 201 passed (201)
```

环境说明：集成工作区 `.venv` 原先缺 hatchling / editables / pyyaml，协议包还停在 0.5.0 的非 editable 副本。已补装依赖，并把协议重装为 0.6.1 的 editable 安装。这是环境问题，不涉及代码。

## 本机真实联调

- 服务端：`apps/server` 使用自签证书，以 TLS 监听 `https://localhost:8443`，数据目录临时。
- Worker：P2 版本 Local Hub，数据目录独立，监听端口 18765。
- 手机端：用脚本模拟浏览器，走 Cookie + CSRF。
- 全程只用本机回环地址，不连外网，不涉及阿里云。
- 执行由本机已配置的 Agent 完成。

| 场景 | 结果 |
| --- | --- |
| 本机发起配对 → 浏览器登录 → 短码预览 → 确认 → Worker 上线 | 通过。预览里的设备信息正确；本机 link 状态为 paired + online |
| 目录上报 → 创建远程对话 | 通过。1 个工作区、3 个场景，对话 authority=remote |
| 手机发送「只回复收到」→ 电脑执行 → 结果回到手机 | 通过。约 7 秒后收到 analyst 回复「收到」，run 为 succeeded，带 executionTaskId |
| 本机 HTTP 写 remote 对话 | 通过。返回 409 `CONVERSATION_AUTHORITY_MISMATCH` |
| 停掉 Worker 后手机连发两条 | 通过。设备显示 offline，两条都是 `queued_offline`，序号为 2 和 3 |
| Worker 重启后自动重连 | 通过。两条按序执行，回复「一」「二」；三条命令均为 completed / acknowledged |
| 运行中远程 cancel | 通过。`command.control_result` 为 confirmed / adapter_confirmed，`executionMayStillBeRunning=false`，无残留进程；执行状态为 cancelled，另发 `command.completed` |
| 凭据泄漏检查 | 通过。测试口令在服务端日志和数据库里各出现 0 次；日志不含 Authorization / Bearer / Cookie，只记录操作名和状态码 |

## 未覆盖与后续

1. **P3 前端**：
   - P3-A 移动布局在 `feat/remote-web-mobile`，等用户目测后再合；
   - P3-B 手机远程网关已交给 Gemini；
   - 电脑端配对面板（依赖 D43）尚未派发；
   - 本次联调没有经过真实浏览器界面。
2. **阿里云部署**没有做。部署前需要：
   - 按 `apps/server/README.md` 配好 Caddy 与 `HQREMOTE_PROXY_IPS`；
   - 用真实域名证书；
   - 从外网手机做一次回归。
3. `apps/server` 的测试依赖（pytest、httpx、pyyaml）没有在 `pyproject.toml` / requirements 里声明，由 Integrator 补 test extras。
4. Worker 事件上报仍按 0.2 秒轮询（P2 回执 G3），留作后续优化。
5. 服务端 SQLite 同步运行在事件循环里（README「已知限制」）。R1 负载下可以接受。
6. `docs/vnext` 需要同步 D40–D43：远程契约映射到现有执行内核，另有线路修订号与本机配对契约。
7. **Hub 解绑后的服务端撤销**：设备 Bearer 没有撤销权限，所以本机只能如实显示「服务端撤销未确认」，需要用户到手机端撤销设备。
