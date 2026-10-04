from __future__ import annotations

import csv
import io
import os
import stat
import subprocess
from pathlib import Path

from protocol.generated.python import HubRuntimeDescriptor


def _current_windows_sid() -> str:
    completed = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        stdin=subprocess.DEVNULL,
        timeout=5,
        capture_output=True,
        text=True,
        encoding="oem",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    row = next(csv.reader(io.StringIO(completed.stdout.strip())))
    return row[1]


def secure_current_user_only(path: Path, directory: bool = False) -> None:
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | (stat.S_IXUSR if directory else 0))
    if os.name != "nt":
        return
    sid = _current_windows_sid()
    grant = f"*{sid}:(OI)(CI)F" if directory else f"*{sid}:F"
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", grant],
        check=True,
        stdin=subprocess.DEVNULL,
        timeout=5,
        capture_output=True,
        text=True,
        encoding="oem",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class RuntimeDescriptorFile:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, descriptor: HubRuntimeDescriptor) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        secure_current_user_only(self.path.parent, directory=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            descriptor.model_dump_json(by_alias=True, exclude_none=True, indent=2),
            encoding="utf-8",
        )
        secure_current_user_only(temporary)
        os.replace(temporary, self.path)

    def remove(self, instance_id: str) -> None:
        try:
            current = HubRuntimeDescriptor.model_validate_json(self.path.read_text(encoding="utf-8"))
            if current.instance_id == instance_id:
                self.path.unlink(missing_ok=True)
        except (OSError, ValueError):
            return
