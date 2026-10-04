---
wp: hub-cursor-scope
status: done
scope_declared: [apps/hub/**, .hqagent/handoffs/hub-cursor-scope.md]
scope_touched: [apps/hub/api/pi_projection.py, apps/hub/api/app.py, apps/hub/runtime/pi_visibility.py, apps/hub/storage/events.py, apps/hub/tests/test_cursor_scope.py, apps/hub/tests/test_pi_projection_wire.py, apps/hub/docs/validation/hub-cursor-scope/**, .hqagent/handoffs/hub-cursor-scope.md]
build: pass
tests: pass
commit: 9768b070e3dc21080e3264a2938c8600fcf974d5
open_questions: 0
---

# 本机事件游标能力登记修复

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/hub-0101`、分支 `feat/hub-0101`。先执行 `git merge integration/phase1`，从 adfa414 快进到 `0d58a23`，本轮以该提交为基线。没有修改前端、协议、PI 适配器、服务端或其它工作区；除本指定回执外，所有新增/修改文件均位于 apps/hub。未合并回 integration、部署或重启实际 Hub。

## 变更

- HTTP 能力切换检查仅匹配 GET `/api/v1/events` 与 `/api/v2/events`；消息列表的消息 sequence、其它接口的 after、page 和不存在路径不再占用或改变事件登记。
- 精确的 `/api/v1/bootstrap`、`/api/v2/bootstrap` 仍登记当前快照能力；不再使用 endswith('/bootstrap')，快照 URL 上无关的 after 不作为事件续读。
- WS 保持既有 `/api/v1/events/stream` 握手中的单独校验，能力来自已签发 ticket，不采信握手 feature header。显式 after 使用相同 scope 函数；省略 after 表示从当前位置新建流，不是消费旧游标。
- 未知或已淘汰 owner：登记当前能力并允许读取。只有 previous 已知、能力不同、使用正事件游标续读时才抛 EVENT_CURSOR_EXPIRED。拒绝后保留原能力，不能通过重复失败请求悄悄切换；重新获取 bootstrap 或 after=0 可建立新能力范围。
- 使用容量 256 的 OrderedDict LRU。每次有效 scope 访问都移到最近使用端，仅移除最旧项，不再整表 clear；已知能力冲突也只刷新最近使用位置，不覆盖其能力。
- 删除 owner:path 分页登记。分页本身不是事件水位，现有资源投影仍逐请求按客户端当前能力执行；无需借助事件游标登记才能过滤 PI 内容，因此不再让大量分页路径挤掉活跃事件客户端。
- EventStore 提供共用水位 detail：在一次 MIN/MAX 查询中获得 oldestAvailableSeq/latestSeq。真实裁剪错误和 HTTP/WS 能力切换错误均携带这两个键及 snapshotUrl。空事件库同样保留两个键，值为 null/0；不伪造事件序号。
- v1/v2 HTTP 能力切换错误指向对应 bootstrap；既有 WS 指向 v1 bootstrap。真实裁剪沿用既有 v1 snapshotUrl，裁剪阈值与事件读取范围没有改变。
- 事件 after 的解析与 FastAPI/Pydantic endpoint 一致：取重复参数最后一个值；正号/空白/整数形式一致；空值、负数和非法值交由 endpoint 返回 422，不改变已有能力登记。HEAD 和其它方法不能借 after=0 修改登记。

## 安全回归

新增 `tests/test_cursor_scope.py` 共 17 个参数化测试实例，覆盖：

1. 消息 after=N 返回正确消息，不创建或改变事件登记；随后真实事件能力变化仍拒绝。
2. v1/v2、旧/新能力 owner 首次使用正事件游标成功。
3. 已知能力的双向切换返回 410，detail 含真实 MIN/MAX 水位；重复错误不覆盖旧能力，快照后可恢复。
4. 256 项容量及 600 次新 owner 插入只淘汰 LRU，持续访问的 owner 保留；淘汰者再次使用作为未知登记接受。
5. 分页、其它 after、不存在 bootstrap 后缀路径、HEAD 不挤占或重设事件登记。
6. 空事件库、实际裁剪、参数解析、未知 WS 首次正游标、WS 降级 4410 及水位。

既有 `test_pi_projection_wire.py` 的内容过滤、能力切换拒绝、ticket feature 与握手 header 不一致的安全断言均保留；仅增强其 WS 错误 detail 断言。真实 WebSocket 握手关闭码测试继续通过，没有删除/放宽安全测试或新增 skip/xfail。

## 真实测试输出

全程使用指定 `E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe`，仅只读使用解释器及依赖，开启 `-B` 和 PYTHONDONTWRITEBYTECODE=1。TEMP/TMP 为 `E:/tmp/hub-cursor-scope-temp`，basetemp 均为 E:/tmp 下独立测试目录。没有修改 vnext-integration 工作区或 venv，没有调用真实模型；没有遇到实际服务端 429/403 错误、0xC0000142 或额度错误。测试内部预期的鉴权拒绝反例正常运行。

Hub 全量（343447f，cwd=apps/hub）：

```text
E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp=E:/tmp/pytest-hub-cursor-scope-full --tb=short
839 passed, 9 skipped, 4 warnings in 405.09s (0:06:45)
```

全量后 9768b07 仅补空查询值保留及相应断言；追加覆盖本轮全部变更的游标/PI/真实 WS 专项，cwd=apps/hub：

```text
E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_cursor_scope.py tests/test_pi_projection_wire.py tests/test_events_and_idempotency.py tests/test_ws_close_codes_real_handshake.py -q -p no:cacheprovider --basetemp=E:/tmp/pytest-hub-cursor-scope-query-final --tb=short
31 passed, 4 warnings in 24.33s
```

随后串行 server 全量，cwd=apps/server：

```text
E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp=E:/tmp/pytest-server-hub-cursor-scope --tb=short
343 passed, 1 warning in 126.08s (0:02:06)
```

9 个跳过都是既有 POSIX 平台条件。完整日志位于本工作区：

- [Hub 全量](../../apps/hub/docs/validation/hub-cursor-scope/hub-tests.txt)
- [末次专项](../../apps/hub/docs/validation/hub-cursor-scope/query-final.txt)
- [server 全量](../../apps/hub/docs/validation/hub-cursor-scope/server-tests.txt)
- [语法检查](../../apps/hub/docs/validation/hub-cursor-scope/syntax.txt)：`Python syntax verified: 6 changed files`

较早的两轮专项 30/31 passed 输出也保留；归档仅统一换行及行尾空白。`git diff --check` 通过，build=pass 指 Python 语法和测试装配，没有重新打桌面安装包。本轮单代理实施，无会话委派。

## 提交

| 提交 | 主题 |
| --- | --- |
| 343447f | 事件接口范围、未知登记、LRU、水位与 HTTP/WS 回归 |
| 9768b07 | 空/重复 after 查询值的校验一致性 |

每次提交后执行 `git log -1 --format=%B` 自查，无禁止署名。只提交 feat/hub-0101，不合并 integration；前端自行恢复轮询的实现仍由前端执行线负责。
