# T-W5 桌面壳与本机接入 —— 交接（中断抢救版）

| 项 | 值 |
| --- | --- |
| 状态 | 代码完成、**一行都没编译过**；被环境缺失硬阻断 |
| 中断原因 | Codex 会话在 303,743 token 处被 `429 Too Many Requests` 打断，重试 5 次失败 |
| 阻断原因 | 本机**没有安装任何 MSVC 工具链**，`link.exe` 不存在，Rust msvc target 无法链接 |
| 落盘情况 | 代码已全部写入工作区，未提交；由 W0 抢救提交 |
| 本文件作者 | W0（架构/审核），**不是执行方自述** |

## provenance 声明

Codex 死在自测之前，**没有留下任何自述结论**。下面区分两类信息：
标「W0 实测」的是抢救时亲自跑的；标「静态审阅」的是读代码得出的，**未经编译验证**。

## 🔴 阻断：本机缺 MSVC 工具链

```
error: linker `link.exe` not found
  = note: program not found
note: the msvc targets depend on the msvc linker but `link.exe` was not found
error: could not compile `serde_core` (build script) due to 1 previous error
[exited with code 101]
```

W0 实测追查结果：

- `vswhere.exe` 不存在 —— 本机没装过任何 Visual Studio / Build Tools
- `C:\Program Files\Microsoft Visual Studio` 与 `(x86)` 版本目录**都不存在**
- 系统 PATH 上没有 `cargo` / `rustc` / `rustup`，`%USERPROFILE%\.cargo` 也不存在

**结论：这不是代码问题，是环境问题。** 在装上 MSVC C++ 生成工具之前，
本包的 `cargo check` / `cargo test` / 安全验收脚本一条都跑不了，
所有 Rust 侧验收只能挂起。

解法（需要人来决定，W0 不擅自安装）：装 **Visual Studio Build Tools** 并勾选
「使用 C++ 的桌面开发」工作负载。这是数 GB 的下载且要管理员权限。
Tauri 在 Windows 上依赖 WebView2 与 MSVC ABI，**不建议**改用 `x86_64-pc-windows-gnu` 绕过。

## 🟡 次级问题：工具链装在临时目录

Codex 因为本机没有 Rust，自己在这些位置装了一套私有工具链：

```
E:\tmp\hqagent-w5-cargo          CARGO_HOME（cargo.exe 等在 bin/ 下）
E:\tmp\hqagent-w5-rustup         RUSTUP_HOME
E:\tmp\hqagent-w5-registry-cache crates 索引缓存
```

并写了 `acceptance/cargo_registry_proxy.py` + `acceptance/run-cargo.ps1`，
用一个本地 sparse registry 代理来绕过沙箱的网络限制。

`E:\tmp` 是随时可能被清理的临时目录。**装好 MSVC 之后应当把 Rust 正式装到
`%USERPROFILE%\.cargo`，并让 `run-cargo.ps1` 的默认路径跟着改**，
否则某天清了 `E:\tmp` 这套构建就整个失效。

## 交付物

24 个文件，2478 行 Rust：

```
src/  autostart commands config credentials error fs_util lib main
      platform process_supervisor runtime_descriptor security state tray window_state
      tauri.conf.json  Cargo.toml  build.rs  capabilities/default.json
acceptance/  hub_stub.py  cargo_registry_proxy.py
             run-cargo.ps1  run-security-acceptance.ps1
README.md
```

## 边界核对（W0 实测，通过）

`git status --short` 在抢救时只有一条 `?? apps/desktop/src-tauri/`，
没有碰 `apps/desktop/src/`（W4 的）、`apps/hub/`（W1 的）、`packages/protocol/`（W0 的）
或仓库根共享配置。

## 静态审阅结论（未经编译）

读 `src/runtime_descriptor.rs` 493 行，实现比任务书要求**更严**，
这几点值得保留，不要在后续改动中被简化掉：

- **陈旧 Descriptor 防护是三重的**，不只看 pid：`instanceId` 要与当前受管进程一致、
  `pid` 要一致、`startedAt` 要落在进程启动窗口内（早于启动 5 秒或晚于当前 30 秒都拒），
  再加 `process_matches_executable(pid, executable)` 确认 pid 没被复用到别的程序上。
- **`baseUrl` 是精确校验**，不是前缀匹配：scheme 必须 `http`、host 必须 `127.0.0.1`、
  port 必须等于 descriptor 里的 port、path 必须 `/`、不允许 query / fragment /
  username / password。堵掉了 `http://127.0.0.1:1234@evil.com` 这类 URL 解析歧义。
- **healthz 交叉验证身份**：pid / appVersion / protocolVersion / startedAt
  四项必须与 Descriptor 完全一致，否则判定为连到了错误的进程。
- **读 Descriptor 前先防文件替换**：`symlink_metadata` 拒绝符号链接与非普通文件，
  64 KiB 上限，响应体 256 KiB 上限。
- **`HubEndpoint` 只序列化两个字段**，且有测试 `endpoint_serialization_only_contains_hub_url_and_token`
  断言 `object.len() == 2` 且不含 `updateAgent`。这是「Vue 拿不到 Update Agent endpoint」
  这条契约的机器化守卫。
- `tauri.conf.json` 的 CSP 里 `connect-src` 只放 `'self'` / `ipc:` / `127.0.0.1:*`，
  `frame-ancestors: none`、`object-src: none`、`assetProtocol.enable: false`、
  `freezePrototype: true`。

**但以上全部只是读出来的。** 编译不过就意味着连类型是否自洽都没验证过。

## 验收状态（全部挂起）

| 验收条目 | 状态 |
| --- | --- |
| 双击第二次激活已有窗口 | ⛔ 未验证，编译阻断 |
| 杀子进程 10 秒内重启 | ⛔ 未验证，编译阻断 |
| 关窗口子进程仍在，托盘可恢复 | ⛔ 未验证，编译阻断 |
| 无 token 打 Hub 返回 401 | ⛔ 未验证，编译阻断 |
| `hub.json` ACL 只有当前用户（要 icacls 实证） | ⛔ 未验证，编译阻断 |
| Bearer 换一次性 Ticket，重放失败 | ⛔ 未验证，编译阻断 |
| 陈旧 Descriptor 被忽略 | 🟡 有单元测试代码，但**从未运行** |
| 非允许 Origin 被拒 | ⛔ 未验证，编译阻断 |

`acceptance/run-security-acceptance.ps1` 与 `hub_stub.py` 是纯 Python，
理论上不依赖 Rust 编译，但它们的验收对象是编译产物，单独跑没有意义。

## 复工清单

1. 装 Visual Studio Build Tools + 「使用 C++ 的桌面开发」工作负载
2. 把 Rust 正式装到 `%USERPROFILE%\.cargo`，改掉 `run-cargo.ps1` 里指向 `E:\tmp` 的默认值
3. `cargo check` → `cargo test` → `pwsh -File acceptance/run-security-acceptance.ps1`
4. 逐条补齐上表的实测证据，ACL 与 Ticket 重放**必须贴真实命令输出**
5. 编译大概率会暴露一批类型错误——2478 行没编译过的 Rust 不可能一次过，
   修的时候注意别把上面「静态审阅结论」里那几条安全校验改松了
