# R3.5-P2 跨平台 Hub 审核记录

- 工作包：R3.5-P2（POSIX 路径守卫与 shell 解包、系统钥匙串凭据、无界面 CLI、systemd/launchd 模板）
- 实施：codex 会话 01a0de45（gpt-6-astra，high），分支 feat/remote-worker，回执 `.hqagent/handoffs/R35-P2-hub.md`
- 合入：integration/phase1 `8d20faf`（2026-09-30）

## 1. 交付核对

| 项 | 结论 |
| --- | --- |
| POSIX 越界守卫 | `adapters/path_guard.py` 按宿主语义解析；POSIX 下 `C:/...` 按相对路径进守卫；bash/sh/zsh `-c` 与 `env` 包装仅对 PATH 上实际存在的 shell 解包，危险环境变量覆盖拒绝 |
| 凭据 | `runtime/remote/keychain.py`：macOS Keychain / Linux Secret Service，不可用回退 0600；迁移失败保留旧文件；Windows DPAPI 不变 |
| CLI | `python -m runtime.cli`：remote pair（segno 终端二维码）/status/unlink、workspace、agents discover、roots；只走本机 v1 API，只连 127.0.0.1 |
| 服务模板 | `apps/hub/packaging/`：systemd user unit、launchd LaunchAgent、安装说明 |
| 其余 skip | npm shim 2 项、deny-delete 1 项确属 Windows 专属，理由成立 |

## 2. Q1 依赖锁（主代理处理）

codex 沙箱无网，未锁 Linux 钥匙串链。主代理用 `pip install --dry-run --platform manylinux… --python-version 3.13` 解析后补锁：SecretStorage 3.5.0、jeepney 0.9.0、cryptography 50.0.1、cffi 2.1.1、pycparser 3.0，均带 `sys_platform == "linux"`。提交 `build(hub): pin the Linux Secret Service chain for keyring`。

## 3. CI（run 36677742192，8d20faf）

8 个 job 全部成功：

- protocol、desktop、server ×3：通过
- hub ubuntu / macos：各 473 passed / 9 skipped；9 项均为 Windows 专属，POSIX 新用例实际运行；ubuntu 安装了 SecretStorage 链，macos 未安装（标记正确）
- hub windows：通过（上一轮 cce9c10 的 `test_r3_upgrade_history` 竞态本轮未复现）

## 4. 审核发现（返修 1，medium）

1. 测试直接构造真实 `CredentialVault`，macOS CI 会写 runner 真实登录钥匙串 —— 测试默认隔离钥匙串（必须修）
2. 钥匙串可用时 `_save` 仍先落明文文件再迁移 —— 应先写钥匙串
3. 文件模式下每次 read 都探测钥匙串 —— 缓存/退避
4. `test_r3_upgrade_history.py:32-35` 把 delivery completed 当成 run 已结束（CI 曾报 `'running' == 'succeeded'`）—— 等 run 结束再断言
5. POSIX 重定向未识别 `&>`、`2>>`、`>|`、`>&` —— 显式处理并补用例
6. `runtime/cli.py` 风格与仓库不一致 —— 重排不改行为

## 5. 仍只能靠真机验证

- systemd / launchd 实际启动、登录环境与自启
- 真实 Keychain / Secret Service 的解锁提示、锁定后的行为
- 无界面 Linux 上 CLI 配对的端到端（真服务器 + 手机扫码）

## 变更记录

- 2026-09-30：首次审核，合入 8d20faf，CI 三平台全绿，派返修 1。
- 2026-09-30：返修 1（b220a62、3e0583a、fc7622c、d4f2f13）审核通过：测试钥匙串由 `apps/hub/conftest.py` 默认隔离；钥匙串可用时先写钥匙串、失败才落 0600 文件，10 分钟退避；中断的钥匙串写入可凭 pending 恢复；重定向按类型处理，`>&2` 这类 fd 复制不算写目标；两处升级测试改为等 run 结束再断言；CLI 重排（AST 不变）。合入 17259d9，本机 Hub 495 passed / 9 skipped，CI run 36679413417 全绿。R3.5-P2 关闭。
