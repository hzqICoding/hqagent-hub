from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HubPaths:
    root: Path
    data: Path
    config: Path
    runtime: Path
    logs: Path
    updates: Path
    staging: Path
    backup: Path
    diagnostics: Path
    worktrees: Path

    @classmethod
    def resolve(cls, override: Path | None = None) -> "HubPaths":
        if override is not None:
            root = override.resolve()
        elif os.environ.get("HQAGENT_HUB_DATA_DIR"):
            root = Path(os.environ["HQAGENT_HUB_DATA_DIR"]).resolve()
        else:
            if os.name == "nt":
                local_app_data = os.environ.get("LOCALAPPDATA")
                if not local_app_data:
                    raise RuntimeError("LOCALAPPDATA 未设置，无法确定 HQAgent-Hub 数据目录")
                root = Path(local_app_data) / "HQAgent-Hub"
            elif sys.platform == "darwin":
                root = Path.home() / "Library/Application Support/HQAgent-Hub"
            else:
                root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "hqagent-hub"
            root = root.resolve()
        return cls(
            root=root,
            data=root / "data",
            config=root / "config",
            runtime=root / "runtime",
            logs=root / "logs",
            updates=root / "updates",
            staging=root / "updates" / "staging",
            backup=root / "updates" / "backup",
            diagnostics=root / "diagnostics",
            # 施工方案 §5 的固定目录。每个写任务在这下面开独立 worktree，
            # WorktreeManager 会强制路径不得越出这个根。
            worktrees=root / "worktrees",
        )

    def create(self) -> None:
        for path in (
            self.root,
            self.data,
            self.config,
            self.runtime,
            self.logs,
            self.updates,
            self.staging,
            self.backup,
            self.diagnostics,
            self.worktrees,
        ):
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError:
                if path != self.logs:
                    raise
                # Logging initializes its own fallback; a read-only log path
                # must not make the rest of the writable data root unusable.
