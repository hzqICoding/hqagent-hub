# HQAgent-Hub Tauri shell

The shell owns native Windows integration only. Vue receives the Local Hub
`baseUrl` and ephemeral Hub `token` through `get_hub_endpoint`; the Update Agent
endpoint and token are never serialized to frontend code.

## Process configuration

Defaults resolve `hqagent-core.exe` and `hqagent-update-agent.exe` next to the
desktop executable. Override them with `%LOCALAPPDATA%\HQAgent-Hub\config\desktop-shell.json`:

```json
{
  "coreExecutable": "C:\\path\\to\\hqagent-core.exe",
  "coreArgs": [],
  "updateAgentExecutable": "C:\\path\\to\\hqagent-update-agent.exe",
  "updateAgentArgs": [],
  "autostart": true
}
```

`HQAGENT_CORE_PATH` and `HQAGENT_UPDATE_AGENT_PATH` override the file for local
testing. Missing binaries remain visible in `get_shell_status`; they are not
silently ignored.

Managed children receive `HQAGENT_INSTANCE_ID`, `HQAGENT_RUNTIME_DIR`, and
`HQAGENT_PARENT_CONTROL=stdio-v1`. On application exit the shell writes
`shutdown\n` to stdin, waits up to 15 seconds, then uses forced termination only
as a last resort. Closing the main window merely hides it to the tray.

## Commands

```powershell
cd apps/desktop/src-tauri
cargo check
cargo test
pwsh -File acceptance/run-security-acceptance.ps1
```

The acceptance stub binds only `127.0.0.1`, writes an atomic FZ-1 `hub.json`,
removes inherited ACLs, grants only the current user, and proves Bearer, Origin,
30-second one-time Ticket, and replay rejection behavior.
