# N0 Adapter I/O 修复交接

## 范围

- Claude/Codex Windows npm shim 只解析受信包的 `package.json.bin`。
- 支持包内 `.exe`、`.js`、`.cjs`、`.mjs`，拒绝未知 batch、目录越界和其他扩展名。
- `ProcessRunner.run/start` 的 stdout/stderr StreamReader 上限统一为 16 MiB。
- Claude/Codex reader 异常会先尝试清理该 Session 持有的专属进程树，并上报不可自动重试的脱敏失败；诊断只含 channel、异常类型和清理结果。

## 定向验证

```text
E:\OtherPro\HQAgent-Hub-worktrees\integration\.venv\Scripts\python.exe \
  -m pytest tests\test_process_io.py adapters\tests -q -p no:cacheprovider \
  --basetemp E:\tmp\pytest-n0-adapter-io-sanitize

22 passed, 2 warnings in 0.21s
```

两条 warning 均来自既有 FastAPI/Starlette TestClient 弃用提示。

合成子进程覆盖单行 200 KB stdout 与 stderr，证明不再受 asyncio 默认 64 KiB
`readline()` 上限影响；另覆盖 Codex reader 异常后进程树清理、清理失败不误报成功，
以及异常文本不进入诊断。

## 本机只读探测

未发起模型任务，仅执行 Adapter 的版本与登录态探测：

```text
shimSuffix=.cmd
launcherSuffix=.exe
installed=true
version=2.1.281 (Claude Code)
status=ready
authValid=true
```

探测输出未包含账号、组织、Token 或其他凭据。
