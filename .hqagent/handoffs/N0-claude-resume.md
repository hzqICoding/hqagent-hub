# N0 Claude 原生会话续接交接

## 原生证据

Claude Code `2.1.281` 使用同一临时 cwd、同一明确 UUID，首轮进程正常退出后，第二个进程通过
`--resume <UUID>` 成功恢复并准确返回首轮随机标识。两轮均使用 `--safe-mode`、空 tools、
`dontAsk`，未使用 `latest/continue`，未输出账号、代理或凭据。

```text
firstExit=0
firstInitSessionMatch=true
firstSuccess=true
secondExit=0
secondInitSessionMatch=true
secondSuccess=true
markerRecoveredExactly=true
stderrPresent=false
```

## 实现

- `session_resume` 能力在兼容且已安装的 Claude Runtime 上声明支持。
- 最低实测版本提升到 `2.1.281`；旧 `2.1.263` 不会宣称支持原生续接。
- 新 Session handle 返回 `supportsResume=true`；成功结果对应的正常 stream end 返回
  `resumable=true`，让 Hub 生命周期落到 `idle`。
- `resume()` 必须收到明确 `externalSessionId` 与持久化 `AgentTaskSpec`；Hub 重启后可据此重建
  Adapter 内存状态，不猜测用户历史。
- `externalSessionId` 必须是小写连字符规范 UUID；`latest`、`continue`、搜索词和非规范 UUID
  会在任何进程启动前被拒绝。
- 恢复规格不得改变工作区、角色、路径白名单、只读标志、模型、effort 或角色指令。
- 续轮使用持久规格复制并替换为本轮 objective，再经统一 `build_task_prompt` 生成中文根目录、
  角色职责和 acceptance 提示；不会把旧 objective 当成本轮任务。
- `system.init.session_id` 与 `result.session_id` 必须和目标 UUID 一致。
- 执行失败使用 `AGENT_EXITED/resumable=false`，避免失败会话被 SessionLifecycle 留在 idle。

## 定向测试

```text
E:\OtherPro\HQAgent-Hub-worktrees\integration\.venv\Scripts\python.exe \
  -m pytest tests\test_claude_resume.py adapters\tests -q -p no:cacheprovider \
  --basetemp E:\tmp\pytest-claude-resume-followup

22 passed, 2 warnings in 0.10s
```

两条 warning 是既有 FastAPI/Starlette TestClient 弃用提示。

## 旧成功 Session 的只读验证建议

旧版本写成 `closed/isValid=false` 的记录不应批量复活。若要验证一条已知成功 Session：

1. 先停止 Hub 并备份 SQLite，不修改供应商 transcript。
2. 仅选择任务成功、external ID 唯一、原生 transcript 顶层 session ID/cwd 与
   `session_spec` 的 workspace/role/worktree 完全一致的一条记录。
3. 对该明确记录做一次有审计的兼容迁移；失败、取消、路径不明或规格缺失的旧记录不迁移。
4. 发送一次只读续接问题，核对新 `system.init/result.session_id` 仍为原 UUID，并验证能引用前轮
   已知上下文；不通过时恢复数据库备份并保持 closed。
5. 普通旧对话默认新建 Session，并把旧结果作为显式 handoff，不声称为原生恢复。
