# 项目上下文

> 每条执行线开工前先读这份。目标是让你不必重新扫描整个仓库就能进入状态。
> 长期稳定的信息写在这里；一次性的过程信息写 `handoffs/`。

## 这是什么

HQAgent-Hub = **本地多 Agent 控制中心**。用户在自己电脑上装一个应用，由它统一发现、启动、续接和管理 Claude Code、Codex 等 Agent，把它们编成一个有角色分工的团队来干活。

核心设计是**角色与厂商解耦**：工作流只写 `dispatch(role="architect")`，运行时才由 Role Resolver 根据用户配置和能力匹配决定实际用哪个 Agent。换 Agent 不改工作流代码——这是产品的立身之本，也是一期唯一必须验证的能力。

## 一期范围（Phase 1）

Windows 本地闭环，**不做云端、不做手机、不做支付**。

要跑通的场景：从桌面端提交一条多角色任务 → architect 出方案 → implementer 在独立 worktree 实现 → reviewer 用独立会话复核真实 diff → 危险动作走审批 → 全程事件可追溯 → 整包 OTA 升级能安全排空任务后安装并在失败时回滚。

Antigravity/Gemini 在 Phase 1.1；云端 Control Plane 和手机 PWA 在 Phase 2。

## 进程构成

```
hqagent-desktop.exe       Tauri 壳（W5）+ Vue 前端（W4）
hqagent-core.exe          Local Hub，Python（W1/W2/W3）—— 业务编排都在这
hqagent-update-agent.exe  升级状态、下载、验签（W6）
hqagent-updater.exe       主进程退出后执行安装与回滚（W6）
Agent Worker              Claude / Codex 等被拉起的进程
```

Vue 只跟 Local Hub 说话，一个 Base URL、一个 Token、一条事件序列。Update Agent 是 Hub 的下游，不对前端暴露。

## 几件容易搞错的事

1. **协议包是唯一事实源**。三端 DTO 全部生成，不许手写第二份。要改协议走 `handoffs/`，别在自己端加兼容字段。
2. **会话不复用**。新任务默认新会话，只有显式恢复才续接。同一个 Agent 做实现和审核时必须是两个会话，否则审核等于自己批自己。
3. **权限绑角色不绑品牌**。换 Agent 后权限不变，不会因为换了供应商就扩大本机访问范围。
4. **Token 不进响应体**。前端拿 Hub Token 的唯一途径是 Tauri `invoke`，不是调接口。
5. **多个 Agent 不共用工作目录**。各自 worktree，合并进 `integration/phase1`。

## 数据位置

```
%LOCALAPPDATA%\Programs\HQAgent-Hub\    程序（当前用户级 NSIS，不需要 UAC）
%LOCALAPPDATA%\HQAgent-Hub\
├── data\hub.db                          SQLite，WAL
├── runtime\hub.json                     端口 + Token，ACL 仅当前用户
├── runtime\update-agent.json
├── logs\
├── updates\{staging,backup}\
└── diagnostics\
```

运行期不写安装目录——这是 OTA 整包替换的前提。

## 相关仓库

| 路径 | 关系 |
| --- | --- |
| `E:\OtherPro\OTA-Platform` | 升级服务端，直接复用，不重建 |
| `E:\OtherPro\HQDroidDeck-Desktop` | Go 更新模块的来源（1619 行纯标准库） |
| `E:\OtherPro\HQUpdateKit` | 抽取出的共享更新模块，两个产品共同依赖（W6 建立） |

## 本机工具链前置条件（2026-09-06 更新）

| 工具链 | 状态 | 位置 |
| --- | --- | --- |
| Python 3.13.7 | ✅ | `E:\SoftWare\Python313`。各 worktree 用自己的 `.venv/` |
| Node + pnpm | ✅ | W4 使用 |
| Go | ✅ | `E:\SoftWare\Go`。W6 Update Agent 使用 |
| Rust 1.98.1 / cargo / rustup 1.29.1 | ✅ | **`E:\SoftWare\cargo` + `E:\SoftWareustup`** |
| MSVC 生成工具 + Windows 11 SDK | ✅ | `E:\SoftWare\VSBuildTools`（SDK 在 C 盘，微软写死） |

### MSVC 阻断已解除（2026-09-05 → 2026-09-06）

9 月 5 日 W5 因本机无 MSVC 工具链完全阻断，`cargo check` 在 build script 阶段
即报 `linker link.exe not found` 退出 101。

9 月 6 日装了 **Visual Studio 生成工具 2022 17.14.39**，只勾两个单个组件：

- `MSVC v143 - VS 2022 C++ x64/x86 生成工具`
- `Windows 11 SDK (10.0.26100.7705)`

**没有勾「使用 C++ 的桌面开发」工作负载**——那个会连带 CMake/ATL/MFC/测试工具，
Rust 一个都用不上，多吃 4–5 GB。实际占用 5.48 GB，其中 C 盘 2.8 GB。

产品路径改到 `E:\SoftWare\VSBuildTools`（C 盘当时只剩 13.8 GB）。
注意 `vswhere.exe` 仍在 `C:\Program Files (x86)\Microsoft Visual Studio\Installer\`，
安装器本体不跟随产品路径，验证时别找错地方。

### Rust 装在 E 盘，不是默认的 %USERPROFILE%\.cargo

C 盘空间紧张，`CARGO_HOME` / `RUSTUP_HOME` 用户级环境变量指向 E 盘：

```
CARGO_HOME  = E:\SoftWare\cargo
RUSTUP_HOME = E:\SoftWareustup
PATH       += E:\SoftWare\cargoin
```

工具链是从 Codex 临时装在 `E:	mp\hqagent-w5-cargo` 的那套**原地搬迁**过来的，
不是重装——`settings.toml` 里没有绝对路径，rustup 的 proxy 在运行时读 `RUSTUP_HOME`，
所以搬完直接可用，省掉一次 2 GB 下载。

`rustup toolchain list` 里有两套：`stable-x86_64-pc-windows-msvc`（默认，在用）
和 `stable-x86_64-pc-windows-gnu`（Codex 当时试图绕过 MSVC 留下的，约 700 MB 死重，
确认 msvc 链路稳定后可以 `rustup toolchain uninstall stable-x86_64-pc-windows-gnu`）。

### W5 的收尾清理

`acceptance/run-cargo.ps1` 和 `acceptance/cargo_registry_proxy.py` 是 Codex 为绕开
沙箱网络限制写的本地 sparse registry 代理，默认路径指向已经不存在的 `E:	mp\hqagent-w5-cargo`。
正式工具链就位后**这两个文件已无用**，直接 `cargo check` / `cargo test` 即可。
清理时一并删 `E:	mp\hqagent-w5-registry-cache`、`hqagent-w5-security-acceptance`、
`hqagent-w5-registry-ready.txt`。
