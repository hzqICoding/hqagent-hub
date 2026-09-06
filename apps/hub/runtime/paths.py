from __future__ import annotations

import os
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

    @classmethod
    def resolve(cls, override: Path | None = None) -> "HubPaths":
        if override is not None:
            root = override.resolve()
        elif os.environ.get("HQAGENT_HUB_DATA_DIR"):
            root = Path(os.environ["HQAGENT_HUB_DATA_DIR"]).resolve()
        else:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if not local_app_data:
                raise RuntimeError("LOCALAPPDATA 未设置，无法确定 HQAgent-Hub 数据目录")
            root = (Path(local_app_data) / "HQAgent-Hub").resolve()
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
        ):
            path.mkdir(parents=True, exist_ok=True)

