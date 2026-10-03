---
wp: hub-local-session
status: done
scope_declared: [apps/hub/**, .hqagent/handoffs/hub-local-session.md]
scope_touched: [apps/hub/core/local_auth.py, apps/hub/api/app.py, apps/hub/api/local_chat.py, apps/hub/runtime/pair.py, apps/hub/README.md, apps/hub/tests/test_local_session_persistence.py, .hqagent/handoffs/hub-local-session.md]
build: pass
tests: pass
commit: 7e45fd940c13482eb5f2c16601f8dd843d1dee43
open_questions: 0
---

# 本机浏览器会话持久化与滑动续期

## 实现

基线 `9e6dfda`（含返修 4、5）；开工执行 `git merge integration/phase1`，实际输出 `Already up to date.`。只改本机 Hub 与本回执；未改协议、服务端、桌面端或既有测试断言。

- `core/local_auth.py`：独立 SQLite `data/browser-sessions.db`，表 `browser_sessions(digest TEXT PRIMARY KEY, expires_at REAL NOT NULL)`。只持久化 SHA-256 摘要及墙上时钟到期时间，不存原始 secret、连接码或 Hub Token。启动清理过期及到期时间超出 `now + 30天` 的记录；有效会话直接从持久存储校验，不维护可复活已撤销会话的进程缓存。
- 默认有效期 30 天。距离上次签发/持久续期达到 1 小时，才更新到 `now + 30天`；上次续期由 `expires_at - session_ttl` 推导，无需额外字段。小时内只读，不更新到期时间。滑动精度为 1 小时，Cookie 与持久到期时间保持一致，不出现客户端比服务端多活一小时的情况。
- Cookie 每个已认证 HTTP 响应更新剩余 Max-Age；新签发/续期时为 `2592000` 秒。保留 HttpOnly、SameSite=strict、Path=/、HTTPS 下 Secure。响应 no-store；login/logout 的 Cookie 不被续期中间件覆盖。
- 墙上时钟回拨使到期时间超出未来 30 天时，立即拒绝并删除该会话。重启也执行相同校验。连接码仍是进程内单调时钟的 10 分钟、一次性、10 次尝试上限，逻辑不变。
- 上限 20 个，兑换插入和淘汰在同一事务完成。以 SQLite rowid 代表创建顺序，淘汰最早创建的会话；续期不会改变创建顺序。
- POSIX 文件在创建时即使用 0600，已有文件启动时收紧至 0600；SQLite 回滚日志继承数据库权限。Windows 使用既有用户数据目录。无新依赖，不修改 Hub 数据库迁移。
- `api/app.py`：按现有 HubPaths 接入数据目录，关闭时释放认证数据库；新增仅受本机 operator Bearer 保护的内部撤销接口，不增加冻结的 `/api/v1` 或 `/api/v2` 协议路径。

## 注销、批量撤销与说明

原 logout 立即删除持久记录。新增 `POST /internal/auth/revoke-sessions` 清空本机浏览器会话；Cookie 单独访问返回 401，必须持有既有本机 operator Token。撤销不解绑远程设备，不影响一次性连接码。

在 `apps/hub` 下使用 Hub 所在虚拟环境：

```sh
python -m runtime.pair --revoke-sessions
python -m runtime.pair --data-dir /path/to/hub-data --revoke-sessions
```

要求 Hub 正在运行。CLI 复用 descriptor，连接 `127.0.0.1` 的实际端口，不使用 descriptor 的远程 baseUrl，不走环境代理/重定向。撤销成功只输出结果，不输出令牌、Cookie 或连接码；原连接码显示仍限交互终端。

已更新 `apps/hub/README.md`，不需要主代理另改 docs。升级之前的内存会话无法恢复，升级部署后的第一次登录仍需连接码，此后可跨重启保留。

## 验证

新增 `tests/test_local_session_persistence.py`：摘要与到期时间存储检查、原 secret 不落盘、重启恢复、30 天到期及启动清理、100 次有效访问不写盘/满一小时只写一次、续期跨原到期时间有效、跨实例注销与全撤销、启动/运行中时钟回拨、20 个上限按创建顺序淘汰、真实 HTTP Cookie 属性/重启/续期/logout、内部撤销鉴权、CLI 路由与非交互撤销。

Windows 本机执行；0600 的实际文件模式断言将在 POSIX 环境执行，本轮不声称已跑 Linux/macOS。

定向命令（cwd `apps/hub`）：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/local-session-focused tests/test_local_session_persistence.py tests/test_connection_code_renewal.py tests/test_local_chat.py
```

实际输出：`26 passed, 1 warning in 2.88s`。

Hub 全量命令（cwd `apps/hub`）：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/local-session-hub --tb=short
```

实际输出：

```text
........................................................................ [ 10%]
........................................................................ [ 21%]
...............................................................s........ [ 32%]
........ssssssss........................................................ [ 42%]
........................................................................ [ 53%]
........................................................................ [ 64%]
........................................................................ [ 75%]
........................................................................ [ 85%]
........................................................................ [ 96%]
远程送达预留清理暂未完成，将重试
远程送达预留清理暂未完成，将重试
......................                                                   [100%]
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
661 passed, 9 skipped, 4 warnings in 266.78s (0:04:26)
```

Server 全量命令（cwd `apps/server`，在 Hub 全量结束后执行）：

```powershell
$env:TEMP=(Resolve-Path ../../.tmp).Path
$env:TMP=$env:TEMP
$env:PYTHONIOENCODING='utf-8'
../../.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp ../../.tmp/local-session-server --tb=short
```

实际输出：

```text
........................................................................ [ 23%]
........................................................................ [ 47%]
........................................................................ [ 71%]
........................................................................ [ 94%]
................                                                         [100%]
============================== warnings summary ===============================
..\..\.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\OtherPro\HQAgent-Hub-worktrees\remote-worker\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
304 passed, 1 warning in 77.09s (0:01:17)
```

`git diff --check` 通过。Hub 的 9 项 skipped 是既有 POSIX 专属测试；4 个 warning 为既有依赖弃用提示。Server 1 个 warning 同为 Starlette/httpx 弃用提示。此次无需协议生成改动，没有运行 vitest。

所有测试串行运行，TEMP / TMP / --basetemp 都在 worktree 内 git 忽略的 `.tmp`，避免沙箱默认临时目录 WinError 5；不跑 vitest、不调用模型、不联网。


## 提交

- `7e45fd940c13482eb5f2c16601f8dd843d1dee43`：会话持久化、滑动续期、CLI 撤销与回归测试。
- 使用说明与本回执另作文档提交；每次提交均执行 `git log -1 --format=%B` 自查，不包含署名或生成标记。未合并回 integration。
