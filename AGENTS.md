# HQAgent-Hub 开发边界与交付规则

本文件对**所有**在本仓库工作的人和 Agent 生效。开工前必读，与你的任务话术冲突时以本文件为准。

## 1. 先读什么

| 你负责 | 必读 |
| --- | --- |
| 任何包 | 本文件、[项目文档](docs/项目文档.md)（§6 所有权/冻结与交付、§7 当前有效决策） |
| W0 协议 | `packages/protocol/README.md` |
| W1/W2/W3 Local Hub | `docs/施工方案.md` §5.3/§6/§7/§8、`packages/protocol/openapi/local-hub.v1.yaml` |
| W4 前端 | [前后端交接手册](docs/前后端交接手册.md) |
| W5 桌面壳 | `packages/protocol/schema/runtime-descriptor.json`、`docs/OTA升级架构设计.md` §4.2 |
| W6 OTA | `docs/OTA升级架构设计.md`、`packages/protocol/openapi/update-agent.internal.v1.yaml` |

## 2. 路径所有权（硬规则）

只改[项目文档 §6](docs/项目文档.md#6-工作方式所有权与交付)为你这个包列出的独占可写路径。看到别的包的目录不要动，哪怕只是"顺手修个明显的 bug"。

**`packages/protocol/` 只有 W0 可写。** 任何包发现协议有问题，写 `.hqagent/handoffs/` 变更请求，不要自己加同名兼容字段——那会制造第二个事实源，是本项目最贵的错误。

共享根文件（`package.json`、`pnpm-workspace.yaml`、`pnpm-lock.yaml`、CI 配置、Composition Root）由当批次 Integrator 统一改。需要加依赖就写 handoff。

## 3. 工作目录隔离（硬规则）

多个 Agent **禁止共用同一工作目录**，即使写不同路径也不行——会争用 Git Index、lockfile 和构建产物。

每条执行线在自己的 worktree 里干活：

```
E:\OtherPro\HQAgent-Hub-worktrees\w1-hub        work/w1-hub
E:\OtherPro\HQAgent-Hub-worktrees\w4-frontend   work/w4-frontend
E:\OtherPro\HQAgent-Hub-worktrees\w5-shell      work/w5-shell
E:\OtherPro\HQAgent-Hub-worktrees\w6-updatekit  work/w6-updatekit
```

合并统一进 `integration/phase1`，不直接推 `main`。

## 4. 生成物

`packages/protocol/generated/**` 由 `pwsh scripts/protocol/generate.ps1` 生成，**禁止手改**。
CI 会跑 `pwsh scripts/protocol/validate.ps1 -CheckGenerated` 重新生成并逐字节比对，手改必定被抓。

三端协议边界 DTO 一律从生成物导入，不许再手写一份：

- TS：`import type { TaskDetailView } from '@hqagent/protocol'`
- Python：`from protocol.generated.python import TaskDetailView`
- Go：`import "hqagent.local/protocol"`

内部领域模型可以手写，但必须通过 Mapper 与生成 DTO 隔离，并有契约测试。

## 5. 提交规范（硬规则）

commit message、PR 描述、tag 说明**一律不出现任何 AI 署名**：

- 不写 `Co-Authored-By: Claude/Codex/...`
- 不写 `🤖 Generated with ...`、`由 XX 生成` 及同类字样

提交信息只描述改动本身。提交后用 `git log -1 --format=%B` 自查一遍。

## 6. 交付标准

- **验收项必须是可执行命令或可复现场景**，不接受"我觉得没问题"。
- 汇报时贴真实命令输出，不要用自述总结代替。审核方会读 `git diff` 和命令输出，不读你的总结。
- 做不到的直接说做不到，并说明卡在哪。**硬能力缺失必须上报能力缺口，不许伪装成完成**——这条既是产品设计原则，也是对你的要求。
- 环境问题就说环境问题，不要包装成代码问题去"修复"。

## 7. 安全红线

- Hub Token / Update Agent Token 不得进入任何 HTTP 响应体、事件 payload、日志或前端持久化存储。
- WS Ticket 只能由专用签发接口 `POST /api/v1/auth/ws-ticket` 返回给已鉴权的调用方（短时、单次、绑定能力集）；除此之外同样不得进入其它响应体、事件 payload、日志或前端持久化存储。
- 设备配对码、API 令牌（PAT）等一次性秘密只能由各自契约规定的专用接口交付一次，不得出现在普通 View、事件、截图或日志中。
- 验签失败没有"忽略并继续"入口。
- 危险动作（deploy / git_push / git_merge / delete / shell / network / db_migrate）未经审批不得执行。
- 运行期不写安装目录，用户数据一律写 `%LOCALAPPDATA%\HQAgent-Hub\`。
