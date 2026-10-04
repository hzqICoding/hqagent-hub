"""Explicit local folder selection, isolated from the Hub's asyncio event loop."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

from core.errors import FeatureUnavailable, HubError
from protocol.generated.python import PickLocalDirectoryInput, PickLocalDirectoryView


class LocalDirectoryPicker:
    def __init__(self, timeout: float = 120) -> None:
        self._lock = asyncio.Lock()
        self.timeout = timeout

    async def pick(self, value: PickLocalDirectoryInput) -> PickLocalDirectoryView:
        if self._lock.locked():
            raise HubError("CONFLICT", "目录选择窗口已打开，请先完成或取消选择")
        async with self._lock:
            initial = ""
            if value.initial_path:
                path = Path(value.initial_path).expanduser()
                if not path.is_absolute() or not path.is_dir():
                    raise HubError("VALIDATION_FAILED", "起始路径必须是本机已有目录的绝对路径")
                initial = str(path.resolve())
            try:
                return await self._launch(initial)
            except (OSError, ValueError, asyncio.TimeoutError) as exc:
                raise FeatureUnavailable("directory_picker", "无法打开目录选择窗口或选择已超时，请重试或手动输入目录") from exc

    async def _launch(self, initial: str) -> PickLocalDirectoryView:
        # A child owns Tk on its main thread; cancelling/timeout also closes its UI.
        # The packaged entry point handles the same private flag before Hub startup.
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command += ["-B", "-m", "runtime.main"]
        command += ["--pick-directory", initial]
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), self.timeout)
            if process.returncode:
                raise OSError("Directory dialog unavailable")
            result = PickLocalDirectoryView.model_validate_json(output)
            if not result.cancelled:
                path = Path(result.selected_path or "")
                if not result.selected_path or not path.is_absolute() or not path.is_dir():
                    raise ValueError("Invalid selected directory")
                result.selected_path = str(path.resolve())
            return result
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except TimeoutError:
                    pass


def show_dialog(initial: str) -> None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askdirectory(parent=root, title="选择已有项目目录 — HQAgent Hub",
                                       initialdir=initial or str(Path.home()), mustexist=True)
        payload = {"cancelled": not bool(path)}
        if path:
            payload["selectedPath"] = str(Path(path).resolve())
        print(json.dumps(payload, ensure_ascii=True), flush=True)
    finally:
        root.destroy()
