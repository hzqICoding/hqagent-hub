# T-W5 桌面壳与本机接入 —— 交接（W0 接手完成版）

| 项 | 值 |
| --- | --- |
| 状态 | **编译通过、18 个测试全绿、安全验收 PASS**；有 2 项未接线待补 |
| 原执行方 | Codex，会话在 303,743 token 处被 429 限流打断，未自测 |
| 接手方 | W0（架构/审核），2026-09-06 |
| 提交 | `123b1da` 抢救落库 → `ea0a8f8` 修编译 → `9a35901` 补 ACL 测试 |

## provenance 声明

Codex 死在自测之前，没有留下任何自述结论。**本文件所有结论均为 W0 实测**，
并明确区分「跑出来的」与「读出来的」。

## 一、阻断解除经过

9 月 5 日本包因本机无 MSVC 工具链完全阻断，`cargo check` 在 build script
阶段即 `linker link.exe not found` 退出 101。

9 月 6 日装 Visual Studio 生成工具 2022（只勾 MSVC v143 + Windows 11 SDK
两个单个组件，未装完整 C++ 工作负载），Rust 从 `E:\tmp` 原地搬迁到
`E:\SoftWare\cargo` / `E:\SoftWare\rustup`。详见 `.hqagent/PROJECT_CONTEXT.md`。

## 二、首次编译修了什么

500+ 个 crate 的 Tauri 依赖树一次性编译通过，问题全在本包自己的 2478 行里，
共 4 类 7 个错误，**全部是类型与模块路径修正，没有一处改动安全语义**：

| 位置 | 问题 | 修法 |
| --- | --- | --- |
| `window_state.rs:5` | tauri 2 没有公开的 `tauri::dpi` 路径 | 从 crate 根导入 `PhysicalPosition`/`PhysicalSize` |
| `platform.rs:141` | `AceFlags` 是 u8，`INHERITED_ACE` 是 u32 | `INHERITED_ACE as u8`（值 0x10，在 u8 内） |
| `platform.rs:151` | `EqualSid` 的 PSID 形参是 `*mut c_void` | const→mut 转换，EqualSid 只读不写 |
| `platform.rs:202` | `STILL_ACTIVE` 是 i32，退出码是 u32 | `STILL_ACTIVE as u32` |
| `platform.rs:11` | windows-sys 0.59 里 `LocalFree` 在 `Foundation` 不在 `System::Memory` | 改导入路径 |
| `platform.rs:20` | `ACCESS_ALLOWED_ACE_TYPE` 在 `System::SystemServices` 不在 `Security`，且为 u32 | 改路径 + `as u8` 窄化比较 |
| `Cargo.toml` | 相应特性 | `Win32_System_Memory` → `Win32_System_SystemServices` |

另补 `icons/`：Codex 未建该目录，`tauri-build` 生成 Windows 资源文件时必需。
占位图为 hq-blue `#2563EB` 底 + hub 造型，配色取自前端 palette。
**这是占位图不是设计稿**，正式视觉待出；macOS 的 `icon.icns` 留到 Phase 3。

## 三、验收逐条结果

### 3.1 `cargo check --all-targets`

通过，0 错误，6 个 warning（见第四节）。

### 3.2 `cargo test` —— 18 passed; 0 failed

