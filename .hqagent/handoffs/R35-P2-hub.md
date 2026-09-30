---
wp: R35-P2
status: done
scope_declared: [apps/hub/**, .hqagent/handoffs/R35-P2-hub.md]
scope_touched: [apps/hub/adapters/path_guard.py, apps/hub/adapters/tests/test_contract_rules.py, apps/hub/packaging/README.md, apps/hub/packaging/hqagent-hub.service, apps/hub/packaging/local.hqagent.hub.plist, apps/hub/pyproject.toml, apps/hub/requirements.local-lock.txt, apps/hub/runtime/cli.py, apps/hub/runtime/main.py, apps/hub/runtime/pair.py, apps/hub/runtime/remote/keychain.py, apps/hub/runtime/remote/security.py, apps/hub/tests/test_connection_code_renewal.py, apps/hub/tests/test_posix_credentials.py, apps/hub/tests/test_posix_path_guard.py, apps/hub/tests/test_runtime_cli.py, apps/hub/tests/test_service_templates.py, .hqagent/handoffs/R35-P2-hub.md, apps/hub/conftest.py, apps/hub/tests/test_r3_upgrade_history.py]
build: pass
tests: pass
commit: fc7622c436bfee4dca94e08879fed92d0a2a9ab1
open_questions: 0
---

# R3.5-P2 跨平台 Hub 实施回执

## Q1（已由主代理关闭）

主代理已补齐并集成 Linux Secret Service 链，Q1 已关闭。首次交付与本次返修的本机验证分别见下文；修后跨平台 CI 仍由主代理推送验证。

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

首次交付时 Linux 传递依赖不在 Windows .venv 中，因此没有编造锁定版本。主代理随后通过 `build(hub): pin the Linux Secret Service chain for keyring` 锁定 SecretStorage 3.5.0、jeepney 0.9.0、cryptography 50.0.1、cffi 2.1.1、pycparser 3.0，均限定 Linux（后两项还排除 PyPy）。本次快进到 8d20faf 后已核对锁文件，Q1 正式关闭。模板使用 Python 3.13；本轮未联网安装或改动依赖锁。

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


Q1 已处理；本次返修后需要主代理再次推送 CI：核对 Ubuntu/macOS 的 POSIX 用例全过，按需建立 D-Bus/Secret Service 测试环境；当前 keyring 的注入测试不依赖 CI 的桌面钥匙串。未合回 integration、未推送远程。

## 返修 1：测试钥匙串隔离、凭据落盘顺序、退避与跨平台细节

开工工作区干净；执行 `git merge integration/phase1`，由 bb1f0a6 快进到 **8d20faf**，合并信息已用 git log -1 --format=%B 自查。确认主代理锁定的 Linux Secret Service 链已在 requirements.local-lock.txt，Q1 关闭。本轮不改依赖锁、协议、CI、Server 或桌面。

### 1. 默认测试隔离与生产默认

新增 apps/hub/conftest.py 的 autouse fixture，覆盖 Hub tests/adapters/orchestrator/security 全部测试树，默认将 runtime.remote.keychain.system_keyring 换为返回 None。不能只在个别构造点 patch CredentialVault，否则其它直接构造仍可能接触 runner 钥匙串。

同时修正 PosixCredentialStore 的默认 backend_factory：旧默认参数在 import 时捕获真实 system_keyring 函数，后续 monkeypatch 不会生效。改为 backend_factory=None 时延迟查找模块函数。**生产仍选择原系统 backend，没有 pytest 环境分支或生产禁用钥匙串。**

钥匙串行为测试显式注入 MemoryKeyring；两个平台选择测试取得原选择函数但先替换对应 backend 模块为内存实现，不实例化 macOS Keychain/Secret Service。新增默认工厂延迟绑定回归。现有真实 P1/Worker 联调和直接 CredentialVault 构造均继承默认隔离，CI 不再写 runner 真实登录钥匙串。

### 2. 首次保存顺序与可靠迁移

PosixCredentialStore._save 改为：

1. backend 可用时，先写无密钥 pending journal，再 set_password、get_password 严格比对；
2. 只有上述成功后才原子写 marker，不先创建明文 credential 文件；
3. backend 不可用、写/校验失败或 marker 无法提交时才走 0600 文件回退；
4. 旧文件的 read→migrate 失败仍保持原字节，成功才换 marker，原迁移语义不变；
5. 首次 keyring 写成功后若进程在 marker 提交前中断，可凭 pending journal 及确定性账户键恢复 marker；不丢掉已存的 secret。

新增操作顺序测试严格断言成功路径仅为 discover/journal/set/verify/marker，**从未** atomic_write secret；失败测试验证确实先尝试 backend 再写 fallback。原 set/校验/marker 失败保留旧文件测试继续通过，另覆盖 pending 首次写恢复。

### 3. 文件模式的 10 分钟退避

失败后记录单调时钟 retry_after=now+600；文件模式后续读取只返回私有文件，不重复连接 D-Bus或写 keyring。达到期限才允许再次迁移；进程重启可重新探测。不存在 marker 模式的负缓存：marker read、已有 marker save、delete 仍直接联系 backend，锁定/失联不以缓存成功冒充。

测试覆盖发现返回 None、发现抛错、校验失败三种退避，600 秒前多次 read 只探测一次，边界时重试迁移成功。marker read 即使 retry_after 还在未来也必须访问 backend。原迁移重试用例只改为推进注入单调时钟 600 秒，不删原文件/结果断言。

### 4. LocalRun 结束等待与检查范围

test_r3_upgrade_history.py 原来等待 submit delivery completed 后立即读 run 并 assert succeeded。现在先以 until 轮询该精确 run_id 的实际状态，再保留原 succeeded 断言。

同文件“真实 grant 执行阻挡升级”用例也增加 run succeeded 等待，然后验证线路升级和最终回执。同类真服务器测试核查：

- test_r15_joint_server.RealPair.send_local 已直接等待 LocalRun succeeded，无需改；
- test_r3_restart_import 的资源 completed 指原子导入资源完成，不会创建 LocalRun，不能增加虚构 run 等待；
- R3 原生 metadata/import 的 completed 校验仍按资源状态，未删除证据；
- 原有 fake WS 执行测试检查了真实执行结果/Adapter 请求，未将其它 completed 断言整体放宽或替换。

### 5. POSIX 重定向

PathGuard 的 shlex 扫描明确识别 >、>>、<、&>、&>>、>|、>&、<&；2>/2>> 被 shlex 分为 fd 数字与操作符，后续目标仍校验。重定向目标优先于命令分隔符处理，缺失/异常连续操作符保守拒绝。

>& / <& 后纯数字或 - 是 fd 复制/关闭，不加入路径；其它参数仍是文件目标。echo x >&2 可通过，但其后附加 > ../out 仍失败；rm >&2 也不能因为 fd 重定向掩盖无法解析的写目标。写动作检测与已解析重定向分离，避免将单独 >&2 误认为没有路径的写命令。

新增 12 项平台无关参数化测试，在 Windows 指定 POSIX 解析模式也真实运行；另增实际 POSIX /tmp/x stderr append 用例。本机 Windows 后者跳过，Linux/macOS CI 应执行。原六项 POSIX wrapper 用例保留。

### 6. CLI 纯格式变更

runtime/cli.py 拆开分号语句、补齐运算符/逗号间距、整理多行调用与模块空行，保留注释和 0o077 权限写法。使用 Python ast.dump 对重排前后整个模块比较，输出：

```text
Formatted CLI AST equals original
```

CLI API路径、参数、错误处理、输出过滤和配对行为均未改；既有 CLI 真实 loopback Hub 集成用例继续运行。

### Q1 与 CI 边界

主代理已在集成锁定 SecretStorage 3.5.0 / jeepney 0.9.0 / cryptography 50.0.1 / cffi 2.1.1 / pycparser 3.0，Linux 平台标记已核对。旧 Q1 不再阻断交付；本轮使用既有离线环境，不联网安装。

主代理报告 run **36677742192（8d20faf）8 个 job 成功**；Hub Ubuntu/macOS 各473 passed/9 skipped，POSIX 用例实际执行，Linux SecretStorage平台安装标记正确。这是**返修前、由主代理提供的 CI 结果**，不是本轮改动后的 CI 证明。修后仍需主代理推送重跑；本机无法验证 macOS/Linux OS backend及真实 POSIX操作。本轮隔离后的 CI 也不能宣称测试了真实 Keychain 持久化，只验证内存 backend 协议和路径选择。

### 验证与交付

定向（凭据、路径、CLI与真实升级联调）：

```text
42 passed, 9 skipped, 1 warning in 11.94s
```

随后 CLI 最终排版及定向回归：

```text
40 passed, 9 skipped, 1 warning in 1.41s
```

全部串行。TEMP/TMP 与 --basetemp 位于 worktree/.tmp，未跑 Vitest、未安装依赖。

Hub 全量，cwd apps/hub：

```powershell
$env:TEMP='E:/OtherPro/HQAgent-Hub-worktrees/remote-worker/.tmp'
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r35-repair1-hub-final --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r35-repair1-hub-final.log
exit $LASTEXITCODE
```

```text
........................................................................ [ 14%]
..................................................s................sssss [ 28%]
sss..................................................................... [ 42%]
........................................................................ [ 57%]
........................................................................ [ 71%]
........................................................................ [ 85%]
远程送达预留清理暂未完成，将重试
........................................................................ [100%]
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
SKIPPED [1] tests\test_posix_credentials.py:166: POSIX mode bits
SKIPPED [1] tests\test_posix_path_guard.py:50: POSIX absolute redirect path
SKIPPED [1] tests\test_posix_path_guard.py:68: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:76: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:84: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:101: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:108: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:115: POSIX shell approval wrappers
SKIPPED [1] tests\test_posix_path_guard.py:122: POSIX executable symlink and directory-fd semantics
495 passed, 9 skipped, 4 warnings in 244.50s (0:04:04)
```

Server 全量，cwd apps/server，TEMP/TMP/PYTHONIOENCODING 同上：

```powershell
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/r35-repair1-server-final --tb=short 2>&1 | Tee-Object -FilePath ../../.tmp/r35-repair1-server-final.log
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
231 passed, 1 warning in 94.12s (0:01:34)
```

退出码均 0。Windows 的9项 skip 为 POSIX专属（原8项加新增绝对重定向路径1项），不是跳过 Windows CI 竞态。git diff --check、范围清单与 CLI AST 等价检查通过。原依赖弃用警告及通用预留清理重试日志仍存在，不宣称本轮修复。没有遇到429、0xC0000142或额度错误。

提交：
- `b220a62`：Hub 测试默认隔离系统钥匙串、先 keyring 后文件及迁移退避。
- `3e0583a`：POSIX 重定向守卫与真实运行结束等待。
- `fc7622c`：CLI 纯格式调整，AST 与重排前一致。
- 回执另提交。每次提交后均 git log -1 --format=%B 自查，无署名或生成标记；未合回 integration。
