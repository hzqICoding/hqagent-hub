from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


DEFAULT_STREAM_LIMIT = 16 * 1024 * 1024
_ALLOWED_NPM_BIN_SUFFIXES = {".exe", ".js", ".cjs", ".mjs"}
_KNOWN_NPM_PACKAGES = {
    "claude": ("@anthropic-ai/claude-code", "claude"),
    "codex": ("@openai/codex", "codex"),
    "pi": ("@earendil-works/pi-coding-agent", "pi"),
}

# Safe mode suppresses customizations; carry user transport configuration in the
# child environment, without enabling hooks/plugins or exposing secrets in argv.
_CLAUDE_TRANSPORT_ENV = frozenset({
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_CUSTOM_HEADERS", "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "CLAUDE_CODE_CLIENT_CERT", "CLAUDE_CODE_CLIENT_KEY", "CLAUDE_CODE_CLIENT_KEY_PASSPHRASE",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CODE_SKIP_BEDROCK_AUTH", "CLAUDE_CODE_SKIP_VERTEX_AUTH", "CLAUDE_CODE_SKIP_FOUNDRY_AUTH",
    "ANTHROPIC_BEDROCK_BASE_URL", "ANTHROPIC_VERTEX_BASE_URL", "ANTHROPIC_FOUNDRY_BASE_URL",
    "ANTHROPIC_FOUNDRY_RESOURCE", "ANTHROPIC_FOUNDRY_API_KEY",
    "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE", "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_BEARER_TOKEN_BEDROCK",
    "ANTHROPIC_VERTEX_PROJECT_ID", "CLOUD_ML_REGION", "GOOGLE_APPLICATION_CREDENTIALS",
})


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class ProcessRunner:
    def __init__(self, *, stream_limit: int = DEFAULT_STREAM_LIMIT) -> None:
        if stream_limit < 64 * 1024 or stream_limit > 64 * 1024 * 1024:
            raise ValueError("stream_limit must be between 64 KiB and 64 MiB")
        self.stream_limit = stream_limit

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
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=self.stream_limit,
            creationflags=self._creation_flags(),
            start_new_session=os.name != "nt",
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except (TimeoutError, asyncio.CancelledError):
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
            limit=self.stream_limit,
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
        _inherit_claude_transport_settings(env)
        for key in ("CLAUDECODE", "CLAUDE_PID"):
            env.pop(key, None)
    elif prefix == "codex":
        for key in ("CODEX_SESSION_ID", "CODEX_THREAD_ID"):
            env.pop(key, None)
    return env


def _inherit_claude_transport_settings(env: dict[str, str]) -> None:
    """Fill missing transport variables from user settings; never edit that file.

    Explicit Worker environment wins, including empty values. Do not evaluate
    shell profiles, load arbitrary env (e.g. NODE_OPTIONS), or enable project hooks.
    Invalid user settings fail closed rather than silently dropping their proxy.
    """
    config_dir = env.get("CLAUDE_CONFIG_DIR")
    root = Path(config_dir).expanduser() if config_dir else Path.home() / ".claude"
    path = root / "settings.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return
    except (OSError, ValueError):
        raise OSError("Claude 用户 settings.json 无法读取或解析；请检查网络配置，未回退为直连") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("env", {}), dict):
        raise OSError("Claude 用户 settings.json 的 env 必须是对象；未回退为直连")
    inherited = {key.upper() for key in env}
    for key, value in raw.get("env", {}).items():
        if key.upper() not in _CLAUDE_TRANSPORT_ENV or key.upper() in inherited:
            continue
        if not isinstance(value, str):
            raise OSError("Claude 用户 settings.json 的网络环境变量必须是字符串；未回退为直连")
        env[key] = value
        inherited.add(key.upper())


def executable_args(executable: str, *args: str) -> list[str]:
    path = Path(executable)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        launcher = _resolve_known_npm_bin(path)
        if launcher.suffix.lower() == ".exe":
            return [str(launcher), *args]
        node = shutil.which("node")
        if not node:
            raise OSError("Node.js executable not found for supported npm CLI launcher")
        return [node, str(launcher), *args]
    return [str(Path(executable)), *args]


def _resolve_known_npm_bin(shim: Path) -> Path:
    package_info = _KNOWN_NPM_PACKAGES.get(shim.stem.lower())
    if package_info is None:
        raise OSError("Unsupported CLI batch launcher; only known npm packages are allowed")
    package_name, bin_name = package_info
    package_root = (shim.parent / "node_modules" / Path(package_name)).resolve()
    package_json = package_root / "package.json"
    try:
        raw = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OSError(f"Unable to read npm package metadata for {shim.stem}") from exc
    bin_value = raw.get("bin")
    if isinstance(bin_value, str):
        relative = bin_value
    elif isinstance(bin_value, dict) and isinstance(bin_value.get(bin_name), str):
        relative = bin_value[bin_name]
    else:
        raise OSError(f"npm package does not declare the expected {bin_name!r} bin")
    launcher = (package_root / relative).resolve()
    try:
        launcher.relative_to(package_root)
    except ValueError as exc:
        raise OSError("npm package bin escapes its package directory") from exc
    if launcher.suffix.lower() not in _ALLOWED_NPM_BIN_SUFFIXES:
        raise OSError("Unsupported npm package bin type")
    if not launcher.is_file():
        raise OSError("Declared npm package bin does not exist")
    return launcher


async def terminate_process_tree(process: asyncio.subprocess.Process, timeout: float = 3) -> bool:
    if process.returncode is not None:
        return True
    # Test doubles do not represent real OS process ownership.
    if not isinstance(process, asyncio.subprocess.Process):
        process.kill()
    elif os.name == "nt":
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill.exe", "/PID", str(process.pid), "/T", "/F",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError:
            return False
        try:
            await asyncio.wait_for(killer.wait(), timeout)
        except TimeoutError:
            try:
                killer.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(killer.wait(), timeout)
            except TimeoutError:
                pass
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
