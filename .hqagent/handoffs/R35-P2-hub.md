---
wp: R35-P2
status: needs-decision
scope_declared: [apps/hub/**, .hqagent/handoffs/R35-P2-hub.md]
scope_touched: [apps/hub/adapters/path_guard.py, apps/hub/adapters/tests/test_contract_rules.py, apps/hub/packaging/README.md, apps/hub/packaging/hqagent-hub.service, apps/hub/packaging/local.hqagent.hub.plist, apps/hub/pyproject.toml, apps/hub/requirements.local-lock.txt, apps/hub/runtime/cli.py, apps/hub/runtime/main.py, apps/hub/runtime/pair.py, apps/hub/runtime/remote/keychain.py, apps/hub/runtime/remote/security.py, apps/hub/tests/test_connection_code_renewal.py, apps/hub/tests/test_posix_credentials.py, apps/hub/tests/test_posix_path_guard.py, apps/hub/tests/test_runtime_cli.py, apps/hub/tests/test_service_templates.py, .hqagent/handoffs/R35-P2-hub.md]
build: pass
tests: pass
commit: 7f67083bd4ae6fed717e8b2cbd3c62879bdfa7f4
open_questions: 1
---

# R3.5-P2 跨平台 Hub 实施回执

## 状态与唯一待裁决项 Q1

本机功能实施及可运行验证见下文；**Linux 依赖完整锁定尚未完成，不应据 tests:pass 宣称三平台可发布**。

按要求合并 integration/phase1，命令返回 Already up to date；HEAD 合并信息为 `merge: sync integration with R3 and CI for cross-platform work`。本轮未修改 .github/CI、协议、Server、桌面、docs 或根共享文件。只在 remote-worker 工作。

已通过 importlib.metadata 离线核实并写入 Hub 锁文件：

| 包 | 已安装版本 |
| --- | --- |
| segno | 1.6.6 |
| keyring | 25.7.0 |
| pywin32-ctypes（win32 标记） | 0.2.3 |
| jaraco.classes | 3.4.0 |
| jaraco.functools | 4.6.0 |
| jaraco.context | 6.1.2 |
| more-itertools | 11.1.0 |

keyring 安装元数据声明 Linux 需要 SecretStorage>=3.2、jeepney>=0.4.2，但当前 .venv 中 **SecretStorage、jeepney、cryptography、cffi、pycparser 均未安装**，也没有给出的已批准版本或离线 wheel。本轮在开始实现时已提出异步信息请求，尚未收到版本补充。Python<3.12 条件依赖 importlib_metadata/zipp/backports.tarfile 同样未安装；安装模板明确使用 Python 3.13，现有项目 requires-python 未缩窄。

因此没有联网、安装或把未知版本伪造为已验证锁。当前 keyring 在 Linux 由 pip 解析其未锁定传递依赖，**这不满足工作包的完全锁定验收**。请主代理提供上述 Linux 链的版本/离线包，再补入 requirements.local-lock.txt（SecretStorage/jeepney 及 Linux 链使用 sys_platform == "linux"；旧 Python 条件依赖如继续支持也需锁定）。pyproject 已声明 segno/keyring 固定直接依赖；没有修改 CI，由主代理决定安装步骤。没有其它公开 API/schema 决策缺口。

## 路径与 POSIX shell 守卫

修改 adapters/path_guard.py：

- file_path/path 等明确路径先 expanduser，再按宿主路径语义相对 worktree 解析、resolve 符号链接、检查真实包含关系；非法展开/解析错误保守拒绝。
- POSIX 的 C:/... 是相对路径，绝不按 Windows 盘符“免检”。仍要经过真实 worktree resolve 和 allowedPaths，包含 C: 目录的符号链接越界也会拒绝。
- 为 bash/sh/zsh 的精确 -c 形式解包；launcher 必须对应当前 PATH 上 shutil.which 找到的实际程序，不能仅凭 basename。env 包装允许普通字面量环境赋值，不允许 PATH/ENV/BASH_ENV/ZDOTDIR/动态加载等会改变解释器语义的覆盖；未知 shell 选项、额外参数、找不到 shell 的包装不予豁免。
- POSIX 单引号/双引号目标、嵌入 node 写文件字面量、绝对/~/../ 路径、常见写命令相对参数及重定向目标都核对；变量/命令替换、cd/eval/source/exec、未解析写目标或通配写路径保守拒绝。
- 解包只豁免可信 launcher 本身；脚本若写 launcher 路径仍按普通目标拦截。没有运行待审批脚本、没有试图把通用 shell 静态分析变成执行授权。现有危险动作审批规则不变。
- Windows PowerShell 路径保持原逻辑，原六项测试在本机通过。

CI 原失败 test_read_outside_the_worktree_is_still_blocked 改为宿主对应绝对路径：Windows 原 C:/Windows/...，POSIX /etc/passwd。保留“必须被阻止”的断言。新增 POSIX 用例还覆盖 ~/.ssh、..、符号链接和 C:/ 相对语义。

新增六个 POSIX PowerShell 对应场景：内联 marker、带空格目标/env、外部目标、写可信 launcher、未知 launcher/选项、未解析写目标。这六项在 Windows 跳过，在 Linux/macOS 对 PATH 上实际可用的 bash/sh/zsh 运行。另有三种 shell 的纯解包测试在 Windows monkeypatch PATH discovery，验证未安装 shell、未知路径和环境覆盖拒绝。

## 凭据生命周期

runtime/remote/keychain.py 提供 POSIX CredentialStore：

- 明确选择 keyring.backends.macOS.Keyring 或 keyring.backends.SecretService.Keyring；不自动采用第三方明文 backend。Windows CredentialVault 保留 DPAPI，不使用 keyring。
- 无可用系统钥匙串时保存 0600 文件，父目录0700；有可用 backend 时 set→读回比对→原子把旧凭据文件换成无密钥 marker。marker 保留原 path.exists 契约，调用方不会因真正 secret 已迁出文件而漏掉凭据过滤/鉴权。
- 旧 0600 文件迁移失败时，旧文件仍是权威凭据；不删除旧 secret、不回显 backend 异常。迁移 journal 只存 pending 标记，确保部分写入的钥匙串条目可在 unlink 清理。
- marker 表示钥匙串存储时，临时锁定/不可用不悄悄降回空文件或重置设备身份；read/delete 结构化失败。恢复后仍可读取原凭据。
- unlink 删除对应钥匙串项、marker 与迁移 journal；未能确认钥匙串删除则返回失败并保留引用，不假称已删除。当前绑定不允许未经 unlink 覆盖另一份 secret。
- 本机日志仅固定 `Device credential storage mode=system-keyring` 或 `mode=file-0600`，不含 secret、账户键、路径、Authorization。RemoteLinkView 不加自造字段。本机诊断日志现成可用，因此不需要协议变更。
- 文件写入在 POSIX 使用 O_NOFOLLOW、fchmod0600、fsync、原子替换；拒绝设备凭据路径符号链接。POSIX store 的同实例读/迁移/删除由锁串行。

Windows 上以注入内存 keyring 测试平台选择、迁移成功、set/读回/marker提交三类失败保留旧文件、不可用时不丢失已迁移凭据、删除和日志无 secret；没有把这些注入测试称为真实 Keychain/Secret Service 验收。

## 无界面 CLI

新增 `python -m runtime.cli`，提供 remote pair/status/unlink、workspace add/list、agents discover、roots list/add/remove。所有写入复用现有 v1 Bearer 本机 API；无直接数据库操作。

- 从数据根 runtime/hub.json 读取生成 DTO descriptor；POSIX 要求当前用户拥有且无组/其他用户权限。只连接 127.0.0.1:descriptor.port，忽略 descriptor.baseUrl；标准 HTTPConnection 不使用环境代理、不跟随重定向。Origin、Idempotency-Key 沿用本机规则。
- remote pair 使用 segno 终端二维码；链接沿桌面已有形式 `<serverOrigin>/remote/pair#code=<pairCode>`，短码在 fragment 中。同时打印短码和有效期，轮询本机 link 等待确认。
- 短码/二维码仅交互终端输出；非 TTY 拒绝配对，SSH 使用 -t。Ctrl-C 只取消仍属于当前 pairRequestId 的配对；过期与已更换请求明确失败。
- status 不输出 pairCode/token/Authorization；API 异常不回显响应体或 descriptor。普通输出经过现有敏感文本过滤。
- roots 使用 GET 最新 version→PUT 全量 CAS，不在冲突时悄悄覆盖。非 Git workspace 由既有 WorkspaceService 只读登记，CLI 不调用 git init。
- runtime.main 的本机浏览器连接码仅在 TTY 输出，systemd/launchd 的 stdout 不会记录短码；既有 runtime.pair 同样拒绝非 TTY。

CLI 集成测试通过真实 loopback uvicorn Hub、本机 Bearer/descriptor、TLS 假远程服务完成配对确认、状态/解绑，以及真实 WorkspaceService/根 CAS 路由。Agent discover 使用受控 discovery port，验证调用的是冻结 v1 /agents/discovery 路由。没有调用外网或模型。

## 服务模板与其余 skipped 审查

apps/hub/packaging/：

- hqagent-hub.service：systemd **user** unit，UMask0077、普通用户目录、回环 Hub、失败重启；PATH 显式提供用户 CLI 目录；登录后启动，若要未登录开机运行需管理员启用该用户 linger。
- local.hqagent.hub.plist：launchd **LaunchAgent**，用户 Keychain 环境、Umask0077、stdout/stderr 日志路径；真实 HOME 由安装者替换，不伪称 plist 支持 ~ 展开。登录后启动，不是系统 LaunchDaemon。
- README.md：数据目录、环境、依赖安装、日志、配对命令、启动/停止、自启边界、升级前备份/停止、卸载及钥匙串迁移注意事项。安装依赖未锁全的 Q1 明确引用本回执。

原另外三项 skipped：

- npm .cmd/.bat shim 的两个测试是真正 Windows 专属；POSIX 原生执行/符号链接由操作系统处理，无需复制 Windows package.json→exe 的分支。新增 POSIX executable symlink 回归。
- Windows deny-delete 句柄语义在 POSIX 不存在同等保证，不能假装持有 fd 就阻止 rename。现有 POSIX directory_lease 在退出时核对原目录稳定身份；新增实际 rename/replacement 用例要求 REMOTE_DIRECTORY_CHANGED。Windows 原测试保持。
- 模板在本机只做 plist/INI 结构与私有权限配置校验；systemd/launchd 实际启动、真实用户钥匙串提示/锁定、登录环境与进程行为由主代理 CI/后续真机验证。

## 原测试变更与验收边界

1. adapters/tests/test_contract_rules.py 越界读目标按平台取合法绝对路径，拒绝断言不变。
2. test_connection_code_renewal.py 原 CLI 测试明确 mock stdout.isatty=True，保持短码可见、令牌不可见、只连loopback全部断言；新增 CLI 非终端用例验证拒绝写短码日志。
3. 其余既有业务断言未删除/放宽。server 代码/测试未改。

本机 Windows 无法执行六个 POSIX shell、真实符号链接/目录 fd、0600 权限位用例，所以最终结果包含8项平台跳过。这些应在 Ubuntu/macOS 上实际运行；Windows 原6+2+1项在本机保持运行，POSIX 上保持9项合理 Windows-specific skip。三平台 CI 是否全绿，本沙箱无法联网读取，不能代替主代理宣布。

## 真实验证

所有命令串行，TEMP/TMP/--basetemp 在 worktree/.tmp，没有 Vitest/并行 pytest/依赖安装。

Windows Hub 全量，cwd apps/hub：

```powershell
$env:TEMP='E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r35-hub-final --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r35-hub-final.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 14%]
.........................................s....sssssss................... [ 29%]
........................................................................ [ 44%]
........................................................................ [ 59%]
........................................................................ [ 74%]
........................................................................ [ 89%]
远程送达预留清理暂未完成，将重试
..................................................                       [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

tests/test_ws_close_codes_real_handshake.py::test_bad_ticket_closes_with_4401_not_a_handshake_rejection
tests/test_ws_close_codes_real_handshake.py::test_bad_origin_closes_with_4403_and_is_distinguishable_from_bad_ticket
tests/test_ws_close_codes_real_handshake.py::test_expired_cursor_closes_with_4410_and_sends_snapshot_url_first
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\websockets\exceptions.py:137: DeprecationWarning: ConnectionClosed.code is deprecated; use Protocol.close_code or ConnectionClosed.rcvd.code
    warnings.warn(  # deprecated in 13.1 - 2024-09-21

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
SKIPPED [1] tests\test_posix_credentials.py:90: POSIX mode bits
SKIPPED [1] tests\test_posix_path_guard.py:45: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:53: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:61: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:78: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:85: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:92: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:99: POSIX executable symlink and directory-fd semantics
474 passed, 8 skipped, 4 warnings in 240.44s (0:04:00)
```

Server 全量，cwd apps/server，TEMP/TMP 同上：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r35-server-final --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r35-server-final.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 31%]
........................................................................ [ 62%]
........................................................................ [ 93%]
...............                                                          [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
231 passed, 1 warning in 71.52s (0:01:11)
```

退出码均 0。git diff --check 及回执范围清单检查通过。首轮全量的两个测试问题分别为原 CLI 测试未模拟 TTY，以及模板测试用 configparser 默认拒绝 systemd 合法的重复 Environment；均修正测试准备后重跑完整套件，没有降低业务断言。既有依赖弃用提示及通用预留清理重试日志仍存在。本轮未遇到 429、0xC0000142 或额度错误。


## 提交与继续事项

- `e84bda7`：POSIX 路径边界、可信 shell 解包与跨平台用例。
- `436ad18`：系统钥匙串、0600 回退及可靠迁移/删除测试。
- `7f67083`：本机 API CLI、服务模板、安装说明和已安装依赖锁。
- 本回执另提交。每次提交后均 `git log -1 --format=%B` 自查，无署名或生成标记。


Q1 处理完后还需要主代理推送 CI：核对 Ubuntu/macOS 的 POSIX 用例全过，按需建立 D-Bus/Secret Service 测试环境；当前 keyring 的注入测试不依赖 CI 的桌面钥匙串。未合回 integration、未推送远程。
