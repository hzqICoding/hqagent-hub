from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from adapters.codex_adapter import _CodexConnection
from adapters.process import ProcessRunner, executable_args


@pytest.mark.skipif(os.name != "nt", reason="npm batch shim resolution is Windows-specific")
def test_known_claude_npm_bin_resolves_native_executable(tmp_path: Path) -> None:
    shim = tmp_path / "claude.cmd"
    shim.write_text("@echo off\r\n", encoding="utf-8")
    package = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code"
    launcher = package / "bin" / "claude.exe"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"MZ")
    (package / "package.json").write_text(
        json.dumps({"bin": {"claude": "bin/claude.exe"}}),
        encoding="utf-8",
    )

    assert executable_args(str(shim), "--version") == [str(launcher.resolve()), "--version"]


@pytest.mark.skipif(os.name != "nt", reason="npm batch shim resolution is Windows-specific")
def test_known_npm_js_bin_uses_node_and_rejects_package_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shim = tmp_path / "codex.cmd"
    shim.write_text("@echo off\r\n", encoding="utf-8")
    package = tmp_path / "node_modules" / "@openai" / "codex"
    launcher = package / "bin" / "codex.cjs"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("", encoding="utf-8")
    metadata = package / "package.json"
    metadata.write_text(json.dumps({"bin": {"codex": "bin/codex.cjs"}}), encoding="utf-8")
    monkeypatch.setattr("adapters.process.shutil.which", lambda command: "C:/node/node.exe")

    assert executable_args(str(shim), "app-server") == [
        "C:/node/node.exe",
        str(launcher.resolve()),
        "app-server",
    ]

    outside = tmp_path / "outside.exe"
    outside.write_bytes(b"MZ")
    metadata.write_text(json.dumps({"bin": {"codex": "../../../outside.exe"}}), encoding="utf-8")
    with pytest.raises(OSError, match="escapes"):
        executable_args(str(shim), "--version")


def test_process_runner_reads_stdout_and_stderr_frames_larger_than_64k(tmp_path: Path) -> None:
    async def scenario() -> None:
        size = 200_000
        script = (
            "import sys;"
            f"sys.stdout.write('x'*{size}+'\\n');sys.stdout.flush();"
            f"sys.stderr.write('e'*{size}+'\\n');sys.stderr.flush()"
        )
        process = await ProcessRunner().start(
            [sys.executable, "-c", script],
            cwd=tmp_path,
        )
        assert process.stdout is not None and process.stderr is not None
        stdout, stderr = await asyncio.gather(
            process.stdout.readline(),
            process.stderr.readline(),
        )
        assert await process.wait() == 0
        assert len(stdout.rstrip(b"\r\n")) == size
        assert len(stderr.rstrip(b"\r\n")) == size

    asyncio.run(scenario())


def test_process_runner_run_collects_large_stdout_and_stderr(tmp_path: Path) -> None:
    async def scenario() -> None:
        size = 200_000
        script = (
            "import sys;"
            f"sys.stdout.write('o'*{size});sys.stdout.flush();"
            f"sys.stderr.write('r'*{size});sys.stderr.flush()"
        )
        result = await ProcessRunner().run(
            [sys.executable, "-c", script],
            cwd=tmp_path,
        )
        assert result.returncode == 0
        assert len(result.stdout) == size
        assert len(result.stderr) == size

    asyncio.run(scenario())


def test_codex_reader_failure_kills_owned_process_tree() -> None:
    class BrokenReader:
        async def readline(self):
            raise ValueError("synthetic oversized frame")

    class EmptyReader:
        async def readline(self):
            return b""

    class FakeStdin:
        def write(self, value):
            return None

        async def drain(self):
            return None

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = BrokenReader()
            self.stderr = EmptyReader()
            self.stdin = FakeStdin()
            self.returncode = None
            self.pid = 12345
            self.killed = False

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    async def scenario() -> None:
        process = FakeProcess()
        disconnected = asyncio.Event()
        observed: dict[str, object] = {}

        async def on_disconnect(alive: bool, detail: str) -> None:
            observed.update({"alive": alive, "detail": detail})
            disconnected.set()

        async def ignore(_value):
            return None

        connection = _CodexConnection(
            process,
            on_notification=ignore,
            on_server_request=ignore,
            on_disconnect=on_disconnect,
        )
        await asyncio.wait_for(disconnected.wait(), timeout=1)
        await asyncio.gather(connection.reader_task, connection.stderr_task)
        assert process.killed is True
        assert observed["alive"] is False
        assert "stdio reader failed" in str(observed["detail"])

    asyncio.run(scenario())
