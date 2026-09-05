# T-W1 Local Hub 内核 —— 交接（中断抢救版）

| 项 | 值 |
| --- | --- |
| 状态 | 代码完成、验收通过；**执行方未自测即中断** |
| 中断原因 | Codex 会话在 164,354 token 处被 `429 Too Many Requests` 打断，重试 5 次失败 |
| 落盘情况 | 代码已全部写入工作区，未提交；由 W0 抢救提交 |
| 本文件作者 | W0（架构/审核），**不是执行方自述** |

## provenance 声明

Codex 死在写完代码、跑自测之前，因此**没有留下任何自述结论**。
下面的验收结果全部是 W0 在抢救时**亲自跑出来的实测**，不是转述。

## 边界核对（通过）

`git status --short` 在抢救时只有一条 `?? apps/hub/`，未越界改动
`packages/protocol/`、`apps/desktop/`、`apps/hub/adapters|orchestrator|security/`
或仓库根共享配置。

## 交付物

28 个 Python 文件，分布：

```
apps/hub/core/       bootstrap constants errors maintenance ports security
apps/hub/storage/    database events idempotency migrations settings
apps/hub/api/        app envelopes update_proxy
apps/hub/runtime/    descriptor instance main paths
apps/hub/tests/      conftest + 5 个测试模块
apps/hub/            pyproject.toml README.md
```

## 硬约束核对

| # | 约束 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | DTO 全部来自 `protocol.generated.python` | 通过 | 13 处 `from protocol.generated.python import`；`grep "class .*BaseModel"` **零命中**，没有手写重复 DTO |
| 2 | Vue 只连 Hub，更新走代理 | 通过 | `api/update_proxy.py` 持有 `UpdateAgentRuntimeDescriptor`，Agent 缺席时返回 `FEATURE_UNAVAILABLE` |
| 3 | `/internal/drain/*` 本包实现 | 通过 | `core/maintenance.py` 产出 `DrainProgress` + `ProcessDescriptor`，含 backup 与 waitPids |
| 4 | `seq` 与业务状态同事务 | 通过 | `EventStore.append` 在传入的 `Transaction` 上 INSERT 拿 `lastrowid` 作 seq，推送挂在 `transaction.after_commit`——提交成功后才广播 |
| 5 | 运行期只写 `%LOCALAPPDATA%` | 通过 | `runtime/paths.py:27`，未设置时直接 `RuntimeError`，不回退到安装目录 |
| 6 | Token / Ticket 不进响应体、事件、日志 | 通过 | Ticket 以 `sha256` 摘要存储、`pop` 单次消费、`hmac.compare_digest` 定时比较；`api/` 下 token 只出现在校验与代理 Authorization 头 |

## 验收实测

```
$ cd apps/hub && ../../.venv/Scripts/python.exe -m pytest tests -q
............                                                             [100%]
12 passed, 2 warnings in 0.98s
```

12 个测试对 10 条验收的覆盖：

| 验收条目 | 覆盖测试 | 结果 |
| --- | --- | --- |
| 起停 20 次无残留锁 | `test_single_instance_lock_releases_cleanly_twenty_times` | 通过 |
| 断连带旧 seq 重连补事件无重复 | `test_websocket_reconnect_replays_without_duplicates` | 通过 |
| 过期 seq 返回 `EVENT_CURSOR_EXPIRED` 且可恢复 | `test_event_cursor_expired_has_snapshot_recovery` | 通过 |
| 相同 Idempotency-Key 重放只一条 | `test_same_idempotency_key_creates_one_task_and_event` + `test_idempotency_mismatch_is_conflict` | 通过 |
| v1→v2 迁移，一致性备份可回滚 | `test_v1_migrates_to_v2_and_consistent_backup_restores_data` | 通过 |
| 无 Token 401；Ticket 一次性 | `test_http_requires_bearer_and_rejects_origin` + `test_ticket_is_single_use` | 通过 |
| 非允许 Origin 被拒 | 同上（合并在一个测试内） | 通过 |
| Update Agent 缺席返回 unavailable | `test_update_agent_absence_is_explicit` | 通过 |
| 排空后建任务返回 `HUB_MAINTENANCE` | `test_drain_enters_maintenance_backs_up_and_returns_wait_pids` | 通过 |
| `/healthz` 免鉴权且只回冻结字段 | `test_health_is_public_and_has_only_frozen_fields` | 通过 |

另加 `test_all_frozen_contract_fixtures_validate_and_round_trip`——对
`packages/protocol/fixtures/contracts` 的契约回环测试，FZ-1 未被绕过。

## 未做 / 需要后续确认

- **端口泄漏未单独验证**。"起停 20 次"只测了单实例锁的获取与释放，没有真正起停 20 次
  HTTP 服务去看端口回收。要补一个真起停的集成测试。
- **`envelope_json` 二次 UPDATE**。`append` 先 INSERT 占位 `'{}'` 拿 `lastrowid`，
  再 UPDATE 回填完整信封。同事务内所以对外一致，但多一次写。SQLite 下可接受，
  记一笔以防将来换库时被忽略。
- **W2/W3 的 Port 是空实现**。按任务书要求，在 `BootstrapView.features` 里如实报
  `available:false`，未用空列表伪装。
- **依赖未锁版本**。`pyproject.toml` 只给了区间，没有 lock 文件。W6 打包前需要补。
- 本地验证用的 venv 建在 `w1-hub/.venv`，已被 `.gitignore` 排除。

## 需要 W0 / 其他包配合

无。本包不依赖其他工作包即可自测通过。
