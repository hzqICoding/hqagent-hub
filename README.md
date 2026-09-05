# HQAgent-Hub

本地多 Agent 控制中心。在自己电脑上统一发现、启动、续接和管理 Claude Code、Codex 等 Agent，把它们编成一个有角色分工的团队来干活。

核心是**角色与厂商解耦**：工作流只写 `dispatch(role="architect")`，运行时才决定实际用哪个 Agent。换 Agent 不改工作流代码。

## 仓库结构

```
docs/                    设计与施工文档（先读 docs/分工与并行开工方案.md）
AGENTS.md                所有执行方的开发边界与交付规则
.hqagent/                项目共享记忆：上下文、架构约束、决策、接口冻结记录
packages/protocol/       协议事实源，三端 DTO 由此生成
apps/
  hub/                   Local Hub（Python）
  desktop/src/           桌面前端（Vue 3 + TS）
  desktop/src-tauri/     桌面壳（Rust）
  update-agent/          升级代理（Go，薄封装）
  updater/               安装器（Go，薄封装）
scripts/protocol/        协议生成与校验
build/ scripts/build/ scripts/release/   打包与发布
```

## 常用命令

```powershell
pwsh scripts/protocol/generate.ps1                  # 重新生成三端协议 DTO
pwsh scripts/protocol/validate.ps1                  # 校验协议包
pwsh scripts/protocol/validate.ps1 -CheckGenerated  # CI：检查生成物是否被手改
```

## 分支模型

```
main                  稳定主线
integration/phase1    一期集成分支，所有工作包合并到这里
work/w1-hub           Local Hub 内核
work/w4-frontend      桌面前端
work/w5-shell         桌面壳与本机接入
work/w6-updatekit     共享更新模块与 OTA
```

多个 Agent 禁止共用同一工作目录。每条线在自己的 worktree 里干活：

```powershell
git worktree list
# E:\OtherPro\HQAgent-Hub-worktrees\w1-hub 等
```

## 当前进度

一期（Phase 1）：Windows 本地闭环，Claude + Codex 双 Agent 协作 + 整包 OTA。
云端 Control Plane 与手机 PWA 属于 Phase 2，不在当前范围。

协议 `0.1.0` 已于 FZ-1 冻结，记录见 `.hqagent/INTERFACES.md`。
