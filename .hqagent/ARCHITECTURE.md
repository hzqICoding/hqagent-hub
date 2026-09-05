# 架构约束

> 只写"会影响你怎么写代码"的约束。完整设计见 `docs/施工方案.md`。

## 1. 四层解耦

```
Workflow Task
    ↓ 只引用抽象角色，禁止出现厂商名
Role                    orchestrator / architect / frontend_implementer /
    ↓ 声明所需能力和权限   general_implementer / reviewer / tester / deployer / integrator
Capability              硬能力（session_resume / file_write / shell / …）不可被用户勾选绕过
    ↓ 由 Role Resolver 动态选择
Agent Instance
    ↓ 通过统一 Adapter 协议执行
Agent Adapter           claude / codex（一期）；antigravity（Phase 1.1）
```

代码里出现 `callClaude()` / `if adapter == "codex"` 这类分支就是设计错误。唯一允许识别厂商的地方是 Adapter 实现内部。

## 2. Role Resolver 优先级

```
单次任务覆盖 (roleOverrides)
    ↓
项目 Team Profile
    ↓
用户全局 Team Profile
    ↓
能力自动匹配
    ↓
备用 Agent (fallbackAgentIds)
    ↓
提示用户选择或暂停节点
```

解析结果必须写 `resolveSource`，前端要展示"为什么用了这个 Agent"。降级时必须给可读的 `fallbackReason`。

## 3. 事件总线

- `seq` 由 Hub 单一分配，单调递增，跨重启不回退。
- 断线重连携带 `lastSeq`，Hub 返回 `(after, now]`。
- 相同 `eventId` 幂等，重复投递不得产生第二次状态迁移。
- Update Agent 的事件由 Hub 消费后重新分配 `seq` 再入总线，它自己不分配。

## 4. 并发写控制

- 每个写任务一个 `git worktree` + 独立分支。
- 任务带 `allowedPaths`；结束时 `git diff --name-only` 对照校验。
- 越界即失败，**保留 worktree 现场**，不自动清理。
- 只允许一个 `integrator` 执行最终合并。

## 5. 安全边界

| 边界 | 规则 |
| --- | --- |
| 网络 | Hub 只监听 `127.0.0.1`，随机高位端口 |
| HTTP | 除 `GET /healthz` 外全部 Bearer |
| WebSocket | 先用 Bearer 换 30 秒一次性 Ticket，再握手。WebView 原生 WS 设不了 Header，所以不能直接用 Bearer |
| Token | 每次启动轮换；不进响应体、事件、日志、前端存储 |
| 文件 | `hub.json` 原子写入，ACL 仅当前用户 |
| 承诺范围 | 阻止其他 Windows 用户、普通网页和误调用。**不承诺**抵御已拥有当前用户权限的恶意进程 |

## 6. 升级与数据

- 安装前：停止接收新任务 → 保存会话 → 等待运行任务 → WAL checkpoint + SQLite Backup → 备份程序 → 启 Updater。
- 排空超时进 `waiting_user`，由用户决定继续等、取消任务还是退出，**不直接杀正在写代码的 Agent**。
- 健康检查失败自动回滚程序和数据库备份。
- 迁移默认向前兼容；不可逆迁移必须标 `rollbackCompatible=false`。

## 7. 分层与生成边界

| 层 | 归属 | 是否生成 |
| --- | --- | --- |
| 协议边界 DTO / Envelope / Event / Enum | `packages/protocol/generated/**` | **生成** |
| `UiGateway`、页面 ViewModel、Application Service | `apps/desktop/src/**` | 手写 |
| Hub 内部领域模型 | `apps/hub/**` | 手写，经 Mapper 与 DTO 隔离 |
| 原子 Contract Fixture | `packages/protocol/fixtures/contracts/**` | 手写，受 Schema 校验 |
| UI 组合场景 | `apps/desktop/src/**/scenarios/` | 手写，引用上面的原子 Fixture |
