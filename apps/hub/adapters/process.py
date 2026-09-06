from __future__ import annotations

import asyncio
import os
import shutil
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
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
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
    return [str(Path(executable)), *args]