```
test config::tests::config_defaults_to_autostart_enabled ... ok
test config::tests::config_store_persists_autostart_choice ... ok
test autostart::tests::autostart_command_quotes_path_and_starts_minimized ... ok
test credentials::tests::credential_names_are_namespaced_and_restricted ... ok
test fs_util::tests::atomic_write_replaces_existing_content ... ok
test platform::tests::accepts_current_user_only_acl ... ok
test platform::tests::rejects_inherited_acl ... ok
test platform::tests::rejects_additional_principal ... ok
test process_supervisor::tests::restart_backoff_is_bounded_below_ten_seconds ... ok
test process_supervisor::tests::missing_executable_has_explicit_status ... ok
test process_supervisor::tests::killed_child_restarts_within_ten_seconds ... ok
test runtime_descriptor::tests::descriptor_rejects_stale_instance_id ... ok
test runtime_descriptor::tests::descriptor_rejects_non_loopback_url ... ok
test runtime_descriptor::tests::endpoint_serialization_only_contains_hub_url_and_token ... ok
test security::tests::development_navigation_only_allows_fixed_vite_origin ... ok
test security::tests::packaged_navigation_rejects_remote_and_loopback_hub_pages ... ok
test tray::tests::generated_tray_icon_has_expected_dimensions ... ok
test window_state::tests::persisted_window_size_is_bounded ... ok

test result: ok. 18 passed; 0 failed
```

`killed_child_restarts_within_ten_seconds` 是真起真杀的进程测试，
运行时输出 `SUCCESS: The process with PID 22176 has been terminated.`。

### 3.3 `pwsh -File acceptance/run-security-acceptance.ps1` —— PASS

```
HTTP_NO_TOKEN=401
HTTP_BAD_ORIGIN=403
TICKET_TTL=30
WS_FIRST=HTTP/1.1 101 Switching Protocols
WS_REPLAY=HTTP/1.1 401 Unauthorized
WS_BAD_ORIGIN=HTTP/1.1 403 Forbidden
ACL_OWNER=DESKTOP-TK6GNQ8\ua-hzq
ACL_ALLOWED=DESKTOP-TK6GNQ8\ua-hzq
ACL_INHERITED=False
...\.work\runtime\hub.json DESKTOP-TK6GNQ8\ua-hzq:(F)
Successfully processed 1 files; Failed processing 0 files
DESCRIPTOR_INSTANCE_ID=aff1feb7-fafd-4b59-b552-3bc8969c4fde
SECURITY_ACCEPTANCE=PASS
```

`icacls` 输出只有一条 ACE、只有当前用户、完全控制——这是任务书要求的实测证据。

### 3.4 ⚠️ 这个验收脚本的真实覆盖范围

**必须说清楚**：`run-security-acceptance.ps1` 全程**不加载任何 Rust 产物**。
它只做两件事——用 `curl.exe` 打 `hub_stub.py`（Python），用 `icacls.exe` 看文件。

所以它证明的是「契约语义可实现」和「stub 写出的 ACL 正确」，
**不证明 Rust 侧的读取与校验逻辑正确**。而写 hub.json、发 Ticket、校验 Bearer
本来就是 **W1** 的职责，不是 W5 的。

发现这一点后补了 `platform.rs` 的三个 ACL 测试（`9a35901`）——
此前 `verify_private_file_acl` 这个本包最关键的安全函数**零覆盖**。
现在它对「只授当前用户」放行、对「带继承」和「多授 Everyone」分别拒绝，
都有真实断言。

### 3.5 任务书 8 条验收对照

| 条目 | 状态 | 证据 |
| --- | --- | --- |
| 双击第二次激活已有窗口 | ⬜ 未验证 | 需 GUI 运行时，单测覆盖不到 |
| 杀子进程 10 秒内自动重启 | ✅ | `killed_child_restarts_within_ten_seconds` |
| 关窗口子进程仍在，托盘可恢复 | ⬜ 未验证 | 需 GUI 运行时 |
| 无 token 打 Hub 返回 401 | ✅（stub） | `HTTP_NO_TOKEN=401` |
| `hub.json` ACL 只有当前用户 | ✅ | `icacls` 输出 + 三个 Rust 单测 |
| Bearer 换一次性 Ticket，重放失败 | ✅（stub） | `WS_FIRST=101` / `WS_REPLAY=401` |
| 陈旧 Descriptor 被忽略 | ✅ | `descriptor_rejects_stale_instance_id` |
| 非允许 Origin 被拒 | ✅ | `HTTP_BAD_ORIGIN=403` / `WS_BAD_ORIGIN=403` + 两个导航测试 |

