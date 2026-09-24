from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class ProcessRunner:
    def find(self, command: str) -> str | None:
        override = os.environ.get(f"HQAGENT_{command.upper()}_PATH")
        if override:
            candidate = Path(override).expanduser()
            return str(candidate.resolve()) if candidate.is_file() else None
        return shutil.which(command)

    async def run(
        self,
        args: Sequence[str],
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 10,
    ) -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd) if cwd else None,
            env=dict(env) if env else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=self._creation_flags(),
            start_new_session=os.name != "nt",
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            await terminate_process_tree(process)
            raise
        return CommandResult(
            returncode=process.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )

    async def start(
        self,
        args: Sequence[str],
        *,
        cwd: str | Path,
        env: Mapping[str, str] | None = None,
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            env=dict(env) if env else None,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=self._creation_flags(),
            start_new_session=os.name != "nt",
        )

    @staticmethod
    def _creation_flags() -> int:
        if os.name != "nt":
            return 0
        return subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW


def command_environment(prefix: str) -> dict[str, str]:
    """剥离父 Agent 的嵌套会话变量，避免供应商 CLI 误接管父会话。"""

    env = dict(os.environ)
    if prefix == "claude":
        for key in tuple(env):
            if key == "CLAUDECODE" or key == "CLAUDE_PID" or key.startswith("CLAUDE_CODE_"):
                env.pop(key, None)
    elif prefix == "codex":
        for key in ("CODEX_SESSION_ID", "CODEX_THREAD_ID"):
            env.pop(key, None)
    return env


def executable_args(executable: str, *args: str) -> list[str]:
    path = Path(executable)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        # npm shims can be launched without interpolating any task text into cmd.
        # Resolve the known package's JS launcher; reject unknown batch wrappers.
        candidates = {
            "codex": path.parent / "node_modules/@openai/codex/bin/codex.js",
            "claude": path.parent / "node_modules/@anthropic-ai/claude-code/cli.js",
        }
        script = candidates.get(path.stem.lower())
        node = shutil.which("node")
        if script is not None and script.is_file() and node:
            return [node, str(script), *args]
        raise OSError("Unsupported CLI batch launcher; install a native executable or supported npm package")
    return [str(Path(executable)), *args]


async def terminate_process_tree(process: asyncio.subprocess.Process, timeout: float = 3) -> bool:
    if process.returncode is not None:
        return True
    # Test doubles do not represent real OS process ownership.
    if not isinstance(process, asyncio.subprocess.Process):
        process.kill()
    elif os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill.exe", "/PID", str(process.pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            await asyncio.wait_for(killer.wait(), timeout)
        except TimeoutError:
            killer.kill()
            await killer.wait()
            return False
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.wait(), timeout)
    except TimeoutError:
        return False
    return process.returncode is not None
