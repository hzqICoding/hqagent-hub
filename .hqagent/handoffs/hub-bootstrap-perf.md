---
wp: hub-bootstrap-perf
status: done
scope_declared: [apps/hub/**, .hqagent/handoffs/hub-bootstrap-perf.md, .hqagent/reviews/hub-bootstrap-perf/**]
scope_touched: [apps/hub/adapters/manager.py, apps/hub/core/agent_snapshot.py, apps/hub/core/bootstrap.py, apps/hub/api/app.py, apps/hub/api/local_chat.py, apps/hub/api/pi_projection.py, apps/hub/api/update_proxy.py, apps/hub/runtime/attachments/capabilities.py, apps/hub/runtime/pi_visibility.py, apps/hub/runtime/composition.py, apps/hub/runtime/workspaces.py, apps/hub/tests/remote_support.py, apps/hub/tests/test_bootstrap_cached_discovery.py, apps/hub/tests/test_pi_projection_wire.py, apps/hub/tests/test_workspace_probe_timeout.py, .hqagent/handoffs/hub-bootstrap-perf.md, .hqagent/reviews/hub-bootstrap-perf/**]
build: pass
tests: pass
commit: 9620969e9af8dc1c96c0ed9dc0655940439f263b
open_questions: 0
---

# Bootstrap 缓存与后台检测

工作区 `E:/OtherPro/HQAgent-Hub-worktrees/hub-0101`，分支 `feat/hub-0101`。开工执行 `git merge integration/phase1`，输出 `Already up to date.`，基线 `ae87050`。只提交本分支，没有合并回 integration、部署或重启用户实际 Hub。

## 问题与修复

原 bootstrap 会等待 Agent discovery、Git 工作区探测、更新代理和活跃任务查询。额外发现 HTTP 的 PI 投影中间件在每个请求前刷新图片能力，并可能发布 catalog、连带触发 Git 查询；因此仅修改 bootstrap 的 agents 调用仍不足以切断慢链。

### Agent 快照与单飞

- AdapterManager 增加 `cached_agents()`：没有缓存时返回注册实例的固定 ID、unknown 版本、`status=discovering` 和后台检测提示，不猜测可用能力；有缓存时立即返回最近观察。
- v1/v2 bootstrap 与 GET /agents 使用快照入口，不等待 discovery 锁、不在其调用链执行 CLI。缓存默认仍为 60 秒，过期读取立即返回旧观察并触发后台刷新。
- 后台 discovery 全局单飞；单个 Adapter 的 detect 也共用在途任务。并发读取、显式 discovery 和 detect 不重复并发启动相同检测。后台任务使用独立 Context，不继承请求的 PI 展示权限上下文。
- 显式 POST /api/v1/agents/discovery、POST /api/v2/agents/discover 仍等待真实检测：有在途检测时加入它，没有时即使缓存有效也重新检测。
- Runtime 检测异常保留已知实例并显示安全错误状态，更新缓存时间避免每次 GET 立即重试；不会回显原始异常文本。
- 执行解析仍使用原 `list_agents()` 的过期后等待真实结果语义，不用展示快照替代执行校验。没有放宽图片验证、PI guard、模型选择或角色权限。

### HTTP 就绪与启动

- `bind_ports()` 不再等待初始探测；默认团队改为注册 discovery 完成回调，只有实际 ready 观察才创建，不从 discovering 占位实例造绑定。
- lifespan 主动安排一次初始 discovery，不依赖第一次 GET，也不等待检测完成才提供 HTTP。
- 退出时取消并等待后台快照任务；Agent 检测在执行服务停止后、数据库关闭前清理，避免打断执行服务的正常恢复标记流程。

### 其它依赖

- Bootstrap 工作区使用 DB 元数据及最近 Git 视图缓存，不启动 Git。缓存缺失/过期时按现有协议表达未知 branch/isClean、禁止据此认为可写；完整工作区数量仍即时取本机库。
- 后台刷新保留正常 workspace 查询的 3 秒预算及进程清理边界；直接工作区查询和执行前读取仍走真实探测。
- 更新代理及活跃任务改为后台快照，5 秒刷新周期内单飞；工作区、活跃任务、更新代理分别有 4/1/5 秒后台时间边界。慢代理不会占住 bootstrap 响应，失败保留安全降级/最近观察。
- 这些快照用于展示，不作为执行、审批或排空的许可依据；实际操作继续走原服务检查。
- 检查更新代理时同时修正 Windows PID 探活：不使用可能终止目标进程的 `os.kill(pid, 0)`，改为 SYNCHRONIZE 权限 OpenProcess + 零等待 WaitForSingleObject。用实际独立测试进程证明探活不会结束它。

### PI 投影保持

HTTP PI 投影改用 cached capability 元数据路径，不等待在途完整刷新，也不在请求前发布 catalog。完整刷新仍用于原有后台/执行路径。

旧客户端 bootstrap 统计改从与 bootstrap 相同的 Agent 缓存取隐藏计数，覆盖冷启动时图片能力刷新锁被占用的情况；未声明 pi-v1 的客户端不会多看到 PI 的 total/ready/issues。已增加该并发反例。

**没有修改 `adapters/pi_*` 内部代码，也没有修改 `runtime/remote/*`、协议或服务端代码。** 合并时请注意本轮涉及共享 `adapters/manager.py`、`runtime/attachments/capabilities.py`、`api/pi_projection.py` 和 `runtime/pi_visibility.py`，不是 PI RPC/续接逻辑。

## 性能与专项

新增 7 个测试覆盖慢 Runtime、TTL 刷新与单飞、显式 discovery、初始 discovery 不阻塞就绪、默认团队只在真实 ready 后生成、失败缓存、退出取消、旧客户端计数隔离、更新代理只读 PID 查询。

Runtime、Git、更新代理和活跃任务同时挂在假阻塞操作时，v1/v2 bootstrap 与 agents 连续 12 次读取：

```text
blocked Runtime/Git/update/drain: 12 reads, max=34.6ms
30 passed, 1 warning in 16.41s
```

见 [projection-clean.txt](../reviews/hub-bootstrap-perf/projection-clean.txt)。探测仍在后台等待时 HTTP 已返回；断言只有一个 discovery 和一组依赖刷新在途。

在当前 Windows 主机启动真实源码桌面模式 Hub、使用隔离数据库与真实 Git 工作区，已有进程回归输出：

```text
{"mode": "stdio-v1", "control": "shutdown", "endpoint": "/api/v1/workspaces", "elapsedMs": 108.2}
{"mode": "stdio-v1", "control": "shutdown", "endpoint": "/api/v1/bootstrap", "elapsedMs": 15.3}
{"control": "shutdown", "exitCode": 0, "exitMs": 373.7}
{"mode": "stdio-v1", "control": "eof", "endpoint": "/api/v1/workspaces", "elapsedMs": 130.4}
{"mode": "stdio-v1", "control": "eof", "endpoint": "/api/v1/bootstrap", "elapsedMs": 2.9}
{"control": "eof", "exitCode": 0, "exitMs": 364.3}
36 passed, 1 warning in 18.41s
```

见 [targeted-final.txt](../reviews/hub-bootstrap-perf/targeted-final.txt)。均低于 500 ms 目标；这是隔离源码进程实测，没有声称已替换安装包或已在用户运行中的数据目录测量。

初次专项中的 Git 清理断言原本假设 bootstrap 返回即探测完成，已改为等待后台刷新后验证所有进程确实清理。追加逆序回归还发现既有升级夹具的 nested monkeypatch 回滚污染：用外层 monkeypatch 恢复 CODECS 会在测试末尾把全局表又降为 v4。改为由 RealPair 自己的 wire_patch 恢复，保留原 v5 断言并增加全局表恢复断言；没有修改线路行为或削弱测试。原失败输出保留在 targeted.txt 和 projection-final.txt。

## 最终串行全量

仅用指定 Python 读取现有依赖，`-B`、PYTHONDONTWRITEBYTECODE=1；TEMP/TMP/basetemp 在本工作区 `.hqagent/r3-tmp/bootstrap-perf-temp` 及对应 pytest 目录。没有修改 vnext-integration 工作区/venv 或 remote-worker 工作区；没有真实模型推理、发布或部署。本轮没有启动子代理。

Hub，cwd=本工作区 apps/hub：

```text
E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp=../../.hqagent/r3-tmp/pytest-bootstrap-perf-hub-final --tb=short
797 passed, 9 skipped, 4 warnings in 374.45s (0:06:14)
```

Hub 完成后串行运行 server，cwd=本工作区 apps/server：

```text
E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp=../../.hqagent/r3-tmp/pytest-bootstrap-perf-server-final --tb=short
343 passed, 1 warning in 119.69s (0:01:59)
```

完整日志：[Hub 最终全量](../reviews/hub-bootstrap-perf/hub-tests-final.txt)、[server 全量](../reviews/hub-bootstrap-perf/server-tests.txt)。首轮 Hub 全量 796 passed 的输出也保留；最终额外纳入旧客户端并发统计用例。9 个跳过均为既有 POSIX 条件，未新增 skip/xfail。

语法检查：`Python syntax verified: 15 changed files`；`git diff --check` 通过。没有遇到实际服务端 429/403 故障、0xC0000142 或额度错误；测试内预期的鉴权/协议拒绝反例正常执行。日志只规范换行和行尾空白。

## 提交

| 提交 | 内容 |
| --- | --- |
| c1a821a | 缓存读取、后台单飞、启动/退出、依赖快照及 PID 探活 |
| a86cc39 | 冷缓存并发情况下的旧客户端 bootstrap 计数隔离 |
| 9620969 | 修复升级测试夹具的回滚隔离 |

每次提交后均执行 `git log -1 --format=%B` 自查，无禁止署名。只交付 feat/hub-0101，未合并回 integration；实际安装版需要主代理整合并重打 core 后验证发布。