标「stub」的三条是对 W1 侧契约的验证，W1 就绪后需要在真实 Hub 上重跑。
标「未验证」的两条需要 GUI 运行时，等 F5 联调时人工过一遍。

## 四、遗留问题

### 4.1 🟡 Update Agent 描述符路径写了但没接线

编译 warning 暴露的真问题：

```
warning: fields `schema_version`, `port`, `token`, `base_url`, `agent_version`
         are never read  --> src\runtime_descriptor.rs:41
warning: function `validate_update_agent_descriptor` is never used
         --> src\runtime_descriptor.rs:250
```

`UpdateAgentRuntimeDescriptor` 和它的校验函数完整实现了，但**没有任何调用点**。
任务书要求壳「拉起并守护 `hqagent-update-agent.exe`」并读取 `update-agent.json`
（且不得把该 endpoint 交给 Vue）。现在读的那一半没接上。

一期这个 exe 还不存在，所以不阻塞，但**不能当成已完成**。

### 4.2 🟡 `config_process_paths` 是死代码

`state.rs:266`，无调用点。要么接上要么删掉。

### 4.3 🟢 三个琐碎 warning

`platform.rs` 未用的 `ptr` 导入、`lib.rs` 未用的 `Arc`、`runtime_descriptor.rs:190`
多余的 `mut`。`cargo fix --lib -p hqagent-desktop` 可自动修。

### 4.4 🟡 acceptance/ 下两个文件已失效

`run-cargo.ps1` 和 `cargo_registry_proxy.py` 是 Codex 为绕开沙箱网络限制写的
本地 sparse registry 代理，默认路径指向已不存在的 `E:\tmp\hqagent-w5-cargo`。
正式工具链就位后直接 `cargo check` / `cargo test` 即可，这两个文件应删。

### 4.5 🟢 `dist/` 占位

`tauri::generate_context!` 要求 `frontendDist` 路径存在。本 worktree 里前端
没构建过，放了 `apps/desktop/dist/index.html` 占位。`dist/` 在 `.gitignore` 内，
不入库。F5 联调时用 W4 真实构建产物替换。

## 五、静态审阅：这几处不要在后续改动中被简化

读 `runtime_descriptor.rs` 493 行，实现比任务书要求更严，值得保留：

- **陈旧 Descriptor 防护是四重的**：`instanceId` 与当前受管进程一致、`pid` 一致、
  `startedAt` 落在启动窗口内（早于启动 5 秒或晚于当前 30 秒都拒）、
  再加 `process_matches_executable` 确认 pid 未被复用到别的程序。
- **`baseUrl` 是精确校验不是前缀匹配**：scheme 必须 `http`、host 必须 `127.0.0.1`、
  port 必须等于 descriptor 的 port、path 必须 `/`，不允许 query / fragment /
  username / password。堵掉 `http://127.0.0.1:1234@evil.com` 这类解析歧义。
- **healthz 交叉验证身份**：pid / appVersion / protocolVersion / startedAt
  四项必须与 Descriptor 完全一致。
- **读 Descriptor 前防文件替换**：`symlink_metadata` 拒符号链接与非普通文件，
  64 KiB 上限，响应体 256 KiB 上限。
- **`HubEndpoint` 只序列化两个字段**，且有测试断言 `object.len() == 2` 且不含
  `updateAgent`——这是「Vue 拿不到 Update Agent endpoint」契约的机器化守卫。

## 六、复现命令

```powershell
$env:CARGO_HOME = "E:\SoftWare\cargo"
$env:RUSTUP_HOME = "E:\SoftWare\rustup"
$env:PATH = "E:\SoftWare\cargo\bin;$env:PATH"
cd E:\OtherPro\HQAgent-Hub-worktrees\w5-shell\apps\desktop\src-tauri
cargo check --all-targets
cargo test
pwsh -File acceptance/run-security-acceptance.ps1
```
